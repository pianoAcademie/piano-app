from __future__ import annotations

import json
import hashlib
import hmac
from datetime import datetime, timezone
from decimal import Decimal
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionLocal, get_db
from app.api.routes.admin_clients import (
    _postprocess_invoice_range_public_payment,
    handle_admin_client_payment_receipt_public_payment_webhook,
    handle_admin_client_range_invoice_public_payment_webhook,
    reconcile_admin_client_range_invoice_public_payment_by_provider_reference,
    return_admin_client_payment_receipt_public_payment,
    return_admin_client_range_invoice_public_payment,
    start_admin_client_payment_receipt_public_payment,
    start_admin_client_range_invoice_public_bank_transfer,
    start_admin_client_range_invoice_public_card_payment,
    start_admin_client_range_invoice_public_payment,
)
from app.api.routes.events import reconcile_event_payment_by_provider_reference
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.subscription_engine import SubscriptionBillingCycle
from app.models.user import User
from app.services.client_purchase_notifications import (
    plan_purchase_notification_label,
    send_client_payment_success_notifications,
    send_plan_purchase_admin_notifications,
)
from app.services.automation_triggers import schedule_plan_purchase_triggers
from app.services.family_billing import resolve_billing_profile
from app.services.notifications.application.orchestrator import enqueue_notifications
from app.services.payment_checkout import lookup_payment
from app.services.payment_provider import (
    PaymentProvider,
    detect_provider_from_reference,
    resolve_provider,
    resolve_stripe_webhook_secret,
    resolve_webhook_secret,
)
from app.services.subscriptions import add_months_utc

router = APIRouter(prefix="/public/payments")
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_reference(request: Request, payload: object) -> str | None:
    if isinstance(payload, dict):
        # Stripe wraps the billable object in ``data.object`` and gives the
        # webhook event itself an ``evt_`` id. Always reconcile the nested
        # Checkout Session / PaymentIntent, never the event id.
        data_node = payload.get("data")
        if isinstance(data_node, dict):
            object_node = data_node.get("object")
            if isinstance(object_node, dict):
                for key in ("payment_id", "paymentId", "id"):
                    value = object_node.get(key)
                    if value:
                        return str(value).strip()
        # Refund notifications contain both the refund id (``id``) and the
        # original payment id. Reconciliation must always use the payment id.
        for key in ("payment_id", "paymentId", "id"):
            value = payload.get(key)
            if value:
                return str(value).strip()
        if isinstance(data_node, dict):
            for key in ("payment_id", "paymentId", "id"):
                value = data_node.get(key)
                if value:
                    return str(value).strip()
    if request.query_params.get("id"):
        return str(request.query_params.get("id")).strip()
    form_id = request.query_params.get("payment_id")
    if form_id:
        return str(form_id).strip()
    return None


