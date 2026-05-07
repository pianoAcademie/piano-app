from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.user import ClientKind, User, UserRole
from app.services.reminders import ensure_booking_reminder

SCRIPT_PREFIX = "PROD_REPAIR_SERIES_BOOKING_GAPS"
TARGET_GROUP_ID = UUID("63b53bc2-f749-47ad-b1d8-21d4154eacea")
TARGET_STUDENT_IDS = (
    UUID("ed333464-6291-47ca-9bcf-0383790deb6b"),  # Garance Guisnel
    UUID("e4ada0e0-d52c-476a-97f4-797dcdbcc6e7"),  # Maxime Germain
)
SCHOOL_YEAR_START_LOCAL = datetime(2026, 9, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
SCHOOL_YEAR_END_LOCAL = datetime(2027, 7, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))

BOOKING_STATUSES_PRESENT = (
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _local_start(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))


def _local_label(session_obj: CourseSession) -> str:
    return _local_start(session_obj).strftime("%Y-%m-%d %H:%M")


def _slot_label(session_obj: CourseSession) -> str:
    start = _local_start(session_obj)
    end = session_obj.end_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))
    weekdays = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    return f"{weekdays[start.weekday()]} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _user_label(user: User) -> str:
    return f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email or str(user.id)


def _course_is_vacation(course_type: CourseType) -> bool:
    haystack = f"{course_type.name or ''} {course_type.code or ''} {course_type.service_code or ''}".casefold()
    return "vacance" in haystack or "vacation" in haystack


def _audit_series_gaps(db) -> list[dict[str, object]]:
    start_utc = SCHOOL_YEAR_START_LOCAL.astimezone(timezone.utc)
    end_utc = SCHOOL_YEAR_END_LOCAL.astimezone(timezone.utc)
    rows = db.execute(
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            CourseSession.recurrence_group_id.is_not(None),
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.start_at_utc >= start_utc,
            CourseSession.start_at_utc < end_utc,
        )
        .order_by(CourseSession.recurrence_group_id.asc(), CourseSession.start_at_utc.asc())
    ).all()

    series: dict[object, list[tuple[CourseSession, CourseType, Location]]] = defaultdict(list)
    for session_obj, course_type, location in rows:
        if _course_is_vacation(course_type):
            continue
        series[session_obj.recurrence_group_id].append((session_obj, course_type, location))

    series = {group_id: group_rows for group_id, group_rows in series.items() if len(group_rows) > 1}
    session_ids = [session_obj.id for group_rows in series.values() for session_obj, _, _ in group_rows]
    _print(f"audit_scope=school_year_2026_2027|series_checked={len(series)}|sessions_checked={len(session_ids)}")

    booking_rows = []
    if session_ids:
        booking_rows = db.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.session_id.in_(session_ids),
                User.role == UserRole.CLIENT,
                User.client_kind == ClientKind.CHILD,
            )
        ).all()

    bookings_by_session_user: dict[tuple[object, object], list[Booking]] = defaultdict(list)
    present_user_ids_by_session: dict[object, set[object]] = defaultdict(set)
    users_by_id: dict[object, User] = {}
    for booking, user in booking_rows:
        bookings_by_session_user[(booking.session_id, booking.user_id)].append(booking)
        users_by_id[user.id] = user
        if booking.status in BOOKING_STATUSES_PRESENT:
            present_user_ids_by_session[booking.session_id].add(user.id)

    anomalies: list[dict[str, object]] = []
    complete_students = 0
    audited_student_series = 0
    for group_id, group_rows in series.items():
        sessions = [session_obj for session_obj, _, _ in group_rows]
        course_type = group_rows[0][1]
        location = group_rows[0][2]
        student_ids = set()
        for session_obj in sessions:
            student_ids.update(present_user_ids_by_session.get(session_obj.id, set()))

        for user_id in sorted(student_ids, key=lambda value: _user_label(users_by_id[value]).casefold()):
            present_indexes = []
            cancelled_indexes = []
            for index, session_obj in enumerate(sessions):
                bookings = bookings_by_session_user.get((session_obj.id, user_id), [])
                if any(booking.status in BOOKING_STATUSES_PRESENT for booking in bookings):
                    present_indexes.append(index)
                elif any(booking.status == BookingStatus.CANCELLED for booking in bookings):
                    cancelled_indexes.append(index)
            if not present_indexes:
                continue

            audited_student_series += 1
            first_index = min(present_indexes)
            missing_indexes = [index for index in range(first_index, len(sessions)) if index not in present_indexes]
            if not missing_indexes:
                complete_students += 1
                continue

            user = users_by_id[user_id]
            missing_sessions = [sessions[index] for index in missing_indexes]
            cancelled_missing = [sessions[index] for index in missing_indexes if index in cancelled_indexes]
            anomalies.append(
                {
                    "group_id": group_id,
                    "student": _user_label(user),
                    "student_id": user_id,
                    "activity": course_type.name,
                    "location": location.name,
                    "slot": _slot_label(sessions[first_index]),
                    "series_sessions": len(sessions),
                    "present_count": len(present_indexes),
                    "missing_count": len(missing_sessions),
                    "cancelled_missing_count": len(cancelled_missing),
                    "first_present": _local_label(sessions[first_index]),
                    "last_present": _local_label(sessions[max(present_indexes)]),
                    "missing_sample": ", ".join(_local_label(session_obj) for session_obj in missing_sessions[:12]),
                }
            )

    _print(f"audit_summary=student_series_audited={audited_student_series}|complete={complete_students}|anomalies={len(anomalies)}")
    for anomaly in sorted(
        anomalies,
        key=lambda item: (
            str(item["activity"]).casefold(),
            str(item["location"]).casefold(),
            str(item["slot"]),
            str(item["student"]).casefold(),
        ),
    ):
        _print(
            "audit_anomaly="
            f"student={anomaly['student']}|student_id={anomaly['student_id']}|"
            f"activity={anomaly['activity']}|location={anomaly['location']}|slot={anomaly['slot']}|"
            f"group={anomaly['group_id']}|series_sessions={anomaly['series_sessions']}|"
            f"present={anomaly['present_count']}|missing={anomaly['missing_count']}|"
            f"cancelled_missing={anomaly['cancelled_missing_count']}|"
            f"first_present={anomaly['first_present']}|last_present={anomaly['last_present']}|"
            f"missing_sample={anomaly['missing_sample']}"
        )
    return anomalies


