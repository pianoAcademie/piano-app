from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import (
    BOOKING_STATUSES_ACTIVE,
    BOOKING_STATUSES_COUNTED_AS_RESERVED,
    _bind_moved_contract,
    _move_planning_reorganization_booking_occurrence,
)
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, Location, Professor
from app.models.client_record import StudentQuoteChange
from app.models.user import User, UserRole
from app.services.makeup_accounting import makeup_role
from app.services.makeup_passes import revoke_pending_makeup_for_corrected_absence
from app.services.reminders import ensure_booking_reminder


SCRIPT = "MOVE_ELIE_ASTRUC_TO_FRIDAY_SCHEFFER_20260910"
STUDENT_ID = UUID("9ff1bb7f-dc22-45d1-9eb2-ab95bc36dfaf")
SOURCE_GROUP_ID = UUID("5c447ca4-b504-4930-8218-014706885b82")
TARGET_GROUP_ID = UUID("fafb558a-433d-4f01-8808-0452eebd379e")
EXPECTED_COUNT = 32
SOURCE_START = datetime(2026, 9, 9, tzinfo=timezone.utc)
TARGET_START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def abort(reason: str) -> None:
    raise SystemExit(f"[{SCRIPT}] {reason}")


def local_signature(session: CourseSession) -> tuple[str, str]:
    local = session.start_at_utc.astimezone(ZoneInfo("Europe/Paris"))
    return local.date().isoformat(), local.strftime("%H:%M")


