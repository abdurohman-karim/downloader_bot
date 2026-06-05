from __future__ import annotations

import datetime
import logging

import aiosqlite

from config import DB_PATH

log = logging.getLogger(__name__)


class Database:
    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          INTEGER PRIMARY KEY,
                language         TEXT    DEFAULT 'ru',
                channels_snapshot TEXT   DEFAULT '',
                first_seen       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS channels (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id   TEXT    UNIQUE NOT NULL,
                title        TEXT    NOT NULL,
                invite_link  TEXT,
                is_active    INTEGER DEFAULT 1,
                added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                added_by     INTEGER
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await self._db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('subscription_enabled', '0')"
        )
        await self._db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', '1')"
        )
        await self._db.commit()
        log.info("Database initialised: %s", DB_PATH)

    # ── Users ─────────────────────────────────────────────────────────────────

    async def get_user(self, user_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def upsert_user(self, user_id: int, **fields: object) -> None:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await self._db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        update = {**fields, "last_active": now}
        set_clause = ", ".join(f"{k} = ?" for k in update)
        values = list(update.values()) + [user_id]
        await self._db.execute(
            f"UPDATE users SET {set_clause} WHERE user_id = ?", values
        )
        await self._db.commit()

    # ── Channels ──────────────────────────────────────────────────────────────

    async def get_channels(self, only_active: bool = True) -> list[dict]:
        query = (
            "SELECT * FROM channels WHERE is_active = 1 ORDER BY added_at"
            if only_active
            else "SELECT * FROM channels ORDER BY added_at"
        )
        async with self._db.execute(query) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def add_channel(
        self,
        channel_id: str,
        title: str,
        invite_link: str | None,
        added_by: int,
    ) -> bool:
        try:
            await self._db.execute(
                "INSERT INTO channels (channel_id, title, invite_link, added_by) "
                "VALUES (?, ?, ?, ?)",
                (channel_id, title, invite_link, added_by),
            )
            await self._db.commit()
            return True
        except Exception as exc:
            log.warning("add_channel failed for %s: %s", channel_id, exc)
            return False

    async def remove_channel(self, channel_id: str) -> bool:
        await self._db.execute(
            "DELETE FROM channels WHERE channel_id = ?", (channel_id,)
        )
        await self._db.commit()
        return True

    async def remove_channel_by_id(self, db_id: int) -> bool:
        await self._db.execute("DELETE FROM channels WHERE id = ?", (db_id,))
        await self._db.commit()
        return True

    async def toggle_channel(self, channel_id: str) -> bool:
        await self._db.execute(
            "UPDATE channels SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END "
            "WHERE channel_id = ?",
            (channel_id,),
        )
        await self._db.commit()
        return True

    async def toggle_channel_by_id(self, db_id: int) -> bool:
        await self._db.execute(
            "UPDATE channels SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END "
            "WHERE id = ?",
            (db_id,),
        )
        await self._db.commit()
        return True

    # ── Settings ──────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> str | None:
        async with self._db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await self._db.commit()

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        async with self._db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users: int = (await cur.fetchone())[0]
        async with self._db.execute(
            "SELECT COUNT(*) FROM users WHERE date(last_active) = date('now')"
        ) as cur:
            active_today: int = (await cur.fetchone())[0]
        async with self._db.execute(
            "SELECT COUNT(*) FROM channels WHERE is_active = 1"
        ) as cur:
            total_channels: int = (await cur.fetchone())[0]
        return {
            "total_users": total_users,
            "active_today": active_today,
            "total_channels": total_channels,
        }


db = Database()
