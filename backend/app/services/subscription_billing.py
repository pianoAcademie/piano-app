from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import ClientPlanSubscription, Plan, PlanKind, PlanPriceTaxMode, SubscriptionStatus
from app.models.user import User
from app.services.family_billing import resolve_billing_profile
from app.services.payment_provider import PaymentProvider, resolve_active_secret, resolve_mode, resolve_provider
from app.services.pricing import compute_tax_totals, resolve_plan_price, resolve_vat_rate, plan_service_code
from app.services.psp_gateway import MollieGateway, PayplugGateway, RecurringChargeRequest
from app.services.subscriptions import add_months_utc, default_next_payment_at, reconcile_subscription_status


@dataclass(frozen=True)
class SubscriptionBillingJobResult:
    checked: int
    charged: int
    skipped: int
    failed: int


def run_subscription_billing_job(db: Session, *, now: datetime, limit: int = 500) -> SubscriptionBillingJobResult:
    provider = resolve_provider(db)
    active_secret = resolve_active_secret(db)
    gateway = MollieGateway(api_key=active_secret, mode=resolve_mode(db)) if provider == PaymentProvider.MOLLIE else PayplugGateway()

    rows = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(Plan.kind == PlanKind.SUBSCRIPTION)
        .order_by(ClientPlanSubscription.next_payment_at.asc().nullsfirst(), ClientPlanSubscription.created_at.asc())
        .limit(limit)
    ).all()

    checked = 0
    charged = 0
    skipped = 0
    failed = 0

    for subscription, plan, owner in rows:
        checked += 1

        if reconcile_subscription_status(subscription, now=now, plan_kind=plan.kind):
            db.add(subscription)

        if not subscription.auto_renew:
            skipped += 1
            continue
        if subscription.status != SubscriptionStatus.ACTIVE:
            skipped += 1
            continue
        if subscription.billing_method_code != "CARD_ONLINE":
            skipped += 1
            continue
        if provider != PaymentProvider.MOLLIE:
            subscription.last_payment_status = "SKIPPED_PROVIDER_NOT_MOLLIE"
            db.add(subscription)
            skipped += 1
            continue

        due_at = subscription.next_payment_at or subscription.ends_at or default_next_payment_at(subscription.started_at)
        subscription.next_payment_at = due_at
        if due_at > now:
            db.add(subscription)
            skipped += 1
            continue

        billing_profile = resolve_billing_profile(db, owner)
        country_code = (billing_profile.residence_country or "FR").upper()
        preferred_currency = (billing_profile.preferred_currency or "EUR").upper()
        vat_rate = resolve_vat_rate(
            db,
            country=country_code,
            service_code=plan_service_code(plan.kind.value),
            on_date=now.date(),
        )

        price_excl_vat: Decimal | None = None
        currency_code = (plan.currency_code or preferred_currency).upper()
        if plan.monthly_price_value is not None:
            raw_price = Decimal(plan.monthly_price_value)
            if plan.price_tax_mode == PlanPriceTaxMode.TTC:
                divisor = Decimal("1") + (vat_rate / Decimal("100"))
                price_excl_vat = raw_price if divisor <= 0 else (raw_price / divisor)
            else:
                price_excl_vat = raw_price
        elif plan.monthly_price_excl_vat is not None:
            price_excl_vat = Decimal(plan.monthly_price_excl_vat)
        else:
            resolved_price = resolve_plan_price(
                db,
                plan_id=plan.id,
                country=country_code,
                currency=preferred_currency,
                on_date=now.date(),
            )
            if resolved_price is not None:
                price_excl_vat = Decimal(resolved_price.price_excl_vat)
                currency_code = resolved_price.currency_code

        if price_excl_vat is None:
            subscription.last_payment_status = "FAILED_NO_PRICE"
            db.add(subscription)
            failed += 1
            continue

        _, _, total_incl_vat = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)

        result = gateway.create_recurring_charge(
            RecurringChargeRequest(
                amount=total_incl_vat,
                currency=currency_code,
                description=f"{plan.name} - renouvellement mensuel",
                customer_reference=subscription.payment_provider_customer_ref,
                mandate_reference=subscription.payment_provider_mandate_ref,
            )
        )

        subscription.last_payment_at = now
        subscription.last_payment_status = result.status
        if result.success:
            next_due = add_months_utc(due_at, 1)
            subscription.next_payment_at = next_due
            subscription.ends_at = next_due
            charged += 1
        else:
            failed += 1
        db.add(subscription)

    return SubscriptionBillingJobResult(
        checked=checked,
        charged=charged,
        skipped=skipped,
        failed=failed,
    )
