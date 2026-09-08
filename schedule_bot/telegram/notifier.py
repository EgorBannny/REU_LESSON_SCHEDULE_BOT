"""Фоновая рассылка: раз в NOTIFY_INTERVAL_SECONDS проверяет по каждому
подписанному чату (личному или групповому), не появилось ли для его группы
новое/изменившееся расписание за последние NOTIFY_LOOKBACK_DAYS дней, и если
да — присылает картинку. Опросник (poller.py) только пишет расписание в БД;
непосредственно отправкой в Telegram занимается бот, потому что только у
него есть открытая сессия с Bot API.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from .. import db, render
from ..config import NOTIFY_INTERVAL_SECONDS, NOTIFY_LOOKBACK_DAYS, NOTIFY_THROTTLE_SECONDS

logger = logging.getLogger(__name__)


async def _notify_chat(bot: Bot, pool: asyncpg.Pool, chat_id: int, group_name: str) -> None:
    pending = await db.days_pending_notification(pool, chat_id, group_name, NOTIFY_LOOKBACK_DAYS)
    for day, content_hash in pending:
        found = day.find_group_with_shift(group_name)
        if found is None:
            continue
        shift, group = found
        caption = f"🔔 Обновилось расписание — {group_name} — {day.schedule_date.strftime('%d.%m.%Y')} ({day.weekday})"
        try:
            png = await asyncio.to_thread(render.render_group_card_bytes, day, shift, group)
            await bot.send_photo(chat_id, BufferedInputFile(png, filename="schedule.png"), caption=caption)
        except (TelegramForbiddenError, TelegramNotFound):
            logger.info("Чат %s недоступен (заблокировал бота/удалён) — пропускаю", chat_id)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            continue
        except Exception:
            logger.exception("Не удалось отправить рассылку в чат %s за %s", chat_id, day.schedule_date)
            continue
        await db.mark_notified(pool, day.schedule_date, chat_id, content_hash)
        await asyncio.sleep(NOTIFY_THROTTLE_SECONDS)


async def notify_tick(bot: Bot, pool: asyncpg.Pool) -> None:
    chats = await db.get_all_chats(pool)
    for row in chats:
        try:
            await _notify_chat(bot, pool, row["chat_id"], row["group_name"])
        except Exception:
            logger.exception("Сбой рассылки для чата %s", row["chat_id"])


async def run_notifier(bot: Bot, pool: asyncpg.Pool) -> None:
    logger.info("Фоновая рассылка запущена, интервал %s сек.", NOTIFY_INTERVAL_SECONDS)
    while True:
        try:
            await notify_tick(bot, pool)
        except Exception:
            logger.exception("Ошибка в цикле рассылки")
        await asyncio.sleep(NOTIFY_INTERVAL_SECONDS)
