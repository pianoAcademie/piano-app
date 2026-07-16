from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.payment_provider import PaymentMode


@dataclass(frozen=True)
class RecurringChargeRequest:
    amount: Decimal
    currency: str
    description: str
    customer_reference: str | None
    mandate_reference: str | None
    idempotency_key: str | None = None
    payment_method_reference: str | None = None
    payment_method_exp_month: int | None = None
    payment_method_exp_year: int | None = None
    customer_email: str | None = None
    customer_first_name: str | None = None
    customer_last_name: str | None = None
    success_return_url: str | None = None
    cancel_return_url: str | None = None
    notification_url: str | None = None


@dataclass(frozen=True)
class RecurringChargeResult:
    success: bool
    provider_reference: str | None
    status: str
    message: str
    retryable: bool
    checkout_url: str | None = None


class PaymentGateway:
    def create_recurring_charge(self, payload: RecurringChargeRequest) -> RecurringChargeResult:
        raise NotImplementedError


class PayplugGateway(PaymentGateway):
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key.strip()

    @staticmethod
    def _authorization(secret: str) -> str:
        lowered = secret.lower()
        if lowered.startswith("bearer ") or lowered.startswith("basic "):
            return secret
        return f"Bearer {secret}"

    @staticmethod
    def _failure_code(parsed: dict[str, object]) -> str:
        failure = parsed.get("failure")
        if isinstance(failure, dict):
            raw = failure.get("code") or failure.get("message")
        else:
            raw = failure
        normalized = str(raw or "PAYMENT_FAILED").strip().upper().replace(" ", "_")
        aliases = {
            "CARD_EXPIRED": "CARD_EXPIRED",
            "EXPIRED_CARD": "CARD_EXPIRED",
            "CARD_DECLINED": "CARD_DECLINED",
            "CARD_BLOCKED": "CARD_DECLINED",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _card_is_expired(month: int | None, year: int | None, *, now: datetime | None = None) -> bool:
        if month is None or year is None:
            return False
        current = now or datetime.now(timezone.utc)
        return (year, month) < (current.year, current.month)

    def create_recurring_charge(self, payload: RecurringChargeRequest) -> RecurringChargeResult:
        if not self.api_key:
            return RecurringChargeResult(False, None, "MISSING_KEY", "Payplug API key is not configured", False)
        card_reference = (payload.payment_method_reference or "").strip()
        if not card_reference.startswith("card_"):
            return RecurringChargeResult(False, None, "MISSING_PAYMENT_METHOD", "Missing saved Payplug card", False)
        if self._card_is_expired(payload.payment_method_exp_month, payload.payment_method_exp_year):
            return RecurringChargeResult(False, None, "CARD_EXPIRED", "The saved card has expired", False)

        billing: dict[str, object] = {"email": payload.customer_email or ""}
        if payload.customer_first_name:
            billing["first_name"] = payload.customer_first_name
        if payload.customer_last_name:
            billing["last_name"] = payload.customer_last_name
        shipping = dict(billing)
        shipping["delivery_type"] = "BILLING"
        body: dict[str, object] = {
            "amount": int((payload.amount.quantize(Decimal("0.01")) * Decimal("100")).to_integral_value()),
            "currency": payload.currency.upper(),
            "payment_method": card_reference,
            "initiator": "MERCHANT",
            "billing": billing,
            "shipping": shipping,
            "description": payload.description[:80],
            "metadata": {
                "source": "SUBSCRIPTION_RENEWAL",
                **({"idempotency_key": payload.idempotency_key} if payload.idempotency_key else {}),
            },
        }
        if payload.success_return_url or payload.cancel_return_url:
            body["hosted_payment"] = {
                **({"return_url": payload.success_return_url} if payload.success_return_url else {}),
                **({"cancel_url": payload.cancel_return_url} if payload.cancel_return_url else {}),
            }
        if payload.notification_url:
            body["notification_url"] = payload.notification_url

        request = Request(
            "https://api.payplug.com/v1/payments",
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": self._authorization(self.api_key),
                "Content-Type": "application/json",
                "PayPlug-Version": "2019-08-06",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                status_code = int(response.status)
            parsed = json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {}
            failure_code = self._failure_code(parsed) if isinstance(parsed, dict) else f"HTTP_{exc.code}"
            provider_reference = str(parsed.get("id") or "").strip() or None if isinstance(parsed, dict) else None
            return RecurringChargeResult(
                False,
                provider_reference,
                failure_code,
                raw or str(exc),
                500 <= exc.code < 600,
            )
        except URLError as exc:
            return RecurringChargeResult(False, None, "NETWORK_ERROR", str(exc.reason), True)
        except Exception as exc:  # pragma: no cover
            return RecurringChargeResult(False, None, "UNEXPECTED_ERROR", str(exc), True)

        if not isinstance(parsed, dict):
            return RecurringChargeResult(False, None, f"HTTP_{status_code}", raw, status_code >= 500)
        provider_reference = str(parsed.get("id") or "").strip() or None
        state = str(parsed.get("state") or parsed.get("status") or "").strip().upper()
        if bool(parsed.get("is_paid")) or state in {"PAID", "SUCCEEDED"}:
            return RecurringChargeResult(True, provider_reference, state or "PAID", "Payplug recurring payment paid", False)

        hosted = parsed.get("hosted_payment")
        payment_url = str(hosted.get("payment_url") or "").strip() if isinstance(hosted, dict) else ""
        if payment_url:
            return RecurringChargeResult(
                False,
                provider_reference,
                "AUTHENTICATION_REQUIRED",
                "Cardholder authentication is required",
                False,
                checkout_url=payment_url,
            )
        failure_code = self._failure_code(parsed)
        return RecurringChargeResult(
            False,
            provider_reference,
            failure_code,
            str(parsed.get("failure") or "Payplug recurring payment failed"),
            status_code >= 500,
        )


class MollieGateway(PaymentGateway):
    def __init__(self, *, api_key: str, mode: PaymentMode) -> None:
        self.api_key = api_key.strip()
        self.mode = mode

    def create_recurring_charge(self, payload: RecurringChargeRequest) -> RecurringChargeResult:
        if not self.api_key:
            return RecurringChargeResult(
                success=False,
                provider_reference=None,
                status="MISSING_KEY",
                message="Mollie API key is not configured",
                retryable=False,
            )
        if not payload.customer_reference:
            return RecurringChargeResult(
                success=False,
                provider_reference=None,
                status="MISSING_CUSTOMER_REF",
                message="Missing Mollie customer reference on subscription",
                retryable=False,
            )
        if not payload.mandate_reference:
            return RecurringChargeResult(
                success=False,
                provider_reference=None,
                status="MISSING_MANDATE_REF",
                message="Missing Mollie mandate reference on subscription",
                retryable=False,
            )

        body = {
            "amount": {
                "currency": payload.currency.upper(),
                "value": f"{payload.amount:.2f}",
            },
            "description": payload.description,
            "sequenceType": "recurring",
            "customerId": payload.customer_reference,
            "mandateId": payload.mandate_reference,
        }

        request = Request(
            "https://api.mollie.com/v2/payments",
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **({"Idempotency-Key": payload.idempotency_key} if payload.idempotency_key else {}),
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return RecurringChargeResult(
                success=True,
                provider_reference=str(parsed.get("id") or ""),
                status=str(parsed.get("status") or "created"),
                message="Mollie recurring payment initiated",
                retryable=False,
            )
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return RecurringChargeResult(
                success=False,
                provider_reference=None,
                status=f"HTTP_{exc.code}",
                message=raw or str(exc),
                retryable=500 <= exc.code < 600,
            )
        except URLError as exc:
            return RecurringChargeResult(
                success=False,
                provider_reference=None,
                status="NETWORK_ERROR",
                message=str(exc.reason),
                retryable=True,
            )
        except Exception as exc:  # pragma: no cover
            return RecurringChargeResult(
                success=False,
                provider_reference=None,
                status="UNEXPECTED_ERROR",
                message=str(exc),
                retryable=True,
            )
