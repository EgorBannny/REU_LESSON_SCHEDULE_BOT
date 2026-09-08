from __future__ import annotations

from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..models import DaySchedule

MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _day_callback(action: str, group: str | None, date_iso: str) -> str:
    return f"day:{action}:{group}:{date_iso}" if group else f"day:{action}:{date_iso}"


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
    """Кнопки последних дней — по возрастанию даты (раньше сверху, позже снизу)."""
    builder = InlineKeyboardBuilder()
    for day in sorted(days, key=lambda d: d.schedule_date):
        label = f"{day.schedule_date.strftime('%d.%m')} ({day.weekday})"
        builder.button(text=label, callback_data=_day_callback(action, group, day.schedule_date.isoformat()))
    builder.button(text="📆 Архив по месяцам", callback_data=f"hist:{action}:{group or '-'}:months")
    builder.adjust(1)
    return builder.as_markup()


def months_keyboard(months: list[tuple[int, int]], action: str, group: str | None = None) -> InlineKeyboardMarkup:
    """Список месяцев, за которые есть архив, по возрастанию, слева направо / сверху вниз."""
    builder = InlineKeyboardBuilder()
    for year, month in months:
        label = f"{MONTH_NAMES[month]} {year}"
        builder.button(text=label, callback_data=f"hist:{action}:{group or '-'}:{year:04d}-{month:02d}")
    builder.adjust(2)
    return builder.as_markup()


def month_dates_keyboard(
    dates: list[date], action: str, group: str | None = None
) -> InlineKeyboardMarkup:
    """Даты внутри выбранного месяца, по возрастанию, слева направо / сверху вниз."""
    builder = InlineKeyboardBuilder()
    for d in sorted(dates):
        builder.button(text=d.strftime("%d.%m"), callback_data=_day_callback(action, group, d.isoformat()))
    builder.adjust(3)
    builder.row(
        InlineKeyboardButton(text="⬅️ К списку месяцев", callback_data=f"hist:{action}:{group or '-'}:months")
    )
    return builder.as_markup()
