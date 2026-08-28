from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, Location, SessionStatus
from app.models.client_record import ClientManualCreditBalance, PaymentReceipt
from app.models.notification_engine import DomainEvent
from app.models.plan import ClientPlanSubscription, Plan, PlanKind
from app.models.user import User
from app.services.reminders import ensure_booking_reminder
from app.services.session_automation import DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY


SCRIPT_PREFIX = "PROD_REPAIR_ASSAS_THURSDAY_17_SLOT"
TARGET_LOCAL_START = datetime(2026, 9, 10, 17, 0, tzinfo=ZoneInfo("Europe/Paris"))
TARGET_START_UTC = TARGET_LOCAL_START.astimezone(timezone.utc)
EXPECTED_LOCATION_FRAGMENT = "assas"
EXPECTED_TITLE_FRAGMENT = "enfant"
EXPECTED_BOOKING_CANCELLATION_REASON = "ADMIN_SESSION_CANCELLED"
REPAIR_EVENT_TYPE = "slot_reactivated_by_admin_repair"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _student_label(user: User) -> str:
    full_name = " ".join(part.strip() for part in (user.first_name or "", user.last_name or "") if part.strip())
    return full_name or str(user.id)


def _undo_restored_credit(db, *, booking: Booking, now: datetime) -> list[str]:  # noqa: ANN001
    changes: list[str] = []
    restored_via_subscription_or_manual = False

    if booking.client_plan_subscription_id is not None:
        row = db.execute(
            select(ClientPlanSubscription, Plan)
            .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
            .where(ClientPlanSubscription.id == booking.client_plan_subscription_id)
            .with_for_update()
        ).first()
        if row is None:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=subscription_not_found")
        subscription, plan = row
        if subscription.user_id != booking.user_id:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=subscription_owner_mismatch")
        if plan.kind == PlanKind.PACK:
            current = int(subscription.credits_remaining or 0)
            if current <= 0:
                raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=pack_credit_not_available_to_reconsume")
            subscription.credits_remaining = current - 1
            changes.append(f"pack_credit:{current}->{current - 1}")
            restored_via_subscription_or_manual = True

    if booking.manual_credit_type_id is not None:
        balance = db.scalar(
            select(ClientManualCreditBalance)
            .where(
                ClientManualCreditBalance.user_id == booking.user_id,
                ClientManualCreditBalance.credit_type_id == booking.manual_credit_type_id,
            )
            .with_for_update()
        )
        if balance is None or int(balance.credits_count or 0) <= 0:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=manual_credit_not_available_to_reconsume")
        current = int(balance.credits_count or 0)
        balance.credits_count = current - 1
        balance.updated_at = now
        changes.append(f"manual_credit:{current}->{current - 1}")
        restored_via_subscription_or_manual = True

    if restored_via_subscription_or_manual:
        return changes

    receipts = db.scalars(
        select(PaymentReceipt)
        .where(PaymentReceipt.booking_id == booking.id)
        .order_by(PaymentReceipt.created_at.asc(), PaymentReceipt.id.asc())
        .with_for_update()
    ).all()
    marked_receipts = [
        receipt
        for receipt in receipts
        if DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY in dict(receipt.receipt_metadata or {})
    ]
    if not marked_receipts:
        return changes
    if len(marked_receipts) != 1:
        raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=unexpected_direct_credit_markers|count={len(marked_receipts)}")

    receipt = marked_receipts[0]
    metadata = dict(receipt.receipt_metadata or {})
    raw_credit_type_id = str(metadata.get("cancelled_booking_credit_type_id") or "").strip()
    try:
        credit_type_id = UUID(raw_credit_type_id)
    except ValueError as exc:
        raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=invalid_direct_credit_type_marker") from exc
    balance = db.scalar(
        select(ClientManualCreditBalance)
        .where(
            ClientManualCreditBalance.user_id == booking.user_id,
            ClientManualCreditBalance.credit_type_id == credit_type_id,
        )
        .with_for_update()
    )
    if balance is None or int(balance.credits_count or 0) <= 0:
        raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=direct_credit_not_available_to_reconsume")
    current = int(balance.credits_count or 0)
    balance.credits_count = current - 1
    balance.updated_at = now
    metadata.pop(DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY, None)
    metadata.pop("cancelled_booking_credit_type_id", None)
    receipt.receipt_metadata = metadata
    receipt.updated_at = now
    changes.append(f"direct_paid_credit:{current}->{current - 1}")
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reactivate only the cancelled Rue d'Assas lesson on 10 September 2026 at 17:00 and its one student."
    )
    parser.add_argument("--apply", action="store_true", help="Commit the guarded repair. Without it, audit only.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return successfully when the exact target does not exist (used by the one-time data migration in non-production databases).",
    )
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        rows = db.execute(
            select(CourseSession, Location)
            .join(Location, Location.id == CourseSession.location_id)
            .where(CourseSession.start_at_utc == TARGET_START_UTC)
            .order_by(CourseSession.id.asc())
            .with_for_update()
        ).all()
        matching_sessions = [
            (session_obj, location)
            for session_obj, location in rows
            if EXPECTED_LOCATION_FRAGMENT in (location.name or "").strip().lower()
            and EXPECTED_TITLE_FRAGMENT in (session_obj.title or "").strip().lower()
        ]
        cancelled_candidates = [
            (session_obj, location)
            for session_obj, location in matching_sessions
            if session_obj.status == SessionStatus.CANCELLED
        ]
        candidates = cancelled_candidates
        if not candidates:
            repaired_session_ids = set(
                db.scalars(
                    select(DomainEvent.related_entity_id).where(
                        DomainEvent.event_type == REPAIR_EVENT_TYPE,
                        DomainEvent.related_entity_type == "slot",
                        DomainEvent.related_entity_id.in_([session_obj.id for session_obj, _ in matching_sessions]),
                    )
                ).all()
            )
            candidates = [
                (session_obj, location)
                for session_obj, location in matching_sessions
                if session_obj.id in repaired_session_ids
            ]
        if not candidates and args.allow_missing:
            db.rollback()
            print(
                f"{SCRIPT_PREFIX}|summary|result=target_missing_noop|"
                f"all_at_time={len(rows)}|applied={args.apply}"
            )
            return 0
        if len(candidates) != 1:
            for candidate_session, candidate_location in matching_sessions:
                booking_count = len(
                    db.scalars(select(Booking.id).where(Booking.session_id == candidate_session.id)).all()
                )
                print(
                    f"{SCRIPT_PREFIX}|candidate|session_id={candidate_session.id}|"
                    f"title={candidate_session.title}|location={candidate_location.name}|"
                    f"status={_enum_value(candidate_session.status)}|reason={candidate_session.cancel_reason or '-'}|"
                    f"recurrence_group_id={candidate_session.recurrence_group_id or '-'}|bookings={booking_count}"
                )
            raise SystemExit(
                f"{SCRIPT_PREFIX}|abort|reason=expected_one_session|found={len(candidates)}|"
                f"all_at_time={len(rows)}|start_utc={TARGET_START_UTC.isoformat()}"
            )
        session_obj, location = candidates[0]

        bookings = db.scalars(
            select(Booking)
            .where(Booking.session_id == session_obj.id)
            .order_by(Booking.booked_at.asc(), Booking.id.asc())
            .with_for_update()
        ).all()
        if len(bookings) != 1:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=expected_one_booking|found={len(bookings)}")
        booking = bookings[0]
        student = db.get(User, booking.user_id)
        if student is None:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=student_not_found")

        latest_cancel_event = db.scalar(
            select(DomainEvent)
            .where(
                DomainEvent.event_type == "slot_cancelled",
                DomainEvent.related_entity_type == "slot",
                DomainEvent.related_entity_id == session_obj.id,
            )
            .order_by(DomainEvent.occurred_at.desc(), DomainEvent.created_at.desc())
        )
        print(
            f"{SCRIPT_PREFIX}|audit|session_id={session_obj.id}|title={session_obj.title}|"
            f"location={location.name}|local_start={TARGET_LOCAL_START.isoformat()}|"
            f"session_status={_enum_value(session_obj.status)}|session_reason={session_obj.cancel_reason or '-'}|"
            f"booking_id={booking.id}|student={_student_label(student)}|"
            f"booking_status={_enum_value(booking.status)}|booking_reason={booking.cancellation_reason or '-'}|"
            f"cancel_event_at={latest_cancel_event.occurred_at.isoformat() if latest_cancel_event else '-'}|"
            f"cancel_actor_id={latest_cancel_event.actor_id if latest_cancel_event else '-'}"
        )

        already_repaired = session_obj.status == SessionStatus.SCHEDULED and booking.status == BookingStatus.BOOKED
        if already_repaired:
            ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(f"{SCRIPT_PREFIX}|summary|result=already_repaired|applied={args.apply}")
            return 0

        if session_obj.status != SessionStatus.CANCELLED:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=unexpected_session_status|status={_enum_value(session_obj.status)}")
        if booking.status != BookingStatus.CANCELLED:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=unexpected_booking_status|status={_enum_value(booking.status)}")
        if (booking.cancellation_reason or "").strip().upper() != EXPECTED_BOOKING_CANCELLATION_REASON:
            raise SystemExit(
                f"{SCRIPT_PREFIX}|abort|reason=unexpected_booking_cancellation_reason|"
                f"value={booking.cancellation_reason or '-'}"
            )
        if latest_cancel_event is None:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=missing_slot_cancel_event")

        credit_changes = _undo_restored_credit(db, booking=booking, now=now)
        session_obj.status = SessionStatus.SCHEDULED
        session_obj.cancel_reason = None
        session_obj.updated_at = now
        booking.status = BookingStatus.BOOKED
        booking.cancelled_at = None
        booking.cancellation_reason = None
        booking.payment_hold_expires_at = None
        ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)
        db.add(
            DomainEvent(
                event_type=REPAIR_EVENT_TYPE,
                source="admin_repair",
                actor_type="system",
                actor_id=None,
                related_entity_type="slot",
                related_entity_id=session_obj.id,
                occurred_at=now,
                payload_json={
                    "slot_id": str(session_obj.id),
                    "booking_id": str(booking.id),
                    "student_id": str(booking.user_id),
                    "previous_slot_cancel_event_id": str(latest_cancel_event.id),
                    "credit_changes": credit_changes,
                },
            )
        )
        db.flush()

        if session_obj.status != SessionStatus.SCHEDULED or booking.status != BookingStatus.BOOKED:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=post_repair_state_invalid")
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(
            f"{SCRIPT_PREFIX}|summary|result=reactivated|student={_student_label(student)}|"
            f"credit_changes={','.join(credit_changes) if credit_changes else 'none'}|applied={args.apply}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
