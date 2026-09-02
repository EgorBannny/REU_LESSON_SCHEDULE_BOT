"""Демо Фазы 1: скачать и разобрать расписание, показать последние 2 дня.

Запуск: uv run main.py
"""

from schedule_bot import BOT_NAME, __version__
from schedule_bot.scraper import fetch_html, get_latest_days, parse_schedule


def main() -> None:
    print(f"{BOT_NAME} v{__version__} — демо парсера расписания")

    html = fetch_html()
    days = parse_schedule(html)
    print(f"Найдено дней с расписанием: {len(days)}")

    for day in get_latest_days(days, count=2):
        print(f"\n=== {day.schedule_date.strftime('%d.%m.%Y')} ({day.weekday}) ===")
        for shift in day.shifts:
            print(f"-- {shift.shift_number} смена, {shift.location}, дежурный: {shift.duty_teacher}")
            for group in shift.groups:
                print(f"  Группа {group.group}:")
                for lesson in group.lessons:
                    if lesson.is_empty:
                        continue
                    print(f"    {lesson.number}. {lesson.time} — {' / '.join(lesson.lines)}")


if __name__ == "__main__":
    main()
