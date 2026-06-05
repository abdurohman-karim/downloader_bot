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
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from admin import admin_router
from config import (
    BOT_TOKEN,
    MAX_QUEUE_SIZE,
    MAX_WORKERS,
    PLATFORM_EMOJIS,
    SUPPORTED_DOMAINS,
)
from database import db
from i18n import t
from queue_manager import DownloadTask, QueueManager, safe_edit
from states import UserStates
from subscription import (
    build_subscribe_message,
    check_user_subscriptions,
    compute_snapshot,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(admin_router)

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


def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
        ]
    ])


async def _get_lang(user_id: int) -> str:
    user = await db.get_user(user_id)
    return user["language"] if user else "ru"


async def _subscription_required(
    user_id: int, lang: str
) -> tuple[bool, str, InlineKeyboardMarkup] | tuple[bool, None, None]:
    """
    Returns (True, text, keyboard) if subscription check is needed,
    or (False, None, None) if user can proceed.
    """
    sub_enabled = await db.get_setting("subscription_enabled")
    if sub_enabled != "1":
        return False, None, None

    channels = await db.get_channels(only_active=True)
    if not channels:
        return False, None, None

    current_snapshot = compute_snapshot(channels)
    user = await db.get_user(user_id)
    user_snapshot = user["channels_snapshot"] if user else ""

    if user_snapshot == current_snapshot:
        return False, None, None

    unsubscribed = await check_user_subscriptions(bot, user_id, channels)
    if not unsubscribed:
        await db.upsert_user(user_id, channels_snapshot=current_snapshot)
        return False, None, None

    text, keyboard = build_subscribe_message(unsubscribed, lang)
    return True, text, keyboard


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@dp.startup()
async def on_startup() -> None:
    await db.init()
    await queue_manager.start()
    log.info("Queue started: %d workers", MAX_WORKERS)


@dp.shutdown()
async def on_shutdown() -> None:
    log.info("Shutting down. Queue size: %d", queue_manager.stats["queue_size"])


# ── /start ────────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = msg.from_user.id
    user = await db.get_user(user_id)

    if user is not None:
        lang = user["language"]
        await msg.answer(t(lang, "send_link"), parse_mode="HTML")
        return

    await state.set_state(UserStates.choosing_language)
    await msg.answer(
        t("ru", "choose_language"),
        parse_mode="HTML",
        reply_markup=_lang_keyboard(),
    )


# ── Language selection ────────────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("lang:"))
async def cb_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":", 1)[1]
    if lang not in ("ru", "en", "uz"):
        await callback.answer()
        return

    user_id = callback.from_user.id
    await db.upsert_user(user_id, language=lang)
    await state.clear()

    await callback.message.edit_text(
        t(lang, "language_set"), parse_mode="HTML"
    )

    needs_sub, sub_text, sub_kb = await _subscription_required(user_id, lang)
    if needs_sub:
        await callback.message.answer(sub_text, parse_mode="HTML", reply_markup=sub_kb)
    else:
        await callback.message.answer(t(lang, "send_link"), parse_mode="HTML")

    await callback.answer()


# ── Subscription check ────────────────────────────────────────────────────────

@dp.callback_query(F.data == "sub:check")
async def cb_sub_check(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    lang = await _get_lang(user_id)

    channels = await db.get_channels(only_active=True)
    if not channels:
        await callback.message.edit_text(t(lang, "subscribe_success"), parse_mode="HTML")
        await callback.answer()
        return

    unsubscribed = await check_user_subscriptions(bot, user_id, channels)

    if unsubscribed:
        text, keyboard = build_subscribe_message(unsubscribed, lang)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer(t(lang, "subscribe_fail", channels=""))
        return

    current_snapshot = compute_snapshot(channels)
    await db.upsert_user(user_id, channels_snapshot=current_snapshot)
    await callback.message.edit_text(t(lang, "subscribe_success"), parse_mode="HTML")
    await callback.message.answer(t(lang, "send_link"), parse_mode="HTML")
    await callback.answer()


# ── /help ─────────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    lang = await _get_lang(msg.from_user.id)
    await msg.answer(t(lang, "help_text"), parse_mode="HTML")


# ── /stats ────────────────────────────────────────────────────────────────────

@dp.message(Command("stats"))
async def cmd_stats(msg: Message) -> None:
    lang = await _get_lang(msg.from_user.id)
    s = queue_manager.stats
    await msg.answer(
        t(
            lang, "stats_text",
            queue_size=s["queue_size"],
            max_queue=MAX_QUEUE_SIZE,
            active=s["active"],
            max_workers=s["max_workers"],
            total_ok=s["total_ok"],
            total_err=s["total_err"],
        ),
        parse_mode="HTML",
    )


# ── Link handler ──────────────────────────────────────────────────────────────

@dp.message(F.text.regexp(r"^[^/]"), StateFilter(None))
async def handle_link(msg: Message) -> None:
    url = extract_url(msg.text or "")
    if not url:
        return

    user_id = msg.from_user.id if msg.from_user else 0
    lang = await _get_lang(user_id)

    if not is_supported(url):
        await msg.reply(t(lang, "error_unsupported"), parse_mode="HTML")
        return

    await db.upsert_user(user_id)

    needs_sub, sub_text, sub_kb = await _subscription_required(user_id, lang)
    if needs_sub:
        await msg.reply(sub_text, parse_mode="HTML", reply_markup=sub_kb)
        return

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
        await safe_edit(status, t(lang, "downloading", emoji=emoji, platform=platform))
    else:
        await safe_edit(status, t(lang, "in_queue", pos=pos))


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("Bot started. Polling…")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
