from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PaymentPlanScheduleInput:
    payment_method_code: str
    total_ttc: Decimal
    registration_date: date
    currency: str = "EUR"
    schedule_type: str = "single"
    schedule_rules: dict[str, Any] | None = None
    payment_method_label: str | None = None
    fixed_fees_ttc: Decimal = Decimal("0.00")


def _split_amount(total: Decimal, parts: int) -> list[Decimal]:
    if parts <= 0:
        return [_quantize(total)]
    base = _quantize(total / Decimal(parts))
    out = [base for _ in range(parts)]
    delta = _quantize(total - sum(out))
    out[-1] = _quantize(out[-1] + delta)
    return out


def _monthly_parts_with_first_fixed_fees(total: Decimal, installments: int, fixed_fees_ttc: Decimal) -> list[Decimal]:
    if installments <= 1:
        return [_quantize(total)]
    fixed_fees = max(Decimal("0.00"), min(_quantize(fixed_fees_ttc), total))
    if fixed_fees <= Decimal("0.00"):
        return _split_amount(total, installments)
    recurring_total = _quantize(total - fixed_fees)
    out = _split_amount(recurring_total, installments)
    out[0] = _quantize(out[0] + fixed_fees)
    return out


def _month_label(month: int) -> str:
    labels = {
        1: "janvier",
        2: "fevrier",
        3: "mars",
        4: "avril",
        5: "mai",
        6: "juin",
        7: "juillet",
        8: "aout",
        9: "septembre",
        10: "octobre",
        11: "novembre",
        12: "decembre",
    }
    return labels.get(month, f"mois {month}")


def _to_int(value: object, default: int) -> int:
    try:
        parsed = int(str(value))
    except Exception:
        return default
    return parsed


def _default_installments(schedule_type: str) -> int:
    normalized = schedule_type.strip().lower()
    if normalized == "split_2":
        return 2
    if normalized == "split_3":
        return 3
    if normalized == "split_4":
        return 4
    if normalized == "monthly":
        return 10
    return 1


def _legacy_installments_from_method_code(method_code: str) -> int:
    normalized = method_code.strip().upper()
    if normalized in {"CHECK_2", "CHEQUE_2", "CHEQUE_X2"}:
        return 2
    if normalized in {"CHECK_3", "CHEQUE_3", "CHEQUE_X3"}:
        return 3
    if normalized in {"CHECK_4", "CHEQUE_4", "CHEQUE_X4", "CARD_4X_FEES"}:
        return 4
    return 1


def _default_deferred_months(schedule_type: str, installments: int) -> list[int]:
    normalized = schedule_type.strip().lower()
    if normalized == "split_2":
        return [12]
    if normalized == "split_3":
        return [12, 2]
    if normalized == "split_4":
        return [12, 2, 4]
    if normalized == "monthly":
        start = _to_int(date.today().month, 1)
        out: list[int] = []
        for index in range(max(0, installments - 1)):
            out.append(((start + index) % 12) + 1)
        return out
    return []


def _legacy_deferred_months_from_method_code(method_code: str, installments: int) -> list[int]:
    normalized = method_code.strip().upper()
    if normalized in {"CHECK_2", "CHEQUE_2", "CHEQUE_X2"}:
        return [12]
    if normalized in {"CHECK_3", "CHEQUE_3", "CHEQUE_X3"}:
        return [12, 2]
    if normalized in {"CHECK_4", "CHEQUE_4", "CHEQUE_X4", "CARD_4X_FEES"}:
        return [12, 2, 4]
    return _default_deferred_months("single", installments)


def build_payment_schedule(payload: PaymentPlanScheduleInput) -> list[dict[str, object]]:
    method_code = payload.payment_method_code.strip().upper()
    schedule_type = payload.schedule_type.strip().lower()
    rules = payload.schedule_rules or {}
    method_label = (payload.payment_method_label or "").strip() or method_code
    total = _quantize(payload.total_ttc)
    default_installments = _default_installments(schedule_type)
    if default_installments <= 1:
        default_installments = _legacy_installments_from_method_code(method_code)
    installments = _to_int(rules.get("installment_count"), default_installments)
    installments = max(1, min(24, installments))
    if installments <= 1:
        return [
            {
                "label": "Paiement unique",
                "due_type": "on_registration",
                "due_label": "à réception de votre facture",
                "amount_ttc": str(total),
                "currency": payload.currency,
                "payment_method": method_label,
            }
        ]

    deferred_raw = rules.get("deferred_due_months")
    deferred_months: list[int] = []
    if isinstance(deferred_raw, list):
        for item in deferred_raw:
            try:
                month = int(str(item))
            except Exception:
                continue
            if 1 <= month <= 12:
                deferred_months.append(month)
    if not deferred_months:
        deferred_months = _default_deferred_months(schedule_type, installments)
    if not deferred_months:
        deferred_months = _legacy_deferred_months_from_method_code(method_code, installments)
    deferred_months = deferred_months[: max(0, installments - 1)]
    check_method_codes = {
        "CHECK",
        "CHEQUE",
        "CHECK_2",
        "CHECK_3",
        "CHECK_4",
        "CHEQUE_2",
        "CHEQUE_3",
        "CHEQUE_4",
        "CHEQUE_X2",
        "CHEQUE_X3",
        "CHEQUE_X4",
    }
    if method_code in check_method_codes and len(deferred_months) >= 1:
        deferred_months[0] = 12

    is_monthly_schedule = schedule_type == "monthly" or method_code in {"CARD_MONTHLY", "CB_MONTHLY"}
    parts = (
        _monthly_parts_with_first_fixed_fees(total, installments, _quantize(payload.fixed_fees_ttc))
        if is_monthly_schedule
        else _split_amount(total, installments)
    )
    is_check = method_code in check_method_codes
    out: list[dict[str, object]] = []
    for index, amount in enumerate(parts):
        item: dict[str, object] = {
            "label": f"{index + 1}e echeance",
            "due_type": "fixed_month",
            "amount_ttc": str(amount),
            "currency": payload.currency,
            "payment_method": method_label,
        }
        if index == 0:
            item["label"] = "1er cheque" if is_check else "1ere echeance"
            item["due_type"] = "before_first_course" if is_check else "on_registration"
            item["due_label"] = "avant le démarrage du 1er cours" if is_check else "à réception de votre facture"
        else:
            month = deferred_months[index - 1] if (index - 1) < len(deferred_months) else None
            if month is not None:
                item["due_month"] = month
                item["due_label"] = _month_label(month)
            if is_check:
                item["label"] = f"{index + 1}e cheque"
        out.append(item)
    return out
