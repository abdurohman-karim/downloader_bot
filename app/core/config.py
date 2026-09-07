"""Настройки приложения. Всё читается из переменных окружения / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_ids(key: str) -> tuple[int, ...]:
    raw = os.getenv(key, "")
    ids: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.lstrip("-").isdigit():
            ids.append(int(chunk))
    return tuple(ids)


@dataclass(frozen=True)
class Settings:
    # ── Telegram ──────────────────────────────────────────────────────────
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", "").strip())
    admin_ids: tuple[int, ...] = field(default_factory=lambda: _env_ids("ADMIN_IDS"))

    # ── Хранилище ─────────────────────────────────────────────────────────
    db_path: str = field(
        default_factory=lambda: os.getenv("DB_PATH", str(BASE_DIR / "bot_data.db"))
    )
    download_dir: str = field(
        default_factory=lambda: os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads"))
    )

    # ── Лимиты ────────────────────────────────────────────────────────────
    # Жёсткий лимит Telegram — 50 МБ; берём 49 МБ с запасом.
    max_file_size: int = field(default_factory=lambda: _env_int("MAX_FILE_SIZE_MB", 49) * 1024 * 1024)
    max_workers: int = field(default_factory=lambda: _env_int("MAX_WORKERS", 15))
    max_queue_size: int = field(default_factory=lambda: _env_int("MAX_QUEUE_SIZE", 500))
    max_user_tasks: int = field(default_factory=lambda: _env_int("MAX_USER_TASKS", 2))
    download_timeout: int = field(default_factory=lambda: _env_int("DOWNLOAD_TIMEOUT", 180))
    max_wait_time: int = field(default_factory=lambda: _env_int("MAX_WAIT_TIME", 600))
    throttle_seconds: float = field(default_factory=lambda: _env_int("THROTTLE_MS", 700) / 1000)

    # ── Прочее ────────────────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    default_lang: str = field(default_factory=lambda: os.getenv("DEFAULT_LANG", "ru"))
    file_cache_enabled: bool = field(default_factory=lambda: _env_bool("FILE_CACHE_ENABLED", True))
    user_flush_interval: int = field(default_factory=lambda: _env_int("USER_FLUSH_INTERVAL", 30))

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен."
            )
        if not self.admin_ids:
            # не критично, но админка будет недоступна
            pass


settings = Settings()

# ── Константы домена ──────────────────────────────────────────────────────────

SUPPORTED_DOMAINS: tuple[str, ...] = (
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "instagram.com",
    "instagr.am",
    "ddinstagram.com",
)

PLATFORM_EMOJIS: dict[str, str] = {
    "TikTok": "🎵",
    "Instagram": "📸",
}

LANGUAGES: tuple[str, ...] = ("ru", "en", "uz")
