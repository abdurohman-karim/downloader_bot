"""
Video Downloader Bot  ·  aiogram 3
Supported: TikTok · Instagram Reels/Posts
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from config import (
    BOT_TOKEN,
    MAX_QUEUE_SIZE,
    MAX_WORKERS,
    PLATFORM_EMOJIS,
    SUPPORTED_DOMAINS,
)
from queue_manager import DownloadTask, QueueManager, safe_edit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
queue_manager = QueueManager()

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def extract_url(text: str) -> Optional[str]:
    m = _URL_RE.search(text)
    return m.group().rstrip(".,);\"'") if m else None


def is_supported(url: str) -> bool:
    return any(d in url.lower() for d in SUPPORTED_DOMAINS)


def platform_of(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u:
        return "TikTok"
    if "instagram.com" in u or "instagr.am" in u:
        return "Instagram"
    return "Video"


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@dp.startup()
async def on_startup() -> None:
    await queue_manager.start()
    log.info("Queue started: %d workers", MAX_WORKERS)


@dp.shutdown()
async def on_shutdown() -> None:
    log.info("Shutting down. Queue size: %d", queue_manager.stats["queue_size"])


# ── Handlers ──────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(msg: Message) -> None:
    await msg.answer(
        "👋 <b>Video Downloader Bot</b>\n\n"
        "Отправь ссылку — скачаю видео и пришлю прямо сюда.\n\n"
        "🎵 <b>TikTok</b>\n"
        "📸 <b>Instagram</b> (Reels, Posts)\n\n"
        "⚠️ Максимальный размер файла: <b>50 МБ</b>",
        parse_mode="HTML",
    )


@dp.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(
        "ℹ️ <b>Как пользоваться</b>\n\n"
        "Просто отправь ссылку на видео — бот скачает и пришлёт файл.\n\n"
        "<b>Платформы:</b>\n"
        "• TikTok\n"
        "• Instagram Reels и Posts\n\n"
        "<b>Ограничения:</b>\n"
        "• Максимальный размер: <b>50 МБ</b>\n"
        "• Приватные видео и видео с авторскими правами не загружаются",
        parse_mode="HTML",
    )


@dp.message(Command("stats"))
async def cmd_stats(msg: Message) -> None:
    s = queue_manager.stats
    await msg.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"• В очереди: <b>{s['queue_size']}</b> / {MAX_QUEUE_SIZE}\n"
        f"• Активных загрузок: <b>{s['active']}</b> / {s['max_workers']}\n"
        f"• Успешно обработано: <b>{s['total_ok']}</b>\n"
        f"• Ошибок: <b>{s['total_err']}</b>",
        parse_mode="HTML",
    )


@dp.message(F.text)
async def handle_link(msg: Message) -> None:
    if msg.text and msg.text.startswith("/"):
        return

    url = extract_url(msg.text or "")
    if not url:
        return

    if not is_supported(url):
        await msg.reply(
            "⚠️ Поддерживаются только ссылки с <b>TikTok</b> и <b>Instagram</b>.",
            parse_mode="HTML",
        )
        return

    user_id = msg.from_user.id if msg.from_user else 0
    platform = platform_of(url)
    emoji = PLATFORM_EMOJIS.get(platform, "🌐")

    status = await msg.reply("⏳ Добавляю в очередь…")

    task = DownloadTask(
        user_id=user_id,
        url=url,
        platform=platform,
        reply_to=msg,
        status_msg=status,
    )

    success, payload = await queue_manager.enqueue(task)
    if not success:
        await safe_edit(status, payload)  # type: ignore[arg-type]
        return

    pos: int = payload  # type: ignore[assignment]
    if pos <= MAX_WORKERS:
        await safe_edit(status, f"{emoji} Загружаю с {platform}…")
    else:
        await safe_edit(status, f"⏳ В очереди: позиция {pos}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("Bot started. Polling…")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
