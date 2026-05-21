from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.user import User, UserRole
from app.services.reminders import ensure_booking_reminder

SCRIPT_PREFIX = "PROD_REPAIR_AVENEL_WONG_POMPE_TUESDAY_BOOKINGS"
DEFAULT_TARGETS = (
    ("rose", "avenel"),
    ("tessa", "wong-wing-cheung"),
)
DEFAULT_LOCATION_NAME = "Rue de la Pompe"
DEFAULT_ACTIVITY_TOKEN = "piano"
DEFAULT_START_LOCAL = datetime(2026, 9, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
DEFAULT_END_LOCAL = datetime(2027, 6, 21, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))

ACTIVE_BOOKING_STATUSES = (
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)


@dataclass(frozen=True)
class BookingRow:
    booking: Booking
    session: CourseSession
    course_type: CourseType
    location: Location
    student: User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_zoneinfo(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((value or "").strip() or "Europe/Paris")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")


def _money(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _local_label(value: datetime, tz_name: str | None) -> str:
    local = value.astimezone(_safe_zoneinfo(tz_name))
    return local.strftime("%Y-%m-%d %H:%M")


def _display_name(user: User) -> str:
    return " ".join(part for part in [user.first_name, user.last_name] if part) or str(user.email or user.id)


def _session_signature(session_obj: CourseSession) -> tuple[UUID, UUID, int, time, time]:
    zone = _safe_zoneinfo(session_obj.timezone)
    local_start = session_obj.start_at_utc.astimezone(zone)
    local_end = session_obj.end_at_utc.astimezone(zone)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        local_start.weekday(),
        local_start.timetz().replace(tzinfo=None, second=0, microsecond=0),
        local_end.timetz().replace(tzinfo=None, second=0, microsecond=0),
    )


def _session_occurrence_key(session_obj: CourseSession) -> tuple[UUID, UUID, date, time, time]:
    zone = _safe_zoneinfo(session_obj.timezone)
    local_start = session_obj.start_at_utc.astimezone(zone)
    local_end = session_obj.end_at_utc.astimezone(zone)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        local_start.date(),
        local_start.timetz().replace(tzinfo=None, second=0, microsecond=0),
        local_end.timetz().replace(tzinfo=None, second=0, microsecond=0),
    )


def _parse_target(raw: str) -> tuple[str, str]:
    parts = [part.strip().casefold() for part in raw.split("|", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError("target must be formatted as first|last")
    return parts[0], parts[1]


def _find_student(db, first_name: str, last_name: str) -> User | None:
    rows = db.scalars(
        select(User)
        .where(
            User.role == UserRole.CLIENT,
            func.lower(func.coalesce(User.first_name, "")) == first_name,
            func.lower(func.coalesce(User.last_name, "")) == last_name,
        )
        .order_by(User.created_at.asc(), User.id.asc())
        .with_for_update()
    ).all()
    print(f"[{SCRIPT_PREFIX}] target={first_name}|{last_name}|matches={len(rows)}")
    for row in rows:
        print(
            f"[{SCRIPT_PREFIX}] student_match=id={row.id}|name={_display_name(row)}|"
            f"email={row.email or '-'}|status={getattr(row.client_status, 'value', row.client_status)}"
        )
    return rows[0] if len(rows) == 1 else None


def _load_source_bookings(
    db,
    *,
    student: User,
    start_utc: datetime,
    end_utc: datetime,
    location_name: str,
    activity_token: str,
) -> list[BookingRow]:
    rows = db.execute(
        select(Booking, CourseSession, CourseType, Location, User)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.user_id == student.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= start_utc,
            CourseSession.start_at_utc < end_utc,
            func.lower(Location.name) == location_name.casefold(),
            func.lower(CourseType.name).like(f"%{activity_token.casefold()}%"),
        )
        .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
        .with_for_update()
    ).all()
    return [BookingRow(booking=row[0], session=row[1], course_type=row[2], location=row[3], student=row[4]) for row in rows]


def _load_target_sessions(db, source_rows: list[BookingRow]) -> list[tuple[CourseSession, CourseType, Location]]:
    source_session = source_rows[0].session
    source_signature = _session_signature(source_session)
    source_start = min(row.session.start_at_utc for row in source_rows)
    recurrence_group_id = source_session.recurrence_group_id

    stmt = select(CourseSession, CourseType, Location).join(CourseType, CourseType.id == CourseSession.course_type_id).join(
        Location, Location.id == CourseSession.location_id
    )
    if recurrence_group_id:
        stmt = stmt.where(CourseSession.recurrence_group_id == recurrence_group_id)
    else:
        stmt = stmt.where(
            CourseSession.course_type_id == source_signature[0],
            CourseSession.location_id == source_signature[1],
        )

    rows = db.execute(
        stmt.where(
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= source_start,
        ).order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
    ).all()
    return [row for row in rows if _session_signature(row[0]) == source_signature]


def _load_existing_occurrences(db, *, student: User, target_rows: list[tuple[CourseSession, CourseType, Location]]) -> set[tuple[UUID, UUID, date, time, time]]:
    if not target_rows:
        return set()
    signatures = {_session_signature(session_obj) for session_obj, _, _ in target_rows}
    min_start = min(session_obj.start_at_utc for session_obj, _, _ in target_rows)
    max_start = max(session_obj.start_at_utc for session_obj, _, _ in target_rows)
    rows = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id == student.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= min_start,
            CourseSession.start_at_utc <= max_start,
        )
        .with_for_update()
    ).all()
    occurrences: set[tuple[UUID, UUID, date, time, time]] = set()
    for _, session_obj in rows:
        if _session_signature(session_obj) in signatures:
            occurrences.add(_session_occurrence_key(session_obj))
    return occurrences


