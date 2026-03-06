from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RecurringChargeResult:
    success: bool
    provider_reference: str | None
    status: str
    message: str
    retryable: bool


class PaymentGateway:
    def create_recurring_charge(self, payload: RecurringChargeRequest) -> RecurringChargeResult:
        raise NotImplementedError


class PayplugGateway(PaymentGateway):
    def create_recurring_charge(self, payload: RecurringChargeRequest) -> RecurringChargeResult:
        return RecurringChargeResult(
            success=False,
            provider_reference=None,
            status="NOT_SUPPORTED",
            message="Recurring charge orchestration is not native in Payplug gateway implementation",
            retryable=False,
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
