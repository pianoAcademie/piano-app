from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PaymentPlanScheduleInput:
    payment_method_code: str
    total_ttc: Decimal
    registration_date: date
    currency: str = "EUR"


def _split_amount(total: Decimal, parts: int) -> list[Decimal]:
    if parts <= 0:
        return [_quantize(total)]
    base = _quantize(total / Decimal(parts))
    out = [base for _ in range(parts)]
    delta = _quantize(total - sum(out))
    out[-1] = _quantize(out[-1] + delta)
    return out


def build_payment_schedule(payload: PaymentPlanScheduleInput) -> list[dict[str, object]]:
    method_code = payload.payment_method_code.strip().upper()
    total = _quantize(payload.total_ttc)

    if method_code in {"CHECK_2", "CHEQUE_2", "CHEQUE_X2"}:
        parts = _split_amount(total, 2)
        return [
            {
                "label": "1er cheque",
                "due_type": "on_registration",
                "amount_ttc": str(parts[0]),
                "currency": payload.currency,
            },
            {
                "label": "2e cheque",
                "due_type": "fixed_month",
                "due_month": 2,
                "due_label": "fevrier",
                "amount_ttc": str(parts[1]),
                "currency": payload.currency,
            },
        ]

    if method_code in {"CHECK_4", "CHEQUE_4", "CHEQUE_X4"}:
        parts = _split_amount(total, 4)
        return [
            {
                "label": "1er cheque",
                "due_type": "on_registration",
                "amount_ttc": str(parts[0]),
                "currency": payload.currency,
            },
            {
                "label": "2e cheque",
                "due_type": "fixed_month",
                "due_month": 12,
                "due_label": "decembre",
                "amount_ttc": str(parts[1]),
                "currency": payload.currency,
            },
            {
                "label": "3e cheque",
                "due_type": "fixed_month",
                "due_month": 1,
                "due_label": "janvier",
                "amount_ttc": str(parts[2]),
                "currency": payload.currency,
            },
            {
                "label": "4e cheque",
                "due_type": "fixed_month",
                "due_month": 4,
                "due_label": "avril",
                "amount_ttc": str(parts[3]),
                "currency": payload.currency,
            },
        ]

    return [
        {
            "label": "Paiement unique",
            "due_type": "on_registration",
            "amount_ttc": str(total),
            "currency": payload.currency,
        }
    ]