def _count_booked(db, session_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count(Booking.id)).where(
                Booking.session_id == session_id,
                Booking.status.in_(
                    [
                        BookingStatus.BOOKED,
                        BookingStatus.PENDING_PAYMENT,
                        BookingStatus.ATTENDED,
                        BookingStatus.NO_SHOW,
                        BookingStatus.EXCUSED_ABSENCE,
                    ]
                ),
            )
        )
        or 0
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair missing Rose Avenel and Tessa Wong Pompe Tuesday bookings.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Without it, dry-run only.")
    parser.add_argument(
        "--target",
        action="append",
        type=_parse_target,
        help="Target student formatted as first|last. Defaults to Rose Avenel and Tessa Wong-Wing-Cheung.",
    )
    parser.add_argument("--location", default=DEFAULT_LOCATION_NAME)
    parser.add_argument("--activity-token", default=DEFAULT_ACTIVITY_TOKEN)
    args = parser.parse_args()

    targets = tuple(args.target or DEFAULT_TARGETS)
    now = _utcnow()
    start_utc = DEFAULT_START_LOCAL.astimezone(timezone.utc)
    end_utc = DEFAULT_END_LOCAL.astimezone(timezone.utc)
    summary: Counter[str] = Counter()

    with SessionLocal() as db:
        for first_name, last_name in targets:
            student = _find_student(db, first_name, last_name)
            if student is None:
                summary["ambiguous_or_missing_students"] += 1
                continue

            source_rows = _load_source_bookings(
                db,
                student=student,
                start_utc=start_utc,
                end_utc=end_utc,
                location_name=args.location,
                activity_token=args.activity_token,
            )
            print(f"[{SCRIPT_PREFIX}] source_bookings={len(source_rows)}|student={_display_name(student)}")
            for row in source_rows[:12]:
                print(
                    f"[{SCRIPT_PREFIX}] source=booking={row.booking.id}|session={row.session.id}|"
                    f"date={_local_label(row.session.start_at_utc, row.session.timezone)}|"
                    f"activity={row.course_type.name}|location={row.location.name}|"
                    f"subscription={row.booking.client_plan_subscription_id or '-'}|total={_money(row.booking.total_incl_vat_snapshot)}"
                )
            if not source_rows:
                summary["students_without_source_bookings"] += 1
                continue

            source_rows = [row for row in source_rows if _session_signature(row.session) == _session_signature(source_rows[0].session)]

            target_rows = _load_target_sessions(db, source_rows)
            target_ids = [session_obj.id for session_obj, _, _ in target_rows]
            existing_occurrences = _load_existing_occurrences(db, student=student, target_rows=target_rows)
            existing_by_session: dict[UUID, Booking] = {}
            if target_ids:
                existing_bookings = db.scalars(
                    select(Booking)
                    .where(Booking.user_id == student.id, Booking.session_id.in_(target_ids))
                    .with_for_update()
                ).all()
                existing_by_session = {booking.session_id: booking for booking in existing_bookings}

            source_booking = source_rows[0].booking
            missing_rows: list[tuple[CourseSession, CourseType, Location, Booking | None]] = []
            already_active = 0
            capacity_blocked = 0
            for session_obj, course_type, location in target_rows:
                existing = existing_by_session.get(session_obj.id)
                if existing is not None and existing.status in ACTIVE_BOOKING_STATUSES:
                    already_active += 1
                    continue
                if _session_occurrence_key(session_obj) in existing_occurrences:
                    already_active += 1
                    print(
                        f"[{SCRIPT_PREFIX}] skip_equivalent_existing|student={_display_name(student)}|"
                        f"session={session_obj.id}|date={_local_label(session_obj.start_at_utc, session_obj.timezone)}"
                    )
                    continue
                booked_count = _count_booked(db, session_obj.id)
                if existing is None and booked_count >= int(session_obj.capacity_max or 0):
                    capacity_blocked += 1
                    print(
                        f"[{SCRIPT_PREFIX}] skip_capacity_full|student={_display_name(student)}|"
                        f"session={session_obj.id}|date={_local_label(session_obj.start_at_utc, session_obj.timezone)}|"
                        f"booked={booked_count}|capacity={session_obj.capacity_max}"
                    )
                    continue
                missing_rows.append((session_obj, course_type, location, existing))

            print(
                f"[{SCRIPT_PREFIX}] plan_summary|student={_display_name(student)}|"
                f"target_sessions={len(target_rows)}|already_active={already_active}|"
                f"missing_or_cancelled={len(missing_rows)}|capacity_blocked={capacity_blocked}"
            )
            for session_obj, course_type, location, existing in missing_rows[:60]:
                print(
                    f"[{SCRIPT_PREFIX}] plan={'restore' if existing is not None else 'create'}|"
                    f"student={_display_name(student)}|session={session_obj.id}|"
                    f"date={_local_label(session_obj.start_at_utc, session_obj.timezone)}|"
                    f"activity={course_type.name}|location={location.name}"
                )

            summary["target_sessions"] += len(target_rows)
            summary["already_active"] += already_active
            summary["missing_or_cancelled"] += len(missing_rows)
            summary["capacity_blocked"] += capacity_blocked
            if not args.apply:
                continue

            for session_obj, _, _, existing in missing_rows:
                if existing is None:
                    booking = Booking(
                        session_id=session_obj.id,
                        user_id=student.id,
                        client_plan_subscription_id=source_booking.client_plan_subscription_id,
                        manual_credit_type_id=source_booking.manual_credit_type_id,
                        status=BookingStatus.BOOKED,
                        booked_at=now,
                        price_excl_vat_snapshot=source_booking.price_excl_vat_snapshot,
                        vat_rate_snapshot=source_booking.vat_rate_snapshot,
                        vat_amount_snapshot=source_booking.vat_amount_snapshot,
                        total_incl_vat_snapshot=source_booking.total_incl_vat_snapshot,
                        currency_snapshot=source_booking.currency_snapshot,
                        student_note=source_booking.student_note,
                    )
                    db.add(booking)
                    db.flush()
                    summary["created"] += 1
                else:
                    existing.client_plan_subscription_id = source_booking.client_plan_subscription_id
                    existing.manual_credit_type_id = source_booking.manual_credit_type_id
                    existing.status = BookingStatus.BOOKED
                    existing.booked_at = now
                    existing.cancelled_at = None
                    existing.cancellation_reason = None
                    existing.payment_hold_expires_at = None
                    existing.price_excl_vat_snapshot = source_booking.price_excl_vat_snapshot
                    existing.vat_rate_snapshot = source_booking.vat_rate_snapshot
                    existing.vat_amount_snapshot = source_booking.vat_amount_snapshot
                    existing.total_incl_vat_snapshot = source_booking.total_incl_vat_snapshot
                    existing.currency_snapshot = source_booking.currency_snapshot
                    existing.student_note = source_booking.student_note
                    db.add(existing)
                    booking = existing
                    summary["restored"] += 1
                ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    for key in sorted(summary):
        print(f"[{SCRIPT_PREFIX}] summary_{key}={summary[key]}")


if __name__ == "__main__":
    main()
