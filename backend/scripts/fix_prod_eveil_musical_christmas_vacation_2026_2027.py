from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import (
    _calendar_closure_dates,
    _calendar_vacation_dates,
    _has_vacation_on_day,
    _is_blocked_by_school_calendar,
    _select_school_calendar_for_day,
)
from app.api.routes.quotes import (
    _load_quote_school_calendars,
    _save_quote_school_calendars,
    _sync_deployed_status_after_payload_change,
)
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, Location

SCRIPT_PREFIX = "PROD_EVEIL_MUSICAL_CHRISTMAS_FIX_2026_2027"
SEED_PREFIX = "PROD_EVEIL_MUSICAL_2026_2027"
TARGET_LOCATION_CODES = ("POMPE", "ASSAS", "RICHELIEU")
TARGET_START = date(2026, 12, 20)
TARGET_END = date(2027, 1, 3)
TARGET_SCHOOL_YEAR = "2026-2027"
TARGET_LABEL = "Vacances de Noel 2026"


def _iter_days(start_day: date, end_day: date) -> list[date]:
    out: list[date] = []
    current = start_day
    while current <= end_day:
        out.append(current)
        current += timedelta(days=1)
    return out


def _local_day(value: datetime, timezone_name: str) -> date:
    try:
        return value.astimezone(ZoneInfo(timezone_name)).date()
    except Exception:
        return value.date()


def _start_of_utc_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _parsed_periods(raw: dict[str, object]) -> list[tuple[date, date, str | None]]:
    values = raw.get("vacation_periods")
    if not isinstance(values, list):
        return []
    out: list[tuple[date, date, str | None]] = []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        start_raw = str(entry.get("start_date") or "").strip()
        end_raw = str(entry.get("end_date") or "").strip()
        if not start_raw or not end_raw:
            continue
        try:
            start_day = date.fromisoformat(start_raw)
            end_day = date.fromisoformat(end_raw)
        except Exception:
            continue
        if end_day < start_day:
            continue
        label = str(entry.get("label") or "").strip() or None
        out.append((start_day, end_day, label))
    return out


