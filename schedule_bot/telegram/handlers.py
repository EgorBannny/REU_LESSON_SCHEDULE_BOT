"""Обработчики диалога бота.

Всё, что требует нескольких шагов (выбор группы), ведётся через FSMContext
aiogram — состояние привязано к конкретному (chat_id, user_id), поэтому
несколько пользователей могут одновременно находиться на разных шагах
диалога, не мешая друг другу.

По потокам: sqlite3.Connection создаётся один раз при старте бота и может
использоваться только из того потока, в котором был создан (в нашем случае —
поток event loop). Поэтому обращения к storage.* здесь синхронные и
выполняются прямо в хендлере — они быстрые (небольшая локальная база).
А вот сеть (скачивание Google Sheets) и рендер картинок — медленные и не
трогают conn, поэтому уходят в отдельный поток через asyncio.to_thread,
чтобы не блокировать бота для остальных пользователей, пока один из них
ждёт обновления расписания или рендера альбома на 30 картинок.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import suppress
from datetime import date
from typing import Iterable

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, ErrorEvent, InputMediaPhoto, Message

from .. import render, storage
from ..scraper import SPARTAKOVSKAYA_SPO_URL, fetch_html, parse_schedule
from .keyboards import days_keyboard, groups_keyboard, main_menu_keyboard
from .states import GroupSelection

logger = logging.getLogger(__name__)

router = Router(name="schedule")

_ALBUM_CHUNK_SIZE = 10
_GENERIC_ERROR_TEXT = "Что-то пошло не так. Попробуйте ещё раз или отправьте /menu."


def _chunks(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _safe_ensure_fresh(conn: sqlite3.Connection) -> None:
    """Обновляет кэш из источника, но никогда не роняет вызывающий хендлер.

    Сеть и парсинг HTML не трогают sqlite-соединение, поэтому спокойно
    уходят в отдельный поток; запись результата в БД остаётся в основном
    потоке. Если Google Sheets недоступен или ответ не разобрался — просто
    работаем с тем, что уже есть в кэше, вместо падения посреди диалога.
    """
    try:
        if not storage.is_stale(conn):
            return
        html = await asyncio.to_thread(fetch_html, SPARTAKOVSKAYA_SPO_URL)
        days = await asyncio.to_thread(parse_schedule, html)
        storage.save_days(conn, days)
    except Exception:
        logger.exception("Не удалось обновить расписание из источника, использую кэш")


def _available_group_names(conn: sqlite3.Connection) -> list[str]:
    days = storage.get_latest_days(conn, 2)
    return sorted({name for day in days for name in day.all_group_names()})


async def _offer_group_choice(target: Message, state: FSMContext, conn: sqlite3.Connection, new_state, prompt: str) -> None:
    await _safe_ensure_fresh(conn)
    names = _available_group_names(conn)
    if not names:
        await target.answer("Список групп пока недоступен, попробуйте позже.")
        return
    await state.set_state(new_state)
    await target.answer(prompt, reply_markup=groups_keyboard(names))


async def _ask_day(target: Message, conn: sqlite3.Connection, action: str, group: str | None = None) -> None:
    await _safe_ensure_fresh(conn)
    days = storage.get_latest_days(conn, 2)
    if not days:
        await target.answer("Расписание пока не загружено, попробуйте позже.")
        return
    label = f"группы {group}" if group else "всех групп" if action == "all" else "вашей группы"
    await target.answer(f"За какой день показать расписание {label}?", reply_markup=days_keyboard(days, action, group))


async def _send_group_schedule(target: Message, conn: sqlite3.Connection, group_name: str | None, date_iso: str) -> None:
    if not group_name:
        await target.answer("Сначала выберите свою группу — отправьте /start.")
        return
    day = storage.get_day(conn, date.fromisoformat(date_iso))
    if day is None:
        await target.answer("Не нашёл расписание за этот день.")
        return
    found = day.find_group_with_shift(group_name)
    if found is None:
        await target.answer(f"У группы {group_name} нет пар {day.schedule_date.strftime('%d.%m.%Y')} ({day.weekday}).")
        return
    shift, group = found

    try:
        png = await asyncio.to_thread(render.render_group_card_bytes, day, shift, group)
    except Exception:
        logger.exception("Не удалось отрендерить карточку группы %s", group_name)
        await target.answer("Не получилось собрать картинку расписания. Попробуйте ещё раз.")
        return

    caption = f"{group_name} — {day.schedule_date.strftime('%d.%m.%Y')} ({day.weekday})"
    try:
        await target.answer_photo(BufferedInputFile(png, filename="schedule.png"), caption=caption)
    except Exception:
        logger.exception("Не удалось отправить фото с расписанием группы %s", group_name)
        await target.answer("Не получилось отправить картинку, попробуйте ещё раз.")
        return
    await target.answer("Что дальше?", reply_markup=main_menu_keyboard())


async def _send_all_schedule(target: Message, conn: sqlite3.Connection, date_iso: str) -> None:
    day = storage.get_day(conn, date.fromisoformat(date_iso))
    if day is None:
        await target.answer("Не нашёл расписание за этот день.")
        return

    try:
        cards = await asyncio.to_thread(render.render_all_group_cards_bytes, day)
    except Exception:
        logger.exception("Не удалось отрендерить карточки всех групп за %s", date_iso)
        await target.answer("Не получилось собрать картинки расписания. Попробуйте ещё раз.")
        return

    if not cards:
        await target.answer("В этот день нет ни одной группы с занятиями.")
        return

    await target.answer(f"Все группы — {day.schedule_date.strftime('%d.%m.%Y')} ({day.weekday})")
    try:
        for chunk in _chunks(cards, _ALBUM_CHUNK_SIZE):
            media = [
                InputMediaPhoto(media=BufferedInputFile(png, filename=f"{name}.png"), caption=name)
                for name, png in chunk
            ]
            await target.answer_media_group(media)
    except Exception:
        logger.exception("Не удалось отправить альбом с расписанием всех групп за %s", date_iso)
        await target.answer("Не получилось отправить часть картинок, попробуйте ещё раз.")
        return
    await target.answer("Что дальше?", reply_markup=main_menu_keyboard())


# --- /start и онбординг ---------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, conn: sqlite3.Connection) -> None:
    await state.clear()
    group = storage.get_user_group(conn, message.from_user.id)
    if group:
        await message.answer(f"С возвращением! Ваша группа — {group}.", reply_markup=main_menu_keyboard())
        return
    await _offer_group_choice(
        message,
        state,
        conn,
        GroupSelection.onboarding,
        "Привет! Я — REU LESSON SCHEDULE, бот с расписанием СПО Спартаковская.\n\nВыберите свою группу:",
    )


@router.callback_query(GroupSelection.onboarding, F.data.startswith("grp:"))
async def onboarding_group_chosen(callback: CallbackQuery, state: FSMContext, conn: sqlite3.Connection) -> None:
    group = callback.data.removeprefix("grp:")
    storage.set_user_group(conn, callback.from_user.id, group)
    await state.clear()
    await callback.message.edit_text(f"Готово! Ваша группа — {group}.")
    await callback.message.answer("Что показать?", reply_markup=main_menu_keyboard())
    await callback.answer()


# --- главное меню -----------------------------------------------------


@router.message(Command("menu"))
async def cmd_menu(message: Message, conn: sqlite3.Connection) -> None:
    group = storage.get_user_group(conn, message.from_user.id)
    if not group:
        await message.answer("Сначала выберите группу — отправьте /start.")
        return
    await message.answer("Меню:", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:my")
async def menu_my(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    group = storage.get_user_group(conn, callback.from_user.id)
    if not group:
        await callback.answer("Сначала выберите группу через /start", show_alert=True)
        return
    await _ask_day(callback.message, conn, "my")
    await callback.answer()


@router.message(Command("my"))
async def cmd_my(message: Message, conn: sqlite3.Connection) -> None:
    group = storage.get_user_group(conn, message.from_user.id)
    if not group:
        await message.answer("Сначала выберите группу — отправьте /start.")
        return
    await _ask_day(message, conn, "my")


@router.callback_query(F.data == "menu:all")
async def menu_all(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    await _ask_day(callback.message, conn, "all")
    await callback.answer()


@router.message(Command("all"))
async def cmd_all(message: Message, conn: sqlite3.Connection) -> None:
    await _ask_day(message, conn, "all")


@router.callback_query(F.data == "menu:change")
async def menu_change(callback: CallbackQuery, state: FSMContext, conn: sqlite3.Connection) -> None:
    await _offer_group_choice(callback.message, state, conn, GroupSelection.changing, "Выберите новую группу:")
    await callback.answer()


@router.message(Command("change"))
async def cmd_change(message: Message, state: FSMContext, conn: sqlite3.Connection) -> None:
    await _offer_group_choice(message, state, conn, GroupSelection.changing, "Выберите новую группу:")


@router.callback_query(GroupSelection.changing, F.data.startswith("grp:"))
async def change_group_chosen(callback: CallbackQuery, state: FSMContext, conn: sqlite3.Connection) -> None:
    group = callback.data.removeprefix("grp:")
    storage.set_user_group(conn, callback.from_user.id, group)
    await state.clear()
    await callback.message.edit_text(f"Группа изменена на {group}.")
    await callback.message.answer("Что показать?", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:other")
async def menu_other(callback: CallbackQuery, state: FSMContext, conn: sqlite3.Connection) -> None:
    await _offer_group_choice(
        callback.message, state, conn, GroupSelection.lookup, "Расписание какой группы показать?"
    )
    await callback.answer()


@router.message(Command("other"))
async def cmd_other(message: Message, command: CommandObject, state: FSMContext, conn: sqlite3.Connection) -> None:
    requested = (command.args or "").strip()
    if requested:
        names = _available_group_names(conn)
        if requested in names:
            await _ask_day(message, conn, "other", group=requested)
            return
        await message.answer(f"Не нашёл группу «{requested}». Выберите из списка:")
    await _offer_group_choice(message, state, conn, GroupSelection.lookup, "Расписание какой группы показать?")


@router.callback_query(GroupSelection.lookup, F.data.startswith("grp:"))
async def lookup_group_chosen(callback: CallbackQuery, state: FSMContext, conn: sqlite3.Connection) -> None:
    group = callback.data.removeprefix("grp:")
    await state.clear()
    await callback.message.edit_text(f"Расписание группы {group}")
    await _ask_day(callback.message, conn, "other", group=group)
    await callback.answer()


# --- выбор дня и отправка расписания -----------------------------------


@router.callback_query(F.data.startswith("day:my:"))
async def send_my_schedule(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    date_iso = callback.data.removeprefix("day:my:")
    group_name = storage.get_user_group(conn, callback.from_user.id)
    await _send_group_schedule(callback.message, conn, group_name, date_iso)
    await callback.answer()


@router.callback_query(F.data.startswith("day:other:"))
async def send_other_schedule(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    try:
        _, _, group_name, date_iso = callback.data.split(":", 3)
    except ValueError:
        logger.warning("Некорректный callback_data: %r", callback.data)
        await callback.answer("Устаревшая кнопка, откройте меню заново: /menu", show_alert=True)
        return
    await _send_group_schedule(callback.message, conn, group_name, date_iso)
    await callback.answer()


@router.callback_query(F.data.startswith("day:all:"))
async def send_all_schedule(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    date_iso = callback.data.removeprefix("day:all:")
    await _send_all_schedule(callback.message, conn, date_iso)
    await callback.answer()


# --- заглушка на всё остальное -----------------------------------------


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Не понял сообщение. Используйте /menu или кнопки под сообщениями бота.")


# --- страховочная сетка --------------------------------------------------


@router.errors()
async def handle_errors(event: ErrorEvent, bot: Bot) -> bool:
    """Ловит всё, что не поймали хендлеры выше, чтобы бот не падал целиком.

    aiogram и так изолирует обработку одного апдейта от другого, но без
    этого хендлера пользователь просто не получил бы никакого ответа при
    неожиданной ошибке, а сама ошибка ушла бы только в логи.
    """
    logger.exception("Необработанная ошибка при обработке апдейта", exc_info=event.exception)

    update = event.update
    if update.callback_query is not None:
        with suppress(Exception):
            await update.callback_query.answer(_GENERIC_ERROR_TEXT, show_alert=True)
        return True

    chat_id = None
    if update.message is not None:
        chat_id = update.message.chat.id
    if chat_id is not None:
        with suppress(Exception):
            await bot.send_message(chat_id, _GENERIC_ERROR_TEXT)
    return True
