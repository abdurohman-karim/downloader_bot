from aiogram import Dispatcher

from app.handlers.admin import admin_router
from app.handlers.user import user_router


def register_routers(dp: Dispatcher) -> None:
    dp.include_router(admin_router)
    dp.include_router(user_router)
