"""Демо Фаз 1-2: кэш расписания в SQLite + рендер картинок-карточек.

Запуск: uv run main.py
"""

from pathlib import Path

from schedule_bot import BOT_NAME, __version__
from schedule_bot.render import render_all_group_cards, render_group_card
from schedule_bot.storage import connect, get_latest_days, refresh_from_source

DEMO_GROUP = "Б-111"
RENDERS_DIR = Path(__file__).parent / "renders"


def main() -> None:
    print(f"{BOT_NAME} v{__version__} — демо")

    conn = connect()
    changed = refresh_from_source(conn)
    if changed:
        print(f"Обновились/появились даты: {', '.join(d.isoformat() for d in changed)}")
    else:
        print("Новых данных нет, кэш уже актуален")

    days = get_latest_days(conn, count=2)
    print(f"В кэше последние {len(days)} дня(ей) с расписанием:")
    for day in days:
        print(f"  {day.schedule_date} ({day.weekday})")

    if not days:
        return
    latest = days[-1]

    found = latest.find_group_with_shift(DEMO_GROUP)
    if found:
        shift, group = found
        path = render_group_card(latest, shift, group, RENDERS_DIR / f"{DEMO_GROUP}.png")
        print(f"Карточка группы {DEMO_GROUP}: {path}")

    all_paths = render_all_group_cards(latest, RENDERS_DIR / "all")
    print(f"Карточки всех групп ({len(all_paths)} шт.) в: {RENDERS_DIR / 'all'}")


if __name__ == "__main__":
    main()
