"""
Подставляет язык пользователя в handler'ы (без запроса к БД на каждое сообщение)
и блокирует бота для обычных пользователей в режиме техработ.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.config import settings
from app.db.database import db
from app.locales import t


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        lang = await db.get_language(user.id)
        data["registered"] = lang is not None
        data["lang"] = lang or settings.default_lang
        data["is_admin"] = user.id in settings.admin_ids
        db.touch(user.id)

        if db.get_setting("bot_active", "1") != "1" and not data["is_admin"]:
            text = t(data["lang"], "bot_disabled")
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return None

        return await handler(event, data)