def _merged_period_dicts(periods: list[tuple[date, date, str | None]]) -> list[dict[str, str | None]]:
    if not periods:
        return []
    ordered = sorted(periods, key=lambda item: (item[0], item[1], item[2] or ""))
    merged: list[tuple[date, date, str | None]] = []
    current_start, current_end, current_label = ordered[0]
    for start_day, end_day, label in ordered[1:]:
        if start_day <= current_end + timedelta(days=1):
            if end_day > current_end:
                current_end = end_day
            if current_label != label:
                current_label = current_label or label
            continue
        merged.append((current_start, current_end, current_label))
        current_start, current_end, current_label = start_day, end_day, label
    merged.append((current_start, current_end, current_label))
    return [
        {
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "label": label,
        }
        for start_day, end_day, label in merged
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fix prod eveil musical Christmas 2026 vacation slots by correcting the school calendar "
            "for Paris locations and removing seeded slots that fall on blocked days."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the calendar and slot updates to the database. Without this flag the script runs in dry-run mode.",
    )
    args = parser.parse_args()

    target_days = set(_iter_days(TARGET_START, TARGET_END))

    with SessionLocal() as db:
        locations = db.scalars(
            select(Location).where(Location.code.in_(TARGET_LOCATION_CODES), Location.active.is_(True))
        ).all()
        location_by_code = {row.code: row for row in locations}
        missing_locations = [code for code in TARGET_LOCATION_CODES if code not in location_by_code]
        if missing_locations:
            raise RuntimeError(f"Missing active locations: {', '.join(missing_locations)}")

        rows = _load_quote_school_calendars(db)
        summary = Counter()
        calendar_updates_by_location = Counter()
        deleted_by_location = Counter()
        blocked_with_bookings: list[str] = []
        missing_calendars: list[str] = []
        deleted_samples: list[str] = []

        for location_code in TARGET_LOCATION_CODES:
            location = location_by_code[location_code]
            row = _select_school_calendar_for_day(rows, location_id=location.id, day=TARGET_START)
            if row is None:
                missing_calendars.append(location_code)
                continue
            school_year_label = str(row.get("school_year_label") or "").strip()
            if school_year_label != TARGET_SCHOOL_YEAR:
                raise RuntimeError(
                    f"Unexpected school year for {location_code}: {school_year_label or 'N/A'} "
                    f"(expected {TARGET_SCHOOL_YEAR})"
                )

            covered_days = _calendar_vacation_dates(row) | _calendar_closure_dates(row)
            if target_days.issubset(covered_days):
                summary["calendar_already_covered"] += 1
                continue

            old_row = dict(row)
            merged_periods = _merged_period_dicts(
                _parsed_periods(row) + [(TARGET_START, TARGET_END, TARGET_LABEL)]
            )
            row["vacation_periods"] = merged_periods
            row["updated_at"] = datetime.now(timezone.utc).isoformat()
            _sync_deployed_status_after_payload_change(old_row=old_row, new_row=row)
            summary["calendar_updated"] += 1
            calendar_updates_by_location[location_code] += 1

        if missing_calendars:
            raise RuntimeError(
                "Missing active school calendars for: " + ", ".join(sorted(missing_calendars))
            )

        if summary["calendar_updated"] > 0:
            _save_quote_school_calendars(db, rows)

        target_location_ids = [location_by_code[code].id for code in TARGET_LOCATION_CODES]
        sessions = db.scalars(
            select(CourseSession).where(
                CourseSession.location_id.in_(target_location_ids),
                CourseSession.private_description.is_not(None),
                CourseSession.private_description.like(f"{SEED_PREFIX}|%"),
            )
        ).all()

        booking_counts = (
            {
                session_id: int(total or 0)
                for session_id, total in db.execute(
                    select(Booking.session_id, func.count(Booking.id))
                    .where(Booking.session_id.in_([session.id for session in sessions]))
                    .group_by(Booking.session_id)
                ).all()
            }
            if sessions
            else {}
        )

        calendar_skip_cache: dict[str, object] = {}
        if summary["calendar_updated"] > 0:
            calendar_skip_cache["rows"] = rows

        for session in sessions:
            location = location_by_code.get(
                next(code for code in TARGET_LOCATION_CODES if location_by_code[code].id == session.location_id)
            )
            if location is None:
                continue
            timezone_name = session.timezone or location.timezone or "Europe/Paris"
            local_day = _local_day(session.start_at_utc, timezone_name)
            if local_day < TARGET_START or local_day > TARGET_END:
                continue

            day_start_utc = _start_of_utc_day(local_day)
            blocked = _has_vacation_on_day(db, location_id=location.id, day_start_utc=day_start_utc) or _is_blocked_by_school_calendar(
                db,
                location_id=location.id,
                location_timezone=timezone_name,
                starts_at_utc=session.start_at_utc,
                include_holidays=True,
                include_school_vacations=True,
                cache=calendar_skip_cache,
            )
            if not blocked:
                continue

            summary["matched_sessions"] += 1
            booking_count = booking_counts.get(session.id, 0)
            sample_line = (
                f"{location.code}|{local_day.isoformat()}|"
                f"{session.start_at_utc.astimezone(ZoneInfo(timezone_name)).strftime('%H:%M')}|{session.id}"
            )
            if booking_count > 0:
                summary["blocked_with_bookings"] += 1
                blocked_with_bookings.append(f"{sample_line}|bookings={booking_count}")
                continue

            if args.apply:
                db.delete(session)
                summary["deleted"] += 1
            else:
                summary["to_delete"] += 1
            deleted_by_location[location.code] += 1
            if len(deleted_samples) < 20:
                deleted_samples.append(sample_line)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode_label = "APPLY" if args.apply else "DRY_RUN"
    print(f"[{SCRIPT_PREFIX}] mode={mode_label}")
    print(f"[{SCRIPT_PREFIX}] target_start={TARGET_START.isoformat()}")
    print(f"[{SCRIPT_PREFIX}] target_end={TARGET_END.isoformat()}")
    print(f"[{SCRIPT_PREFIX}] calendar_updated={summary['calendar_updated']}")
    print(f"[{SCRIPT_PREFIX}] calendar_already_covered={summary['calendar_already_covered']}")
    print(f"[{SCRIPT_PREFIX}] matched_sessions={summary['matched_sessions']}")
    print(f"[{SCRIPT_PREFIX}] to_delete={summary['to_delete']}")
    print(f"[{SCRIPT_PREFIX}] deleted={summary['deleted']}")
    print(f"[{SCRIPT_PREFIX}] blocked_with_bookings={summary['blocked_with_bookings']}")
    for location_code in TARGET_LOCATION_CODES:
        print(
            f"[{SCRIPT_PREFIX}] location={location_code} "
            f"calendar_updates={calendar_updates_by_location[location_code]} "
            f"slot_candidates={deleted_by_location[location_code]}"
        )

    if deleted_samples:
        print(f"[{SCRIPT_PREFIX}] sample_count={len(deleted_samples)}")
        for line in deleted_samples:
            print(f"[{SCRIPT_PREFIX}] sample={line}")

    if blocked_with_bookings:
        print(f"[{SCRIPT_PREFIX}] booking_conflict_count={len(blocked_with_bookings)}")
        for line in blocked_with_bookings[:20]:
            print(f"[{SCRIPT_PREFIX}] booking_conflict={line}")


if __name__ == "__main__":
    main()
