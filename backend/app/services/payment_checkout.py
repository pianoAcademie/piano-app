from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.services.payment_provider import PaymentProvider, resolve_active_secret, resolve_provider


@dataclass(frozen=True)
class CheckoutCreateRequest:
    amount: Decimal
    currency: str
    description: str
    customer_email: str
    success_return_url: str
    cancel_return_url: str
    webhook_url: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class CheckoutCreateResult:
    success: bool
    provider: PaymentProvider
    checkout_url: str | None
    provider_reference: str | None
    status: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class PaymentLookupResult:
    success: bool
    provider: PaymentProvider
    provider_reference: str
    status: str
    paid: bool
    cancelled: bool
    failed: bool
    metadata: dict[str, str]
    message: str


def _request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, object] | None = None,
    timeout_seconds: int = 20,
) -> tuple[int, dict[str, object] | None, str]:
    request = Request(
        url,
        method=method.upper(),
        headers=headers,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(response.status)
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw) if raw else None
        return status_code, parsed, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = None
        return int(exc.code), parsed, raw
    except URLError as exc:
        return 0, None, str(exc.reason)
    except Exception as exc:  # pragma: no cover
        return 0, None, str(exc)


def _payplug_auth_header(secret: str) -> str:
    token = secret.strip()
    if not token:
        return ""
    lowered = token.lower()
    if lowered.startswith("bearer ") or lowered.startswith("basic "):
        return token
    return f"Bearer {token}"


