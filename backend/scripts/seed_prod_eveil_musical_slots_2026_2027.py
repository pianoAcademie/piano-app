from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.admin import (
    _has_vacation_on_day,
    _is_blocked_by_school_calendar,
    _recurrence_datetimes_until,
    _serialize_recurrence_rule,
    _utc_from_local_wall_clock,
)
from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, DeliveryMode, Location, SessionStatus
from app.services.invoice_documents import normalize_billing_entity

SEED_PREFIX = "PROD_EVEIL_MUSICAL_2026_2027"
DATE_START = date(2026, 9, 23)
DATE_END = date(2027, 6, 20)


@dataclass(frozen=True)
class SeriesDefinition:
    key: str
    location_code: str
    weekday: int
    hour: int
    minute: int = 0


def _stable_uuid(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"piano-academie:{SEED_PREFIX}:{name}")


def _first_occurrence_on_or_after(start_date: date, weekday: int) -> date:
    return start_date + timedelta(days=(weekday - start_date.weekday()) % 7)


def _start_of_utc_day(value: datetime) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _session_marker(series_key: str, occurrence_day: date, *, hour: int, minute: int) -> str:
    return f"{SEED_PREFIX}|{series_key}|{occurrence_day.isoformat()}|{hour:02d}:{minute:02d}"


def _slot_signature(definition: SeriesDefinition) -> tuple[str, int, int, int]:
    return (definition.location_code, definition.weekday, definition.hour, definition.minute)


def _build_series_definitions() -> list[SeriesDefinition]:
    return [
        SeriesDefinition(key="eveil-pompe-wed-10", location_code="POMPE", weekday=2, hour=10),
        SeriesDefinition(key="eveil-pompe-wed-16", location_code="POMPE", weekday=2, hour=16),
        SeriesDefinition(key="eveil-pompe-sat-10", location_code="POMPE", weekday=5, hour=10),
        SeriesDefinition(key="eveil-assas-wed-16", location_code="ASSAS", weekday=2, hour=16),
        SeriesDefinition(key="eveil-assas-sat-10", location_code="ASSAS", weekday=5, hour=10),
        SeriesDefinition(key="eveil-richelieu-wed-16", location_code="RICHELIEU", weekday=2, hour=16),
        SeriesDefinition(key="eveil-richelieu-sat-10", location_code="RICHELIEU", weekday=5, hour=10),
    ]


def _course_type_haystack(course_type: CourseType) -> str:
    return " ".join(
        [
            str(course_type.code or ""),
            str(course_type.service_code or ""),
            str(course_type.name or ""),
            str(course_type.description or ""),
        ]
    ).strip().lower()


