"""Простой антифлуд: не чаще одного апдейта в N мс от пользователя."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.config import settings

_MAX_TRACKED = 20_000


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        previous = self._last.get(user.id, 0.0)
        if now - previous < settings.throttle_seconds:
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None  # молча игнорируем флуд

        if len(self._last) > _MAX_TRACKED:
            cutoff = now - 60
            self._last = {k: v for k, v in self._last.items() if v > cutoff}
        self._last[user.id] = now

        if isinstance(event, (Message, CallbackQuery)):
            data["throttle_ts"] = now
        return await handler(event, data)
