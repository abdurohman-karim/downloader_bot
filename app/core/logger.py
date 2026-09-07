from __future__ import annotations

import logging

from app.core.config import settings


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    )
    # Библиотеки шумят на INFO — приглушаем.
    for noisy in ("aiogram.event", "aiosqlite", "yt_dlp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
