"""Состояния диалога (aiogram FSM).

FSMContext в aiogram по умолчанию хранит состояние отдельно для каждого
(chat_id, user_id) — поэтому пока один пользователь выбирает группу, это
никак не задевает состояние остальных пользователей бота.
"""

from aiogram.fsm.state import State, StatesGroup


class GroupSelection(StatesGroup):
    onboarding = State()  # первый выбор группы сразу после /start
    changing = State()  # смена своей группы из меню
    lookup = State()  # разовый просмотр расписания чужой группы
