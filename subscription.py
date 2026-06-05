from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from i18n import t

log = logging.getLogger(__name__)

_SUBSCRIBED = {"member", "administrator", "creator"}


def compute_snapshot(channels: list[dict]) -> str:
    return ",".join(sorted(str(c["channel_id"]) for c in channels))


async def check_user_subscriptions(
    bot: Bot, user_id: int, channels: list[dict]
) -> list[dict]:
    unsubscribed: list[dict] = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["channel_id"], user_id)
            if member.status not in _SUBSCRIBED:
                unsubscribed.append(channel)
        except Exception as exc:
            log.warning(
                "Cannot check channel %s for user %d: %s",
                channel["channel_id"], user_id, exc,
            )
    return unsubscribed


def build_subscribe_message(
    unsubscribed: list[dict], lang: str
) -> tuple[str, InlineKeyboardMarkup]:
    lines: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []

    for ch in unsubscribed:
        lines.append(f"• {ch['title']}")
        link: str | None = ch.get("invite_link")
        if not link:
            cid: str = ch["channel_id"]
            if cid.startswith("@"):
                link = f"https://t.me/{cid[1:]}"
        if link:
            buttons.append(
                [InlineKeyboardButton(text=f"➡️ {ch['title']}", url=link)]
            )

    channels_text = "\n".join(lines)
    text = t(lang, "subscribe_required", channels=channels_text)
    buttons.append(
        [InlineKeyboardButton(text=t(lang, "subscribe_check_btn"), callback_data="sub:check")]
    )
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)