def _repair_target_series(db) -> None:
    now = datetime.now(timezone.utc)
    sessions = db.scalars(
        select(CourseSession)
        .where(
            CourseSession.recurrence_group_id == TARGET_GROUP_ID,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
        .with_for_update()
    ).all()
    _print(f"target_series_sessions={len(sessions)}|group={TARGET_GROUP_ID}")
    if len(sessions) != 32:
        raise RuntimeError(f"Unexpected target series size: {len(sessions)}")

    users = db.scalars(
        select(User)
        .where(
            User.id.in_(TARGET_STUDENT_IDS),
            User.role == UserRole.CLIENT,
            User.client_kind == ClientKind.CHILD,
        )
        .order_by(User.last_name.asc(), User.first_name.asc())
        .with_for_update()
    ).all()
    users_by_id = {user.id: user for user in users}
    _print(f"target_students={len(users_by_id)}")
    if set(users_by_id) != set(TARGET_STUDENT_IDS):
        raise RuntimeError("Target students not found or not children")

    session_ids = [session_obj.id for session_obj in sessions]
    all_group_bookings = db.execute(
        select(Booking, User)
        .join(User, User.id == Booking.user_id)
        .where(Booking.session_id.in_(session_ids))
        .with_for_update()
    ).all()

    bookings_by_session_user: dict[tuple[object, object], Booking] = {}
    present_count_by_session: dict[object, int] = defaultdict(int)
    for booking, _user in all_group_bookings:
        bookings_by_session_user[(booking.session_id, booking.user_id)] = booking
        if booking.status in BOOKING_STATUSES_PRESENT:
            present_count_by_session[booking.session_id] += 1

    created = 0
    restored = 0
    for student_id in TARGET_STUDENT_IDS:
        user = users_by_id[student_id]
        present_indexes = [
            index
            for index, session_obj in enumerate(sessions)
            if (existing := bookings_by_session_user.get((session_obj.id, student_id))) is not None
            and existing.status in BOOKING_STATUSES_PRESENT
        ]
        if not present_indexes:
            raise RuntimeError(f"No source booking found for {student_id}")

        source_booking = bookings_by_session_user[(sessions[present_indexes[0]].id, student_id)]
        missing_indexes = [
            index
            for index in range(min(present_indexes), len(sessions))
            if (
                bookings_by_session_user.get((sessions[index].id, student_id)) is None
                or bookings_by_session_user[(sessions[index].id, student_id)].status not in BOOKING_STATUSES_PRESENT
            )
        ]
        _print(
            "repair_student="
            f"student={_user_label(user)}|student_id={student_id}|present={len(present_indexes)}|missing={len(missing_indexes)}"
        )

        for index in missing_indexes:
            session_obj = sessions[index]
            existing = bookings_by_session_user.get((session_obj.id, student_id))
            active_other_count = present_count_by_session[session_obj.id]
            if existing is not None and existing.status in BOOKING_STATUSES_PRESENT:
                continue
            if active_other_count >= session_obj.capacity_max:
                raise RuntimeError(f"Capacity exceeded for session {session_obj.id} at {_local_label(session_obj)}")

            if existing is None:
                booking = Booking(
                    session_id=session_obj.id,
                    user_id=student_id,
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
                bookings_by_session_user[(session_obj.id, student_id)] = booking
                created += 1
                action = "create"
            else:
                existing.client_plan_subscription_id = source_booking.client_plan_subscription_id
                existing.manual_credit_type_id = source_booking.manual_credit_type_id
                existing.status = BookingStatus.BOOKED
                existing.booked_at = now
                existing.payment_hold_expires_at = None
                existing.cancelled_at = None
                existing.cancellation_reason = None
                existing.price_excl_vat_snapshot = source_booking.price_excl_vat_snapshot
                existing.vat_rate_snapshot = source_booking.vat_rate_snapshot
                existing.vat_amount_snapshot = source_booking.vat_amount_snapshot
                existing.total_incl_vat_snapshot = source_booking.total_incl_vat_snapshot
                existing.currency_snapshot = source_booking.currency_snapshot
                existing.student_note = source_booking.student_note
                db.add(existing)
                booking = existing
                restored += 1
                action = "restore"

            present_count_by_session[session_obj.id] += 1
            ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)
            _print(f"repair_plan_applied={action}|student={_user_label(user)}|session={session_obj.id}|start={_local_label(session_obj)}")

    db.commit()
    _print(f"repair_applied=created={created}|restored={restored}")


def main() -> None:
    with SessionLocal() as db:
        _print("phase=before_audit")
        before = _audit_series_gaps(db)
        _print(f"before_anomalies={len(before)}")
        _print("phase=repair")
        _repair_target_series(db)
        _print("phase=after_audit")
        after = _audit_series_gaps(db)
        _print(f"after_anomalies={len(after)}")
        if after:
            raise RuntimeError("Remaining booking series anomalies after repair")


if __name__ == "__main__":
    main()
