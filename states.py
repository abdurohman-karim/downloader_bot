from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    choosing_language = State()


class AdminStates(StatesGroup):
    waiting_channel_id = State()
    waiting_invite_link = State()
