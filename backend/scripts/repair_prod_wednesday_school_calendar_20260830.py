from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.client_record import ClientInvoiceLine
from app.models.quote import QuoteEvent
from app.services.reminders import ensure_booking_reminder


SCRIPT_PREFIX = "PROD_REPAIR_WEDNESDAY_SCHOOL_CALENDAR_20260830"
SEASON_START = datetime(2026, 8, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 7, 15, tzinfo=timezone.utc)
ZONE = ZoneInfo("Europe/Paris")
ACTIVE_BOOKING_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}
WRONG_DATES = tuple(
    date.fromisoformat(value)
    for value in (
        "2026-10-21",
        "2026-10-28",
        "2026-11-11",
        "2026-12-23",
        "2026-12-30",
        "2027-02-10",
        "2027-02-17",
        "2027-04-07",
        "2027-04-14",
    )
)
TARGET_DATES = tuple(
    date.fromisoformat(value)
    for value in (
        "2027-04-21",
        "2027-04-28",
        "2027-05-05",
        "2027-05-12",
        "2027-05-19",
        "2027-05-26",
        "2027-06-02",
        "2027-06-09",
        "2027-06-16",
    )
)


@dataclass(frozen=True)
class SeriesCase:
    label: str
    anchor_student_id: UUID
    course_type_id: UUID
    location_id: UUID
    weekday: int
    start_time: str
    end_time: str
    expected_sessions: int
    quote_ids: tuple[UUID, ...]


CASES = (
    SeriesCase(
        label="Piano collectif Richelieu mercredi 11h",
        anchor_student_id=UUID("026a58f4-27ef-46ef-a49a-5e55a2d577e3"),
        course_type_id=UUID("4bdf5d1e-fe55-4f95-80d4-0cafd3ce7683"),
        location_id=UUID("b66fe0d7-2990-4a58-b2f0-360911c611ee"),
        weekday=2,
        start_time="11:00",
        end_time="12:00",
        expected_sessions=32,
        quote_ids=(
            UUID("12064314-f5c4-42b4-b33c-7a020bb39cc4"),
            UUID("74b1e477-3d9c-44ea-9262-ea9584f1c3a3"),
            UUID("7c459a39-4a87-4d3d-9f46-b08aeeb8cc73"),
            UUID("67bb2352-43a3-42a1-98c7-f34e7020c44a"),
        ),
    ),
    SeriesCase(
        label="Initiation Pompe mercredi 15h",
        anchor_student_id=UUID("c367d74b-e4f2-45e7-969b-7a4466b2f0d7"),
        course_type_id=UUID("4cd88342-aaac-4f19-ac96-0f284b3a01a5"),
        location_id=UUID("cb3337a8-6a32-431d-b5c4-2cd8667be97f"),
        weekday=2,
        start_time="15:00",
        end_time="16:00",
        expected_sessions=32,
        quote_ids=(
            UUID("9bf0a67a-a085-442c-a731-788eb541202e"),
            UUID("50e053a0-4e48-4cbb-a116-7226b4aee0ea"),
            UUID("0dbb6684-044f-4d68-a82e-e70922b3c002"),
            UUID("98eca2ec-be80-419e-a91e-05e28120cc32"),
        ),
    ),
    SeriesCase(
        label="Piano collectif Assas mercredi 16h",
        anchor_student_id=UUID("73d93bd4-9b48-44f4-91fd-78b9c4622296"),
        course_type_id=UUID("4bdf5d1e-fe55-4f95-80d4-0cafd3ce7683"),
        location_id=UUID("1be3c4dc-2f55-4712-bcf9-32a4624ff1ad"),
        weekday=2,
        start_time="16:00",
        end_time="17:00",
        expected_sessions=32,
        quote_ids=(UUID("105a3a05-8e36-4802-95de-10dc43a36a95"),),
    ),
)


def abort(case: SeriesCase, reason: str) -> None:
    raise RuntimeError(f"{SCRIPT_PREFIX}|abort|series={case.label}|reason={reason}")


