from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus
from app.models.client_record import ClientNoteEntry
from app.models.plan import ClientPlanSubscription, Plan, SubscriptionStatus
from app.models.user import User
from app.services.automation_triggers import cancel_pending_trial_attended_triggers
from app.services.payment_checkout import lookup_payment
from app.services.payment_provider import PaymentProvider

SCRIPT_PREFIX = "PROD_REPAIR_HERYA_TRIAL_PURCHASE"
USER_ID = UUID("ce692442-0ca6-4005-a4fb-9f3d5c88448b")
BOOKING_ID = UUID("461a8109-dc72-4aa1-890e-5c0f0e50a4ee")
PAID_SUBSCRIPTION_ID = UUID("8728143c-8257-4409-a512-e65acc5ff768")
FAILED_SUBSCRIPTIONS = {
    UUID("707dceb8-52a2-49a7-baf9-79bcb99be2a4"): "pay_4kje4fnrO5QMLOJ0wFtJSB",
    UUID("c945a06d-f0ad-4a44-a7da-27a780c2a480"): "pay_6UF7VI5AfgcejqMusdePJP",
}
PAID_REFERENCE = "pay_2OJThxN0jZCaAaneHHV6Mk"
AUDIT_MESSAGE = (
    "Correction administrative du cours d'essai : séance non effectuée, crédit payé restauré à 1/1 "
    "et deux tentatives de paiement PayPlug échouées archivées."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_and_assert(db):
    user = db.scalar(select(User).where(User.id == USER_ID).with_for_update())
    booking = db.scalar(select(Booking).where(Booking.id == BOOKING_ID).with_for_update())
    rows = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(ClientPlanSubscription.user_id == USER_ID)
        .with_for_update()
    ).all()
    by_id = {subscription.id: (subscription, plan) for subscription, plan in rows}
    expected_ids = {PAID_SUBSCRIPTION_ID, *FAILED_SUBSCRIPTIONS.keys()}
    if user is None or booking is None or set(by_id) != expected_ids:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target rows are missing or unexpected")
    if user.email.strip().lower() != "heryarosie9@gmail.com":
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected user email: {user.email}")

    paid, paid_plan = by_id[PAID_SUBSCRIPTION_ID]
    if paid_plan.name.strip() != "Cours d'essai de piano en présentiel":
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected paid plan: {paid_plan.name}")
    if paid.status != SubscriptionStatus.ACTIVE or paid.credits_initial != 1:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected paid subscription state")
    if (paid.payment_provider_subscription_ref or "").strip() != PAID_REFERENCE:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected paid payment reference")
    if (paid.last_payment_status or "").strip().upper() != "PAID":
        raise SystemExit(f"[{SCRIPT_PREFIX}] paid subscription is not marked paid")
    if booking.user_id != USER_ID or booking.client_plan_subscription_id != paid.id or not booking.is_trial_course:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected booking ownership")
    if booking.status not in {BookingStatus.ATTENDED, BookingStatus.CANCELLED}:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected booking status: {booking.status.value}")
    if paid.credits_remaining not in {0, 1}:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected paid credits: {paid.credits_remaining}")

    failed: list[tuple[ClientPlanSubscription, str]] = []
    for subscription_id, expected_reference in FAILED_SUBSCRIPTIONS.items():
        subscription, plan = by_id[subscription_id]
        if plan.id != paid_plan.id or plan.name != paid_plan.name:
            raise SystemExit(f"[{SCRIPT_PREFIX}] duplicate does not use the paid trial plan")
        if subscription.status not in {SubscriptionStatus.PENDING, SubscriptionStatus.CANCELLED}:
            raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected duplicate status: {subscription.status.value}")
        if (subscription.payment_provider_subscription_ref or "").strip() != expected_reference:
            raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected duplicate payment reference")
        lookup = lookup_payment(
            db,
            provider=PaymentProvider.PAYPLUG,
            payment_reference=expected_reference,
        )
        print(
            f"[{SCRIPT_PREFIX}] provider={expected_reference}|status={lookup.status}|"
            f"paid={lookup.paid}|failed={lookup.failed}|cancelled={lookup.cancelled}"
        )
        if not lookup.success or lookup.paid or not (lookup.failed or lookup.cancelled):
            raise SystemExit(f"[{SCRIPT_PREFIX}] provider state is not safely archivable: {expected_reference}")
        failed.append((subscription, (lookup.status or "FAILED").strip().upper() or "FAILED"))
    return user, booking, paid, failed


def run(*, apply: bool) -> None:
    with SessionLocal() as db:
        user, booking, paid, failed = _load_and_assert(db)
        now = _utcnow()
        changes: list[str] = []

        if booking.status != BookingStatus.CANCELLED:
            changes.append(f"booking.status:{booking.status.value}->CANCELLED")
            if apply:
                cancel_pending_trial_attended_triggers(db, booking_id=booking.id, now=now)
                booking.status = BookingStatus.CANCELLED
                booking.cancelled_at = now
                booking.cancellation_reason = "Correction administrative : cours d'essai non effectué"
                db.add(booking)
        if paid.credits_remaining != 1:
            changes.append(f"paid_subscription.credits:{paid.credits_remaining}->1")
            if apply:
                paid.credits_remaining = 1
                paid.bookings_blocked = False
                db.add(paid)

        for subscription, provider_status in failed:
            if subscription.status != SubscriptionStatus.CANCELLED or subscription.credits_remaining != 0:
                changes.append(f"failed_subscription.{subscription.id}:archive")
                if apply:
                    subscription.status = SubscriptionStatus.CANCELLED
                    subscription.credits_remaining = 0
                    subscription.auto_renew = False
                    subscription.bookings_blocked = True
                    subscription.next_payment_at = None
                    subscription.last_payment_status = provider_status
                    db.add(subscription)

        existing_note = db.scalar(
            select(ClientNoteEntry.id).where(
                ClientNoteEntry.user_id == user.id,
                ClientNoteEntry.message == AUDIT_MESSAGE,
            )
        )
        if existing_note is None:
            changes.append("audit_note:create")
            if apply:
                db.add(
                    ClientNoteEntry(
                        user_id=user.id,
                        author_user_id=None,
                        entry_type="AUTO",
                        message=AUDIT_MESSAGE,
                        created_at=now,
                    )
                )

        if apply:
            db.commit()
        else:
            db.rollback()
        print(f"[{SCRIPT_PREFIX}] mode={'APPLY' if apply else 'DRY_RUN'}")
        print(f"[{SCRIPT_PREFIX}] changes={changes or ['none']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(apply=args.apply)
