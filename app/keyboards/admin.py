from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Каналы", callback_data="admin:channels"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings"),
        ],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")]
    ])


def channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        icon, label = ("🔴", "Выключить") if ch["is_active"] else ("🟢", "Включить")
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {label}", callback_data=f"admin:toggle:{ch['id']}"
            ),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin:del:{ch['id']}"),
        ])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin:add_channel"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_channel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔗 Есть ссылка", callback_data="admin:has_link"),
            InlineKeyboardButton(text="➡️ Без ссылки", callback_data="admin:no_link"),
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin:menu")],
    ])


def settings_kb(sub_enabled: bool, bot_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⛔ Выключить проверку подписки" if sub_enabled else "✅ Включить проверку подписки",
            callback_data="admin:toggle_sub",
        )],
        [InlineKeyboardButton(
            text="🛠 Включить техработы" if bot_active else "▶️ Выключить техработы",
            callback_data="admin:toggle_active",
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")],
    ])
