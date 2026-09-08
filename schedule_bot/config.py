from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://schedule:schedule@localhost:5432/schedule")

# Опросник: как часто дёргать источник (минуты).
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "5"))

# Бот: как часто проверять, кому нужно разослать обновившееся расписание (секунды).
NOTIFY_INTERVAL_SECONDS = int(os.getenv("NOTIFY_INTERVAL_SECONDS", "60"))

# На сколько дней назад ещё имеет смысл слать уведомление (чтобы не заваливать
# только что подключившийся чат старой историей).
NOTIFY_LOOKBACK_DAYS = int(os.getenv("NOTIFY_LOOKBACK_DAYS", "2"))

# Пауза между отправками подряд при рассылке — чтобы не упереться в лимиты Telegram.
NOTIFY_THROTTLE_SECONDS = float(os.getenv("NOTIFY_THROTTLE_SECONDS", "0.1"))