def _normalize_metadata(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        text_key = str(key).strip()
        if not text_key:
            continue
        out[text_key] = str(value) if value is not None else ""
    return out


def _mollie_create_checkout(secret: str, payload: CheckoutCreateRequest) -> CheckoutCreateResult:
    status_code, parsed, message = _request_json(
        method="POST",
        url="https://api.mollie.com/v2/payments",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
        body={
            "amount": {
                "currency": payload.currency.upper(),
                "value": f"{payload.amount.quantize(Decimal('0.01')):.2f}",
            },
            "description": payload.description,
            "redirectUrl": payload.success_return_url,
            "webhookUrl": payload.webhook_url,
            "metadata": payload.metadata,
            "method": "creditcard",
        },
    )
    if status_code == 0 or parsed is None:
        return CheckoutCreateResult(
            success=False,
            provider=PaymentProvider.MOLLIE,
            checkout_url=None,
            provider_reference=None,
            status="NETWORK_ERROR",
            message=message,
            retryable=True,
        )

    checkout_url = (
        str((((parsed.get("_links") or {}) if isinstance(parsed, dict) else {}).get("checkout") or {}).get("href") or "")
        if isinstance(parsed, dict)
        else ""
    )
    provider_ref = str(parsed.get("id") or "") if isinstance(parsed, dict) else ""
    if 200 <= status_code < 300 and checkout_url:
        return CheckoutCreateResult(
            success=True,
            provider=PaymentProvider.MOLLIE,
            checkout_url=checkout_url,
            provider_reference=provider_ref or None,
            status=str(parsed.get("status") or "open"),
            message="Mollie checkout created",
            retryable=False,
        )
    return CheckoutCreateResult(
        success=False,
        provider=PaymentProvider.MOLLIE,
        checkout_url=None,
        provider_reference=provider_ref or None,
        status=f"HTTP_{status_code}",
        message=message or "Mollie checkout creation failed",
        retryable=500 <= status_code < 600,
    )


def _payplug_create_checkout(secret: str, payload: CheckoutCreateRequest) -> CheckoutCreateResult:
    amount_cents = int((payload.amount.quantize(Decimal("0.01")) * Decimal("100")).to_integral_value())
    status_code, parsed, message = _request_json(
        method="POST",
        url="https://api.payplug.com/v1/payments",
        headers={
            "Authorization": _payplug_auth_header(secret),
            "Content-Type": "application/json",
        },
        body={
            "amount": amount_cents,
            "currency": payload.currency.upper(),
            "customer": {
                "email": payload.customer_email,
            },
            "hosted_payment": {
                "return_url": payload.success_return_url,
                "cancel_url": payload.cancel_return_url,
            },
            "notification_url": payload.webhook_url,
            "metadata": payload.metadata,
        },
    )
    if status_code == 0 or parsed is None:
        return CheckoutCreateResult(
            success=False,
            provider=PaymentProvider.PAYPLUG,
            checkout_url=None,
            provider_reference=None,
            status="NETWORK_ERROR",
            message=message,
            retryable=True,
        )

    hosted_payment = parsed.get("hosted_payment") if isinstance(parsed, dict) else None
    checkout_url = str((hosted_payment or {}).get("payment_url") or "") if isinstance(hosted_payment, dict) else ""
    provider_ref = str(parsed.get("id") or "") if isinstance(parsed, dict) else ""

    if 200 <= status_code < 300 and checkout_url:
        return CheckoutCreateResult(
            success=True,
            provider=PaymentProvider.PAYPLUG,
            checkout_url=checkout_url,
            provider_reference=provider_ref or None,
            status="open",
            message="Payplug checkout created",
            retryable=False,
        )
    return CheckoutCreateResult(
        success=False,
        provider=PaymentProvider.PAYPLUG,
        checkout_url=None,
        provider_reference=provider_ref or None,
        status=f"HTTP_{status_code}",
        message=message or "Payplug checkout creation failed",
        retryable=500 <= status_code < 600,
    )


def create_checkout_session(db: Session, payload: CheckoutCreateRequest) -> CheckoutCreateResult:
    provider = resolve_provider(db)
    secret = resolve_active_secret(db).strip()
    if not secret:
        return CheckoutCreateResult(
            success=False,
            provider=provider,
            checkout_url=None,
            provider_reference=None,
            status="MISSING_SECRET",
            message="PSP secret is not configured",
            retryable=False,
        )
    if provider == PaymentProvider.MOLLIE:
        return _mollie_create_checkout(secret, payload)
    return _payplug_create_checkout(secret, payload)


def _mollie_lookup_payment(secret: str, payment_reference: str) -> PaymentLookupResult:
    status_code, parsed, message = _request_json(
        method="GET",
        url=f"https://api.mollie.com/v2/payments/{payment_reference}",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
    )
    if status_code == 0 or not isinstance(parsed, dict):
        return PaymentLookupResult(
            success=False,
            provider=PaymentProvider.MOLLIE,
            provider_reference=payment_reference,
            status="NETWORK_ERROR",
            paid=False,
            cancelled=False,
            failed=True,
            metadata={},
            message=message,
        )
    payment_status = str(parsed.get("status") or "").strip().lower()
    paid = payment_status == "paid"
    cancelled = payment_status in {"canceled", "expired"}
    failed = payment_status in {"failed"} or (not paid and cancelled)
    return PaymentLookupResult(
        success=200 <= status_code < 300,
        provider=PaymentProvider.MOLLIE,
        provider_reference=str(parsed.get("id") or payment_reference),
        status=payment_status or f"http_{status_code}",
        paid=paid,
        cancelled=cancelled,
        failed=failed,
        metadata=_normalize_metadata(parsed.get("metadata")),
        message=message or "ok",
    )


def _payplug_lookup_payment(secret: str, payment_reference: str) -> PaymentLookupResult:
    status_code, parsed, message = _request_json(
        method="GET",
        url=f"https://api.payplug.com/v1/payments/{payment_reference}",
        headers={
            "Authorization": _payplug_auth_header(secret),
            "Content-Type": "application/json",
        },
    )
    if status_code == 0 or not isinstance(parsed, dict):
        return PaymentLookupResult(
            success=False,
            provider=PaymentProvider.PAYPLUG,
            provider_reference=payment_reference,
            status="NETWORK_ERROR",
            paid=False,
            cancelled=False,
            failed=True,
            metadata={},
            message=message,
        )

    payment_status = str(parsed.get("state") or parsed.get("status") or "").strip().lower()
    is_paid = bool(parsed.get("is_paid")) or payment_status in {"paid", "succeeded"}
    is_refunded = bool(parsed.get("is_refunded")) or payment_status == "refunded"
    is_canceled = bool(parsed.get("is_canceled")) or payment_status in {"cancelled", "canceled"}
    is_failed = payment_status in {"failed"} or bool(parsed.get("failure")) or bool(parsed.get("is_expired"))

    return PaymentLookupResult(
        success=200 <= status_code < 300,
        provider=PaymentProvider.PAYPLUG,
        provider_reference=str(parsed.get("id") or payment_reference),
        status=payment_status or f"http_{status_code}",
        paid=is_paid,
        cancelled=is_refunded or is_canceled,
        failed=is_failed and not is_paid,
        metadata=_normalize_metadata(parsed.get("metadata")),
        message=message or "ok",
    )


def lookup_payment(db: Session, *, provider: PaymentProvider, payment_reference: str) -> PaymentLookupResult:
    secret = resolve_active_secret(db).strip()
    if not secret:
        return PaymentLookupResult(
            success=False,
            provider=provider,
            provider_reference=payment_reference,
            status="MISSING_SECRET",
            paid=False,
            cancelled=False,
            failed=True,
            metadata={},
            message="PSP secret is not configured",
        )
    if provider == PaymentProvider.MOLLIE:
        return _mollie_lookup_payment(secret, payment_reference)
    return _payplug_lookup_payment(secret, payment_reference)


def with_webhook_secret(url: str, webhook_secret: str) -> str:
    token = webhook_secret.strip()
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'token': token})}"
