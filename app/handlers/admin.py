from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.config import settings
from app.db.database import db
from app.keyboards.admin import (
    add_channel_kb,
    back_kb,
    channels_kb,
    main_menu_kb,
    settings_kb,
)
from app.services.queue import queue_manager
from app.states import AdminStates
from app.utils.text import esc

log = logging.getLogger(__name__)
admin_router = Router(name="admin")

_MENU_TITLE = "🛠 <b>Админ-панель</b>"


class AdminFilter(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in settings.admin_ids


admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())


async def _edit(callback: CallbackQuery, text: str, markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


async def _channels_view() -> tuple[str, object]:
    channels = await db.get_channels(only_active=False)
    if not channels:
        text = "📋 <b>Каналы</b>\n\nКаналов пока нет."
    else:
        lines = ["📋 <b>Каналы</b>\n"]
        for ch in channels:
            status = "✅" if ch["is_active"] else "⛔"
            lines.append(
                f"{status} <b>{esc(ch['title'])}</b> — <code>{esc(ch['channel_id'])}</code>"
            )
        text = "\n".join(lines)
    return text, channels_kb(channels)


# ── Меню ──────────────────────────────────────────────────────────────────────

@admin_router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer(_MENU_TITLE, reply_markup=main_menu_kb())


@admin_router.callback_query(F.data == "admin:menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(callback, _MENU_TITLE, main_menu_kb())
    await callback.answer()


# ── Каналы ────────────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:channels")
async def cb_channels(callback: CallbackQuery) -> None:
    text, kb = await _channels_view()
    await _edit(callback, text, kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:toggle:"))
async def cb_toggle_channel(callback: CallbackQuery) -> None:
    await db.toggle_channel_by_id(int(callback.data.rsplit(":", 1)[1]))
    text, kb = await _channels_view()
    await _edit(callback, text, kb)
    await callback.answer("Статус изменён")


@admin_router.callback_query(F.data.startswith("admin:del:"))
async def cb_del_channel(callback: CallbackQuery) -> None:
    await db.remove_channel_by_id(int(callback.data.rsplit(":", 1)[1]))
    text, kb = await _channels_view()
    await _edit(callback, text, kb)
    await callback.answer("Канал удалён")


# ── Добавление канала ─────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_channel_id)
    await _edit(
        callback,
        "📥 <b>Добавление канала</b>\n\n"
        "Отправьте username канала в формате <code>@channel</code> "
        "или числовой ID (<code>-100xxxxxxxxxx</code>).\n\n"
        "Бот должен быть администратором канала для проверки подписок.",
        back_kb(),
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_channel_id)
async def process_channel_id(msg: Message, state: FSMContext, bot: Bot) -> None:
    channel_input = (msg.text or "").strip()
    if not channel_input:
        await msg.answer("Отправьте username или ID канала.")
        return

    bot_is_member = True
    try:
        chat = await bot.get_chat(channel_input)
        title = chat.title or channel_input
    except TelegramBadRequest:
        title, bot_is_member = channel_input, False
    except Exception as exc:  # noqa: BLE001
        await msg.answer(
            f"❌ Не удалось получить информацию о канале:\n<code>{esc(exc)}</code>\n\n"
            "Проверьте правильность username/ID."
        )
        return

    await state.update_data(channel_id=channel_input, title=title)
    await state.set_state(AdminStates.waiting_invite_link)

    warning = (
        ""
        if bot_is_member
        else "\n\n⚠️ <b>Внимание:</b> бот не состоит в этом канале — проверка подписок "
             "работать не будет. Добавьте бота администратором."
    )
    await msg.answer(
        f"✅ Канал: <b>{esc(title)}</b> (<code>{esc(channel_input)}</code>){warning}\n\n"
        "Есть ли пригласительная ссылка?",
        reply_markup=add_channel_kb(),
    )


async def _finish_add(
    state: FSMContext, added_by: int, invite_link: str | None
) -> tuple[str, object]:
    data = await state.get_data()
    await state.clear()
    ok = await db.add_channel(
        channel_id=data["channel_id"],
        title=data["title"],
        invite_link=invite_link,
        added_by=added_by,
    )
    if not ok:
        return "❌ Не удалось добавить канал. Возможно, он уже существует.", back_kb()

    text, kb = await _channels_view()
    return f"✅ Канал <b>{esc(data['title'])}</b> добавлен.\n\n{text}", kb


@admin_router.callback_query(AdminStates.waiting_invite_link, F.data == "admin:has_link")
async def cb_has_link(callback: CallbackQuery) -> None:
    await _edit(callback, "🔗 Отправьте пригласительную ссылку на канал:", back_kb())
    await callback.answer()


@admin_router.callback_query(AdminStates.waiting_invite_link, F.data == "admin:no_link")
async def cb_no_link(callback: CallbackQuery, state: FSMContext) -> None:
    text, kb = await _finish_add(state, callback.from_user.id, None)
    await _edit(callback, text, kb)
    await callback.answer()


@admin_router.message(AdminStates.waiting_invite_link)
async def process_invite_link(msg: Message, state: FSMContext) -> None:
    invite_link = (msg.text or "").strip()
    if not invite_link.startswith("http"):
        await msg.answer("Ссылка должна начинаться с http:// или https://")
        return
    text, kb = await _finish_add(state, msg.from_user.id, invite_link)
    await msg.answer(text, reply_markup=kb)


# ── Настройки ─────────────────────────────────────────────────────────────────

def _settings_view() -> tuple[str, object]:
    sub_enabled = db.get_setting("subscription_enabled") == "1"
    bot_active = db.get_setting("bot_active", "1") == "1"
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"Проверка подписки: <b>{'✅ включена' if sub_enabled else '⛔ выключена'}</b>\n"
        f"Состояние бота: <b>{'▶️ работает' if bot_active else '🛠 техработы'}</b>"
    )
    return text, settings_kb(sub_enabled, bot_active)


@admin_router.callback_query(F.data == "admin:settings")
async def cb_settings(callback: CallbackQuery) -> None:
    text, kb = _settings_view()
    await _edit(callback, text, kb)
    await callback.answer()


@admin_router.callback_query(F.data == "admin:toggle_sub")
async def cb_toggle_sub(callback: CallbackQuery) -> None:
    current = db.get_setting("subscription_enabled")
    await db.set_setting("subscription_enabled", "0" if current == "1" else "1")
    text, kb = _settings_view()
    await _edit(callback, text, kb)
    await callback.answer("Настройки обновлены")


@admin_router.callback_query(F.data == "admin:toggle_active")
async def cb_toggle_active(callback: CallbackQuery) -> None:
    current = db.get_setting("bot_active", "1")
    await db.set_setting("bot_active", "0" if current == "1" else "1")
    text, kb = _settings_view()
    await _edit(callback, text, kb)
    await callback.answer("Состояние изменено")


# ── Статистика ────────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    s = await db.get_stats()
    q = queue_manager.stats
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{s['total_users']}</b>\n"
        f"🟢 Активных сегодня: <b>{s['active_today']}</b>\n"
        f"📢 Активных каналов: <b>{s['total_channels']}</b>\n"
        f"🎞 Видео в кэше: <b>{s['cached_videos']}</b>\n\n"
        f"⏳ В очереди: <b>{q['queue_size']}</b>\n"
        f"⚙️ Загружается: <b>{q['active']}</b> / {q['max_workers']}\n"
        f"✅ Успешно: <b>{q['total_ok']}</b> (из кэша: {q['total_cached']})\n"
        f"❌ Ошибок: <b>{q['total_err']}</b>"
    )
    await _edit(callback, text, back_kb())
    await callback.answer()
