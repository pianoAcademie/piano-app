from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.services.annual_discounts import AnnualEligibility, annual_discount_price
from app.services.annual_contracts import bind_contract_course, contract_price_for_session
from app.services.client_pricing import booking_snapshot_fields
from app.api.routes.quotes import _quote_discount_target_service_line


@pytest.mark.parametrize("site,audience,family,returning,second,base,net", [
    ("PARIS", "CHILD", False, False, False, 38, 38),
    ("PARIS", "CHILD", False, True, False, 38, 36),
    ("PARIS", "CHILD", True, False, False, 38, 34),
    ("PARIS", "CHILD", True, True, False, 38, 34),
    ("PARIS", "CHILD", False, True, True, 38, 32),
    ("PARIS", "CHILD", True, True, True, 38, 29),
    ("PARIS", "CHILD", True, False, True, 38, 29),
    ("PARIS", "TEEN", False, True, False, 38, 38),
    ("PARIS", "TEEN", True, True, False, 38, 36),
    ("PARIS", "TEEN", False, False, True, 38, 36),
    ("PARIS", "TEEN", True, True, True, 38, 34),
    ("BAR_LE_DUC", "CHILD", True, True, False, 22, 20),
    ("BAR_LE_DUC", "CHILD", False, True, True, 22, 22),
    ("BAR_LE_DUC", "TEEN", True, True, False, 22, 20),
    ("BAR_LE_DUC", "CHILD", True, True, True, 22, 22),
    ("PARIS", "ADULT", True, True, True, 38, 38),
    ("OTHER", "CHILD", True, True, True, 38, 38),
])
def test_approved_rules(site, audience, family, returning, second, base, net):
    price = annual_discount_price(base=Decimal(base), vat_rate=Decimal(20),
        eligibility=AnnualEligibility(site, audience, "COLLECTIVE_ONSITE", family, returning, second))
    assert price.total_incl_vat == Decimal(net)
    assert price.amount_excl_vat + price.vat_amount == Decimal(net)
    assert price.base_amount_ttc + sum(c.amount_ttc for c in price.components) == Decimal(net)


@pytest.mark.parametrize("channel", ["TRIAL", "EXTERNAL_UNIT", "PACK", "SUBSCRIPTION"])
def test_no_discount_outside_annual_contract(channel):
    price = annual_discount_price(base=Decimal(38), vat_rate=Decimal(20),
        eligibility=AnnualEligibility("PARIS", "CHILD", "COLLECTIVE_ONSITE", True, True, True, channel))
    assert price.total_incl_vat == 38 and not price.components


@pytest.mark.parametrize("family_code,site,base,expected", [
    ("MUSICAL_AWAKENING", "PARIS", 22, 20), ("MUSICAL_AWAKENING", "BAR_LE_DUC", 12, 12),
    ("SOLFEGE", "PARIS", 0, 0), ("PRIVATE", "PARIS", 80, 80),
])
def test_other_families(family_code, site, base, expected):
    p = annual_discount_price(base=Decimal(base), vat_rate=Decimal(20), eligibility=AnnualEligibility(site, "CHILD", family_code, True, True))
    assert p.total_incl_vat == expected


def test_unknown_paris_base_requires_review():
    with pytest.raises(ValueError):
        annual_discount_price(base=Decimal(39), vat_rate=Decimal(20), eligibility=AnnualEligibility("PARIS", "CHILD", "COLLECTIVE_ONSITE", True))


def test_contract_keeps_components_and_never_uses_booking_order():
    p = annual_discount_price(base=Decimal(38), vat_rate=Decimal(20), eligibility=AnnualEligibility("PARIS", "CHILD", "COLLECTIVE_ONSITE", True, True, True))
    now = datetime.now(timezone.utc)
    source = SimpleNamespace(id=uuid4(), course_type_id=uuid4(), location_id=uuid4(), recurrence_group_id=uuid4(), start_at_utc=now, end_at_utc=now + timedelta(hours=1))
    decision = {"course_key": "course-2", "activity_id": str(source.course_type_id), "location_id": str(source.location_id),
        "duration_minutes": 60, "quantity": "1", "version": p.version, "pricing": p.snapshot_breakdown(), "base": "38"}
    subscription = SimpleNamespace(annual_pricing_terms=[])
    bind_contract_course(subscription, decision, [source])
    resolved = contract_price_for_session(subscription, source, now=now)
    assert resolved.total_incl_vat == 29
    assert resolved.components == p.components
    assert booking_snapshot_fields(resolved)["price_book_version_snapshot"] == p.version
    # A newly appended date in the same series is not included in the accepted quantity.
    source.id = uuid4()
    with pytest.raises(HTTPException, match="cours contractuel"):
        contract_price_for_session(subscription, source, now=now)


def test_explicit_discount_target_beats_equal_quantities():
    first = SimpleNamespace(meta={"annual_course_key": "one"}, amount_ttc=380)
    second = SimpleNamespace(meta={"annual_course_key": "two"}, amount_ttc=380)
    discount = SimpleNamespace(meta={"target_course_key": "two"})
    assert _quote_discount_target_service_line(discount, [first, second]) is second
    with pytest.raises(HTTPException):
        _quote_discount_target_service_line(discount, [first])
