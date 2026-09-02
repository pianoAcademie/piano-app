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
from app.models.user import ClientStatus, User, UserRole


SCRIPT_PREFIX = "RESTORE_PROD_PAUL_HENRI_ENROLLMENT"
TARGET_STUDENT_ID = UUID("4ef64d90-8afa-4852-8b24-71026835b649")
TARGET_QUOTE_ID = UUID("7c8faf2d-9a14-41f7-8a3f-cc776696369e")
TARGET_QUOTE_NUMBER = "DV-20260618092030-0BA5"
TARGET_INVOICE_NUMBER = "PA26-0664"
TARGET_INVOICE_NOTE_ID = UUID("88a335e1-0772-40dd-bf26-adc684b81a04")
TARGET_BILLING_ID = UUID("4a1594ec-3009-4471-8e22-84b0cb0017d9")
TARGET_TOTAL = Decimal("819.00")
EXECUTION_KEY = "quote_to_enrollment_execution"
TRANSFORMATION_KEY = "quote_to_enrollment"
CAPACITY_STATUSES = (BookingStatus.BOOKED, BookingStatus.PENDING_PAYMENT)
LEGACY_BOOKING_IDS = tuple(
    UUID(value)
    for value in (
        "27fb54bc-d68a-4567-a05d-a0ec25cf2e5b",
        "bdea64dc-7dba-4bed-9bd8-5ddce1f7cff5",
        "206619b7-cdbb-4bb1-b935-e0c6019ffd12",
        "c2368ecf-9707-49ac-a0b7-8c412d33468b",
        "cb74a468-ce3e-490c-8a8b-cb80fa31d68a",
        "80f92498-a920-45e0-9eaa-7d14f113b2c3",
        "25a04e3c-1cd3-4fe4-915a-79442bed0df5",
        "a0f90b5e-3bc1-4aa1-80de-ee13cf65450b",
        "227b8f93-e79c-4043-ac96-8f967b272ff0",
        "31934aee-9cd7-4970-bb0b-1553d73af94a",
        "5a4372fc-f1f9-4d52-89a6-8f38a6551a1a",
        "9c67576c-d58e-41d5-97ea-9016aaedefac",
        "f8070466-8a21-4c1c-ab41-438a89484ee7",
        "84428c00-832e-446c-a2f1-329386107727",
        "51fd4cc9-a4df-4246-aebe-b412e4c21162",
        "4a2146a1-265f-420d-80a4-29637c75beaf",
        "13f22cca-fb05-4e5f-bb22-9215b12eaf79",
        "358077f9-f19b-4d7a-99c7-0f7f478ef4b5",
        "2f8e2368-ed15-4c38-98a9-924ff9d2b712",
        "4cc4849b-04c0-4e2e-947e-6cf86b743c40",
        "526ccc66-8f23-4257-9070-b4d81054794a",
        "a80dcd21-89ac-4cdd-878b-9a21aff3ef8b",
        "1dc63de3-02fc-40b7-912e-a0bf38f52daf",
        "83fff0c4-e7f1-4132-9a3a-a0accd5dcefe",
        "e5cc9952-858d-4917-913f-97e3c0868227",
        "4764a9aa-2f74-42b2-9b6f-eaf6354cb45e",
        "037cc666-ff82-4671-8446-28f7a760d9da",
        "21df7a8c-fcfa-4db5-9f24-1a19cc756ece",
        "93724be1-ee05-4152-a1bc-fd3214225c11",
        "6fa082d6-99ed-401f-9089-014d0cf1e78e",
        "0cd0ccd4-fa6a-4ced-a6b8-c24ed701ffaf",
        "73a296c2-677d-4b8f-8e5d-abbfd13d5ee5",
    )
)


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

        invoice_note = db.scalar(
            select(ClientNoteEntry).where(ClientNoteEntry.id == TARGET_INVOICE_NOTE_ID).with_for_update()
        )
        if invoice_note is None or invoice_note.user_id != TARGET_BILLING_ID:
            print(f"[{SCRIPT_PREFIX}] abort=exact_annual_invoice_not_found")
            db.rollback()
            return

        invoice_meta = _invoice_metadata(invoice_note)
        invoice_number = str(invoice_meta.get("invoice_number") or "")
        invoice_status = str(invoice_meta.get("invoice_status") or "ISSUED").upper()
        invoice_to_pay = _money((invoice_meta.get("total_to_pay_by_currency") or {}).get("EUR"))
        if (
            invoice_number != TARGET_INVOICE_NUMBER
            or invoice_status not in {"ISSUED", "PAID", "CANCELLED"}
            or invoice_to_pay != TARGET_TOTAL
        ):
            print(
                f"[{SCRIPT_PREFIX}] abort=annual_invoice_metadata_mismatch|"
                f"invoice_number={invoice_number or '-'}|invoice_status={invoice_status}|"
                f"invoice_to_pay={invoice_to_pay}"
            )
            db.rollback()
            return
        invoice_source_quote_id = str(invoice_meta.get("source_quote_id") or "")
        if invoice_source_quote_id and invoice_source_quote_id != str(TARGET_QUOTE_ID):
            print(f"[{SCRIPT_PREFIX}] abort=annual_invoice_source_quote_mismatch")
            db.rollback()
            return

        execution_raw = (followup.payload or {}).get(EXECUTION_KEY)
        execution = execution_raw if isinstance(execution_raw, dict) else {}
        execution_status = str(execution.get("status") or "").lower()
        modern_execution = execution_status == "executed"
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
            booking_ids = list(LEGACY_BOOKING_IDS)
        if set(booking_ids) != set(LEGACY_BOOKING_IDS):
            print(f"[{SCRIPT_PREFIX}] abort=booking_ids_do_not_match_reviewed_invoice_export")
            db.rollback()
            return
        if not booking_ids:
            print(f"[{SCRIPT_PREFIX}] abort=no_invoice_or_execution_bookings")
            db.rollback()
            return

        bookings = db.scalars(
            select(Booking).where(Booking.id.in_(booking_ids)).with_for_update()
        ).all()
        replay_required = execution_status == "rolled_back" and not bookings
        if replay_required:
            transformation = (followup.payload or {}).get(TRANSFORMATION_KEY)
            if not isinstance(transformation, dict) or not transformation:
                print(f"[{SCRIPT_PREFIX}] abort=rolled_back_without_transformation_payload")
                db.rollback()
                return
            print(
                f"[{SCRIPT_PREFIX}] audit=quote_status={quote.status}|student_status={student.client_status.value}|"
                f"integration_trace=rolled_back_replay|historical_bookings={len(booking_ids)}|"
                f"historical_invoice_status={invoice_status}|action=replay_guarded_transformation"
            )
            if not args.apply:
                db.rollback()
                return

            admin_user = db.scalar(
                select(User)
                .where(User.role == UserRole.ADMIN, User.email == "admin@piano-academie.com")
                .with_for_update()
            )
            if admin_user is None:
                print(f"[{SCRIPT_PREFIX}] abort=system_admin_not_found")
                db.rollback()
                return

            prior_quote_status = str((execution.get("quote_snapshot") or {}).get("status") or "approved")
            if prior_quote_status in {"cancelled", "rejected", "replaced"}:
                prior_quote_status = "approved"
            quote.status = prior_quote_status
            quote.cancelled_at = None
            quote.updated_at = now
            from app.api.routes.quotes import _execute_quote_followup_transformation

            new_execution = _execute_quote_followup_transformation(
                db,
                quote=quote,
                followup=followup,
                current_user=admin_user,
            )
            db.add(
                QuoteEvent(
                    quote_id=quote.id,
                    event_type="enrollment_restored_admin_repair",
                    actor_type="system_repair",
                    actor_id=admin_user.id,
                    payload={
                        "notifications_sent": False,
                        "restoration_mode": "replayed_rolled_back_transformation",
                        "historical_invoice_number": TARGET_INVOICE_NUMBER,
                        "historical_invoice_status": invoice_status,
                        "created_booking_count": len(new_execution.get("created_booking_ids") or []),
                        "created_subscription_count": len(new_execution.get("created_subscription_ids") or []),
                        "created_invoice_count": len(new_execution.get("created_invoice_note_ids") or []),
                    },
                    created_at=now,
                )
            )
            db.commit()
            print(
                f"[{SCRIPT_PREFIX}] applied=true|mode=replayed_rolled_back_transformation|"
                f"bookings_created={len(new_execution.get('created_booking_ids') or [])}|"
                f"subscriptions_created={len(new_execution.get('created_subscription_ids') or [])}|"
                f"invoices_created={len(new_execution.get('created_invoice_note_ids') or [])}|"
                "notifications_sent=false"
            )
            return

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
                    "historical_invoice_status": invoice_status,
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
