"""Рендер расписания группы в виде красивой карточки-картинки (синяя тема).

Один и тот же шаблон карточки используется для обоих сценариев запроса:
- расписание одной выбранной группы -> одна картинка;
- расписание всех групп -> список картинок (по одной на группу), которые
  вызывающий код (бот) отправляет вместе, например альбомом.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import DaySchedule, GroupSchedule, ShiftSchedule

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"

_BG_TOP = (7, 12, 24)
_BG_BOTTOM = (11, 21, 42)
_ACCENT = (74, 144, 255)
_ACCENT_DIM = (43, 90, 168)
_CARD_BG = (13, 22, 42)
_CARD_BORDER = (35, 58, 102)
_TEXT_PRIMARY = (245, 247, 251)
_TEXT_SECONDARY = (137, 150, 179)
_TEXT_MUTED = (90, 102, 130)
_CHIP_BG = (19, 33, 61)
_DIVIDER = (28, 44, 74)

_WIDTH = 1200
_MARGIN = 64
_CARD_PAD = 44
_CHIP_W = 190
_CHIP_H = 78
_ROW_GAP = 26

_BOT_USERNAME_LINE = "t.me/REU_LESSON_SCHEDULE_BOT"
_LOCATION_LABEL = "Корпус «Спартаковская, 112»"

_RU_MONTHS_NOM = {
    1: "ЯНВАРЯ", 2: "ФЕВРАЛЯ", 3: "МАРТА", 4: "АПРЕЛЯ", 5: "МАЯ", 6: "ИЮНЯ",
    7: "ИЮЛЯ", 8: "АВГУСТА", 9: "СЕНТЯБРЯ", 10: "ОКТЯБРЯ", 11: "НОЯБРЯ", 12: "ДЕКАБРЯ",
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS_DIR / name), size)


def _f_bold(size: int) -> ImageFont.FreeTypeFont:
    return _font("DejaVuSans-Bold.ttf", size)


def _f_regular(size: int) -> ImageFont.FreeTypeFont:
    return _font("DejaVuSans.ttf", size)


def _f_mono(size: int) -> ImageFont.FreeTypeFont:
    return _font("DejaVuSansMono.ttf", size)


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int = 3
) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def _draw_vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    base = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.point((0, y), fill=color)
    return base.resize((width, height))


def _draw_house_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: tuple[int, int, int]) -> None:
    roof = [(x, y + size * 0.55), (x + size / 2, y), (x + size, y + size * 0.55)]
    draw.line(roof, fill=color, width=3, joint="curve")
    draw.rectangle(
        [x + size * 0.18, y + size * 0.5, x + size * 0.82, y + size], outline=color, width=3
    )


def _draw_dot_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: tuple[int, int, int]) -> None:
    draw.ellipse([x, y, x + size, y + size], fill=color)


def _measure_lesson_block_height(
    draw: ImageDraw.ImageDraw, group: GroupSchedule, content_width: int
) -> list[tuple[object, list[str], list[str]]]:
    """Возвращает для каждой непустой пары (lesson, subject_lines, detail_lines)."""
    subject_font = _f_bold(26)
    detail_font = _f_regular(19)
    text_width = content_width - _CHIP_W - 30
    blocks = []
    for lesson in group.lessons:
        if lesson.is_empty:
            continue
        subject = lesson.subject or ""
        subject_lines = _wrap_text(draw, subject, subject_font, text_width, max_lines=2)
        detail_text = " · ".join(lesson.details)
        detail_lines = _wrap_text(draw, detail_text, detail_font, text_width - 26, max_lines=1) if detail_text else []
        blocks.append((lesson, subject_lines, detail_lines))
    return blocks


def _build_group_image(day: DaySchedule, shift: ShiftSchedule, group: GroupSchedule) -> Image.Image:
    scratch_img = Image.new("RGB", (10, 10))
    scratch_draw = ImageDraw.Draw(scratch_img)
    content_width = _WIDTH - 2 * _MARGIN - 2 * _CARD_PAD
    blocks = _measure_lesson_block_height(scratch_draw, group, content_width)

    header_h = 210
    title_block_h = 130
    card_header_h = 130
    row_heights = []
    for _lesson, subject_lines, detail_lines in blocks:
        text_h = len(subject_lines) * 32 + (len(detail_lines) * 26 if detail_lines else 0)
        row_heights.append(max(_CHIP_H, text_h) + _ROW_GAP)
    lessons_h = sum(row_heights) if row_heights else 60
    footer_h = 100

    height = _MARGIN + header_h + title_block_h + _CARD_PAD + card_header_h + lessons_h + _CARD_PAD + footer_h

    img = _draw_vertical_gradient((_WIDTH, height), _BG_TOP, _BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    x = _MARGIN
    y = _MARGIN

    draw.text((x, y), "REU", font=_f_bold(40), fill=_TEXT_PRIMARY)
    reu_w = draw.textlength("REU", font=_f_bold(40))
    draw.text((x + reu_w, y), ".", font=_f_bold(40), fill=_ACCENT)
    dot_w = draw.textlength(".", font=_f_bold(40))
    draw.text((x + reu_w + dot_w, y), "Schedule", font=_f_bold(40), fill=_TEXT_PRIMARY)
    draw.text((x + 2, y + 54), "Р А С П И С А Н И Е   З А Н Я Т И Й", font=_f_regular(14), fill=_TEXT_SECONDARY)

    date_str = str(day.schedule_date.day)
    date_font = _f_bold(56)
    month_font = _f_regular(20)
    month_str = f"{_RU_MONTHS_NOM.get(day.schedule_date.month, '')} · {day.weekday.upper()}"
    date_w = draw.textlength(date_str, font=date_font)
    month_w = draw.textlength(month_str, font=month_font)
    total_w = date_w + 14 + month_w
    dx = _WIDTH - _MARGIN - total_w
    draw.text((dx, y - 6), date_str, font=date_font, fill=_ACCENT)
    draw.text((dx + date_w + 14, y + 18), month_str, font=month_font, fill=_TEXT_SECONDARY)

    divider_y = y + 100
    draw.line([(x, divider_y), (x + 90, divider_y)], fill=_ACCENT, width=4)
    draw.line([(x + 90, divider_y), (_WIDTH - _MARGIN, divider_y)], fill=_DIVIDER, width=2)

    ty = divider_y + 36
    draw.text((x, ty), "Расписание для вашей группы", font=_f_bold(38), fill=_TEXT_PRIMARY)
    ty += 58
    _draw_house_icon(draw, x + 2, ty + 4, 18, _ACCENT)
    draw.text((x + 30, ty), _LOCATION_LABEL, font=_f_regular(21), fill=_TEXT_SECONDARY)

    card_top = ty + 56
    card_bottom = card_top + card_header_h + lessons_h + _CARD_PAD
    draw.rounded_rectangle(
        [x, card_top, _WIDTH - _MARGIN, card_bottom],
        radius=26,
        fill=_CARD_BG,
        outline=_CARD_BORDER,
        width=2,
    )

    cx = x + _CARD_PAD
    cy = card_top + _CARD_PAD - 6
    draw.text((cx, cy), group.group, font=_f_bold(46), fill=_TEXT_PRIMARY)

    first_time = next((lesson.time for lesson in group.lessons if not lesson.is_empty), "")
    start_time = first_time.split("-")[0].replace(".", ":").strip() if first_time else "—"
    meta_label_font = _f_regular(15)
    meta_value_font = _f_bold(30)
    meta_lines = ["НАЧАЛО В", start_time, f"{shift.shift_number}-Я СМЕНА"]
    label_w = max(draw.textlength(s, font=meta_label_font) for s in (meta_lines[0], meta_lines[2]))
    value_w = draw.textlength(start_time, font=meta_value_font)
    meta_w = max(label_w, value_w)
    mx = _WIDTH - _MARGIN - _CARD_PAD - meta_w
    my = card_top + _CARD_PAD - 10
    draw.text((mx + (meta_w - draw.textlength(meta_lines[0], font=meta_label_font)), my), meta_lines[0], font=meta_label_font, fill=_TEXT_MUTED)
    my += 22
    draw.text((mx + (meta_w - draw.textlength(start_time, font=meta_value_font)), my), start_time, font=meta_value_font, fill=_ACCENT)
    my += 40
    draw.text((mx + (meta_w - draw.textlength(meta_lines[2], font=meta_label_font)), my), meta_lines[2], font=meta_label_font, fill=_TEXT_MUTED)

    row_y = card_top + card_header_h
    draw.line([(cx, row_y), (_WIDTH - _MARGIN - _CARD_PAD, row_y)], fill=_DIVIDER, width=2)
    row_y += 24

    chip_label_font = _f_regular(14)
    chip_time_font = _f_bold(19)
    subject_font = _f_bold(26)
    detail_font = _f_regular(19)

    for (lesson, subject_lines, detail_lines), row_h in zip(blocks, row_heights):
        chip_y = row_y
        draw.rounded_rectangle(
            [cx, chip_y, cx + _CHIP_W - 24, chip_y + _CHIP_H],
            radius=16,
            fill=_CHIP_BG,
            outline=_ACCENT_DIM,
            width=2,
        )
        label = f"{lesson.number}-Я ПАРА"
        draw.text(
            (cx + (_CHIP_W - 24) / 2 - draw.textlength(label, font=chip_label_font) / 2, chip_y + 14),
            label,
            font=chip_label_font,
            fill=_ACCENT,
        )
        time_label = lesson.time.replace(" ", "")
        draw.text(
            (cx + (_CHIP_W - 24) / 2 - draw.textlength(time_label, font=chip_time_font) / 2, chip_y + 38),
            time_label,
            font=chip_time_font,
            fill=_TEXT_PRIMARY,
        )

        text_x = cx + _CHIP_W
        text_y = row_y
        for line in subject_lines:
            draw.text((text_x, text_y), line, font=subject_font, fill=_TEXT_PRIMARY)
            text_y += 32
        if detail_lines:
            _draw_dot_icon(draw, text_x + 3, text_y + 8, 6, _ACCENT)
            draw.text((text_x + 20, text_y), detail_lines[0], font=detail_font, fill=_TEXT_SECONDARY)

        row_y += row_h

    footer_y = card_bottom + 34
    draw.line([(_MARGIN, footer_y), (_WIDTH - _MARGIN, footer_y)], fill=_DIVIDER, width=2)
    footer_text = _BOT_USERNAME_LINE
    footer_font = _f_mono(17)
    draw.text(
        ((_WIDTH - draw.textlength(footer_text, font=footer_font)) / 2, footer_y + 24),
        footer_text,
        font=footer_font,
        fill=_TEXT_SECONDARY,
    )

    return img


def render_group_card(
    day: DaySchedule,
    shift: ShiftSchedule,
    group: GroupSchedule,
    out_path: str | Path,
) -> Path:
    """Рендерит одну карточку расписания группы и сохраняет её как PNG."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _build_group_image(day, shift, group).save(out_path, "PNG")
    return out_path


def render_group_card_bytes(day: DaySchedule, shift: ShiftSchedule, group: GroupSchedule) -> bytes:
    """Рендерит карточку расписания группы и возвращает PNG в виде байтов (для отправки в Telegram)."""
    buf = BytesIO()
    _build_group_image(day, shift, group).save(buf, "PNG")
    return buf.getvalue()


def render_all_group_cards(day: DaySchedule, out_dir: str | Path) -> list[Path]:
    """Рендерит по одной карточке на каждую группу этого дня и сохраняет их как PNG."""
    out_dir = Path(out_dir)
    paths: list[Path] = []
    for shift in day.shifts:
        for group in shift.groups:
            safe_name = group.group.replace("/", "-")
            path = out_dir / f"{day.schedule_date.isoformat()}_{shift.shift_number}_{safe_name}.png"
            paths.append(render_group_card(day, shift, group, path))
    return paths


def render_all_group_cards_bytes(day: DaySchedule) -> list[tuple[str, bytes]]:
    """Рендерит карточки всех групп этого дня в память: [(название группы, PNG-байты), ...]."""
    result: list[tuple[str, bytes]] = []
    for shift in day.shifts:
        for group in shift.groups:
            result.append((group.group, render_group_card_bytes(day, shift, group)))
    return result
