from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_LOCAL_TIMEZONE = "Europe/Paris"


def resolve_timezone_name(
    *candidates: str | None,
    default: str = DEFAULT_LOCAL_TIMEZONE,
) -> str:
    for raw_candidate in (*candidates, default):
        candidate = (raw_candidate or "").strip()
        if not candidate:
            continue
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
        return candidate
    return DEFAULT_LOCAL_TIMEZONE


def localize_datetime(
    value: datetime,
    *timezone_candidates: str | None,
) -> tuple[datetime, str]:
    timezone_name = resolve_timezone_name(*timezone_candidates)
    aware_value = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware_value.astimezone(ZoneInfo(timezone_name)), timezone_name
