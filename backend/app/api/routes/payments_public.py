from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionLocal, get_db
from app.api.routes.admin_clients import (
    handle_admin_client_payment_receipt_public_payment_webhook,
    handle_admin_client_range_invoice_public_payment_webhook,
    return_admin_client_payment_receipt_public_payment,
    return_admin_client_range_invoice_public_payment,
    start_admin_client_payment_receipt_public_payment,
    start_admin_client_range_invoice_public_payment,
)
from app.core.config import settings
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.user import User
from app.services.client_purchase_notifications import send_client_payment_success_notifications
from app.services.payment_checkout import lookup_payment
from app.services.payment_provider import detect_provider_from_reference, resolve_provider

router = APIRouter(prefix="/public/payments")
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_reference(request: Request, payload: object) -> str | None:
    if isinstance(payload, dict):
        for key in ("id", "payment_id", "paymentId"):
            value = payload.get(key)
            if value:
                return str(value).strip()
        data_node = payload.get("data")
        if isinstance(data_node, dict):
            value = data_node.get("id")
            if value:
                return str(value).strip()
            object_node = data_node.get("object")
            if isinstance(object_node, dict):
                object_id = object_node.get("id")
                if object_id:
                    return str(object_id).strip()
    if request.query_params.get("id"):
        return str(request.query_params.get("id")).strip()
    form_id = request.query_params.get("payment_id")
    if form_id:
        return str(form_id).strip()
    return None


@router.api_route("/webhook", methods=["POST", "GET"])
async def payment_webhook(
    request: Request,
    client_id: UUID | None = Query(default=None),
    subscription_id: UUID | None = Query(default=None),
    token: str | None = Query(default=None),
) -> dict[str, object]:
    configured = (settings.payment_webhook_secret or "").strip()
    if configured and token != configured:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook token")

    raw_body = await request.body()
    payload: object = {}
    if raw_body:
        body_text = raw_body.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(body_text)
        except Exception:
            payload = {}

    payment_reference = _extract_reference(request, payload)
    if subscription_id is None:
        return {"ok": True, "processed": False, "reason": "missing_subscription_id"}

    db: Session = SessionLocal()
    try:
        sub = db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id).with_for_update())
        if sub is None:
            return {"ok": True, "processed": False, "reason": "subscription_not_found"}
        if client_id is not None and sub.user_id != client_id:
            return {"ok": True, "processed": False, "reason": "client_mismatch"}
        was_paid_before = sub.last_payment_at is not None

        plan = db.scalar(select(Plan).where(Plan.id == sub.plan_id))
        if plan is None:
            return {"ok": True, "processed": False, "reason": "plan_not_found"}

        if payment_reference:
            sub.payment_provider_subscription_ref = payment_reference

        reference = (sub.payment_provider_subscription_ref or "").strip()
        if not reference:
            db.add(sub)
            db.commit()
            return {"ok": True, "processed": False, "reason": "missing_reference"}

        provider = detect_provider_from_reference(reference) or resolve_provider(db)
        lookup = lookup_payment(db, provider=provider, payment_reference=reference)
        status_text = (lookup.status or "").strip().upper() or "UNKNOWN"
        sub.last_payment_status = status_text
        if lookup.paid:
            customer_reference = (lookup.metadata.get("customer_reference") or "").strip()
            mandate_reference = (lookup.metadata.get("mandate_reference") or "").strip()
            if customer_reference:
                sub.payment_provider_customer_ref = customer_reference
            if mandate_reference:
                sub.payment_provider_mandate_ref = mandate_reference
            sub.last_payment_at = _utcnow()
            sub.last_successful_charge_at = sub.last_payment_at
            if sub.status in {
                SubscriptionStatus.PENDING,
                SubscriptionStatus.PAUSED,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAYMENT_ALERT,
                SubscriptionStatus.PRE_TERMINATION,
                SubscriptionStatus.TERMINATED,
            }:
                sub.status = SubscriptionStatus.ACTIVE
            sub.bookings_blocked = False
            sub.payment_alert_started_at = None
            sub.pre_termination_at = None
            sub.direct_payment_recovery_url = None
            if plan.kind == PlanKind.SUBSCRIPTION:
                billing_method_code = (sub.billing_method_code or "").strip().upper()
                has_customer_ref = bool((sub.payment_provider_customer_ref or "").strip())
                has_mandate_ref = bool((sub.payment_provider_mandate_ref or "").strip())
                if billing_method_code == "CARD_ONLINE" and (not has_customer_ref or not has_mandate_ref):
                    sub.auto_renew = False
                    sub.last_payment_status = "PAID_MANDATE_MISSING"
                else:
                    sub.auto_renew = True
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
            if owner is not None and owner.email:
                try:
                    amount_paid: Decimal | None = None
                    if plan.monthly_price_value is not None:
                        amount_paid = Decimal(plan.monthly_price_value).quantize(Decimal("0.01"))
                    send_client_payment_success_notifications(
                        db,
                        to_email=owner.email,
                        first_name=owner.first_name,
                        last_name=owner.last_name,
                        plan_name=plan.name,
                        subscription_id=sub.id,
                        paid_at=sub.last_payment_at or _utcnow(),
                        amount_paid=amount_paid,
                        currency=(plan.currency_code or owner.preferred_currency or "EUR"),
                        language=owner.preferred_language,
                    )
                except Exception:
                    logger.exception("Unable to send paid confirmation emails for subscription=%s", sub.id)

        return {"ok": True, "processed": True, "payment_status": status_text}
    finally:
        db.close()


@router.get("/invoices/range/{client_id}/{note_id}")
def start_invoice_range_public_payment(
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return start_admin_client_range_invoice_public_payment(
        client_id=client_id,
        note_id=note_id,
        token=token,
        db=db,
    )


@router.post("/invoices/range/{client_id}/{note_id}/webhook")
def handle_invoice_range_public_payment_webhook(
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return handle_admin_client_range_invoice_public_payment_webhook(
        client_id=client_id,
        note_id=note_id,
        token=token,
        secret=secret,
        db=db,
    )


@router.get("/invoices/range/{client_id}/{note_id}/return")
def return_invoice_range_public_payment(
    client_id: UUID,
    note_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    state: str = Query(default="success"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return return_admin_client_range_invoice_public_payment(
        client_id=client_id,
        note_id=note_id,
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
    client_id: UUID,
    receipt_id: UUID,
    token: str = Query(min_length=24, max_length=4096),
    secret: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return handle_admin_client_payment_receipt_public_payment_webhook(
        client_id=client_id,
        receipt_id=receipt_id,
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