def _resolve_course_type(db) -> CourseType:
    rows = db.scalars(
        select(CourseType).where(
            CourseType.active.is_(True),
            CourseType.mode == DeliveryMode.ONSITE,
            CourseType.allows_student_bookings.is_(True),
        )
    ).all()
    matches = [row for row in rows if "eveil" in _course_type_haystack(row) and "demo" not in _course_type_haystack(row)]
    if len(matches) == 1:
        return matches[0]

    preferred = [
        row
        for row in matches
        if row.code == "EVEIL_MUSICAL"
        or row.service_code == "EVEIL_MUSICAL"
        or str(row.name or "").strip().lower() == "eveil musical"
    ]
    if len(preferred) == 1:
        return preferred[0]

    if not matches:
        raise RuntimeError("No active onsite course type found for eveil musical.")

    candidates = ", ".join(f"{row.code}|{row.service_code}|{row.name}" for row in matches)
    raise RuntimeError(f"Ambiguous active onsite course types for eveil musical: {candidates}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed recurring private eveil musical onsite slots for the 2026-2027 season."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing slots to the database. Without this flag the script runs in dry-run mode.",
    )
    args = parser.parse_args()

    definitions = _build_series_definitions()
    desired_parallel_counts = Counter(_slot_signature(definition) for definition in definitions)

    with SessionLocal() as db:
        course_type = _resolve_course_type(db)
        course_type_summary = f"{course_type.code}|{course_type.service_code}|{course_type.name}"
        course_type_default_capacity = int(course_type.default_capacity)

        if int(course_type.duration_minutes or 0) <= 0:
            raise RuntimeError(f"Invalid duration for course type {course_type.code}: {course_type.duration_minutes}")
        if int(course_type.default_capacity or 0) <= 0:
            raise RuntimeError(f"Invalid default capacity for course type {course_type.code}: {course_type.default_capacity}")

        location_codes = sorted({definition.location_code for definition in definitions})
        location_rows = db.scalars(select(Location).where(Location.code.in_(location_codes), Location.active.is_(True))).all()
        locations = {location.code: location for location in location_rows}
        missing_locations = [code for code in location_codes if code not in locations]
        if missing_locations:
            raise RuntimeError(f"Missing active locations: {', '.join(missing_locations)}")

        summary = Counter()
        created_by_location = Counter()
        covered_by_location = Counter()
        calendar_skip_cache: dict[str, object] = {}

        recurrence_rule = _serialize_recurrence_rule(
            frequency="WEEKLY",
            interval=1,
            time_basis="LOCAL",
        )

        for definition in definitions:
            location = locations[definition.location_code]
            session_timezone = location.timezone or "Europe/Paris"
            local_anchor_day = _first_occurrence_on_or_after(DATE_START, definition.weekday)
            local_anchor = datetime(
                local_anchor_day.year,
                local_anchor_day.month,
                local_anchor_day.day,
                definition.hour,
                definition.minute,
            )
            anchor_start_at_utc = _utc_from_local_wall_clock(local_anchor, timezone_name=session_timezone)
            recurrence_group_id = _stable_uuid(definition.key)
            occurrence_starts = _recurrence_datetimes_until(
                anchor_start_at_utc=anchor_start_at_utc,
                recurrence_frequency="WEEKLY",
                recurrence_interval=1,
                recurrence_until_date=DATE_END,
                session_timezone=session_timezone,
                recurrence_time_basis="LOCAL",
                limit=200,
            )

            for start_at_utc in occurrence_starts:
                day_start_utc = _start_of_utc_day(start_at_utc)
                if _has_vacation_on_day(db, location_id=location.id, day_start_utc=day_start_utc):
                    summary["skipped_location_vacation"] += 1
                    continue
                if _is_blocked_by_school_calendar(
                    db,
                    location_id=location.id,
                    location_timezone=location.timezone,
                    starts_at_utc=start_at_utc,
                    include_holidays=bool(course_type.exclude_holidays_in_recurrence),
                    include_school_vacations=bool(course_type.exclude_school_vacations_in_recurrence),
                    cache=calendar_skip_cache,
                ):
                    summary["skipped_school_calendar"] += 1
                    continue

                local_day = start_at_utc.astimezone(ZoneInfo(session_timezone)).date()
                marker = _session_marker(
                    definition.key,
                    local_day,
                    hour=definition.hour,
                    minute=definition.minute,
                )
                target = db.scalar(
                    select(CourseSession).where(CourseSession.private_description == marker).limit(1)
                )
                if target is not None:
                    summary["already_managed"] += 1
                    continue

                end_at_utc = start_at_utc + timedelta(minutes=int(course_type.duration_minutes))
                same_slot_sessions = db.scalars(
                    select(CourseSession).where(
                        CourseSession.location_id == location.id,
                        CourseSession.course_type_id == course_type.id,
                        CourseSession.start_at_utc == start_at_utc,
                        CourseSession.end_at_utc == end_at_utc,
                    )
                ).all()

                allowed_parallel = desired_parallel_counts[_slot_signature(definition)]
                if len(same_slot_sessions) >= allowed_parallel:
                    summary["already_covered"] += 1
                    covered_by_location[location.code] += 1
                    continue

                session_obj = CourseSession(
                    course_type_id=course_type.id,
                    billing_entity_snapshot=normalize_billing_entity(course_type.billing_entity_code),
                    snapshot_seller_legal_entity_id=course_type.seller_legal_entity_id,
                    snapshot_payor_legal_entity_id=course_type.payor_legal_entity_id,
                    location_id=location.id,
                    professor_id=None,
                    title=course_type.name,
                    description="Prod recurring eveil musical slot 2026-2027",
                    private_description=marker,
                    start_at_utc=start_at_utc,
                    end_at_utc=end_at_utc,
                    is_all_day=False,
                    capacity_max=int(course_type.default_capacity),
                    status=SessionStatus.SCHEDULED,
                    auto_cancel_deadline_utc=start_at_utc - timedelta(hours=12),
                    cancel_reason=None,
                    zoom_link=None,
                    is_private=True,
                    allow_online_booking=False,
                    timezone=session_timezone,
                    recurrence_group_id=recurrence_group_id,
                    recurrence_rule=recurrence_rule,
                    recurrence_until_date=DATE_END,
                )
                if args.apply:
                    db.add(session_obj)
                    summary["created"] += 1
                else:
                    summary["planned_creates"] += 1
                created_by_location[location.code] += 1

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode_label = "APPLY" if args.apply else "DRY_RUN"
    print(f"[{SEED_PREFIX}] mode={mode_label}")
    print(f"[{SEED_PREFIX}] course_type={course_type_summary}")
    print(f"[{SEED_PREFIX}] default_capacity={course_type_default_capacity}")
    print(f"[{SEED_PREFIX}] series={len(definitions)}")
    print(f"[{SEED_PREFIX}] planned_creates={summary['planned_creates']}")
    print(f"[{SEED_PREFIX}] created={summary['created']}")
    print(f"[{SEED_PREFIX}] already_managed={summary['already_managed']}")
    print(f"[{SEED_PREFIX}] already_covered={summary['already_covered']}")
    print(f"[{SEED_PREFIX}] skipped_location_vacation={summary['skipped_location_vacation']}")
    print(f"[{SEED_PREFIX}] skipped_school_calendar={summary['skipped_school_calendar']}")
    for location_code in sorted(created_by_location):
        print(
            f"[{SEED_PREFIX}] location={location_code} "
            f"to_create={created_by_location[location_code]} "
            f"already_covered={covered_by_location[location_code]}"
        )


if __name__ == "__main__":
    main()