def main() -> None:
    parser = argparse.ArgumentParser(description="Move Elie Astruc's full piano series to Friday 16:00 at Scheffer.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        student = db.scalar(select(User).where(User.id == STUDENT_ID).with_for_update())
        if student is None or student.first_name.strip().lower() != "elie" or student.last_name.strip().lower() != "astruc":
            abort("student_identity_guard_failed")

        source_rows = list(
            db.execute(
                select(Booking, CourseSession)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.user_id == STUDENT_ID,
                    Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                    CourseSession.recurrence_group_id == SOURCE_GROUP_ID,
                    CourseSession.start_at_utc >= SOURCE_START,
                )
                .order_by(CourseSession.start_at_utc)
                .with_for_update()
            ).all()
        )
        target_sessions = list(
            db.scalars(
                select(CourseSession)
                .where(
                    CourseSession.recurrence_group_id == TARGET_GROUP_ID,
                    CourseSession.start_at_utc >= TARGET_START,
                )
                .order_by(CourseSession.start_at_utc)
                .with_for_update()
            ).all()
        )
        if len(source_rows) != EXPECTED_COUNT or len(target_sessions) != EXPECTED_COUNT:
            abort(f"series_count_guard_failed source={len(source_rows)} target={len(target_sessions)}")

        source_first = source_rows[0][1]
        target_first = target_sessions[0]
        source_location = db.get(Location, source_first.location_id)
        target_location = db.get(Location, target_first.location_id)
        source_professor = db.get(Professor, source_first.professor_id) if source_first.professor_id else None
        target_professor = db.get(Professor, target_first.professor_id) if target_first.professor_id else None
        if (
            source_location is None
            or "pompe" not in source_location.name.lower()
            or source_professor is None
            or "malaika" not in source_professor.first_name.lower()
            or target_location is None
            or "scheffer" not in target_location.name.lower()
            or target_professor is None
            or "elena" not in target_professor.first_name.lower().replace("é", "e")
        ):
            abort("series_identity_guard_failed")
        if local_signature(source_first) != ("2026-09-09", "16:00"):
            abort(f"source_anchor_guard_failed actual={local_signature(source_first)}")
        if local_signature(target_first) != ("2026-09-11", "16:00"):
            abort(f"target_anchor_guard_failed actual={local_signature(target_first)}")

        first_booking = source_rows[0][0]
        if first_booking.status != BookingStatus.EXCUSED_ABSENCE:
            abort(f"first_status_guard_failed actual={first_booking.status}")
        if makeup_role(first_booking) != "original":
            abort(f"first_makeup_guard_failed actual={makeup_role(first_booking)}")
        if any(booking.status != BookingStatus.BOOKED for booking, _ in source_rows[1:]):
            abort("future_booking_status_guard_failed")

        existing_target = db.scalar(
            select(func.count())
            .select_from(Booking)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == STUDENT_ID,
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                CourseSession.recurrence_group_id == TARGET_GROUP_ID,
            )
        )
        if existing_target:
            abort(f"target_already_booked count={existing_target}")

        for target in target_sessions:
            reserved = db.scalar(
                select(func.count())
                .select_from(Booking)
                .where(
                    Booking.session_id == target.id,
                    Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED),
                )
            )
            if int(reserved or 0) >= target.capacity_max:
                abort(f"target_full session={target.id} reserved={reserved} capacity={target.capacity_max}")

        price_changes = [
            (booking.id, booking.total_incl_vat_snapshot)
            for booking, _ in source_rows
            if Decimal(booking.total_incl_vat_snapshot) != Decimal("36.00")
            or str(booking.currency_snapshot).upper() != "EUR"
        ]
        if price_changes:
            abort(f"source_price_guard_failed {price_changes[:3]}")

        actor = db.scalar(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at).limit(1))
        if actor is None:
            abort("admin_actor_missing")

        print(
            f"[{SCRIPT}] mode={'apply' if args.apply else 'dry-run'} student=Elie_Astruc "
            f"move={EXPECTED_COUNT} source=Wednesday_16_Pompe target=Friday_16_Scheffer_Elena "
            f"source_first={source_first.start_at_utc.isoformat()} target_first={target_first.start_at_utc.isoformat()} "
            f"target_last={target_sessions[-1].start_at_utc.isoformat()} invoice_change=0 notification=false"
        )
        if not args.apply:
            db.rollback()
            print(f"[{SCRIPT}] committed=false")
            return

        if not revoke_pending_makeup_for_corrected_absence(db, booking=first_booking, now=now):
            abort("pending_makeup_revoke_failed")
        first_booking.status = BookingStatus.BOOKED
        first_booking.cancelled_at = None
        first_booking.cancellation_reason = None

        moved_count = 0
        for index, ((booking, source_session), target_session) in enumerate(
            zip(source_rows, target_sessions, strict=True)
        ):
            _bind_moved_contract(db, booking, target_session, "series_future")
            moved, detail = _move_planning_reorganization_booking_occurrence(
                db,
                booking=booking,
                source_session=source_session,
                target_session=target_session,
                now=now,
                target_price_snapshot=None,
                lock_price_snapshot=True,
            )
            if not moved:
                abort(f"move_failed index={index} booking={booking.id} detail={detail}")
            if index == 0:
                ensure_booking_reminder(db, booking=booking, session_obj=target_session, now=now)
            moved_count += 1

        db.add(
            StudentQuoteChange(
                user_id=STUDENT_ID,
                student_user_id=STUDENT_ID,
                actor_user_id=actor.id,
                change_type="SLOT_CHANGE",
                status="VALIDATED",
                effective_date=target_first.start_at_utc.date(),
                title="Déplacement de 32 séances vers le vendredi 16 h rue Scheffer — tarif conservé",
                description=(
                    "Transfert de toute la série de piano du mercredi 16 h rue de la Pompe vers le vendredi "
                    "16 h rue Scheffer avec Eléna Ortu, à partir du 11 septembre 2026. Le cours du 9 septembre "
                    "n'ayant pas été suivi, sa réservation a été transférée sur le 11 septembre. Facturation "
                    "et tarif existants conservés; aucun message envoyé."
                ),
                before_snapshot={
                    "source_group_id": str(SOURCE_GROUP_ID),
                    "source_booking_ids": [str(booking.id) for booking, _ in source_rows],
                },
                after_snapshot={
                    "target_group_id": str(TARGET_GROUP_ID),
                    "target_session_ids": [str(session.id) for session in target_sessions],
                },
                financial_impact_ttc=Decimal("0.00"),
                currency="EUR",
                billing_action="NONE",
            )
        )
        db.commit()

    with SessionLocal() as verify:
        source_remaining = verify.scalar(
            select(func.count())
            .select_from(Booking)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == STUDENT_ID,
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                CourseSession.recurrence_group_id == SOURCE_GROUP_ID,
            )
        )
        target_rows = list(
            verify.execute(
                select(Booking, CourseSession)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.user_id == STUDENT_ID,
                    Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                    CourseSession.recurrence_group_id == TARGET_GROUP_ID,
                )
                .order_by(CourseSession.start_at_utc)
            ).all()
        )
        if int(source_remaining or 0) != 0 or len(target_rows) != EXPECTED_COUNT:
            abort(f"postcheck_count_failed source={source_remaining} target={len(target_rows)}")
        if any(booking.status != BookingStatus.BOOKED for booking, _ in target_rows):
            abort("postcheck_status_failed")
        if local_signature(target_rows[0][1]) != ("2026-09-11", "16:00"):
            abort("postcheck_first_target_failed")
        print(
            f"[{SCRIPT}] committed=true moved={moved_count} source_remaining=0 target_bookings=32 "
            "makeup_credit_restored=true invoice_change=0 notification=false"
        )


if __name__ == "__main__":
    main()
