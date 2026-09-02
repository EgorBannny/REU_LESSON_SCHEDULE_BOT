"""Точка входа Telegram-бота REU LESSON SCHEDULE.

Запуск: uv run bot.py
Требует переменную окружения BOT_TOKEN (см. .env.example).
"""

import asyncio
import logging

from schedule_bot.telegram.app import run

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        logging.exception("Бот аварийно завершился")
        raise