def _metadata_uuid(metadata: dict[str, str], key: str) -> UUID | None:
    raw = (metadata.get(key) or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _verify_stripe_webhook_signature(
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    now_timestamp: int | None = None,
    tolerance_seconds: int = 300,
) -> bool:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in (signature_header or "").split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return False
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures or not webhook_secret:
        return False
    current = now_timestamp if now_timestamp is not None else int(_utcnow().timestamp())
    if abs(current - timestamp) > tolerance_seconds:
        return False
    signed_payload = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    client_id: UUID | None = Query(default=None),
    subscription_id: UUID | None = Query(default=None),
    cycle_id: UUID | None = Query(default=None),
    token: str | None = Query(default=None),
) -> dict[str, object]:
    db: Session = SessionLocal()
    try:
        configured = resolve_webhook_secret(db)
        if token != configured:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook token")

        raw_body = await request.body()
        payload: object = {}
        if raw_body:
            body_text = raw_body.decode("utf-8", errors="ignore")
            try:
                payload = json.loads(body_text)
            except Exception:
                payload = {}
        if isinstance(payload, dict) and str(payload.get("id") or "").startswith("evt_"):
            stripe_webhook_secret = resolve_stripe_webhook_secret(db)
            if not _verify_stripe_webhook_signature(
                raw_body,
                request.headers.get("Stripe-Signature", ""),
                stripe_webhook_secret,
            ):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Stripe webhook signature")

        payment_reference = _extract_reference(request, payload)
        preloaded_lookup = None
        if subscription_id is None:
            if not payment_reference:
                return {"ok": True, "processed": False, "reason": "missing_payment_reference"}
            provider = detect_provider_from_reference(payment_reference) or resolve_provider(db)
            lookup = lookup_payment(db, provider=provider, payment_reference=payment_reference)
            preloaded_lookup = lookup
            event_group_id = _metadata_uuid(lookup.metadata, "event_registration_group_id")
            if event_group_id is not None:
                return reconcile_event_payment_by_provider_reference(
                    db,
                    group_id=event_group_id,
                    payment_reference=lookup.provider_reference or payment_reference,
                    preloaded_lookup=lookup,
                )
            invoice_client_id = _metadata_uuid(lookup.metadata, "client_id")
            invoice_note_id = _metadata_uuid(lookup.metadata, "note_id")
            if invoice_client_id is not None and invoice_note_id is not None:
                result = reconcile_admin_client_range_invoice_public_payment_by_provider_reference(
                    db,
                    client_id=invoice_client_id,
                    note_id=invoice_note_id,
                    provider_reference=lookup.provider_reference or payment_reference,
                    defer_postprocessing=True,
                )
                if bool(result.get("paid")):
                    background_tasks.add_task(
                        _postprocess_invoice_range_public_payment,
                        client_id=invoice_client_id,
                        note_id=invoice_note_id,
                    )
                return result
            subscription_id = _metadata_uuid(lookup.metadata, "subscription_id")
            client_id = client_id or _metadata_uuid(lookup.metadata, "client_id")
            cycle_id = cycle_id or _metadata_uuid(lookup.metadata, "cycle_id")
            if subscription_id is None:
                return {"ok": True, "processed": False, "reason": "missing_subscription_id"}

        sub = db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id).with_for_update())
        if sub is None:
            return {"ok": True, "processed": False, "reason": "subscription_not_found"}
        if client_id is not None and sub.user_id != client_id:
            return {"ok": True, "processed": False, "reason": "client_mismatch"}
        if (
            preloaded_lookup is not None
            and preloaded_lookup.setup_complete
            and preloaded_lookup.payment_method_type == "sepa_debit"
            and preloaded_lookup.payment_method_reference
            and (preloaded_lookup.metadata.get("source") or "").strip().upper() == "SEPA_SETUP"
        ):
            sub.payment_provider_code = PaymentProvider.STRIPE.value
            sub.payment_provider_payment_method_ref = preloaded_lookup.payment_method_reference
            sub.payment_method_type = preloaded_lookup.payment_method_type
            sub.payment_method_brand = preloaded_lookup.payment_method_brand
            sub.payment_method_last4 = preloaded_lookup.payment_method_last4
            sub.payment_method_exp_month = preloaded_lookup.payment_method_exp_month
            sub.payment_method_exp_year = preloaded_lookup.payment_method_exp_year
            sub.payment_provider_mandate_ref = (preloaded_lookup.metadata.get("mandate_reference") or "").strip() or None
            sub.payment_method_setup_required = False
            sub.payment_method_setup_completed_at = _utcnow()
            sub.last_payment_status = "SEPA_MANDATE_ACTIVE"
            sub.auto_renew = True
            db.add(sub)
            db.commit()
            return {"ok": True, "processed": True, "payment_status": "SEPA_MANDATE_ACTIVE"}
        was_paid_before = sub.last_payment_at is not None
        status_before = sub.status
        was_setup_required = bool(sub.payment_method_setup_required)

        cycle: SubscriptionBillingCycle | None = None
        if cycle_id is not None:
            cycle = db.scalar(
                select(SubscriptionBillingCycle).where(
                    SubscriptionBillingCycle.id == cycle_id,
                    SubscriptionBillingCycle.subscription_id == sub.id,
                )
            )
            if cycle is None:
                return {"ok": True, "processed": False, "reason": "cycle_mismatch"}

        plan = db.scalar(select(Plan).where(Plan.id == sub.plan_id))
        if plan is None:
            return {"ok": True, "processed": False, "reason": "plan_not_found"}

        current_reference = (
            (cycle.payment_recovery_provider_ref or "").strip()
            if cycle is not None
            else (sub.payment_provider_subscription_ref or "").strip()
        )
        if current_reference and payment_reference and payment_reference != current_reference:
            return {"ok": True, "processed": False, "reason": "reference_mismatch"}
        if not current_reference and payment_reference and cycle is None:
            sub.payment_provider_subscription_ref = payment_reference

        reference = current_reference or (payment_reference or "").strip()
        if not reference:
            db.add(sub)
            db.commit()
            return {"ok": True, "processed": False, "reason": "missing_reference"}

        provider = detect_provider_from_reference(reference) or resolve_provider(db)
        lookup = (
            preloaded_lookup
            if preloaded_lookup is not None and preloaded_lookup.provider_reference == reference
            else lookup_payment(db, provider=provider, payment_reference=reference)
        )
        status_text = (lookup.status or "").strip().upper() or "UNKNOWN"
        sub.last_payment_status = status_text
        if lookup.paid:
            customer_reference = (lookup.metadata.get("customer_reference") or "").strip()
            mandate_reference = (lookup.metadata.get("mandate_reference") or "").strip()
            if customer_reference:
                sub.payment_provider_customer_ref = customer_reference
            if mandate_reference:
                sub.payment_provider_mandate_ref = mandate_reference
            paid_at = _utcnow()
            if provider.value == "PAYPLUG" and lookup.payment_method_reference:
                sub.payment_provider_code = provider.value
                sub.payment_provider_payment_method_ref = lookup.payment_method_reference
                sub.payment_method_type = lookup.payment_method_type or "card"
                sub.payment_method_brand = lookup.payment_method_brand
                sub.payment_method_last4 = lookup.payment_method_last4
                sub.payment_method_exp_month = lookup.payment_method_exp_month
                sub.payment_method_exp_year = lookup.payment_method_exp_year
                sub.payment_method_setup_required = False
                sub.payment_method_setup_completed_at = paid_at
                sub.billing_method_code = "CARD_ONLINE"
            elif provider == PaymentProvider.STRIPE and lookup.payment_method_reference:
                sub.payment_provider_code = provider.value
                sub.payment_provider_payment_method_ref = lookup.payment_method_reference
                sub.payment_method_type = lookup.payment_method_type
                sub.payment_method_brand = lookup.payment_method_brand
                sub.payment_method_last4 = lookup.payment_method_last4
                sub.payment_method_exp_month = lookup.payment_method_exp_month
                sub.payment_method_exp_year = lookup.payment_method_exp_year
                if (sub.billing_method_code or "").strip().upper() == "CARD_ONLINE":
                    sub.payment_method_setup_required = False
                    sub.payment_method_setup_completed_at = paid_at
                else:
                    sub.payment_method_setup_required = True
            sub.last_payment_at = paid_at
            sub.last_successful_charge_at = sub.last_payment_at
            if sub.status in {
                SubscriptionStatus.PENDING,
                SubscriptionStatus.PAUSED,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAYMENT_ALERT,
                SubscriptionStatus.PRE_TERMINATION,
                SubscriptionStatus.TERMINATED,
            }:
                if status_before != SubscriptionStatus.PAUSED:
                    sub.status = SubscriptionStatus.ACTIVE
            sub.bookings_blocked = False
            sub.payment_alert_started_at = None
            sub.pre_termination_at = None
            sub.direct_payment_recovery_url = None
            if plan.kind == PlanKind.SUBSCRIPTION:
                billing_method_code = (sub.billing_method_code or "").strip().upper()
                if provider.value == "PAYPLUG":
                    payment_method_ready = bool((sub.payment_provider_payment_method_ref or "").strip())
                elif provider == PaymentProvider.STRIPE:
                    payment_method_ready = bool((sub.payment_provider_customer_ref or "").strip()) and bool(
                        (sub.payment_provider_payment_method_ref or "").strip()
                    )
                else:
                    payment_method_ready = bool((sub.payment_provider_customer_ref or "").strip()) and bool(
                        (sub.payment_provider_mandate_ref or "").strip()
                    )
                if billing_method_code == "CARD_ONLINE" and not payment_method_ready:
                    sub.auto_renew = False
                    sub.payment_method_setup_required = True
                    sub.last_payment_status = "PAID_PAYMENT_METHOD_MISSING"
                elif billing_method_code == "SEPA_DEBIT" and sub.payment_method_setup_required:
                    sub.auto_renew = False
                else:
                    sub.auto_renew = True
                due_at = sub.next_payment_at or sub.current_period_end
                if (
                    cycle is None
                    and was_setup_required
                    and status_before in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_ALERT}
                    and due_at is not None
                    and due_at <= paid_at
                ):
                    next_start = due_at
                    next_end = add_months_utc(due_at, 1)
                    sub.current_period_start = next_start
                    sub.current_period_end = next_end
                    sub.next_payment_at = next_end
                    sub.ends_at = next_end
        elif lookup.cancelled:
            if sub.status == SubscriptionStatus.PENDING:
                sub.status = SubscriptionStatus.CANCELLED
                sub.auto_renew = False
                sub.next_payment_at = None
        elif lookup.failed and sub.status == SubscriptionStatus.PENDING:
            sub.status = SubscriptionStatus.PENDING

        db.add(sub)
        db.commit()

        if lookup.paid and not was_paid_before:
            owner = db.scalar(select(User).where(User.id == sub.user_id))
            if owner is not None:
                billing_profile = resolve_billing_profile(db, owner)
                purchase_label = plan_purchase_notification_label(
                    plan_name=plan.name,
                    price_breakdown=sub.initial_price_breakdown_json,
                )
                student_name = (
                    f"{(owner.first_name or '').strip()} {(owner.last_name or '').strip()}".strip()
                    or owner.email
                )
                amount_paid: Decimal | None = None
                if sub.initial_total_incl_vat is not None:
                    amount_paid = Decimal(sub.initial_total_incl_vat).quantize(Decimal("0.01"))
                elif plan.monthly_price_value is not None:
                    amount_paid = Decimal(plan.monthly_price_value).quantize(Decimal("0.01"))
                currency_code = (
                    sub.initial_currency_code
                    or plan.currency_code
                    or billing_profile.preferred_currency
                    or "EUR"
                )
                if billing_profile.email:
                    try:
                        send_client_payment_success_notifications(
                            db,
                            to_email=billing_profile.email,
                            first_name=billing_profile.first_name,
                            last_name=billing_profile.last_name,
                            plan_name=purchase_label,
                            subscription_id=sub.id,
                            paid_at=sub.last_payment_at or _utcnow(),
                            amount_paid=amount_paid,
                            currency=currency_code,
                            language=billing_profile.preferred_language,
                        )
                    except Exception:
                        logger.exception("Unable to send paid confirmation emails for subscription=%s", sub.id)
                try:
                    send_plan_purchase_admin_notifications(
                        db,
                        client_id=owner.id,
                        client_email=billing_profile.email or owner.email,
                        first_name=billing_profile.first_name,
                        last_name=billing_profile.last_name,
                        student_name=student_name,
                        plan_name=purchase_label,
                        subscription_id=sub.id,
                        payment_reference=lookup.provider_reference or reference,
                        payment_method=lookup.provider.value,
                        paid_at=sub.last_payment_at or _utcnow(),
                        amount_paid=amount_paid,
                        currency=currency_code,
                    )
                except Exception:
                    logger.exception("Unable to send admin purchase email for subscription=%s", sub.id)

            automation_notifications = schedule_plan_purchase_triggers(
                db,
                subscription=sub,
                plan=plan,
                occurred_at=sub.last_payment_at or _utcnow(),
            )
            db.commit()
            enqueue_notifications(automation_notifications)

        return {"ok": True, "processed": True, "payment_status": status_text}
    finally:
        db.close()


