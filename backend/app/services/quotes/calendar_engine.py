from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable
from uuid import UUID


@dataclass(frozen=True)
class CalendarGenerationInput:
    start_date: date
    end_date: date
    weekdays: list[int]
    start_time: time
    end_time: time
    recurrence_frequency: str = "weekly"
    activity_id: UUID | None = None
    location_id: UUID | None = None
    modality: str | None = None
    holiday_dates: list[date] | None = None
    closure_dates: list[date] | None = None


def _normalize_weekdays(weekdays: Iterable[int]) -> set[int]:
    out: set[int] = set()
    for weekday in weekdays:
        if 0 <= int(weekday) <= 6:
            out.add(int(weekday))
    return out


def _iso_date(value: date) -> str:
    return value.isoformat()


def _iso_time(value: time) -> str:
    return value.strftime("%H:%M")


def _normalize_recurrence(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"weekly", "biweekly", "monthly"}:
        return normalized
    return "weekly"


def generate_calendar_snapshot(payload: CalendarGenerationInput) -> dict[str, object]:
    if payload.end_date < payload.start_date:
        raise ValueError("end_date must be greater than or equal to start_date")
    weekdays = _normalize_weekdays(payload.weekdays)
    if not weekdays:
        raise ValueError("weekdays must contain at least one value between 0 and 6")
    if payload.end_time <= payload.start_time:
        raise ValueError("end_time must be greater than start_time")

    holiday_dates = {item for item in (payload.holiday_dates or [])}
    closure_dates = {item for item in (payload.closure_dates or [])}
    recurrence = _normalize_recurrence(payload.recurrence_frequency)

    candidate_days: list[date] = []
    current = payload.start_date
    while current <= payload.end_date:
        if current.weekday() in weekdays and current not in holiday_dates and current not in closure_dates:
            candidate_days.append(current)
        current += timedelta(days=1)

    selected_days: list[date] = []
    if recurrence == "weekly":
        selected_days = candidate_days
    elif recurrence == "biweekly":
        first_by_weekday: dict[int, date] = {}
        for day in candidate_days:
            weekday = day.weekday()
            first = first_by_weekday.get(weekday)
            if first is None:
                first_by_weekday[weekday] = day
                selected_days.append(day)
                continue
            delta_days = (day - first).days
            if delta_days % 14 == 0:
                selected_days.append(day)
    else:  # monthly
        seen_month_by_weekday: set[tuple[int, int, int]] = set()
        for day in candidate_days:
            key = (day.year, day.month, day.weekday())
            if key in seen_month_by_weekday:
                continue
            seen_month_by_weekday.add(key)
            selected_days.append(day)

    sessions: list[dict[str, object]] = []
    for day in selected_days:
        start_at = datetime.combine(day, payload.start_time)
        end_at = datetime.combine(day, payload.end_time)
        duration_minutes = int((end_at - start_at).total_seconds() // 60)
        sessions.append(
            {
                "date": _iso_date(day),
                "start_time": _iso_time(payload.start_time),
                "end_time": _iso_time(payload.end_time),
                "duration_minutes": duration_minutes,
                "activity_id": str(payload.activity_id) if payload.activity_id is not None else None,
                "location_id": str(payload.location_id) if payload.location_id is not None else None,
                "modality": payload.modality,
            }
        )

    return {
        "start_date": _iso_date(payload.start_date),
        "end_date": _iso_date(payload.end_date),
        "weekdays": sorted(weekdays),
        "recurrence_frequency": recurrence,
        "start_time": _iso_time(payload.start_time),
        "end_time": _iso_time(payload.end_time),
        "holiday_dates": sorted(_iso_date(value) for value in holiday_dates),
        "closure_dates": sorted(_iso_date(value) for value in closure_dates),
        "sessions": sessions,
        "sessions_count": len(sessions),
    }
