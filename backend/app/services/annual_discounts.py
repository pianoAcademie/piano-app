"""Annual discount policy. Eligibility is established by the review service, never by booking order."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.services.client_pricing import (
    PriceUnit, PricingChannel, PricingComponent, PricingComputation, build_price_version, split_tax,
)

POLICY_VERSION = "annual-discounts-2026-2027-v1"


@dataclass(frozen=True)
class AnnualEligibility:
    site: str
    audience: str
    activity_family: str
    family: bool = False
    returning: bool = False
    second_course: bool = False
    channel: str = "ANNUAL_FORFAIT"


def annual_discount_price(*, base: Decimal, eligibility: AnnualEligibility, vat_rate: Decimal,
                          currency: str = "EUR", source: str = "annual-review",
                          evidence_version: str = "", at: datetime | None = None) -> PricingComputation:
    base = Decimal(base).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not base.is_finite() or base < 0:
        raise ValueError("Tarif de base invalide")
    e = eligibility
    components: list[PricingComponent] = []
    eligible = e.channel == "ANNUAL_FORFAIT" and base > 0 and currency == "EUR"
    collective = e.activity_family == "COLLECTIVE_ONSITE"
    if eligible and e.site == "PARIS" and collective and e.audience == "CHILD":
        # Fixed 32/29 prices are only agreed for the 38 EUR standard course.
        if base != Decimal("38"):
            raise ValueError("Tarif collectif enfant Paris different de 38 EUR : arbitrage requis")
        if e.second_course:
            components.append(PricingComponent("SECOND_COURSE", "Remise deuxième cours", Decimal("-6")))
            if e.family:
                rounded = (Decimal("32") * Decimal("0.90")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                components.append(PricingComponent("FAMILY", "Remise famille sur deuxième cours (10 %, prix arrondi)", rounded - Decimal("32")))
        elif e.family:
            components.append(PricingComponent("FAMILY", "Remise famille", Decimal("-4")))
        elif e.returning:
            components.append(PricingComponent("LOYALTY", "Remise fidélité — inscrit la saison précédente", Decimal("-2")))
    elif eligible and collective and e.audience in {"CHILD", "TEEN"}:
        if e.site == "PARIS" and e.audience == "TEEN":
            if e.second_course:
                components.append(PricingComponent("SECOND_COURSE", "Remise deuxième cours adolescent", Decimal("-2")))
            if e.family:
                components.append(PricingComponent("FAMILY", "Remise famille adolescent", Decimal("-2")))
        elif e.site == "BAR_LE_DUC" and e.family and not e.second_course:
            components.append(PricingComponent("FAMILY", "Remise famille Bar-le-Duc", Decimal("-2")))
    elif eligible and e.site == "PARIS" and e.activity_family == "MUSICAL_AWAKENING" and e.audience == "CHILD" and e.family and not e.second_course:
        components.append(PricingComponent("FAMILY", "Remise famille éveil musical", Decimal("-2")))
    net = base + sum((c.amount_ttc for c in components), Decimal("0"))
    if net < 0:
        raise ValueError("Les remises dépassent le tarif du cours")
    rate = Decimal(vat_rate).quantize(Decimal("0.001"))
    ht, tax, total = split_tax(net, vat_rate=rate)
    return PricingComputation(
        channel=PricingChannel.ANNUAL_FORFAIT, source=source,
        version=build_price_version(POLICY_VERSION, base=base, eligibility=e.__dict__,
                                    vat_rate=rate, evidence_version=evidence_version, currency=currency),
        unit=PriceUnit.PER_SESSION, base_amount_ttc=base, components=tuple(components),
        amount_excl_vat=ht, vat_rate=rate, vat_amount=tax, total_incl_vat=total,
        currency=currency, calculated_at=at or datetime.now(timezone.utc), locked=True,
    )
