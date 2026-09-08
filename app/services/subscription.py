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


async def _is_member(bot: Bot, channel_id: str, user_id: int) -> tuple[bool, bool]:
    """
    Возвращает (is_member, had_error).
    При ошибке API: is_member=True (не блокируем), had_error=True (не кэшируем результат).
    """
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in _SUBSCRIBED, False
    except Exception as exc:  # noqa: BLE001
        log.error(
            "subscription check failed for channel=%s user=%d — бот должен быть "
            "администратором канала! Ошибка: %s",
            channel_id, user_id, exc,
        )
        return True, True  # пропускаем, но не сохраняем снепшот


async def check_user_subscriptions(
    bot: Bot, user_id: int, channels: list[dict]
) -> tuple[list[dict], bool]:
    """
    Возвращает (unsubscribed_channels, had_errors).
    Проверки идут параллельно.
    """
    if not channels:
        return [], False

    results = await asyncio.gather(
        *(_is_member(bot, ch["channel_id"], user_id) for ch in channels)
    )
    unsubscribed = [ch for ch, (ok, _err) in zip(channels, results) if not ok]
    had_errors = any(err for _ok, err in results)
    return unsubscribed, had_errors


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

    unsubscribed, had_errors = await check_user_subscriptions(bot, user_id, channels)
    if not unsubscribed:
        if not had_errors:
            # Сохраняем снепшот только если все проверки прошли без ошибок.
            # При ошибках API (бот не admin канала) снепшот не кэшируем,
            # чтобы при следующем сообщении снова попробовать проверить.
            await db.upsert_user(user_id, channels_snapshot=snapshot)
        return None

    return build_subscribe_message(unsubscribed, lang)
