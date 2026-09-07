"""Проверка обязательной подписки на каналы."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from app.db.database import db
from app.keyboards.user import subscribe_kb
from app.locales import t
from app.utils.text import esc

log = logging.getLogger(__name__)

_SUBSCRIBED = frozenset({"member", "administrator", "creator"})


def compute_snapshot(channels: list[dict]) -> str:
    return ",".join(sorted(str(c["channel_id"]) for c in channels))


async def _is_member(bot: Bot, channel_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in _SUBSCRIBED
    except Exception as exc:  # noqa: BLE001
        log.warning("cannot check %s for %d: %s", channel_id, user_id, exc)
        return True  # не наказываем пользователя за проблему на нашей стороне


async def check_user_subscriptions(
    bot: Bot, user_id: int, channels: list[dict]
) -> list[dict]:
    """Каналы, на которые пользователь не подписан. Проверки идут параллельно."""
    if not channels:
        return []
    results = await asyncio.gather(
        *(_is_member(bot, ch["channel_id"], user_id) for ch in channels)
    )
    return [ch for ch, ok in zip(channels, results) if not ok]


def build_subscribe_message(
    unsubscribed: list[dict], lang: str
) -> tuple[str, InlineKeyboardMarkup]:
    channels_text = "\n".join(f"• {esc(ch['title'])}" for ch in unsubscribed)
    text = t(lang, "subscribe_required", channels=channels_text)
    return text, subscribe_kb(unsubscribed, lang)


async def subscription_gate(
    bot: Bot, user_id: int, lang: str
) -> tuple[str, InlineKeyboardMarkup] | None:
    """
    None — пользователь может пользоваться ботом.
    Иначе — текст и клавиатура с требованием подписки.
    """
    if db.get_setting("subscription_enabled") != "1":
        return None

    channels = await db.get_channels(only_active=True)
    if not channels:
        return None

    snapshot = compute_snapshot(channels)
    user = await db.get_user(user_id)
    if user and user["channels_snapshot"] == snapshot:
        return None

    unsubscribed = await check_user_subscriptions(bot, user_id, channels)
    if not unsubscribed:
        await db.upsert_user(user_id, channels_snapshot=snapshot)
        return None

    return build_subscribe_message(unsubscribed, lang)
