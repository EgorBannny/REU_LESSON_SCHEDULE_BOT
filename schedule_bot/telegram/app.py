"""Сборка и запуск бота: Bot, Dispatcher, роутеры, пул БД, фоновая рассылка."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.client.session.aiohttp import AiohttpSession

from .. import db
from ..config import BOT_TOKEN, DATABASE_URL, TELEGRAM_PROXY
from .handlers import router
from .middlewares import ChatMemberTrackerMiddleware
from .notifier import run_notifier

logger = logging.getLogger(__name__)

_COMMANDS = [
    BotCommand(command="start", description="Начать / выбрать группу"),
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="my", description="Моё расписание"),
    BotCommand(command="all", description="Расписание всех групп"),
    BotCommand(command="other", description="Расписание другой группы"),
    BotCommand(command="change", description="Сменить группу"),
    BotCommand(command="sbor", description="Созыв — позвать всех в чате (только группы)"),
]


async def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан. Укажите его в .env (см. .env.example) или переменных окружения."
        )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    bot_kwargs = {"default": DefaultBotProperties(parse_mode=ParseMode.HTML)}

    # Если прокси есть (на сервере), добавляем сессию в словарь
    if TELEGRAM_PROXY:
        bot_kwargs["session"] = AiohttpSession(proxy=TELEGRAM_PROXY)


    bot = Bot(token=BOT_TOKEN, **bot_kwargs)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(ChatMemberTrackerMiddleware())
    dp.include_router(router)

    pool = await db.create_pool(DATABASE_URL)

    try:
        await bot.set_my_commands(_COMMANDS)
    except Exception:
        logger.exception("Не удалось выставить список команд бота")

    notifier_task = asyncio.create_task(run_notifier(bot, pool))
    try:
        await dp.start_polling(bot, pool=pool)
    finally:
        notifier_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notifier_task
        await pool.close()
        await bot.session.close()
