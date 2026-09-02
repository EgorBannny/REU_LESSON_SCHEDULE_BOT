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
