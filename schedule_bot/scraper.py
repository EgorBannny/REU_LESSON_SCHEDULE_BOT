"""Загрузка и разбор расписания СПО Спартаковская из опубликованного Google Sheet.

Сайт РЭУ (rea.ru) при клике на "Расписание" просто открывает опубликованную
Google-таблицу (pubhtml). Реальные данные расписания лежат там, поэтому
парсим напрямую эту страницу, без похода на rea.ru.

Таблица устроена блоками: каждый блок начинается со строки-заголовка вида
"РАСПИСАНИЕ НА 02 СЕНТЯБРЯ 2026 г. (Среда) 1 смена ... Дежурный преподаватель ...",
где несколько таких заголовков (по числу смен) лежат в одной строке рядом
(colspan). Следом идёт строка с шапкой столбцов ("Группа", "1. 8.15-09.50", ...),
а затем — произвольное число строк данных на группу (предмет, затем в
отдельных под-строках преподаватель/аудитория/примечания — колледж не
объединяет ячейки, а просто переносит текст на новые строки таблицы).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from .models import DaySchedule, GroupSchedule, Lesson, ShiftSchedule

SPARTAKOVSKAYA_SPO_URL = (
    "https://docs.google.com/spreadsheets/u/0/d/e/"
    "2PACX-1vQnQ6GHmX4k8T2pYdKodgDjU9M-UAQQByJZH93TWDOL-40eTaRCnzU6O3O2_ihU9lI8BCrSwBiVZfU0/"
    "pubhtml/sheet?headers=false&gid=2015835982"
)

_BLOCK_HEADER_RE = re.compile(r"РАСПИСАНИЕ НА", re.IGNORECASE)
_DATE_RE = re.compile(r"РАСПИСАНИЕ НА\s+([^()]+?)\s*\(([^)]+)\)", re.IGNORECASE)
_SHIFT_RE = re.compile(r"(\d+)\s*смена", re.IGNORECASE)
_DUTY_RE = re.compile(r"Дежурный преподаватель\s*(.+)$", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"смена\s*(.*?)\s*(?:Дежурный преподаватель|$)", re.IGNORECASE | re.DOTALL
)
_LESSON_HEADER_RE = re.compile(r"^(\d+)\.\s*(.+)$")
_DAY_MONTH_YEAR_RE = re.compile(r"(\d{1,2})\s+([А-Яа-яЁё]+)\s+(\d{4})")
# Код группы вида "Б-111", "ТиГ--211", "ИСиП-411" — заглавные буквы, дефис(ы), цифры.
# Нужен, чтобы отличать реальное название группы от заметок ("занятия", "с 12.05"),
# которые иногда попадают в ту же колонку и иначе ошибочно считаются новой группой.
_GROUP_CODE_RE = re.compile(r"^[А-Яа-яЁё]{1,6}-{1,2}\d{1,5}$")

_RU_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def fetch_html(url: str = SPARTAKOVSKAYA_SPO_URL, timeout: float = 15.0) -> str:
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _parse_ru_date(text: str) -> date:
    match = _DAY_MONTH_YEAR_RE.search(text)
    if not match:
        raise ValueError(f"Не удалось разобрать дату: {text!r}")
    day, month_name, year = match.groups()
    month = _RU_MONTHS.get(month_name.lower())
    if month is None:
        raise ValueError(f"Неизвестный месяц: {month_name!r}")
    return date(int(year), month, int(day))


def _row_cells(row: Tag) -> list[Tag]:
    return [
        c
        for c in row.find_all(["td", "th"], recursive=False)
        if not any("row-header" in cls for cls in c.get("class", []))
    ]


def _cell_text(cell: Tag) -> str:
    return cell.get_text(" ", strip=True)


def parse_schedule(html: str) -> list[DaySchedule]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    tbody = table.find("tbody")
    if tbody is None:
        return []
    rows = tbody.find_all("tr", recursive=False)

    days: list[DaySchedule] = []
    block_start: int | None = None
    for i, row in enumerate(rows):
        joined = " ".join(_cell_text(c) for c in _row_cells(row))
        if _BLOCK_HEADER_RE.search(joined):
            if block_start is not None:
                days.append(_parse_block(rows[block_start:i]))
            block_start = i
    if block_start is not None:
        days.append(_parse_block(rows[block_start:]))
    return days


def _parse_block(rows: list[Tag]) -> DaySchedule:
    header_cells = _row_cells(rows[0])

    shifts: list[ShiftSchedule] = []
    ranges: list[tuple[int, int]] = []
    day_date: date | None = None
    weekday = ""
    col = 0
    for cell in header_cells:
        text = _cell_text(cell)
        span = int(cell.get("colspan", 1))
        ranges.append((col, col + span))
        col += span

        date_match = _DATE_RE.search(text)
        if date_match and day_date is None:
            day_date = _parse_ru_date(date_match.group(1))
            weekday = date_match.group(2).strip()

        shift_match = _SHIFT_RE.search(text)
        shift_number = int(shift_match.group(1)) if shift_match else len(shifts) + 1
        location_match = _LOCATION_RE.search(text)
        location = location_match.group(1).strip(" ,") if location_match else ""
        duty_match = _DUTY_RE.search(text)
        duty_teacher = duty_match.group(1).strip() if duty_match else None
        shifts.append(
            ShiftSchedule(
                shift_number=shift_number,
                location=location or None,
                duty_teacher=duty_teacher,
                groups=[],
            )
        )

    if day_date is None:
        raise ValueError("Не удалось найти дату в блоке расписания")

    group_cols: list[int] = []
    lesson_cols: list[list[tuple[int, int, str]]] = []
    if len(rows) > 1:
        col_cells = _row_cells(rows[1])
        for start, end in ranges:
            group_cols.append(start)
            cols: list[tuple[int, int, str]] = []
            for abs_col in range(start + 1, end):
                if abs_col >= len(col_cells):
                    continue
                m = _LESSON_HEADER_RE.match(_cell_text(col_cells[abs_col]))
                if m:
                    cols.append((abs_col, int(m.group(1)), m.group(2).strip()))
            lesson_cols.append(cols)
    else:
        group_cols = [start for start, _ in ranges]
        lesson_cols = [[] for _ in ranges]

    data_rows = rows[2:]
    for shift, group_col, cols in zip(shifts, group_cols, lesson_cols):
        _fill_shift_groups(shift, group_col, cols, data_rows)

    return DaySchedule(schedule_date=day_date, weekday=weekday, shifts=shifts)


def _fill_shift_groups(
    shift: ShiftSchedule,
    group_col: int,
    cols: list[tuple[int, int, str]],
    data_rows: list[Tag],
) -> None:
    current_group: str | None = None
    current_lines: dict[int, list[str]] = {}

    def flush() -> None:
        if current_group is None:
            return
        lessons = [
            Lesson(number=num, time=time, lines=current_lines.get(abs_col, []))
            for abs_col, num, time in cols
        ]
        if any(not lesson.is_empty for lesson in lessons):
            shift.groups.append(GroupSchedule(group=current_group, lessons=lessons))

    for row in data_rows:
        cells = _row_cells(row)
        if group_col >= len(cells):
            continue
        group_text = _cell_text(cells[group_col])
        if group_text and _GROUP_CODE_RE.match(group_text):
            flush()
            current_group = group_text
            current_lines = {}
        if current_group is None:
            continue
        for abs_col, _num, _time in cols:
            if abs_col >= len(cells):
                continue
            text = _cell_text(cells[abs_col])
            if text:
                current_lines.setdefault(abs_col, []).append(text)
    flush()


def get_latest_days(days: list[DaySchedule], count: int = 2) -> list[DaySchedule]:
    return sorted(days, key=lambda d: d.schedule_date)[-count:]
