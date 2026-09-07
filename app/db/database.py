"""
Асинхронный слой доступа к SQLite.

Оптимизации:
* WAL + synchronous=NORMAL — записи не блокируют чтения;
* in-memory кэш настроек и списка каналов (инвалидируется при записи);
* LRU-кэш языка пользователя — убирает запрос к БД на каждое сообщение;
* отложенная (write-behind) запись `last_active` пачками раз в N секунд.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Iterable

import aiosqlite

from app.core.config import settings

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY,
    language          TEXT      DEFAULT 'ru',
    channels_snapshot TEXT      DEFAULT '',
    first_seen        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active);

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  TEXT    UNIQUE NOT NULL,
    title       TEXT    NOT NULL,
    invite_link TEXT,
    is_active   INTEGER DEFAULT 1,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_channels_active ON channels(is_active);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Кэш уже отправленных видео: повторная ссылка отдаётся мгновенно по file_id.
CREATE TABLE IF NOT EXISTS video_cache (
    url_key    TEXT PRIMARY KEY,
    file_id    TEXT NOT NULL,
    title      TEXT,
    duration   INTEGER,
    hits       INTEGER   DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_DEFAULT_SETTINGS = {
    "subscription_enabled": "0",
    "bot_active": "1",
}


class Database:
    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None
        self._settings_cache: dict[str, str] = {}
        self._channels_cache: dict[bool, list[dict]] = {}
        self._lang_cache: dict[int, str] = {}
        self._known_users: set[int] = set()
        self._pending_active: set[int] = set()
        self._flush_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database.init() не был вызван")
        return self._db

    async def init(self) -> None:
        self._db = await aiosqlite.connect(settings.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(
            "PRAGMA journal_mode=WAL;"
            "PRAGMA synchronous=NORMAL;"
            "PRAGMA temp_store=MEMORY;"
            "PRAGMA cache_size=-16000;"
            "PRAGMA busy_timeout=5000;"
        )
        await self._db.executescript(_SCHEMA)
        await self._db.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            list(_DEFAULT_SETTINGS.items()),
        )
        await self._db.commit()

        await self._load_settings_cache()
        self._flush_task = asyncio.create_task(self._flush_loop(), name="db-flush")
        log.info("Database ready: %s", settings.db_path)

    async def close(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        await self._flush_pending()
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ── Users ─────────────────────────────────────────────────────────────

    async def get_user(self, user_id: int) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_language(self, user_id: int) -> str | None:
        """Язык из кэша; None — пользователь ещё не зарегистрирован."""
        cached = self._lang_cache.get(user_id)
        if cached is not None:
            return cached
        async with self.conn.execute(
            "SELECT language FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        self._lang_cache[user_id] = row[0]
        self._known_users.add(user_id)
        return row[0]

    async def ensure_user(self, user_id: int) -> None:
        """Регистрирует пользователя при первом обращении (без лишних записей)."""
        if user_id in self._known_users:
            self.touch(user_id)
            return
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, language) VALUES (?, ?)",
            (user_id, settings.default_lang),
        )
        await self.conn.commit()
        self._known_users.add(user_id)

    def touch(self, user_id: int) -> None:
        """Отмечает активность — реальная запись в БД произойдёт пачкой."""
        self._pending_active.add(user_id)

    async def upsert_user(self, user_id: int, **fields: Any) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            await self.conn.execute(
                f"UPDATE users SET {set_clause}, last_active = CURRENT_TIMESTAMP "
                "WHERE user_id = ?",
                [*fields.values(), user_id],
            )
        await self.conn.commit()

        self._known_users.add(user_id)
        if "language" in fields:
            self._lang_cache[user_id] = str(fields["language"])

    async def all_user_ids(self) -> list[int]:
        async with self.conn.execute("SELECT user_id FROM users") as cur:
            return [r[0] for r in await cur.fetchall()]

    # ── Channels ──────────────────────────────────────────────────────────

    async def get_channels(self, only_active: bool = True) -> list[dict]:
        cached = self._channels_cache.get(only_active)
        if cached is not None:
            return cached

        query = (
            "SELECT * FROM channels WHERE is_active = 1 ORDER BY added_at"
            if only_active
            else "SELECT * FROM channels ORDER BY added_at"
        )
        async with self.conn.execute(query) as cur:
            rows = await cur.fetchall()
        result = [dict(r) for r in rows]
        self._channels_cache[only_active] = result
        return result

    def _invalidate_channels(self) -> None:
        self._channels_cache.clear()

    async def add_channel(
        self, channel_id: str, title: str, invite_link: str | None, added_by: int
    ) -> bool:
        try:
            await self.conn.execute(
                "INSERT INTO channels (channel_id, title, invite_link, added_by) "
                "VALUES (?, ?, ?, ?)",
                (channel_id, title, invite_link, added_by),
            )
            await self.conn.commit()
        except Exception as exc:  # noqa: BLE001 — чаще всего UNIQUE constraint
            log.warning("add_channel failed for %s: %s", channel_id, exc)
            return False
        self._invalidate_channels()
        return True

    async def remove_channel_by_id(self, db_id: int) -> bool:
        await self.conn.execute("DELETE FROM channels WHERE id = ?", (db_id,))
        await self.conn.commit()
        self._invalidate_channels()
        return True

    async def toggle_channel_by_id(self, db_id: int) -> bool:
        await self.conn.execute(
            "UPDATE channels SET is_active = 1 - is_active WHERE id = ?", (db_id,)
        )
        await self.conn.commit()
        self._invalidate_channels()
        return True

    # ── Settings ──────────────────────────────────────────────────────────

    async def _load_settings_cache(self) -> None:
        async with self.conn.execute("SELECT key, value FROM settings") as cur:
            self._settings_cache = {k: v for k, v in await cur.fetchall()}

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Синхронно — значения живут в памяти."""
        return self._settings_cache.get(key, default)

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await self.conn.commit()
        self._settings_cache[key] = value

    # ── Кэш видео (file_id) ───────────────────────────────────────────────

    async def get_cached_video(self, url_key: str) -> dict | None:
        async with self.conn.execute(
            "SELECT file_id, title, duration FROM video_cache WHERE url_key = ?",
            (url_key,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        await self.conn.execute(
            "UPDATE video_cache SET hits = hits + 1 WHERE url_key = ?", (url_key,)
        )
        await self.conn.commit()
        return dict(row)

    async def save_cached_video(
        self, url_key: str, file_id: str, title: str | None, duration: int | None
    ) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO video_cache (url_key, file_id, title, duration) "
            "VALUES (?, ?, ?, ?)",
            (url_key, file_id, title, duration),
        )
        await self.conn.commit()

    async def drop_cached_video(self, url_key: str) -> None:
        await self.conn.execute("DELETE FROM video_cache WHERE url_key = ?", (url_key,))
        await self.conn.commit()

    # ── Stats ─────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        async with self.conn.execute(
            "SELECT "
            " (SELECT COUNT(*) FROM users), "
            " (SELECT COUNT(*) FROM users WHERE last_active >= date('now')), "
            " (SELECT COUNT(*) FROM channels WHERE is_active = 1), "
            " (SELECT COUNT(*) FROM video_cache)"
        ) as cur:
            total_users, active_today, total_channels, cached_videos = await cur.fetchone()
        return {
            "total_users": total_users,
            "active_today": active_today,
            "total_channels": total_channels,
            "cached_videos": cached_videos,
        }

    # ── Write-behind ──────────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.user_flush_interval)
                await self._flush_pending()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("last_active flush failed: %s", exc)

    async def _flush_pending(self) -> None:
        if not self._pending_active or self._db is None:
            return
        batch: Iterable[int] = list(self._pending_active)
        self._pending_active.clear()
        await self._db.executemany(
            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            [(uid,) for uid in batch],
        )
        await self._db.commit()
        log.debug("flushed last_active for %d users", len(list(batch)))


db = Database()
