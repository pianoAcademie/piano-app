from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import ClientPlanSubscription, SubscriptionStatus
from app.services.payment_checkout import lookup_payment
from app.services.payment_provider import PaymentProvider, detect_provider_from_reference, resolve_provider


def _subscription_payment_provider(db: Session, subscription: ClientPlanSubscription) -> PaymentProvider:
    raw_provider = (subscription.payment_provider_code or "").strip().upper()
    if raw_provider:
        try:
            return PaymentProvider(raw_provider)
        except ValueError:
            pass
    reference = (subscription.payment_provider_subscription_ref or "").strip()
    return detect_provider_from_reference(reference) or resolve_provider(db)


def has_unresolved_pending_plan_purchase(
    db: Session,
    *,
    user_id: UUID,
    plan_id: UUID,
) -> bool:
    """Reconcile stale one-off checkouts and report whether one is still unresolved.

    A pending checkout never grants usable credits. Failed or cancelled provider
    sessions are archived before a replacement checkout is created. An open,
    paid-but-not-yet-reconciled, or unverifiable checkout blocks a duplicate.
    The caller must already hold the user's purchase lock.
    """

    subscriptions = list(
        db.scalars(
            select(ClientPlanSubscription)
            .where(
                ClientPlanSubscription.user_id == user_id,
                ClientPlanSubscription.plan_id == plan_id,
                ClientPlanSubscription.status == SubscriptionStatus.PENDING,
            )
            .order_by(ClientPlanSubscription.created_at.asc(), ClientPlanSubscription.id.asc())
            .with_for_update()
        ).all()
    )
    unresolved = False
    for subscription in subscriptions:
        reference = (subscription.payment_provider_subscription_ref or "").strip()
        if not reference:
            unresolved = True
            continue

        lookup = lookup_payment(
            db,
            provider=_subscription_payment_provider(db, subscription),
            payment_reference=reference,
        )
        subscription.last_payment_status = (lookup.status or "UNKNOWN").strip().upper() or "UNKNOWN"
        if lookup.success and (lookup.failed or lookup.cancelled):
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.credits_remaining = 0
            subscription.auto_renew = False
            subscription.bookings_blocked = True
            subscription.next_payment_at = None
            db.add(subscription)
            continue

        unresolved = True
        db.add(subscription)

    return unresolved


__all__ = ["has_unresolved_pending_plan_purchase"]
