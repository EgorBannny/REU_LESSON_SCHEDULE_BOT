"""SQLite-кэш разобранного расписания.

Хранит уже распарсенные дни, чтобы не дёргать Google Sheets на каждый запрос
пользователя, и позволяет быстро достать последние N дней, для которых
расписание реально присутствует в таблице. Каждый день хранится вместе с
хэшем содержимого — если колледж поправил уже опубликованный день, повторный
refresh это заметит (изменится content_hash), даже если дата та же.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import DaySchedule, day_from_dict, day_to_dict
from .scraper import SPARTAKOVSKAYA_SPO_URL, fetch_html, parse_schedule

DEFAULT_DB_PATH = Path(__file__).parent.parent / "schedule.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS days (
    schedule_date TEXT PRIMARY KEY,
    weekday TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    data TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    group_name TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _hash_day(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_day(conn: sqlite3.Connection, day: DaySchedule) -> bool:
    """Сохраняет день в кэш. Возвращает True, если данные новые или изменились."""
    data = day_to_dict(day)
    content_hash = _hash_day(data)
    now = datetime.now().isoformat()
    date_str = day.schedule_date.isoformat()

    row = conn.execute(
        "SELECT content_hash FROM days WHERE schedule_date = ?", (date_str,)
    ).fetchone()

    if row is not None and row[0] == content_hash:
        return False

    if row is None:
        conn.execute(
            "INSERT INTO days (schedule_date, weekday, content_hash, data, first_seen_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date_str, day.weekday, content_hash, json.dumps(data, ensure_ascii=False), now, now),
        )
    else:
        conn.execute(
            "UPDATE days SET weekday = ?, content_hash = ?, data = ?, updated_at = ? WHERE schedule_date = ?",
            (day.weekday, content_hash, json.dumps(data, ensure_ascii=False), now, date_str),
        )
    conn.commit()
    return True


def save_days(conn: sqlite3.Connection, days: list[DaySchedule]) -> list[date]:
    """Сохраняет несколько дней. Возвращает даты, которые оказались новыми или изменились."""
    return [day.schedule_date for day in days if save_day(conn, day)]


def get_latest_days(conn: sqlite3.Connection, count: int = 2) -> list[DaySchedule]:
    """Последние `count` дней из кэша, у которых есть расписание, по возрастанию даты."""
    rows = conn.execute(
        "SELECT data FROM days ORDER BY schedule_date DESC LIMIT ?", (count,)
    ).fetchall()
    days = [day_from_dict(json.loads(row[0])) for row in rows]
    return sorted(days, key=lambda d: d.schedule_date)


def get_day(conn: sqlite3.Connection, schedule_date: date) -> DaySchedule | None:
    row = conn.execute(
        "SELECT data FROM days WHERE schedule_date = ?", (schedule_date.isoformat(),)
    ).fetchone()
    return day_from_dict(json.loads(row[0])) if row else None


def refresh_from_source(conn: sqlite3.Connection, url: str = SPARTAKOVSKAYA_SPO_URL) -> list[date]:
    """Качает и парсит источник, сохраняет всё найденное в кэш. Возвращает изменившиеся даты."""
    html = fetch_html(url)
    days = parse_schedule(html)
    return save_days(conn, days)


def is_stale(conn: sqlite3.Connection, max_age_minutes: int = 15) -> bool:
    """Пуст ли кэш или последнее обновление было раньше, чем max_age_minutes назад."""
    row = conn.execute("SELECT MAX(updated_at) FROM days").fetchone()
    if row is None or row[0] is None:
        return True
    last_updated = datetime.fromisoformat(row[0])
    return datetime.now() - last_updated > timedelta(minutes=max_age_minutes)


def ensure_fresh(
    conn: sqlite3.Connection, url: str = SPARTAKOVSKAYA_SPO_URL, max_age_minutes: int = 15
) -> list[date]:
    """Обновляет кэш из источника, только если он пуст или устарел. Возвращает изменившиеся даты."""
    if not is_stale(conn, max_age_minutes):
        return []
    return refresh_from_source(conn, url)


def get_user_group(conn: sqlite3.Connection, telegram_id: int) -> str | None:
    row = conn.execute(
        "SELECT group_name FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    return row[0] if row else None


def set_user_group(conn: sqlite3.Connection, telegram_id: int, group_name: str) -> None:
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO users (telegram_id, group_name, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET group_name = excluded.group_name, updated_at = excluded.updated_at",
        (telegram_id, group_name, now),
    )
    conn.commit()
