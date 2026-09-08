from __future__ import annotations

import contextlib
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.config import LANGUAGES, PLATFORM_EMOJIS, settings
from app.db.database import db
from app.keyboards.user import language_kb
from app.locales import t
from app.services.queue import DownloadTask, queue_manager, safe_edit
from app.services.subscription import (
    check_user_subscriptions,
    compute_snapshot,
    subscription_gate,
)
from app.states import UserStates
from app.utils.text import build_caption
from app.utils.urls import cache_key, extract_url, is_supported, platform_of

log = logging.getLogger(__name__)
user_router = Router(name="user")


# ── /start ────────────────────────────────────────────────────────────────────

@user_router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, lang: str, registered: bool) -> None:
    await state.clear()
    if registered:
        await msg.answer(t(lang, "send_link"))
        return

    await state.set_state(UserStates.choosing_language)
    await msg.answer(t(settings.default_lang, "choose_language"), reply_markup=language_kb())


@user_router.message(Command("lang"))
async def cmd_lang(msg: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(UserStates.choosing_language)
    await msg.answer(t(lang, "choose_language"), reply_markup=language_kb())


@user_router.callback_query(F.data.startswith("lang:"))
async def cb_language(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    lang = callback.data.split(":", 1)[1]
    if lang not in LANGUAGES:
        await callback.answer()
        return

    user_id = callback.from_user.id
    await db.upsert_user(user_id, language=lang)
    await state.clear()

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(t(lang, "language_set"))

    gate = await subscription_gate(bot, user_id, lang)
    if gate:
        text, kb = gate
        await callback.message.answer(text, reply_markup=kb)
    else:
        await callback.message.answer(t(lang, "send_link"))
    await callback.answer()


# ── Проверка подписки ─────────────────────────────────────────────────────────

@user_router.callback_query(F.data == "sub:check")
async def cb_sub_check(callback: CallbackQuery, bot: Bot, lang: str) -> None:
    user_id = callback.from_user.id
    channels = await db.get_channels(only_active=True)

    unsubscribed, _ = await check_user_subscriptions(bot, user_id, channels) if channels else ([], False)
    if unsubscribed:
        await callback.answer(t(lang, "subscribe_fail"), show_alert=True)
        return

    if channels:
        await db.upsert_user(user_id, channels_snapshot=compute_snapshot(channels))
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(t(lang, "subscribe_success"))
    await callback.message.answer(t(lang, "send_link"))
    await callback.answer()


# ── Инфо-команды ──────────────────────────────────────────────────────────────

@user_router.message(Command("help"))
async def cmd_help(msg: Message, lang: str) -> None:
    await msg.answer(t(lang, "help_text"))


@user_router.message(Command("stats"))
async def cmd_stats(msg: Message, lang: str) -> None:
    s = queue_manager.stats
    await msg.answer(
        t(
            lang, "stats_text",
            queue_size=s["queue_size"],
            max_queue=settings.max_queue_size,
            active=s["active"],
            max_workers=s["max_workers"],
            total_ok=s["total_ok"],
            total_cached=s["total_cached"],
            total_err=s["total_err"],
        )
    )


# ── Ссылки ────────────────────────────────────────────────────────────────────

@user_router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_link(msg: Message, bot: Bot, lang: str) -> None:
    url = extract_url(msg.text or "")
    if not url:
        return

    user_id = msg.from_user.id
    if not is_supported(url):
        await msg.reply(t(lang, "error_unsupported"))
        return

    await db.ensure_user(user_id)

    gate = await subscription_gate(bot, user_id, lang)
    if gate:
        text, kb = gate
        await msg.reply(text, reply_markup=kb)
        return

    platform = platform_of(url)
    emoji = PLATFORM_EMOJIS.get(platform, "🌐")
    key = cache_key(url)

    # Быстрый путь: видео уже загружали — отдаём по file_id, без очереди.
    if settings.file_cache_enabled:
        cached = await db.get_cached_video(key)
        if cached:
            try:
                await msg.reply_video(
                    video=cached["file_id"],
                    caption=build_caption(
                        cached["title"], cached["duration"], platform, emoji
                    ),
                )
                return
            except TelegramBadRequest as exc:
                log.info("stale file_id for %s: %s", key, exc)
                await db.drop_cached_video(key)

    status = await msg.reply(t(lang, "adding_to_queue"))
    task = DownloadTask(
        user_id=user_id,
        url=url,
        url_key=key,
        platform=platform,
        lang=lang,
        reply_to=msg,
        status_msg=status,
    )

    ok, payload = await queue_manager.enqueue(task)
    if not ok:
        await safe_edit(status, str(payload))
        return

    position = int(payload)
    if position <= settings.max_workers:
        await safe_edit(status, t(lang, "downloading", emoji=emoji, platform=platform))
    else:
        await safe_edit(status, t(lang, "in_queue", pos=position))
