from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Lesson:
    number: int
    time: str
    lines: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def subject(self) -> str | None:
        return self.lines[0] if self.lines else None

    @property
    def details(self) -> list[str]:
        return self.lines[1:]


@dataclass
class GroupSchedule:
    group: str
    lessons: list[Lesson] = field(default_factory=list)


@dataclass
class ShiftSchedule:
    shift_number: int
    location: str | None
    duty_teacher: str | None
    groups: list[GroupSchedule] = field(default_factory=list)

    def find_group(self, group: str) -> GroupSchedule | None:
        group_norm = group.strip().lower()
        for g in self.groups:
            if g.group.strip().lower() == group_norm:
                return g
        return None


@dataclass
class DaySchedule:
    schedule_date: date
    weekday: str
    shifts: list[ShiftSchedule] = field(default_factory=list)

    def find_group(self, group: str) -> GroupSchedule | None:
        for shift in self.shifts:
            found = shift.find_group(group)
            if found is not None:
                return found
        return None

    def find_group_with_shift(self, group: str) -> tuple[ShiftSchedule, GroupSchedule] | None:
        for shift in self.shifts:
            found = shift.find_group(group)
            if found is not None:
                return shift, found
        return None

    def all_group_names(self) -> list[str]:
        return [g.group for shift in self.shifts for g in shift.groups]


def day_to_dict(day: DaySchedule) -> dict:
    return {
        "schedule_date": day.schedule_date.isoformat(),
        "weekday": day.weekday,
        "shifts": [
            {
                "shift_number": shift.shift_number,
                "location": shift.location,
                "duty_teacher": shift.duty_teacher,
                "groups": [
                    {
                        "group": g.group,
                        "lessons": [
                            {"number": l.number, "time": l.time, "lines": l.lines}
                            for l in g.lessons
                        ],
                    }
                    for g in shift.groups
                ],
            }
            for shift in day.shifts
        ],
    }


def day_from_dict(data: dict) -> DaySchedule:
    return DaySchedule(
        schedule_date=date.fromisoformat(data["schedule_date"]),
        weekday=data["weekday"],
        shifts=[
            ShiftSchedule(
                shift_number=shift["shift_number"],
                location=shift["location"],
                duty_teacher=shift["duty_teacher"],
                groups=[
                    GroupSchedule(
                        group=g["group"],
                        lessons=[Lesson(**lesson) for lesson in g["lessons"]],
                    )
                    for g in shift["groups"]
                ],
            )
            for shift in data["shifts"]
        ],
    )