@router.post("/stripe-webhook")
async def stripe_payment_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, object]:
    """Stripe-only webhook secured by Stripe's signing secret.

    The shared reconciliation endpoint also has an application token for PSPs
    that support a callback URL per payment. Stripe uses one account-level URL,
    so this dedicated route keeps that internal token out of the Stripe UI.
    """
    db: Session = SessionLocal()
    try:
        internal_token = resolve_webhook_secret(db)
    finally:
        db.close()
    return await payment_webhook(
        request=request,
        background_tasks=background_tasks,
        client_id=None,
        subscription_id=None,
        cycle_id=None,
        token=internal_token,
    )


@router.get("/invoices/range/{client_id}/{note_id}")
def start_invoice_range_public_payment(
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return start_admin_client_range_invoice_public_payment(
        client_id=client_id,
        note_id=note_id,
        token=token,
        db=db,
    )


@router.post("/invoices/range/{client_id}/{note_id}/webhook")
def handle_invoice_range_public_payment_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return handle_admin_client_range_invoice_public_payment_webhook(
        client_id=client_id,
        note_id=note_id,
        request=request,
        background_tasks=background_tasks,
        token=token,
        secret=secret,
        db=db,
    )


@router.post("/invoices/range/{client_id}/{note_id}/card")
def start_invoice_range_public_card_payment(
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return start_admin_client_range_invoice_public_card_payment(
        client_id=client_id,
        note_id=note_id,
        token=token,
        db=db,
    )


@router.post("/invoices/range/{client_id}/{note_id}/bank-transfer")
def start_invoice_range_public_bank_transfer(
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return start_admin_client_range_invoice_public_bank_transfer(
        client_id=client_id,
        note_id=note_id,
        token=token,
        db=db,
    )


@router.get("/invoices/range/{client_id}/{note_id}/return")
def return_invoice_range_public_payment(
    client_id: UUID,
    note_id: UUID,
    background_tasks: BackgroundTasks,
    token: str = Query(min_length=24, max_length=4096),
    state: str = Query(default="success"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return return_admin_client_range_invoice_public_payment(
        client_id=client_id,
        note_id=note_id,
        background_tasks=background_tasks,
        token=token,
        state=state,
        db=db,
    )


@router.get("/bookings/{client_id}/{receipt_id}")
def start_booking_public_payment(
    client_id: UUID,
    receipt_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return start_admin_client_payment_receipt_public_payment(
        client_id=client_id,
        receipt_id=receipt_id,
        token=token,
        db=db,
    )


@router.post("/bookings/{client_id}/{receipt_id}/webhook")
def handle_booking_public_payment_webhook(
    request: Request,
    client_id: UUID,
    receipt_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return handle_admin_client_payment_receipt_public_payment_webhook(
        client_id=client_id,
        receipt_id=receipt_id,
        request=request,
        token=token,
        secret=secret,
        db=db,
    )


@router.get("/bookings/{client_id}/{receipt_id}/return")
def return_booking_public_payment(
    client_id: UUID,
    receipt_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    state: str = Query(default="success"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return return_admin_client_payment_receipt_public_payment(
        client_id=client_id,
        receipt_id=receipt_id,
        token=token,
        state=state,
        db=db,
    )