def local_parts(session: CourseSession) -> tuple[date, int, str, str]:
    zone = ZoneInfo(session.timezone or "Europe/Paris")
    start = session.start_at_utc.astimezone(zone)
    end = session.end_at_utc.astimezone(zone)
    return start.date(), start.weekday(), start.strftime("%H:%M"), end.strftime("%H:%M")


def at_local(day: date, raw_time: str, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name or "Europe/Paris")
    return datetime.combine(day, time.fromisoformat(raw_time), tzinfo=zone).astimezone(timezone.utc)


def money(value: object) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def note_total(db, note_id: UUID) -> Decimal:  # noqa: ANN001
    return money(
        db.scalar(
            select(func.sum(ClientInvoiceLine.total_incl_vat)).where(ClientInvoiceLine.note_id == note_id)
        )
    )


def append_note(value: str | None, marker: str) -> str:
    current = (value or "").strip()
    if marker in current:
        return current
    return f"{current} | {marker}".strip(" |")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remplace neuf mercredis de vacances/férié par neuf mercredis de cours sur trois séries 2026-2027."
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    marker = "Calendrier annuel corrigé le 30/08/2026 : vacances exclues, 32 séances conservées, aucun e-mail."

    if any(day.weekday() != 2 for day in (*WRONG_DATES, *TARGET_DATES)):
        raise RuntimeError(f"{SCRIPT_PREFIX}|abort|reason=non_wednesday_date")

    with SessionLocal() as db:
        plans: list[dict[str, object]] = []
        print(f"{SCRIPT_PREFIX}|start|apply={args.apply}|series={len(CASES)}")

        for case in CASES:
            anchor_rows = db.execute(
                select(Booking, CourseSession)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.user_id == case.anchor_student_id,
                    Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                    CourseSession.course_type_id == case.course_type_id,
                    CourseSession.location_id == case.location_id,
                    CourseSession.start_at_utc >= SEASON_START,
                    CourseSession.start_at_utc < SEASON_END,
                )
                .with_for_update()
            ).all()
            group_ids = {
                session.recurrence_group_id
                for _, session in anchor_rows
                if session.recurrence_group_id is not None
                and local_parts(session)[1:] == (case.weekday, case.start_time, case.end_time)
            }
            if len(group_ids) != 1:
                abort(case, f"anchor_recurrence_groups_{len(group_ids)}")
            group_id = next(iter(group_ids))

            sessions = list(
                db.scalars(
                    select(CourseSession)
                    .where(
                        CourseSession.recurrence_group_id == group_id,
                        CourseSession.course_type_id == case.course_type_id,
                        CourseSession.location_id == case.location_id,
                        CourseSession.start_at_utc >= SEASON_START,
                        CourseSession.start_at_utc < SEASON_END,
                    )
                    .order_by(CourseSession.start_at_utc)
                    .with_for_update()
                ).all()
            )
            exact_sessions = [
                session
                for session in sessions
                if session.status == SessionStatus.SCHEDULED
                and local_parts(session)[1:] == (case.weekday, case.start_time, case.end_time)
            ]
            if len(exact_sessions) != case.expected_sessions:
                abort(case, f"scheduled_count_{len(exact_sessions)}")
            by_date = {local_parts(session)[0]: session for session in exact_sessions}
            if len(by_date) != case.expected_sessions:
                abort(case, "duplicate_dates_in_series")

            current_dates = set(by_date)
            wrong_present = set(WRONG_DATES) & current_dates
            target_present = set(TARGET_DATES) & current_dates
            if wrong_present == set(WRONG_DATES) and not target_present:
                state = "pending"
            elif target_present == set(TARGET_DATES) and not wrong_present:
                state = "aligned"
            else:
                abort(
                    case,
                    f"mixed_calendar_wrong_{len(wrong_present)}_target_{len(target_present)}",
                )

            session_bookings: dict[UUID, list[Booking]] = {}
            active_students: set[UUID] = set()
            invoice_note_ids: set[UUID] = set()
            moved_booking_ids: list[UUID] = []
            for session in exact_sessions:
                bookings = list(
                    db.scalars(select(Booking).where(Booking.session_id == session.id).with_for_update()).all()
                )
                session_bookings[session.id] = bookings
                active_students.update(
                    booking.user_id for booking in bookings if booking.status in ACTIVE_BOOKING_STATUSES
                )
                if local_parts(session)[0] in WRONG_DATES:
                    moved_booking_ids.extend(booking.id for booking in bookings)

            if state == "pending":
                for target_date in TARGET_DATES:
                    conflicts = db.execute(
                        select(Booking.user_id, CourseSession)
                        .join(CourseSession, CourseSession.id == Booking.session_id)
                        .where(
                            Booking.user_id.in_(active_students),
                            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                            CourseSession.start_at_utc >= at_local(target_date, "00:00", "Europe/Paris"),
                            CourseSession.start_at_utc
                            < at_local(target_date + timedelta(days=1), "00:00", "Europe/Paris"),
                        )
                    ).all()
                    conflicting_users = {
                        user_id
                        for user_id, session in conflicts
                        if session.recurrence_group_id != group_id
                        and local_parts(session)[1:] == (case.weekday, case.start_time, case.end_time)
                    }
                    if conflicting_users:
                        abort(case, f"target_student_conflicts_{target_date}_{len(conflicting_users)}")

                lines = list(
                    db.scalars(
                        select(ClientInvoiceLine)
                        .where(
                            ClientInvoiceLine.source == "BOOKING",
                            ClientInvoiceLine.source_payment_id.in_(moved_booking_ids),
                        )
                        .with_for_update()
                    ).all()
                )
                invoice_note_ids = {line.note_id for line in lines}
                invoice_totals = {note_id: note_total(db, note_id) for note_id in invoice_note_ids}
            else:
                lines = []
                invoice_totals = {}

            print(
                f"{SCRIPT_PREFIX}|series|label={case.label}|group={group_id}|state={state}|"
                f"sessions={len(exact_sessions)}|active_students={len(active_students)}|"
                f"bookings_to_shift={len(moved_booking_ids) if state == 'pending' else 0}|"
                f"invoice_notes={len(invoice_note_ids)}"
            )
            plans.append(
                {
                    "case": case,
                    "group_id": group_id,
                    "sessions": exact_sessions,
                    "by_date": by_date,
                    "session_bookings": session_bookings,
                    "lines": lines,
                    "invoice_totals": invoice_totals,
                    "state": state,
                }
            )

        if not args.apply:
            db.rollback()
            pending = sum(plan["state"] == "pending" for plan in plans)
            print(f"{SCRIPT_PREFIX}|summary|result=dry_run|pending={pending}|aligned={len(plans) - pending}")
            return 0

        shifted_sessions = shifted_bookings = updated_invoice_dates = updated_reminders = 0
        for plan in plans:
            case: SeriesCase = plan["case"]  # type: ignore[assignment]
            if plan["state"] == "aligned":
                print(f"{SCRIPT_PREFIX}|verified|label={case.label}|result=already_aligned")
                continue

            by_date: dict[date, CourseSession] = plan["by_date"]  # type: ignore[assignment]
            session_bookings: dict[UUID, list[Booking]] = plan["session_bookings"]  # type: ignore[assignment]
            line_by_booking: dict[UUID, list[ClientInvoiceLine]] = {}
            for line in plan["lines"]:  # type: ignore[union-attr]
                line_by_booking.setdefault(line.source_payment_id, []).append(line)

            for old_date, target_date in zip(WRONG_DATES, TARGET_DATES):
                session = by_date[old_date]
                timezone_name = session.timezone or "Europe/Paris"
                old_start = session.start_at_utc
                old_end = session.end_at_utc
                new_start = at_local(target_date, case.start_time, timezone_name)
                new_end = at_local(target_date, case.end_time, timezone_name)
                delta = new_start - old_start
                if old_end - old_start != new_end - new_start:
                    abort(case, f"duration_changed_{old_date}_{target_date}")

                session.start_at_utc = new_start
                session.end_at_utc = new_end
                session.auto_cancel_deadline_utc = session.auto_cancel_deadline_utc + delta
                session.auto_cancel_checked_at = None
                session.internal_note = append_note(session.internal_note, marker)
                session.updated_at = now
                shifted_sessions += 1

                for booking in session_bookings[session.id]:
                    if booking.student_start_at_utc is not None:
                        booking.student_start_at_utc = booking.student_start_at_utc + delta
                    if booking.student_end_at_utc is not None:
                        booking.student_end_at_utc = booking.student_end_at_utc + delta
                    booking.internal_note = append_note(booking.internal_note, marker)
                    booking.updated_at = now
                    shifted_bookings += 1
                    effective_start = booking.student_start_at_utc or new_start
                    for line in line_by_booking.get(booking.id, []):
                        line.occurred_at = effective_start
                        updated_invoice_dates += 1
                    if booking.status == BookingStatus.BOOKED:
                        if ensure_booking_reminder(db, booking=booking, session_obj=session, now=now) is not None:
                            updated_reminders += 1

            final_until = max(TARGET_DATES)
            for session in plan["sessions"]:  # type: ignore[union-attr]
                session.recurrence_until_date = final_until

            for quote_id in case.quote_ids:
                existing_event = db.scalar(
                    select(QuoteEvent.id).where(
                        QuoteEvent.quote_id == quote_id,
                        QuoteEvent.event_type == "paris_school_calendar_repair",
                    )
                )
                if existing_event is None:
                    db.add(
                        QuoteEvent(
                            quote_id=quote_id,
                            event_type="paris_school_calendar_repair",
                            actor_type="system",
                            payload={
                                "script": SCRIPT_PREFIX,
                                "recurrence_group_id": str(plan["group_id"]),
                                "reason": (
                                    "Vacances scolaires et 11 novembre exclus; "
                                    "neuf mercredis avril-juin restaurés"
                                ),
                                "sessions_before_after": case.expected_sessions,
                                "invoice_amounts_changed": 0,
                                "emails_sent": 0,
                                "series_created": 0,
                            },
                        )
                    )

            db.flush()
            final_sessions = list(
                db.scalars(
                    select(CourseSession).where(
                        CourseSession.recurrence_group_id == plan["group_id"],
                        CourseSession.status == SessionStatus.SCHEDULED,
                        CourseSession.start_at_utc >= SEASON_START,
                        CourseSession.start_at_utc < SEASON_END,
                    )
                ).all()
            )
            final_dates = {
                local_parts(session)[0]
                for session in final_sessions
                if local_parts(session)[1:] == (case.weekday, case.start_time, case.end_time)
            }
            if len(final_dates) != case.expected_sessions:
                abort(case, f"post_count_{len(final_dates)}")
            if set(WRONG_DATES) & final_dates or not set(TARGET_DATES).issubset(final_dates):
                abort(case, "post_calendar_mismatch")
            for note_id, before in plan["invoice_totals"].items():  # type: ignore[union-attr]
                after = note_total(db, note_id)
                if after != before:
                    abort(case, f"invoice_total_changed_{note_id}_{before}_{after}")
            print(
                f"{SCRIPT_PREFIX}|verified|label={case.label}|group={plan['group_id']}|"
                f"sessions={len(final_dates)}|first={min(final_dates)}|last={max(final_dates)}"
            )

        db.commit()
        print(
            f"{SCRIPT_PREFIX}|summary|result=applied|sessions_shifted={shifted_sessions}|"
            f"bookings_shifted={shifted_bookings}|invoice_dates_updated={updated_invoice_dates}|"
            f"reminders_updated={updated_reminders}|invoice_amounts_changed=0|emails=0|series_created=0"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
