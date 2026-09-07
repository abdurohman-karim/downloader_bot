from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.locales import t

_LANG_TITLES = (("ru", "🇷🇺 Русский"), ("en", "🇬🇧 English"), ("uz", "🇺🇿 O'zbek"))


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=title, callback_data=f"lang:{code}")
                for code, title in _LANG_TITLES
            ]
        ]
    )


def subscribe_kb(channels: list[dict], lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        link = ch.get("invite_link")
        if not link:
            cid = str(ch["channel_id"])
            if cid.startswith("@"):
                link = f"https://t.me/{cid[1:]}"
        if link:
            rows.append([InlineKeyboardButton(text=f"➡️ {ch['title']}", url=link)])
    rows.append(
        [InlineKeyboardButton(text=t(lang, "subscribe_check_btn"), callback_data="sub:check")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
