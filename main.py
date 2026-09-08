"""Демо парсера и рендера без БД и без Telegram — быстрый способ проверить

разбор расписания и внешний вид карточек локально.

Запуск: uv run main.py
Реальный сервис — это poller.py (наполняет БД) + bot.py (Telegram-бот),
оба работают через общий PostgreSQL (см. docker-compose.yml).
"""

from pathlib import Path

from schedule_bot import BOT_NAME, __version__
from schedule_bot.render import render_all_group_cards, render_group_card
from schedule_bot.scraper import fetch_html, get_latest_days, parse_schedule

DEMO_GROUP = "Б-111"
RENDERS_DIR = Path(__file__).parent / "renders"


def main() -> None:
    print(f"{BOT_NAME} v{__version__} — демо парсера/рендера")

    html = fetch_html()
    days = parse_schedule(html)
    print(f"Найдено дней с расписанием: {len(days)}")

    latest = get_latest_days(days, count=2)
    for day in latest:
        print(f"  {day.schedule_date} ({day.weekday})")

    if not latest:
        return
    latest_day = latest[-1]

    found = latest_day.find_group_with_shift(DEMO_GROUP)
    if found:
        shift, group = found
        path = render_group_card(latest_day, shift, group, RENDERS_DIR / f"{DEMO_GROUP}.png")
        print(f"Карточка группы {DEMO_GROUP}: {path}")

    all_paths = render_all_group_cards(latest_day, RENDERS_DIR / "all")
    print(f"Карточки всех групп ({len(all_paths)} шт.) в: {RENDERS_DIR / 'all'}")


if __name__ == "__main__":
    main()
