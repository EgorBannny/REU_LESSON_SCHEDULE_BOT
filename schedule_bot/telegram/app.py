"""Сборка и запуск бота: Bot, Dispatcher, роутеры, соединение с БД."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .. import storage
from ..config import BOT_TOKEN
from .handlers import router

logger = logging.getLogger(__name__)

_COMMANDS = [
    BotCommand(command="start", description="Начать / выбрать группу"),
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="my", description="Моё расписание"),
    BotCommand(command="all", description="Расписание всех групп"),
    BotCommand(command="other", description="Расписание другой группы"),
    BotCommand(command="change", description="Сменить группу"),
]


async def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан. Укажите его в .env (см. .env.example) или переменных окружения."
        )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    conn = storage.connect()
    try:
        # Разовый блокирующий вызов до начала polling — conn создан в этом же
        # потоке, поэтому здесь (в отличие от хендлеров) можно звать напрямую.
        storage.ensure_fresh(conn)
    except Exception:
        logger.exception("Не удалось загрузить расписание при старте, продолжаю с тем, что есть в кэше")

    try:
        await bot.set_my_commands(_COMMANDS)
    except Exception:
        logger.exception("Не удалось выставить список команд бота")

    try:
        await dp.start_polling(bot, conn=conn)
    finally:
        conn.close()
        await bot.session.close()
