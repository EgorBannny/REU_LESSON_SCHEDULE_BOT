"""Асинхронный слой доступа к PostgreSQL.

Общая БД для двух отдельных процессов/контейнеров: опросник (`poller.py`,
только пишет расписание) и бот (`bot.py`, читает расписание и пишет чаты/
участников/лог рассылок). asyncpg + пул соединений — все вызовы неблокирующие,
в отличие от старой версии на sqlite3, где приходилось городить
asyncio.to_thread из-за привязки соединения к потоку.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import asyncpg

from .models import DaySchedule, day_from_dict, day_to_dict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS days (
    schedule_date DATE PRIMARY KEY,
    weekday TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    data TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id BIGINT PRIMARY KEY,
    chat_type TEXT NOT NULL,
    group_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_members (
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    username TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS notifications_log (
    schedule_date DATE NOT NULL,
    chat_id BIGINT NOT NULL,
    content_hash TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (schedule_date, chat_id)
);
"""


async def create_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA)
    return pool


def _hash_day(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- расписание -----------------------------------------------------------


async def save_day(pool: asyncpg.Pool, day: DaySchedule) -> bool:
    """Сохраняет день в БД. Возвращает True, если данные новые или изменились."""
    data = day_to_dict(day)
    content_hash = _hash_day(data)

    async with pool.acquire() as conn:
        existing_hash = await conn.fetchval(
            "SELECT content_hash FROM days WHERE schedule_date = $1", day.schedule_date
        )
        if existing_hash == content_hash:
            return False
        await conn.execute(
            """
            INSERT INTO days (schedule_date, weekday, content_hash, data, first_seen_at, updated_at)
            VALUES ($1, $2, $3, $4, now(), now())
            ON CONFLICT (schedule_date) DO UPDATE
                SET weekday = EXCLUDED.weekday,
                    content_hash = EXCLUDED.content_hash,
                    data = EXCLUDED.data,
                    updated_at = now()
            """,
            day.schedule_date,
            day.weekday,
            content_hash,
            json.dumps(data, ensure_ascii=False),
        )
    return True


async def save_days(pool: asyncpg.Pool, days: list[DaySchedule]) -> list[date]:
    """Сохраняет несколько дней. Возвращает даты, которые оказались новыми или изменились."""
    return [day.schedule_date for day in days if await save_day(pool, day)]


def _row_to_day(row: asyncpg.Record) -> DaySchedule:
    return day_from_dict(json.loads(row["data"]))


async def get_latest_days(pool: asyncpg.Pool, count: int = 2, today: date | None = None) -> list[DaySchedule]:
    """Последние `count` дней не дальше чем на 1 день вперёд от сегодня, по возрастанию даты.

    Ограничение "не дальше завтра" защищает от того, что источник иногда
    публикует расписание на несколько дней вперёд одновременно — без этого
    "последние N по дате" со временем всё дальше уезжали бы в будущее и
    переставали бы включать текущий день.
    """
    cutoff = (today or datetime.now(timezone.utc).date()) + timedelta(days=1)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT data FROM days WHERE schedule_date <= $1 ORDER BY schedule_date DESC LIMIT $2",
            cutoff,
            count,
        )
    days = [_row_to_day(row) for row in rows]
    return sorted(days, key=lambda d: d.schedule_date)


async def get_available_months(pool: asyncpg.Pool) -> list[tuple[int, int]]:
    """Месяцы (год, месяц), за которые в архиве есть хоть один день, по возрастанию."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT date_trunc('month', schedule_date)::date AS month_start "
            "FROM days ORDER BY month_start ASC"
        )
    return [(row["month_start"].year, row["month_start"].month) for row in rows]


async def get_dates_in_month(pool: asyncpg.Pool, year: int, month: int) -> list[date]:
    """Все даты конкретного месяца, для которых есть расписание, по возрастанию."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT schedule_date FROM days "
            "WHERE date_trunc('month', schedule_date) = date_trunc('month', $1::date) "
            "ORDER BY schedule_date ASC",
            date(year, month, 1),
        )
    return [row["schedule_date"] for row in rows]


async def get_day(pool: asyncpg.Pool, schedule_date: date) -> DaySchedule | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT data FROM days WHERE schedule_date = $1", schedule_date)
    return _row_to_day(row) if row else None


async def is_stale(pool: asyncpg.Pool, max_age_minutes: int = 15) -> bool:
    async with pool.acquire() as conn:
        last_updated = await conn.fetchval("SELECT MAX(updated_at) FROM days")
    if last_updated is None:
        return True
    return datetime.now(timezone.utc) - last_updated > timedelta(minutes=max_age_minutes)


# --- чаты (личные и групповые) --------------------------------------------


async def get_chat_group(pool: asyncpg.Pool, chat_id: int) -> str | None:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT group_name FROM chats WHERE chat_id = $1", chat_id)


async def set_chat_group(pool: asyncpg.Pool, chat_id: int, chat_type: str, group_name: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chats (chat_id, chat_type, group_name, created_at, updated_at)
            VALUES ($1, $2, $3, now(), now())
            ON CONFLICT (chat_id) DO UPDATE
                SET chat_type = EXCLUDED.chat_type,
                    group_name = EXCLUDED.group_name,
                    updated_at = now()
            """,
            chat_id,
            chat_type,
            group_name,
        )


async def get_all_chats(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Все чаты с выбранной группой — для фоновой рассылки. Поля: chat_id, group_name."""
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT chat_id, group_name FROM chats WHERE group_name IS NOT NULL")


# --- участники чата (для /сбор) -------------------------------------------


async def upsert_chat_member(
    pool: asyncpg.Pool, chat_id: int, user_id: int, display_name: str, username: str | None
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_members (chat_id, user_id, display_name, username, last_seen_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (chat_id, user_id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    username = EXCLUDED.username,
                    last_seen_at = now()
            """,
            chat_id,
            user_id,
            display_name,
            username,
        )


async def get_chat_members(pool: asyncpg.Pool, chat_id: int) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, display_name, username FROM chat_members WHERE chat_id = $1", chat_id
        )


# --- лог рассылок -----------------------------------------------------------


async def days_pending_notification(
    pool: asyncpg.Pool, chat_id: int, group_name: str, lookback_days: int = 3
) -> list[tuple[DaySchedule, str]]:
    """Дни за последние `lookback_days`, которые этому чату ещё не отправляли
    (или отправляли, но с тех пор контент изменился — определяется по хэшу).
    Возвращает пары (день, content_hash) — хэш нужен вызывающему коду, чтобы
    потом отметить именно эту версию отправленной через mark_notified.
    """
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.data, d.content_hash
            FROM days d
            LEFT JOIN notifications_log n
                ON n.schedule_date = d.schedule_date AND n.chat_id = $1
            WHERE d.schedule_date >= $2
                AND (n.content_hash IS NULL OR n.content_hash != d.content_hash)
            ORDER BY d.schedule_date ASC
            """,
            chat_id,
            cutoff,
        )
    pending = []
    for row in rows:
        day = day_from_dict(json.loads(row["data"]))
        if day.find_group(group_name) is not None:
            pending.append((day, row["content_hash"]))
    return pending


async def mark_notified(pool: asyncpg.Pool, schedule_date: date, chat_id: int, content_hash: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO notifications_log (schedule_date, chat_id, content_hash, sent_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (schedule_date, chat_id) DO UPDATE
                SET content_hash = EXCLUDED.content_hash, sent_at = now()
            """,
            schedule_date,
            chat_id,
            content_hash,
        )
