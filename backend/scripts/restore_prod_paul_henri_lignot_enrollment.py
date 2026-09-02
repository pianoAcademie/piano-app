from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.client_record import ClientNoteEntry
from app.models.plan import ClientPlanSubscription, SubscriptionStatus
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteEvent
from app.models.user import ClientStatus, User


SCRIPT_PREFIX = "RESTORE_PROD_PAUL_HENRI_ENROLLMENT"
TARGET_STUDENT_ID = UUID("4ef64d90-8afa-4852-8b24-71026835b649")
TARGET_QUOTE_ID = UUID("7c8faf2d-9a14-41f7-8a3f-cc776696369e")
TARGET_QUOTE_NUMBER = "DV-20260618092030-0BA5"
TARGET_INVOICE_NUMBER = "PA26-0664"
TARGET_TOTAL = Decimal("819.00")
EXECUTION_KEY = "quote_to_enrollment_execution"
CAPACITY_STATUSES = (BookingStatus.BOOKED, BookingStatus.PENDING_PAYMENT)


def _uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, list):
        return []
    result: list[UUID] = []
    for raw in value:
        try:
            result.append(UUID(str(raw)))
        except (TypeError, ValueError, AttributeError):
            continue
    return result


def _money(value: object) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _invoice_metadata(note: ClientNoteEntry) -> dict[str, object]:
    marker = "INVOICE_RANGE::"
    message = note.message or ""
    index = message.find(marker)
    if index < 0:
        return {}
    try:
        parsed = json.loads(message[index + len(marker) :].strip())
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and restore one previously integrated production enrollment. Dry-run by default."
    )
    parser.add_argument("--apply", action="store_true", help="Apply the repair after all safeguards pass.")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        print(f"[{SCRIPT_PREFIX}] dry_run={not args.apply}")
        quote = db.scalar(select(Quote).where(Quote.id == TARGET_QUOTE_ID).with_for_update())
        student = db.scalar(select(User).where(User.id == TARGET_STUDENT_ID).with_for_update())
        followup = db.scalar(
            select(QuoteAcceptanceFollowup)
            .where(QuoteAcceptanceFollowup.quote_id == TARGET_QUOTE_ID)
            .with_for_update()
        )

        if quote is None or student is None or followup is None:
            print(f"[{SCRIPT_PREFIX}] abort=missing_target_record")
            db.rollback()
            return
        if quote.quote_number != TARGET_QUOTE_NUMBER or quote.client_id != TARGET_STUDENT_ID:
            print(f"[{SCRIPT_PREFIX}] abort=quote_identity_mismatch")
            db.rollback()
            return
        if _money(quote.total_ttc) != TARGET_TOTAL or followup.target_client_id != TARGET_STUDENT_ID:
            print(f"[{SCRIPT_PREFIX}] abort=quote_amount_or_followup_target_mismatch")
            db.rollback()
            return

        invoice_rows = db.scalars(
            select(ClientNoteEntry).where(
                ClientNoteEntry.message.contains(TARGET_INVOICE_NUMBER),
                ClientNoteEntry.message.contains(str(TARGET_QUOTE_ID)),
            )
        ).all()
        if len(invoice_rows) != 1:
            print(f"[{SCRIPT_PREFIX}] abort=active_annual_invoice_not_found_exactly_once")
            db.rollback()
            return

        invoice_meta = _invoice_metadata(invoice_rows[0])
        if (
            str(invoice_meta.get("invoice_number") or "") != TARGET_INVOICE_NUMBER
            or str(invoice_meta.get("source_quote_id") or "") != str(TARGET_QUOTE_ID)
            or str(invoice_meta.get("invoice_status") or "ISSUED").upper() == "CANCELLED"
        ):
            print(f"[{SCRIPT_PREFIX}] abort=annual_invoice_metadata_mismatch")
            db.rollback()
            return

        execution_raw = (followup.payload or {}).get(EXECUTION_KEY)
        execution = execution_raw if isinstance(execution_raw, dict) else {}
        modern_execution = str(execution.get("status") or "").lower() == "executed"
        if modern_execution and str(execution.get("student_client_id") or "") != str(TARGET_STUDENT_ID):
            print(f"[{SCRIPT_PREFIX}] abort=execution_student_mismatch")
            db.rollback()
            return

        booking_ids = _uuid_list(execution.get("created_booking_ids")) if modern_execution else []
        if not booking_ids:
            booking_ids = _uuid_list(
                [
                    key.split(":", 1)[1]
                    for key in invoice_meta.get("included_payment_keys", [])
                    if isinstance(key, str) and key.startswith("BOOKING:")
                ]
            )
        if not booking_ids:
            print(f"[{SCRIPT_PREFIX}] abort=no_invoice_or_execution_bookings")
            db.rollback()
            return

        bookings = db.scalars(
            select(Booking).where(Booking.id.in_(booking_ids)).with_for_update()
        ).all()
        if len(bookings) != len(set(booking_ids)) or any(row.user_id != TARGET_STUDENT_ID for row in bookings):
            print(f"[{SCRIPT_PREFIX}] abort=booking_set_mismatch")
            db.rollback()
            return

        sessions = db.scalars(
            select(CourseSession).where(CourseSession.id.in_([row.session_id for row in bookings])).with_for_update()
        ).all()
        session_by_id = {row.id: row for row in sessions}
        if len(session_by_id) != len({row.session_id for row in bookings}):
            print(f"[{SCRIPT_PREFIX}] abort=session_set_mismatch")
            db.rollback()
            return

        subscription_ids = set(_uuid_list(execution.get("created_subscription_ids")))
        subscription_ids.update(
            row.client_plan_subscription_id for row in bookings if row.client_plan_subscription_id is not None
        )
        subscriptions = db.scalars(
            select(ClientPlanSubscription)
            .where(ClientPlanSubscription.id.in_(subscription_ids))
            .with_for_update()
        ).all() if subscription_ids else []
        if len(subscriptions) != len(subscription_ids):
            print(f"[{SCRIPT_PREFIX}] abort=subscription_set_mismatch")
            db.rollback()
            return

        restorable_bookings: list[Booking] = []
        skipped_cancelled_sessions = 0
        for booking in bookings:
            session = session_by_id[booking.session_id]
            if booking.status != BookingStatus.CANCELLED:
                continue
            if session.status == SessionStatus.CANCELLED:
                skipped_cancelled_sessions += 1
                continue
            if session.end_at_utc < now:
                continue
            occupied = db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.session_id == session.id,
                    Booking.status.in_(CAPACITY_STATUSES),
                    Booking.id != booking.id,
                )
            ) or 0
            if occupied >= session.capacity_max:
                print(f"[{SCRIPT_PREFIX}] abort=capacity_conflict session={session.id}")
                db.rollback()
                return
            restorable_bookings.append(booking)

        restorable_subscriptions = [
            row
            for row in subscriptions
            if row.status in {
                SubscriptionStatus.CANCELLED,
                SubscriptionStatus.TERMINATED,
                SubscriptionStatus.EXPIRED,
                SubscriptionStatus.PAUSED,
            }
        ]
        prior_quote_status = str((execution.get("quote_snapshot") or {}).get("status") or "approved")
        if prior_quote_status in {"cancelled", "rejected", "replaced"}:
            prior_quote_status = "approved"

        print(
            f"[{SCRIPT_PREFIX}] audit="
            f"quote_status={quote.status}|student_status={student.client_status.value}|"
            f"integration_trace={'modern' if modern_execution else 'legacy_invoice'}|"
            f"execution_bookings={len(bookings)}|bookings_to_restore={len(restorable_bookings)}|"
            f"cancelled_sessions_skipped={skipped_cancelled_sessions}|"
            f"subscriptions={len(subscriptions)}|subscriptions_to_restore={len(restorable_subscriptions)}|"
            f"invoice={TARGET_INVOICE_NUMBER}"
        )

        if not args.apply:
            db.rollback()
            return

        quote.status = prior_quote_status
        quote.cancelled_at = None
        quote.updated_at = now
        if student.client_status in {ClientStatus.INACTIVE, ClientStatus.ARCHIVED, ClientStatus.PENDING}:
            student.client_status = ClientStatus.ACTIVE
            student.updated_at = now

        for subscription in restorable_subscriptions:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.bookings_blocked = False
            subscription.updated_at = now

        for booking in restorable_bookings:
            booking.status = BookingStatus.BOOKED
            booking.cancelled_at = None
            booking.cancellation_reason = None

        db.add(
            QuoteEvent(
                quote_id=quote.id,
                event_type="enrollment_restored_admin_repair",
                actor_type="system_repair",
                payload={
                    "notifications_sent": False,
                    "restored_booking_ids": [str(row.id) for row in restorable_bookings],
                    "restored_subscription_ids": [str(row.id) for row in restorable_subscriptions],
                    "skipped_cancelled_session_count": skipped_cancelled_sessions,
                    "invoice_number": TARGET_INVOICE_NUMBER,
                },
                created_at=now,
            )
        )
        db.commit()
        print(
            f"[{SCRIPT_PREFIX}] applied=true|quote_status={quote.status}|"
            f"bookings_restored={len(restorable_bookings)}|subscriptions_restored={len(restorable_subscriptions)}|"
            "notifications_sent=false"
        )


if __name__ == "__main__":
    main()
