from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from uuid import UUID


CENT = Decimal("0.01")


@dataclass(frozen=True)
class BillingAllocationInput:
    payer_user_id: UUID
    allocation_type: str
    allocation_value: Decimal | None


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_billing_allocations(rows: list[BillingAllocationInput]) -> list[BillingAllocationInput]:
    if len(rows) < 2:
        raise ValueError("Au moins deux payeurs sont nécessaires pour répartir une facture.")
    if len({row.payer_user_id for row in rows}) != len(rows):
        raise ValueError("Un payeur ne peut apparaître qu'une seule fois.")

    normalized: list[BillingAllocationInput] = []
    remainder_count = 0
    percent_total = Decimal("0.00")
    has_fixed = False
    for row in rows:
        allocation_type = (row.allocation_type or "").strip().upper()
        if allocation_type not in {"PERCENT", "FIXED", "REMAINDER"}:
            raise ValueError("Type de répartition inconnu.")
        if allocation_type == "REMAINDER":
            remainder_count += 1
            value = None
        else:
            if row.allocation_value is None:
                raise ValueError("La valeur de répartition est obligatoire.")
            value = money(row.allocation_value)
            if value <= Decimal("0.00"):
                raise ValueError("Chaque pourcentage ou montant doit être supérieur à zéro.")
            if allocation_type == "PERCENT":
                if value > Decimal("100.00"):
                    raise ValueError("Un pourcentage ne peut pas dépasser 100 %.")
                percent_total += value
            else:
                has_fixed = True
        normalized.append(BillingAllocationInput(row.payer_user_id, allocation_type, value))

    if remainder_count > 1:
        raise ValueError("Un seul payeur peut recevoir le solde restant.")
    if percent_total > Decimal("100.00"):
        raise ValueError("La somme des pourcentages ne peut pas dépasser 100 %.")
    if remainder_count == 0:
        if has_fixed:
            raise ValueError("Une répartition avec montant fixe doit désigner le payeur du solde restant.")
        if percent_total != Decimal("100.00"):
            raise ValueError("Sans payeur du solde, les pourcentages doivent totaliser exactement 100 %.")
    return normalized


def allocate_billing_total(
    total: Decimal,
    rows: list[BillingAllocationInput],
) -> dict[UUID, Decimal]:
    normalized = validate_billing_allocations(rows)
    invoice_total = money(total)
    if invoice_total < Decimal("0.00"):
        raise ValueError("La répartition automatique d'un avoir n'est pas prise en charge.")

    allocated: dict[UUID, Decimal] = {}
    remainder_row: BillingAllocationInput | None = None
    percent_rows: list[BillingAllocationInput] = []
    for row in normalized:
        if row.allocation_type == "REMAINDER":
            remainder_row = row
        elif row.allocation_type == "FIXED":
            allocated[row.payer_user_id] = money(row.allocation_value or Decimal("0.00"))
        else:
            percent_rows.append(row)
            allocated[row.payer_user_id] = money(
                invoice_total * (row.allocation_value or Decimal("0.00")) / Decimal("100.00")
            )

    subtotal = money(sum(allocated.values(), Decimal("0.00")))
    if subtotal > invoice_total:
        raise ValueError("La répartition dépasse le montant de la facture.")
    difference = money(invoice_total - subtotal)
    if remainder_row is not None:
        allocated[remainder_row.payer_user_id] = difference
    elif percent_rows:
        last = percent_rows[-1]
        allocated[last.payer_user_id] = money(allocated[last.payer_user_id] + difference)

    if money(sum(allocated.values(), Decimal("0.00"))) != invoice_total:
        raise ValueError("La répartition ne couvre pas exactement le montant de la facture.")
    return allocated


def allocate_signed_amount_by_targets(
    amount: Decimal,
    targets: dict[UUID, Decimal],
) -> dict[UUID, Decimal]:
    """Distribute a signed amount proportionally while preserving every cent."""

    normalized_targets = {payer_id: money(value) for payer_id, value in targets.items()}
    target_total = money(sum(normalized_targets.values(), Decimal("0.00")))
    if target_total <= Decimal("0.00"):
        raise ValueError("Le montant de référence de la répartition doit être positif.")

    normalized_amount = money(amount)
    sign = Decimal("-1") if normalized_amount < Decimal("0.00") else Decimal("1")
    cents_to_allocate = int((abs(normalized_amount) * 100).to_integral_value())
    if cents_to_allocate == 0:
        return {payer_id: Decimal("0.00") for payer_id in normalized_targets}

    raw_shares: list[tuple[UUID, Decimal, int]] = []
    allocated_cents = 0
    for payer_id, target in normalized_targets.items():
        raw_cents = Decimal(cents_to_allocate) * target / target_total
        floor_cents = int(raw_cents.to_integral_value(rounding=ROUND_FLOOR))
        raw_shares.append((payer_id, raw_cents - Decimal(floor_cents), floor_cents))
        allocated_cents += floor_cents

    remaining_cents = cents_to_allocate - allocated_cents
    order = sorted(raw_shares, key=lambda row: (-row[1], str(row[0])))
    extra_by_payer = {payer_id: 0 for payer_id in normalized_targets}
    for payer_id, _, _ in order[:remaining_cents]:
        extra_by_payer[payer_id] += 1

    return {
        payer_id: money(sign * Decimal(floor_cents + extra_by_payer[payer_id]) / Decimal("100"))
        for payer_id, _, floor_cents in raw_shares
    }
