from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..models import DaySchedule


def groups_keyboard(group_names: list[str], columns: int = 3) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name in group_names:
        builder.button(text=name, callback_data=f"grp:{name}")
    builder.adjust(columns)
    return builder.as_markup()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Моё расписание", callback_data="menu:my")
    builder.button(text="📚 Расписание всех групп", callback_data="menu:all")
    builder.button(text="🔍 Расписание другой группы", callback_data="menu:other")
    builder.button(text="🔄 Сменить группу", callback_data="menu:change")
    builder.adjust(1)
    return builder.as_markup()


def days_keyboard(days: list[DaySchedule], action: str, group: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in reversed(days):
        label = f"{day.schedule_date.strftime('%d.%m')} ({day.weekday})"
        date_iso = day.schedule_date.isoformat()
        data = f"day:{action}:{group}:{date_iso}" if group else f"day:{action}:{date_iso}"
        builder.button(text=label, callback_data=data)
    builder.adjust(1)
    return builder.as_markup()
