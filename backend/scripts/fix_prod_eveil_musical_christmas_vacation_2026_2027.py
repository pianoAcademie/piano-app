from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus

SCRIPT_PREFIX = "PROD_REPAIR_ONLINE_CHILD_PIANO_MISSING_SESSIONS"
COURSE_NAME = "Cours de piano collectif en ligne - enfants (1h)"
LOCATION_CODE = "ONLINE"
TARGET_DATES = (date(2027, 3, 30), date(2027, 5, 18))
START_TIME = time(18, 0)
END_TIME = time(19, 0)


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _session_local_time(session_obj: CourseSession) -> tuple[date, time, time]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start_local = session_obj.start_at_utc.astimezone(tz)
    end_local = session_obj.end_at_utc.astimezone(tz)
    return start_local.date(), start_local.time().replace(tzinfo=None), end_local.time().replace(tzinfo=None)


def _target_bounds(target_date: date, timezone_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name or "Europe/Paris")
    start_local = datetime.combine(target_date, START_TIME, tzinfo=tz)
    end_local = datetime.combine(target_date, END_TIME, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _nearest_template(sessions: list[CourseSession], target_date: date) -> CourseSession | None:
    eligible: list[CourseSession] = []
    for session_obj in sessions:
        local_date, local_start, local_end = _session_local_time(session_obj)
        if local_date.weekday() == target_date.weekday() and local_start == START_TIME and local_end == END_TIME:
            eligible.append(session_obj)
    if not eligible:
        return None
    return min(eligible, key=lambda session_obj: abs((_session_local_time(session_obj)[0] - target_date).days))


def _copy_session(template: CourseSession, *, start_utc: datetime, end_utc: datetime, target_date: date) -> CourseSession:
    deadline_delta = template.start_at_utc - template.auto_cancel_deadline_utc
    if deadline_delta.total_seconds() <= 0:
        deadline_delta = template.end_at_utc - template.start_at_utc
    return CourseSession(
        course_type_id=template.course_type_id,
        billing_entity_snapshot=template.billing_entity_snapshot,
        snapshot_seller_legal_entity_id=template.snapshot_seller_legal_entity_id,
        snapshot_payor_legal_entity_id=template.snapshot_payor_legal_entity_id,
        location_id=template.location_id,
        professor_id=template.professor_id,
        substitute_teacher_id=template.substitute_teacher_id,
        substitute_set_at=template.substitute_set_at,
        substitute_set_by=template.substitute_set_by,
        substitute_note=template.substitute_note,
        title=template.title,
        description=template.description,
        private_description=template.private_description,
        group_note=template.group_note,
        professor_reminder_note=template.professor_reminder_note,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        is_all_day=template.is_all_day,
        capacity_max=template.capacity_max,
        status=SessionStatus.SCHEDULED,
        auto_cancel_deadline_utc=start_utc - deadline_delta,
        cancel_reason=None,
        zoom_link=template.zoom_link,
        is_private=template.is_private,
        allow_online_booking=template.allow_online_booking,
        visibility_scope=template.visibility_scope,
        booking_scope=template.booking_scope,
        external_booking_price_ttc=template.external_booking_price_ttc,
        show_external_remaining_seats=template.show_external_remaining_seats,
        timezone=template.timezone,
        recurrence_group_id=template.recurrence_group_id,
        recurrence_rule=template.recurrence_rule,
        recurrence_until_date=max(template.recurrence_until_date or target_date, target_date),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create the two missing sessions. Without it, only prints a dry-run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        course = db.scalar(select(CourseType).where(CourseType.name == COURSE_NAME).limit(1))
        location = db.scalar(select(Location).where(Location.code == LOCATION_CODE).limit(1))
        if course is None or location is None:
            raise RuntimeError(f"Missing course or location: course={bool(course)} location={bool(location)}")

        sessions = db.scalars(
            select(CourseSession)
            .where(
                CourseSession.course_type_id == course.id,
                CourseSession.location_id == location.id,
                CourseSession.status != SessionStatus.CANCELLED,
                CourseSession.start_at_utc >= datetime(2026, 9, 1, tzinfo=timezone.utc),
                CourseSession.start_at_utc < datetime(2027, 7, 1, tzinfo=timezone.utc),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()

        created = 0
        already_present = 0
        missing_template = 0
        created_dates: list[str] = []

        for target_date in TARGET_DATES:
            template = _nearest_template(sessions, target_date)
            timezone_name = template.timezone if template is not None else location.timezone
            start_utc, end_utc = _target_bounds(target_date, timezone_name)
            existing = db.scalar(
                select(CourseSession.id)
                .where(
                    CourseSession.course_type_id == course.id,
                    CourseSession.location_id == location.id,
                    CourseSession.status != SessionStatus.CANCELLED,
                    CourseSession.start_at_utc == start_utc,
                    CourseSession.end_at_utc == end_utc,
                )
                .limit(1)
            )
            if existing is not None:
                already_present += 1
                _print(f"already_present date={target_date.isoformat()}|session={existing}")
                continue
            if template is None:
                missing_template += 1
                _print(f"missing_template date={target_date.isoformat()}")
                continue

            local_template_date, _, _ = _session_local_time(template)
            _print(
                "create_session "
                f"date={target_date.isoformat()}|template={template.id}|template_date={local_template_date.isoformat()}|"
                f"start_utc={start_utc.isoformat()}|end_utc={end_utc.isoformat()}|apply={args.apply}"
            )
            if args.apply:
                session_obj = _copy_session(template, start_utc=start_utc, end_utc=end_utc, target_date=target_date)
                db.add(session_obj)
                db.flush()
                sessions.append(session_obj)
                created_dates.append(target_date.isoformat())
            created += 1

        if args.apply:
            db.commit()
        else:
            db.rollback()

        summary = (
            f"apply={args.apply}|course={course.id}|location={location.id}|created={created if args.apply else 0}|"
            f"would_create={created}|already_present={already_present}|missing_template={missing_template}|"
            f"created_dates={','.join(created_dates) or '-'}"
        )
        _print(f"summary {summary}")
        print(f"::notice title=Online child piano missing sessions::{summary}")


if __name__ == "__main__":
    main()
