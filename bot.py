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
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from config import BOT_TOKEN, PLATFORM_EMOJIS, SUPPORTED_DOMAINS
from downloader import DownloadResult, VideoDownloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
downloader = VideoDownloader()

_busy: set[int] = set()
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


def format_duration(secs: Optional[int]) -> str:
    if not secs:
        return ""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_caption(result: DownloadResult, platform: str) -> str:
    emoji = PLATFORM_EMOJIS.get(platform, "🌐")
    lines: list[str] = []
    if result.title:
        lines.append(f"<b>{result.title[:100]}</b>")
    dur = format_duration(result.duration)
    if dur:
        lines.append(f"⏱ {dur}")
    lines.append(f"{emoji} {platform}")
    return "\n".join(lines)


async def safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        pass


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

    if user_id in _busy:
        await msg.reply("⏳ Подожди — предыдущая загрузка ещё не завершена.")
        return

    platform = platform_of(url)
    emoji = PLATFORM_EMOJIS.get(platform, "🌐")
    status = await msg.reply(f"{emoji} Загружаю с {platform}…")
    _busy.add(user_id)
    result: Optional[DownloadResult] = None

    try:
        result = await downloader.download(url)

        if not result.ok:
            await safe_edit(status, f"❌ {result.error}")
            return

        await safe_edit(status, "📤 Отправляю…")
        await msg.reply_video(
            video=FSInputFile(result.path),
            caption=build_caption(result, platform),
            parse_mode="HTML",
        )
        await status.delete()

    except TelegramBadRequest as exc:
        log.warning("Telegram error [user=%s]: %s", user_id, exc)
        await safe_edit(
            status,
            "❌ Не удалось отправить файл — вероятно, он слишком большой для Telegram.",
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Unhandled error [user=%s]", user_id)
        await safe_edit(status, f"❌ Непредвиденная ошибка: {str(exc)[:120]}")
    finally:
        _busy.discard(user_id)
        if result and result.path:
            VideoDownloader.cleanup(result.path)


async def main() -> None:
    log.info("Bot started. Polling…")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
