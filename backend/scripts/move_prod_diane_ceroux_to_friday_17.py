from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import BOOKING_STATUSES_ACTIVE, _move_planning_reorganization_booking_occurrence
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location, SessionStatus
from app.models.notification_engine import DomainEvent
from app.models.user import User, UserRole


SCRIPT_PREFIX = "PROD_MOVE_DIANE_CEROUX_TO_FRIDAY_17"
FIRST_NAME = "diane"
LAST_NAME = "ceroux"
SEASON_START_LOCAL = datetime(2026, 9, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
SEASON_END_LOCAL = datetime(2027, 7, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
TARGET_WEEKDAY = 4  # Friday
TARGET_TIME = time(17, 0)
REPAIR_EVENT_TYPE = "booking_series_moved_by_admin_repair"


@dataclass(frozen=True)
class BookingRow:
    booking: Booking
    session: CourseSession
    course_type: CourseType
    location: Location


def _abort(reason: str) -> None:
    raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason={reason}")


def _safe_zoneinfo(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((value or "").strip() or "Europe/Paris")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")


def _local_start(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(_safe_zoneinfo(session_obj.timezone))


def _week_start(local_value: datetime) -> date:
    return local_value.date() - timedelta(days=local_value.weekday())


def _signature(session_obj: CourseSession) -> tuple[UUID, UUID, int, time]:
    local_value = _local_start(session_obj)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        local_value.weekday(),
        local_value.timetz().replace(tzinfo=None, second=0, microsecond=0),
    )


def _money_snapshot(booking: Booking) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    return (
        Decimal(booking.price_excl_vat_snapshot or 0),
        Decimal(booking.vat_rate_snapshot or 0),
        Decimal(booking.vat_amount_snapshot or 0),
        Decimal(booking.total_incl_vat_snapshot or 0),
        str(booking.currency_snapshot or "EUR").strip().upper(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move Diane Ceroux's 2026-2027 weekly bookings to Friday 17h at the same location."
    )
    parser.add_argument("--apply", action="store_true", help="Commit the guarded move. Without it, audit only.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return successfully when the production-only student is absent.",
    )
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    start_utc = SEASON_START_LOCAL.astimezone(timezone.utc)
    end_utc = SEASON_END_LOCAL.astimezone(timezone.utc)

    with SessionLocal() as db:
        students = db.scalars(
            select(User)
            .where(
                User.role == UserRole.CLIENT,
                func.lower(func.coalesce(User.first_name, "")) == FIRST_NAME,
                func.lower(func.coalesce(User.last_name, "")) == LAST_NAME,
            )
            .order_by(User.created_at.asc(), User.id.asc())
            .with_for_update()
        ).all()
        if not students and args.allow_missing:
            db.rollback()
            print(f"{SCRIPT_PREFIX}|summary|result=student_missing_noop|applied={args.apply}")
            return 0
        if len(students) != 1:
            _abort(f"expected_one_student_found_{len(students)}")
        student = students[0]

        rows = db.execute(
            select(Booking, CourseSession, CourseType, Location)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                Booking.user_id == student.id,
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= start_utc,
                CourseSession.start_at_utc < end_utc,
            )
            .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
            .with_for_update()
        ).all()
        booking_rows = [BookingRow(row[0], row[1], row[2], row[3]) for row in rows]
        if not booking_rows:
            _abort("student_has_no_active_season_booking")

        rows_by_signature: dict[tuple[UUID, UUID, int, time], list[BookingRow]] = {}
        for row in booking_rows:
            rows_by_signature.setdefault(_signature(row.session), []).append(row)
        recurring_groups = {
            signature: signature_rows
            for signature, signature_rows in rows_by_signature.items()
            if len(signature_rows) >= 10
        }
        for signature, signature_rows in sorted(rows_by_signature.items(), key=lambda item: str(item[0])):
            first = signature_rows[0]
            print(
                f"{SCRIPT_PREFIX}|source_candidate|count={len(signature_rows)}|"
                f"activity={first.course_type.name}|location={first.location.name}|"
                f"weekday={signature[2]}|time={signature[3].strftime('%H:%M')}"
            )
        if len(recurring_groups) != 1:
            _abort(f"expected_one_recurring_source_group_found_{len(recurring_groups)}")
        source_signature, source_rows = next(iter(recurring_groups.items()))
        source_course_type_id, source_location_id, source_weekday, source_time = source_signature
        if source_weekday == TARGET_WEEKDAY and source_time == TARGET_TIME:
            db.rollback()
            print(
                f"{SCRIPT_PREFIX}|summary|result=already_on_target|bookings={len(source_rows)}|"
                f"applied={args.apply}"
            )
            return 0

        target_candidates = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                CourseSession.course_type_id == source_course_type_id,
                CourseSession.location_id == source_location_id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= start_utc,
                CourseSession.start_at_utc < end_utc,
            )
            .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
            .with_for_update()
        ).all()
        friday_rows = [
            row
            for row in target_candidates
            if _local_start(row[0]).weekday() == TARGET_WEEKDAY
            and _local_start(row[0]).timetz().replace(tzinfo=None, second=0, microsecond=0) == TARGET_TIME
        ]
        targets_by_week: dict[date, list[CourseSession]] = {}
        for session_obj, _, _ in friday_rows:
            targets_by_week.setdefault(_week_start(_local_start(session_obj)), []).append(session_obj)

        source_by_week: dict[date, BookingRow] = {}
        for row in source_rows:
            week = _week_start(_local_start(row.session))
            if week in source_by_week:
                _abort(f"multiple_source_bookings_in_week_{week.isoformat()}")
            source_by_week[week] = row

        pairs: list[tuple[BookingRow, CourseSession]] = []
        for week, source_row in sorted(source_by_week.items()):
            week_targets = targets_by_week.get(week, [])
            if len(week_targets) != 1:
                _abort(f"expected_one_friday_17_target_in_week_{week.isoformat()}_found_{len(week_targets)}")
            target_session = week_targets[0]
            existing = db.scalar(
                select(Booking).where(
                    Booking.user_id == student.id,
                    Booking.session_id == target_session.id,
                )
            )
            if existing is not None and existing.id != source_row.booking.id:
                _abort(f"student_already_has_target_booking_in_week_{week.isoformat()}")
            pairs.append((source_row, target_session))

        if len(pairs) != len(source_rows):
            _abort("source_target_pair_count_mismatch")
        original_snapshots = {row.booking.id: _money_snapshot(row.booking) for row in source_rows}
        source_session_ids = [row.session.id for row in source_rows]
        target_session_ids = [target.id for _, target in pairs]
        if len(set(target_session_ids)) != len(target_session_ids):
            _abort("target_session_reused")

        sample_source = source_rows[0]
        sample_target = pairs[0][1]
        print(
            f"{SCRIPT_PREFIX}|audit|student={student.first_name} {student.last_name}|"
            f"bookings={len(source_rows)}|activity={sample_source.course_type.name}|"
            f"location={sample_source.location.name}|source_weekday={source_weekday}|"
            f"source_time={source_time.strftime('%H:%M')}|target_weekday={TARGET_WEEKDAY}|"
            f"target_time={TARGET_TIME.strftime('%H:%M')}|"
            f"first_target={_local_start(sample_target).isoformat()}|price_policy=keep_source"
        )

        moved_count = 0
        for source_row, target_session in pairs:
            moved, detail = _move_planning_reorganization_booking_occurrence(
                db,
                booking=source_row.booking,
                source_session=source_row.session,
                target_session=target_session,
                now=now,
                target_price_snapshot=None,
                lock_price_snapshot=True,
            )
            if not moved:
                _abort(f"move_rejected_{detail or 'unknown'}")
            if _money_snapshot(source_row.booking) != original_snapshots[source_row.booking.id]:
                _abort("price_snapshot_changed")
            moved_count += 1

        db.flush()
        remaining_source_count = int(
            db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.user_id == student.id,
                    Booking.session_id.in_(source_session_ids),
                    Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                )
            )
            or 0
        )
        moved_target_count = int(
            db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.user_id == student.id,
                    Booking.session_id.in_(target_session_ids),
                    Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                )
            )
            or 0
        )
        if remaining_source_count != 0 or moved_target_count != len(source_rows):
            _abort("post_move_booking_counts_invalid")

        db.add(
            DomainEvent(
                event_type=REPAIR_EVENT_TYPE,
                source="admin_repair",
                actor_type="system",
                actor_id=None,
                related_entity_type="student",
                related_entity_id=student.id,
                occurred_at=now,
                payload_json={
                    "student_id": str(student.id),
                    "source_session_ids": [str(session_id) for session_id in source_session_ids],
                    "target_session_ids": [str(session_id) for session_id in target_session_ids],
                    "moved_booking_ids": [str(row.booking.id) for row in source_rows],
                    "price_policy": "keep_source",
                    "price_changes": [],
                },
            )
        )
        db.flush()

        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(
            f"{SCRIPT_PREFIX}|summary|result=moved|moved_bookings={moved_count}|"
            f"student={student.first_name} {student.last_name}|price_changes=none|applied={args.apply}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
