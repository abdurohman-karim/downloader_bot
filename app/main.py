"""Точка входа: сборка Dispatcher, запуск polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.core.config import settings
from app.core.logger import setup_logging
from app.db.database import db
from app.handlers import register_routers
from app.middlewares import ThrottlingMiddleware, UserContextMiddleware
from app.services.queue import queue_manager

log = logging.getLogger(__name__)

_COMMANDS = [
    BotCommand(command="start", description="Начать / Start"),
    BotCommand(command="lang", description="Сменить язык / Change language"),
    BotCommand(command="help", description="Помощь / Help"),
    BotCommand(command="stats", description="Статистика / Stats"),
]


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(ThrottlingMiddleware())
        observer.outer_middleware(UserContextMiddleware())

    register_routers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


async def on_startup(bot: Bot) -> None:
    await db.init()
    await queue_manager.start()
    await bot.set_my_commands(_COMMANDS)
    me = await bot.get_me()
    log.info("Bot @%s started", me.username)


async def on_shutdown() -> None:
    log.info("Shutting down (queue size: %d)", queue_manager.stats["queue_size"])
    await queue_manager.stop()
    await db.close()


async def main() -> None:
    setup_logging()
    settings.validate()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()
    try:
        await dp.start_polling(
            bot,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Stopped by user")


if __name__ == "__main__":
    run()
