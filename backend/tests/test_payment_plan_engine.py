from datetime import date
from decimal import Decimal

from app.services.quotes.payment_plan_engine import PaymentPlanScheduleInput, build_payment_schedule


def _amounts(schedule: list[dict[str, object]]) -> list[Decimal]:
    return [Decimal(str(item["amount_ttc"])) for item in schedule]


def test_monthly_card_schedule_fallback_places_fixed_fees_on_first_installment() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY",
            payment_method_label="Carte bancaire mensuelle",
            schedule_type="monthly",
            schedule_rules={"installment_count": 10},
            total_ttc=Decimal("797.00"),
            fixed_fees_ttc=Decimal("120.00"),
            registration_date=date(2026, 5, 20),
        )
    )

    amounts = _amounts(schedule)
    assert amounts == [Decimal("187.70")] + [Decimal("67.70")] * 9
    assert sum(amounts) == Decimal("797.00")


def test_monthly_card_schedule_uses_real_course_months_and_first_fixed_fees() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY",
            payment_method_label="Carte bancaire mensuelle",
            schedule_type="monthly",
            schedule_rules={"installment_count": 10},
            total_ttc=Decimal("797.00"),
            fixed_fees_ttc=Decimal("120.00"),
            monthly_service_amounts_ttc={
                "2026-09": Decimal("76.00"),
                "2026-10": Decimal("152.00"),
                "2026-11": Decimal("114.00"),
                "2026-12": Decimal("76.00"),
                "2027-01": Decimal("76.00"),
                "2027-02": Decimal("38.00"),
                "2027-03": Decimal("76.00"),
                "2027-04": Decimal("38.00"),
                "2027-05": Decimal("19.00"),
                "2027-06": Decimal("12.00"),
            },
            registration_date=date(2026, 5, 20),
        )
    )

    amounts = _amounts(schedule)
    assert amounts == [
        Decimal("196.00"),
        Decimal("152.00"),
        Decimal("114.00"),
        Decimal("76.00"),
        Decimal("76.00"),
        Decimal("38.00"),
        Decimal("76.00"),
        Decimal("38.00"),
        Decimal("19.00"),
        Decimal("12.00"),
    ]
    assert sum(amounts) == Decimal("797.00")
    assert schedule[0]["due_date"] == "2026-09-01"
    assert schedule[0]["due_label"] == "1er septembre 2026"
    assert schedule[-1]["due_date"] == "2027-06-01"
    assert schedule[-1]["due_label"] == "1er juin 2027"


def test_monthly_card_schedule_keeps_total_when_rounding_with_fixed_fees() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY",
            schedule_type="monthly",
            schedule_rules={"installment_count": 3},
            total_ttc=Decimal("100.00"),
            fixed_fees_ttc=Decimal("10.00"),
            registration_date=date(2026, 5, 20),
        )
    )

    amounts = _amounts(schedule)
    assert amounts == [Decimal("40.00"), Decimal("30.00"), Decimal("30.00")]
    assert sum(amounts) == Decimal("100.00")


def test_non_monthly_schedule_ignores_fixed_fees() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CHECK_2",
            schedule_type="split_2",
            schedule_rules={"installment_count": 2},
            total_ttc=Decimal("100.00"),
            fixed_fees_ttc=Decimal("20.00"),
            registration_date=date(2026, 5, 20),
        )
    )

    assert _amounts(schedule) == [Decimal("50.00"), Decimal("50.00")]
