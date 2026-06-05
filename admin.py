from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import ADMIN_IDS
from database import db
from states import AdminStates

log = logging.getLogger(__name__)
admin_router = Router(name="admin")


# ── Filter ────────────────────────────────────────────────────────────────────

class AdminFilter(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in ADMIN_IDS


admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Каналы", callback_data="admin:channels"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
        ],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")]
    ])


async def _channels_message() -> tuple[str, InlineKeyboardMarkup]:
    channels = await db.get_channels(only_active=False)
    if not channels:
        text = "📋 <b>Каналы</b>\n\nКаналов пока нет."
    else:
        lines = ["📋 <b>Каналы</b>\n"]
        for ch in channels:
            status = "✅" if ch["is_active"] else "⛔"
            lines.append(f"{status} <b>{ch['title']}</b> — <code>{ch['channel_id']}</code>")
        text = "\n".join(lines)

    buttons: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        toggle_label = "Выключить" if ch["is_active"] else "Включить"
        toggle_icon = "🔴" if ch["is_active"] else "🟢"
        buttons.append([
            InlineKeyboardButton(
                text=f"{toggle_icon} {toggle_label}",
                callback_data=f"admin:toggle:{ch['id']}",
            ),
            InlineKeyboardButton(
                text="🗑 Удалить",
                callback_data=f"admin:del:{ch['id']}",
            ),
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin:add_channel"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu"),
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ── /admin command ─────────────────────────────────────────────────────────────

@admin_router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer(
        "🛠 <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=_main_menu_kb(),
    )


# ── Main menu ─────────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=_main_menu_kb(),
    )
    await callback.answer()


# ── Channels section ──────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:channels")
async def cb_channels(callback: CallbackQuery) -> None:
    text, kb = await _channels_message()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:toggle:"))
async def cb_toggle_channel(callback: CallbackQuery) -> None:
    db_id = int(callback.data.split(":", 2)[2])
    await db.toggle_channel_by_id(db_id)
    text, kb = await _channels_message()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Статус изменён")


@admin_router.callback_query(F.data.startswith("admin:del:"))
async def cb_del_channel(callback: CallbackQuery) -> None:
    db_id = int(callback.data.split(":", 2)[2])
    await db.remove_channel_by_id(db_id)
    text, kb = await _channels_message()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Канал удалён")


# ── Add channel flow ──────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_channel_id)
    await callback.message.edit_text(
        "📥 <b>Добавление канала</b>\n\n"
        "Отправьте username канала в формате <code>@channel</code> "
        "или числовой ID (<code>-100xxxxxxxxxx</code>).\n\n"
        "Бот должен быть администратором канала для проверки подписок.",
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_channel_id)
async def process_channel_id(msg: Message, state: FSMContext, bot: Bot) -> None:
    channel_input = (msg.text or "").strip()
    if not channel_input:
        await msg.answer("Отправьте username или ID канала.")
        return

    title: str
    bot_is_member = True

    try:
        chat = await bot.get_chat(channel_input)
        title = chat.title or channel_input
    except TelegramBadRequest:
        title = channel_input
        bot_is_member = False
    except Exception as exc:
        await msg.answer(
            f"❌ Не удалось получить информацию о канале:\n<code>{exc}</code>\n\n"
            "Проверьте правильность username/ID.",
            parse_mode="HTML",
        )
        return

    await state.update_data(channel_id=channel_input, title=title)
    await state.set_state(AdminStates.waiting_invite_link)

    warning = ""
    if not bot_is_member:
        warning = (
            "\n\n⚠️ <b>Внимание:</b> бот не является участником этого канала. "
            "Проверка подписок для него работать не будет. "
            "Добавьте бота в канал как администратора."
        )

    await msg.answer(
        f"✅ Канал: <b>{title}</b> (<code>{channel_input}</code>){warning}\n\n"
        "Есть ли пригласительная ссылка для вступления в канал?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔗 Есть ссылка", callback_data="admin:has_link"),
                InlineKeyboardButton(text="➡️ Без ссылки", callback_data="admin:no_link"),
            ],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin:menu")],
        ]),
    )


@admin_router.callback_query(AdminStates.waiting_invite_link, F.data == "admin:has_link")
async def cb_has_link(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🔗 Отправьте пригласительную ссылку для вступления в канал:",
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@admin_router.callback_query(AdminStates.waiting_invite_link, F.data == "admin:no_link")
async def cb_no_link(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    success = await db.add_channel(
        channel_id=data["channel_id"],
        title=data["title"],
        invite_link=None,
        added_by=callback.from_user.id,
    )
    if success:
        text, kb = await _channels_message()
        await callback.message.edit_text(
            f"✅ Канал <b>{data['title']}</b> добавлен без ссылки.\n\n" + text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось добавить канал. Возможно, он уже существует.",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )
    await callback.answer()


@admin_router.message(AdminStates.waiting_invite_link)
async def process_invite_link(msg: Message, state: FSMContext) -> None:
    invite_link = (msg.text or "").strip()
    if not invite_link.startswith("http"):
        await msg.answer("Ссылка должна начинаться с http:// или https://")
        return

    data = await state.get_data()
    await state.clear()
    success = await db.add_channel(
        channel_id=data["channel_id"],
        title=data["title"],
        invite_link=invite_link,
        added_by=msg.from_user.id,
    )
    if success:
        text, kb = await _channels_message()
        await msg.answer(
            f"✅ Канал <b>{data['title']}</b> добавлен со ссылкой.\n\n" + text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await msg.answer(
            "❌ Не удалось добавить канал. Возможно, он уже существует.",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )


# ── Settings section ──────────────────────────────────────────────────────────

async def _settings_text_and_kb() -> tuple[str, InlineKeyboardMarkup]:
    sub_enabled = await db.get_setting("subscription_enabled") == "1"
    sub_status = "✅ Включена" if sub_enabled else "⛔ Выключена"
    sub_btn = "⛔ Выключить" if sub_enabled else "✅ Включить"

    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"Проверка подписки: <b>{sub_status}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sub_btn, callback_data="admin:toggle_sub")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")],
    ])
    return text, kb


@admin_router.callback_query(F.data == "admin:settings")
async def cb_settings(callback: CallbackQuery) -> None:
    text, kb = await _settings_text_and_kb()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data == "admin:toggle_sub")
async def cb_toggle_sub(callback: CallbackQuery) -> None:
    current = await db.get_setting("subscription_enabled")
    new_value = "0" if current == "1" else "1"
    await db.set_setting("subscription_enabled", new_value)
    text, kb = await _settings_text_and_kb()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Настройки обновлены")


# ── Stats section ─────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    from bot import queue_manager  # lazy import to avoid circular dependency

    db_stats = await db.get_stats()
    q = queue_manager.stats

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{db_stats['total_users']}</b>\n"
        f"🟢 Активных сегодня: <b>{db_stats['active_today']}</b>\n"
        f"📢 Активных каналов: <b>{db_stats['total_channels']}</b>\n\n"
        f"⏳ В очереди: <b>{q['queue_size']}</b>\n"
        f"⚙️ Загружается: <b>{q['active']}</b>\n"
        f"✅ Успешно: <b>{q['total_ok']}</b>\n"
        f"❌ Ошибок: <b>{q['total_err']}</b>"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=_back_kb()
    )
    await callback.answer()
