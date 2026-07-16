from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
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
    customer_first_name: str | None = None
    customer_last_name: str | None = None
    customer_address_line: str | None = None
    customer_postal_code: str | None = None
    customer_city: str | None = None
    customer_country: str | None = None
    save_payment_method: bool = False


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
    payment_method_reference: str | None = None
    payment_method_exp_month: int | None = None
    payment_method_exp_year: int | None = None


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


def _request_form(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, str] | None = None,
    timeout_seconds: int = 20,
) -> tuple[int, dict[str, object] | None, str]:
    encoded_body: bytes | None = None
    if body is not None:
        encoded_body = urlencode(body).encode("utf-8")
    request = Request(
        url,
        method=method.upper(),
        headers=headers,
        data=encoded_body,
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


def _looks_like_local_callback_url(url: str) -> bool:
    candidate = (url or "").strip()
    if not candidate:
        return False
    try:
        hostname = (urlparse(candidate).hostname or "").strip().lower()
    except Exception:
        return False
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    return hostname.endswith(".local")


def _payplug_lookup_status_label(
    *,
    status_code: int,
    payment_status: str,
    is_paid: bool,
    is_refunded: bool,
    is_canceled: bool,
    is_failed: bool,
) -> str:
    normalized = (payment_status or "").strip()
    if normalized:
        return normalized
    if is_paid:
        return "PAID"
    if is_refunded:
        return "REFUNDED"
    if is_canceled:
        return "CANCELLED"
    if is_failed:
        return "FAILED"
    return f"HTTP_{status_code}"


def _mollie_create_checkout(secret: str, payload: CheckoutCreateRequest) -> CheckoutCreateResult:
    body: dict[str, object] = {
        "amount": {
            "currency": payload.currency.upper(),
            "value": f"{payload.amount.quantize(Decimal('0.01')):.2f}",
        },
        "description": payload.description,
        "redirectUrl": payload.success_return_url,
        "metadata": payload.metadata,
        "method": "creditcard",
    }
    if payload.webhook_url and not _looks_like_local_callback_url(payload.webhook_url):
        body["webhookUrl"] = payload.webhook_url
    status_code, parsed, message = _request_json(
        method="POST",
        url="https://api.mollie.com/v2/payments",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
        body=body,
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
    billing: dict[str, object] = {"email": payload.customer_email}
    if payload.customer_first_name:
        billing["first_name"] = payload.customer_first_name
    if payload.customer_last_name:
        billing["last_name"] = payload.customer_last_name
    if payload.customer_address_line:
        billing["address1"] = payload.customer_address_line
    if payload.customer_postal_code:
        billing["postcode"] = payload.customer_postal_code
    if payload.customer_city:
        billing["city"] = payload.customer_city
    if payload.customer_country:
        billing["country"] = payload.customer_country.upper()

    shipping = dict(billing)
    shipping["delivery_type"] = "BILLING"

    body: dict[str, object] = {
        "amount": amount_cents,
        "currency": payload.currency.upper(),
        "billing": billing,
        "shipping": shipping,
        "description": payload.description[:80],
        "hosted_payment": {
            "return_url": payload.success_return_url,
            "cancel_url": payload.cancel_return_url,
        },
        "metadata": payload.metadata,
    }
    if payload.save_payment_method:
        body["save_card"] = True
    if payload.webhook_url and not _looks_like_local_callback_url(payload.webhook_url):
        body["notification_url"] = payload.webhook_url
    status_code, parsed, message = _request_json(
        method="POST",
        url="https://api.payplug.com/v1/payments",
        headers={
            "Authorization": _payplug_auth_header(secret),
            "Content-Type": "application/json",
            "PayPlug-Version": "2019-08-06",
        },
        body=body,
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


def _stripe_create_checkout(secret: str, payload: CheckoutCreateRequest) -> CheckoutCreateResult:
    amount_cents = int((payload.amount.quantize(Decimal("0.01")) * Decimal("100")).to_integral_value())
    body: dict[str, str] = {
        "mode": "payment",
        "success_url": payload.success_return_url,
        "cancel_url": payload.cancel_return_url,
        "customer_email": payload.customer_email,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": payload.currency.lower(),
        "line_items[0][price_data][unit_amount]": str(max(amount_cents, 0)),
        "line_items[0][price_data][product_data][name]": payload.description,
    }
    for key, value in payload.metadata.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        body[f"metadata[{normalized_key}]"] = str(value or "")

    status_code, parsed, message = _request_form(
        method="POST",
        url="https://api.stripe.com/v1/checkout/sessions",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=body,
    )
    if status_code == 0 or not isinstance(parsed, dict):
        return CheckoutCreateResult(
            success=False,
            provider=PaymentProvider.STRIPE,
            checkout_url=None,
            provider_reference=None,
            status="NETWORK_ERROR",
            message=message,
            retryable=True,
        )

    checkout_url = str(parsed.get("url") or "").strip()
    provider_ref = str(parsed.get("id") or "").strip()
    checkout_status = str(parsed.get("status") or "open")
    if 200 <= status_code < 300 and checkout_url:
        return CheckoutCreateResult(
            success=True,
            provider=PaymentProvider.STRIPE,
            checkout_url=checkout_url,
            provider_reference=provider_ref or None,
            status=checkout_status,
            message="Stripe checkout created",
            retryable=False,
        )
    return CheckoutCreateResult(
        success=False,
        provider=PaymentProvider.STRIPE,
        checkout_url=None,
        provider_reference=provider_ref or None,
        status=f"HTTP_{status_code}",
        message=message or "Stripe checkout creation failed",
        retryable=500 <= status_code < 600,
    )


def create_checkout_session(
    db: Session,
    payload: CheckoutCreateRequest,
    *,
    legal_entity_id: UUID | None = None,
) -> CheckoutCreateResult:
    provider = resolve_provider(db, legal_entity_id=legal_entity_id)
    secret = resolve_active_secret(db, provider=provider).strip()
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
    if provider == PaymentProvider.STRIPE:
        return _stripe_create_checkout(secret, payload)
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
    metadata = _normalize_metadata(parsed.get("metadata"))
    customer_reference = str(parsed.get("customerId") or "").strip()
    mandate_reference = str(parsed.get("mandateId") or "").strip()
    if customer_reference:
        metadata["customer_reference"] = customer_reference
    if mandate_reference:
        metadata["mandate_reference"] = mandate_reference

    return PaymentLookupResult(
        success=200 <= status_code < 300,
        provider=PaymentProvider.MOLLIE,
        provider_reference=str(parsed.get("id") or payment_reference),
        status=payment_status or f"http_{status_code}",
        paid=paid,
        cancelled=cancelled,
        failed=failed,
        metadata=metadata,
        message=message or "ok",
    )


def _payplug_lookup_payment(secret: str, payment_reference: str) -> PaymentLookupResult:
    status_code, parsed, message = _request_json(
        method="GET",
        url=f"https://api.payplug.com/v1/payments/{payment_reference}",
        headers={
            "Authorization": _payplug_auth_header(secret),
            "Content-Type": "application/json",
            "PayPlug-Version": "2019-08-06",
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
    status_label = _payplug_lookup_status_label(
        status_code=status_code,
        payment_status=payment_status,
        is_paid=is_paid,
        is_refunded=is_refunded,
        is_canceled=is_canceled,
        is_failed=is_failed,
    )
    card = parsed.get("card")
    card_reference: str | None = None
    card_exp_month: int | None = None
    card_exp_year: int | None = None
    if isinstance(card, dict):
        raw_reference = str(card.get("id") or "").strip()
        if raw_reference.startswith("card_"):
            card_reference = raw_reference
        try:
            parsed_month = int(card.get("exp_month"))
            if 1 <= parsed_month <= 12:
                card_exp_month = parsed_month
        except (TypeError, ValueError):
            pass
        try:
            parsed_year = int(card.get("exp_year"))
            if 2000 <= parsed_year <= 9999:
                card_exp_year = parsed_year
        except (TypeError, ValueError):
            pass

    return PaymentLookupResult(
        success=200 <= status_code < 300,
        provider=PaymentProvider.PAYPLUG,
        provider_reference=str(parsed.get("id") or payment_reference),
        status=status_label,
        paid=is_paid,
        cancelled=is_refunded or is_canceled,
        failed=is_failed and not is_paid,
        metadata=_normalize_metadata(parsed.get("metadata")),
        message=message or "ok",
        payment_method_reference=card_reference,
        payment_method_exp_month=card_exp_month,
        payment_method_exp_year=card_exp_year,
    )


def _stripe_lookup_payment(secret: str, payment_reference: str) -> PaymentLookupResult:
    status_code, parsed, message = _request_form(
        method="GET",
        url=f"https://api.stripe.com/v1/checkout/sessions/{payment_reference}",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=None,
    )
    if status_code == 0 or not isinstance(parsed, dict):
        return PaymentLookupResult(
            success=False,
            provider=PaymentProvider.STRIPE,
            provider_reference=payment_reference,
            status="NETWORK_ERROR",
            paid=False,
            cancelled=False,
            failed=True,
            metadata={},
            message=message,
        )

    checkout_status = str(parsed.get("status") or "").strip().lower()
    payment_status = str(parsed.get("payment_status") or "").strip().lower()
    paid = payment_status in {"paid", "no_payment_required"}
    cancelled = checkout_status in {"expired"}
    failed = (not paid) and cancelled
    metadata = _normalize_metadata(parsed.get("metadata"))
    customer_reference = str(parsed.get("customer") or "").strip()
    if customer_reference:
        metadata["customer_reference"] = customer_reference

    return PaymentLookupResult(
        success=200 <= status_code < 300,
        provider=PaymentProvider.STRIPE,
        provider_reference=str(parsed.get("id") or payment_reference),
        status=payment_status or checkout_status or f"http_{status_code}",
        paid=paid,
        cancelled=cancelled,
        failed=failed,
        metadata=metadata,
        message=message or "ok",
    )


def lookup_payment(db: Session, *, provider: PaymentProvider, payment_reference: str) -> PaymentLookupResult:
    secret = resolve_active_secret(db, provider=provider).strip()
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
    if provider == PaymentProvider.STRIPE:
        return _stripe_lookup_payment(secret, payment_reference)
    return _payplug_lookup_payment(secret, payment_reference)


def with_webhook_secret(url: str, webhook_secret: str, *, param_name: str = "token") -> str:
    token = webhook_secret.strip()
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({param_name: token})}"
