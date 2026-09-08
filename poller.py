"""Фоновый опросник: отдельный процесс/контейнер, который периодически

качает и парсит расписание и складывает его в общую БД. Не знает про
Telegram — только источник и БД. Бот и опросник общаются исключительно
через БД (см. схему в schedule_bot/db.py).

Запуск: uv run poller.py
"""

from __future__ import annotations

import asyncio
import logging

from schedule_bot import BOT_NAME
from schedule_bot.config import DATABASE_URL, POLL_INTERVAL_MINUTES
from schedule_bot.db import create_pool, save_days
from schedule_bot.scraper import SPARTAKOVSKAYA_SPO_URL, fetch_html, parse_schedule

logger = logging.getLogger(__name__)


async def poll_once(pool) -> None:
    html = await asyncio.to_thread(fetch_html, SPARTAKOVSKAYA_SPO_URL)
    days = parse_schedule(html)
    if not days:
        logger.warning("Источник вернул 0 дней с расписанием — похоже, разметка страницы изменилась")
        return
    changed = await save_days(pool, days)
    if changed:
        logger.info("Обновились/появились даты: %s", ", ".join(d.isoformat() for d in changed))
    else:
        logger.info("Опрос: изменений нет (дни в источнике: %s)", ", ".join(d.schedule_date.isoformat() for d in days))


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("%s — опросник запущен, интервал %s мин.", BOT_NAME, POLL_INTERVAL_MINUTES)

    pool = await create_pool(DATABASE_URL)
    try:
        while True:
            try:
                await poll_once(pool)
            except Exception:
                logger.exception("Ошибка при опросе источника, попробую в следующий раз")
            await asyncio.sleep(POLL_INTERVAL_MINUTES * 60)
    finally:
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        logging.exception("Опросник аварийно завершился")
        raise
