from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, Location, SessionStatus
from app.models.notification_engine import DomainEvent
from app.models.user import User
from app.services.reminders import ensure_booking_reminder


SCRIPT_PREFIX = "PROD_RECONCILE_ASSAS_THURSDAY_17_SERIES"
SOURCE_ANCHOR_SESSION_ID = UUID("32b69c99-9ea6-4d61-9c96-96292b111f43")
REPAIR_EVENT_TYPE = "assas_thursday_17_series_reconciled"
EXPECTED_LOCATION_FRAGMENT = "assas"
EXPECTED_TITLE_FRAGMENT = "enfant"
EXPECTED_STUDENT_FRAGMENT = "ryo"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _student_label(user: User) -> str:
    full_name = " ".join(part.strip() for part in (user.first_name or "", user.last_name or "") if part.strip())
    return full_name or str(user.id)


def _abort(reason: str) -> None:
    raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason={reason}")


def _count_rows_for_sessions(db, *, table_name: str, session_ids: list[UUID]) -> int:  # noqa: ANN001
    if not session_ids:
        return 0
    return int(
        db.scalar(
            text(f"SELECT count(*) FROM {table_name} WHERE session_id = ANY(:session_ids)"),
            {"session_ids": session_ids},
        )
        or 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge Ryo's accidentally cancelled Assas Thursday 17h series into the active empty duplicate series."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Commit the guarded repair. Without it, audit only.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return successfully when the production-only anchor is absent.",
    )
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        anchor = db.scalar(
            select(CourseSession)
            .where(CourseSession.id == SOURCE_ANCHOR_SESSION_ID)
            .with_for_update()
        )
        if anchor is None:
            if args.allow_missing:
                db.rollback()
                print(f"{SCRIPT_PREFIX}|summary|result=anchor_missing_noop|applied={args.apply}")
                return 0
            _abort("anchor_missing")

        already_done = db.scalar(
            select(DomainEvent.id).where(
                DomainEvent.event_type == REPAIR_EVENT_TYPE,
                DomainEvent.related_entity_type == "recurrence_group",
                DomainEvent.related_entity_id == anchor.recurrence_group_id,
            )
        )
        if already_done is not None:
            db.rollback()
            print(f"{SCRIPT_PREFIX}|summary|result=already_reconciled|applied={args.apply}")
            return 0

        if anchor.recurrence_group_id is None:
            _abort("source_anchor_without_recurrence_group")
        location = db.get(Location, anchor.location_id)
        if location is None or EXPECTED_LOCATION_FRAGMENT not in (location.name or "").strip().lower():
            _abort("unexpected_anchor_location")
        if EXPECTED_TITLE_FRAGMENT not in (anchor.title or "").strip().lower():
            _abort("unexpected_anchor_title")

        source_group_id = anchor.recurrence_group_id
        grouped_sessions = db.scalars(
            select(CourseSession)
            .where(
                CourseSession.recurrence_group_id == source_group_id,
                CourseSession.start_at_utc >= anchor.start_at_utc,
            )
            .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
            .with_for_update()
        ).all()
        if not grouped_sessions:
            _abort("source_series_empty")
        if any(
            session_obj.location_id != anchor.location_id
            or session_obj.course_type_id != anchor.course_type_id
            or (session_obj.title or "").strip() != (anchor.title or "").strip()
            for session_obj in grouped_sessions
        ):
            _abort("source_series_signature_mismatch")
        if any(
            session_obj.status not in (SessionStatus.SCHEDULED, SessionStatus.CANCELLED)
            for session_obj in grouped_sessions
        ):
            _abort("source_series_has_non_future_status")

        grouped_ids = [session_obj.id for session_obj in grouped_sessions]
        booking_counts = {
            session_id: int(count)
            for session_id, count in db.execute(
                select(Booking.session_id, func.count(Booking.id))
                .where(Booking.session_id.in_(grouped_ids))
                .group_by(Booking.session_id)
            ).all()
        }
        sessions_by_start: dict[datetime, list[CourseSession]] = {}
        for session_obj in grouped_sessions:
            sessions_by_start.setdefault(session_obj.start_at_utc, []).append(session_obj)

        source_by_start: dict[datetime, CourseSession] = {}
        target_by_start: dict[datetime, CourseSession] = {}
        for start_at, pair in sessions_by_start.items():
            if len(pair) != 2:
                _abort(f"expected_two_occurrences_at_{start_at.isoformat()}_found_{len(pair)}")
            empty_scheduled = [
                session_obj
                for session_obj in pair
                if session_obj.status == SessionStatus.SCHEDULED
                and booking_counts.get(session_obj.id, 0) == 0
            ]
            if len(empty_scheduled) != 1:
                _abort(
                    f"expected_one_active_empty_occurrence_at_{start_at.isoformat()}_found_{len(empty_scheduled)}"
                )
            target_session = empty_scheduled[0]
            source_session = next(session_obj for session_obj in pair if session_obj.id != target_session.id)
            if (
                target_session.end_at_utc != source_session.end_at_utc
                or target_session.capacity_max != source_session.capacity_max
            ):
                _abort(f"source_target_shape_mismatch_at_{start_at.isoformat()}")
            source_by_start[start_at] = source_session
            target_by_start[start_at] = target_session

        source_sessions = [source_by_start[start_at] for start_at in sorted(source_by_start)]
        target_sessions = [target_by_start[start_at] for start_at in sorted(target_by_start)]
        source_ids = [session_obj.id for session_obj in source_sessions]

        target_ids = [target_by_start[session_obj.start_at_utc].id for session_obj in source_sessions]
        target_group_ids = sorted(
            {
                str(session_obj.recurrence_group_id)
                for session_obj in target_sessions
                if session_obj.recurrence_group_id is not None
            }
        )
        target_booking_count = int(
            db.scalar(select(func.count(Booking.id)).where(Booking.session_id.in_(target_ids))) or 0
        )
        if target_booking_count != 0:
            _abort(f"target_series_not_empty_booking_count_{target_booking_count}")

        source_booking_rows = db.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(Booking.session_id.in_(source_ids))
            .order_by(Booking.booked_at.asc(), Booking.id.asc())
            .with_for_update()
        ).all()
        if not source_booking_rows:
            _abort("source_series_has_no_booking")
        student_ids = {booking.user_id for booking, _ in source_booking_rows}
        if len(student_ids) != 1:
            _abort(f"source_series_has_{len(student_ids)}_students")
        student = source_booking_rows[0][1]
        if EXPECTED_STUDENT_FRAGMENT not in _student_label(student).strip().lower():
            _abort("unexpected_source_student")
        if any(booking.status != BookingStatus.BOOKED for booking, _ in source_booking_rows):
            statuses = sorted({_enum_value(booking.status) for booking, _ in source_booking_rows})
            _abort(f"source_booking_statuses_{','.join(statuses)}")
        booking_counts_by_session: dict[UUID, int] = {}
        for booking, _ in source_booking_rows:
            booking_counts_by_session[booking.session_id] = booking_counts_by_session.get(booking.session_id, 0) + 1
        if any(count != 1 for count in booking_counts_by_session.values()):
            _abort("multiple_bookings_on_source_occurrence")

        # Future cancelled duplicates must not already have attendance, payout,
        # professor-message or makeup activity. Professor assignments themselves
        # are expected and are safely removed with their duplicate session.
        for table_name in ("professor_session_messages", "professor_session_payouts", "makeup_request_options"):
            count = _count_rows_for_sessions(db, table_name=table_name, session_ids=source_ids)
            if count:
                _abort(f"source_series_has_{count}_rows_in_{table_name}")

        status_counts: dict[str, int] = {}
        for session_obj in source_sessions:
            status = _enum_value(session_obj.status)
            status_counts[status] = status_counts.get(status, 0) + 1
        print(
            f"{SCRIPT_PREFIX}|audit|source_group={source_group_id}|"
            f"target_groups={','.join(target_group_ids) if target_group_ids else 'none'}|"
            f"source_sessions={len(source_sessions)}|target_sessions={len(target_sessions)}|"
            f"moved_bookings={len(source_booking_rows)}|student={_student_label(student)}|"
            f"source_statuses={status_counts}|target_existing_bookings={target_booking_count}"
        )

        for booking, _ in source_booking_rows:
            source_session = source_by_start[next(
                start_at for start_at, session_obj in source_by_start.items() if session_obj.id == booking.session_id
            )]
            target_session = target_by_start[source_session.start_at_utc]
            if (
                target_session.end_at_utc != source_session.end_at_utc
                or target_session.capacity_max != source_session.capacity_max
            ):
                _abort("source_target_occurrence_shape_mismatch")
            booking.session_id = target_session.id
            ensure_booking_reminder(db, booking=booking, session_obj=target_session, now=now)

        db.flush()
        remaining_source_bookings = int(
            db.scalar(select(func.count(Booking.id)).where(Booking.session_id.in_(source_ids))) or 0
        )
        moved_target_bookings = int(
            db.scalar(select(func.count(Booking.id)).where(Booking.session_id.in_(target_ids))) or 0
        )
        if remaining_source_bookings != 0 or moved_target_bookings != len(source_booking_rows):
            _abort("post_move_booking_counts_invalid")

        for session_obj in source_sessions:
            db.delete(session_obj)
        db.flush()
        remaining_sources = int(
            db.scalar(select(func.count(CourseSession.id)).where(CourseSession.id.in_(source_ids))) or 0
        )
        if remaining_sources != 0:
            _abort("source_duplicate_sessions_not_deleted")

        db.add(
            DomainEvent(
                event_type=REPAIR_EVENT_TYPE,
                source="admin_repair",
                actor_type="system",
                actor_id=None,
                related_entity_type="recurrence_group",
                related_entity_id=source_group_id,
                occurred_at=now,
                payload_json={
                    "source_recurrence_group_id": str(source_group_id),
                    "target_recurrence_group_ids": target_group_ids,
                    "removed_duplicate_session_ids": [str(session_id) for session_id in source_ids],
                    "moved_booking_ids": [str(booking.id) for booking, _ in source_booking_rows],
                    "student_id": str(next(iter(student_ids))),
                    "credit_changes": [],
                },
            )
        )
        db.flush()

        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(
            f"{SCRIPT_PREFIX}|summary|result=reconciled|removed_sessions={len(source_ids)}|"
            f"moved_bookings={len(source_booking_rows)}|student={_student_label(student)}|"
            f"credit_changes=none|applied={args.apply}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
