from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import and_, func, or_, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.user import ClientKind, User, UserRole
from app.services.reminders import ensure_booking_reminder

SCRIPT_PREFIX = "PROD_REPAIR_GUISNEL_SOLFEGE1_BOOKINGS"
TARGET_FIRST_NAME = "gustave"
TARGET_LAST_NAME = "guisnel"
TARGET_END_LOCAL = datetime(2027, 5, 31, 23, 59, 59, tzinfo=ZoneInfo("Europe/Paris"))
ACTIVE_BOOKING_STATUSES = (
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _local_label(value: datetime, tz_name: str | None) -> str:
    tz = ZoneInfo(tz_name or "Europe/Paris")
    local = value.astimezone(tz)
    return local.strftime("%Y-%m-%d %H:%M")


def _money(value: Decimal | None) -> Decimal:
    return Decimal(value or Decimal("0.00")).quantize(Decimal("0.01"))


def _user_label(user: User) -> str:
    return (
        f"{user.id}|{user.first_name or '-'} {user.last_name or '-'}|"
        f"email={user.email}|kind={user.client_kind.value}|status={user.client_status.value}"
    )


def _is_solfege_level_1(course_type: CourseType) -> bool:
    haystack = f"{course_type.name or ''} {course_type.code or ''} {course_type.service_code or ''}".casefold()
    if "solf" not in haystack:
        return False
    return any(token in haystack for token in ("niveau 1", "level 1", "_1", "-1", "n1"))


def _session_signature(session_obj: CourseSession) -> tuple[object, object, int, time, time]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start = session_obj.start_at_utc.astimezone(tz)
    end = session_obj.end_at_utc.astimezone(tz)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        start.weekday(),
        start.timetz().replace(tzinfo=None, microsecond=0),
        end.timetz().replace(tzinfo=None, microsecond=0),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Repair Gustave Guisnel Solfege 1 production bookings by extending the already-booked "
            "series through 2027-05-31. Dry-run by default."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Apply the repair. Without it, no data is changed.")
    args = parser.parse_args()

    now = _utcnow()
    target_end_utc = TARGET_END_LOCAL.astimezone(timezone.utc)

    with SessionLocal() as db:
        users = db.scalars(
            select(User)
            .where(
                User.role == UserRole.CLIENT,
                User.client_kind == ClientKind.CHILD,
                func.lower(func.coalesce(User.first_name, "")) == TARGET_FIRST_NAME,
                func.lower(func.coalesce(User.last_name, "")) == TARGET_LAST_NAME,
            )
            .order_by(User.created_at.asc(), User.id.asc())
            .with_for_update()
        ).all()

        print(f"[{SCRIPT_PREFIX}] dry_run={not args.apply}")
        print(f"[{SCRIPT_PREFIX}] matching_users={len(users)}")
        for user in users:
            print(f"[{SCRIPT_PREFIX}] user={_user_label(user)}")

        if len(users) != 1:
            print(f"[{SCRIPT_PREFIX}] abort=expected_exactly_one_child_user")
            db.rollback()
            return

        student = users[0]

        booking_rows = db.execute(
            select(Booking, CourseSession, CourseType, Location)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                Booking.user_id == student.id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                or_(
                    func.lower(CourseType.name).like("%solf%"),
                    func.lower(CourseType.code).like("%solf%"),
                    func.lower(CourseType.service_code).like("%solf%"),
                ),
            )
            .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
            .with_for_update()
        ).all()

        print(f"[{SCRIPT_PREFIX}] active_solfege_bookings={len(booking_rows)}")
        for booking, session_obj, course_type, location in booking_rows:
            print(
                f"[{SCRIPT_PREFIX}] current="
                f"booking={booking.id}|session={session_obj.id}|status={booking.status.value}|"
                f"activity={course_type.name}|code={course_type.code}|location={location.name}|"
                f"start={_local_label(session_obj.start_at_utc, session_obj.timezone)}|"
                f"end={_local_label(session_obj.end_at_utc, session_obj.timezone)}|"
                f"recurrence_group={session_obj.recurrence_group_id or '-'}|"
                f"subscription={booking.client_plan_subscription_id or '-'}|total={_money(booking.total_incl_vat_snapshot)}"
            )

        source_rows = [
            row
            for row in booking_rows
            if _is_solfege_level_1(row[2])
        ]
        if not source_rows:
            print(f"[{SCRIPT_PREFIX}] abort=no_active_solfege_level_1_booking_found")
            db.rollback()
            return

        signatures = {_session_signature(session_obj) for _, session_obj, _, _ in source_rows}
        recurrence_group_ids = {session_obj.recurrence_group_id for _, session_obj, _, _ in source_rows if session_obj.recurrence_group_id}
        course_type_ids = {session_obj.course_type_id for _, session_obj, _, _ in source_rows}

        print(f"[{SCRIPT_PREFIX}] source_level_1_bookings={len(source_rows)}")
        print(f"[{SCRIPT_PREFIX}] source_signatures={len(signatures)}")
        print(f"[{SCRIPT_PREFIX}] source_recurrence_groups={len(recurrence_group_ids)}")

        if len(course_type_ids) != 1:
            print(f"[{SCRIPT_PREFIX}] abort=ambiguous_solfege_level_1_course_type")
            db.rollback()
            return
        if len(signatures) != 1 and len(recurrence_group_ids) != 1:
            print(f"[{SCRIPT_PREFIX}] abort=ambiguous_solfege_level_1_series")
            db.rollback()
            return

        source_booking, source_session, source_course_type, source_location = source_rows[0]
        first_source_start = min(session_obj.start_at_utc for _, session_obj, _, _ in source_rows)

        target_stmt = select(CourseSession, CourseType, Location).join(
            CourseType, CourseType.id == CourseSession.course_type_id
        ).join(Location, Location.id == CourseSession.location_id)

        if len(recurrence_group_ids) == 1:
            target_stmt = target_stmt.where(CourseSession.recurrence_group_id == next(iter(recurrence_group_ids)))
        else:
            signature = next(iter(signatures))
            target_stmt = target_stmt.where(
                CourseSession.course_type_id == signature[0],
                CourseSession.location_id == signature[1],
            )

        target_rows = db.execute(
            target_stmt.where(
                CourseSession.status != SessionStatus.CANCELLED,
                CourseSession.start_at_utc >= first_source_start,
                CourseSession.start_at_utc <= target_end_utc,
            ).order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
        ).all()

        if len(recurrence_group_ids) != 1:
            signature = next(iter(signatures))
            target_rows = [
                row
                for row in target_rows
                if _session_signature(row[0]) == signature
            ]

        target_session_ids = [session_obj.id for session_obj, _, _ in target_rows]
        existing_by_session = {}
        if target_session_ids:
            existing_bookings = db.scalars(
                select(Booking)
                .where(
                    Booking.user_id == student.id,
                    Booking.session_id.in_(target_session_ids),
                )
                .with_for_update()
            ).all()
            existing_by_session = {booking.session_id: booking for booking in existing_bookings}

        missing_rows = []
        already_active = 0
        cancelled_to_restore = 0
        for session_obj, course_type, location in target_rows:
            existing = existing_by_session.get(session_obj.id)
            if existing is not None and existing.status in ACTIVE_BOOKING_STATUSES:
                already_active += 1
                continue
            if existing is not None:
                cancelled_to_restore += 1
            missing_rows.append((session_obj, course_type, location, existing))

        print(
            f"[{SCRIPT_PREFIX}] target_series="
            f"activity={source_course_type.name}|code={source_course_type.code}|location={source_location.name}|"
            f"first={_local_label(first_source_start, source_session.timezone)}|"
            f"until=2027-05-31|target_sessions={len(target_rows)}|"
            f"already_active={already_active}|missing_or_cancelled={len(missing_rows)}|cancelled_to_restore={cancelled_to_restore}"
        )

        for session_obj, course_type, location, existing in missing_rows:
            print(
                f"[{SCRIPT_PREFIX}] plan="
                f"{'restore' if existing is not None else 'create'}|session={session_obj.id}|"
                f"start={_local_label(session_obj.start_at_utc, session_obj.timezone)}|"
                f"activity={course_type.name}|location={location.name}"
            )

        if not args.apply:
            db.rollback()
            return

        created = 0
        restored = 0
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
                created += 1
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
                restored += 1

            ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)

        db.commit()
        print(f"[{SCRIPT_PREFIX}] applied_created={created}|applied_restored={restored}")


if __name__ == "__main__":
    main()
