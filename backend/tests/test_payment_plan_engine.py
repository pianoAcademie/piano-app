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


def test_monthly_card_schedule_fallback_starts_on_first_course_month() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY",
            payment_method_label="Carte bancaire mensuelle",
            schedule_type="monthly",
            schedule_rules={"installment_count": 10},
            total_ttc=Decimal("797.00"),
            fixed_fees_ttc=Decimal("120.00"),
            monthly_start_month="2027-09",
            registration_date=date(2026, 5, 22),
        )
    )

    assert len(schedule) == 10
    assert schedule[0]["due_date"] == "2027-09-01"
    assert schedule[0]["due_label"] == "1er septembre 2027"
    assert schedule[1]["due_date"] == "2027-10-01"
    assert schedule[1]["due_label"] == "1er octobre 2027"
    assert schedule[-1]["due_date"] == "2028-06-01"
    assert schedule[-1]["due_label"] == "1er juin 2028"
    assert sum(_amounts(schedule)) == Decimal("797.00")


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


def test_monthly_fixed_card_schedule_uses_active_course_months_and_equal_amounts() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY_FIXED",
            payment_method_label="CB mensuel fixe",
            schedule_type="monthly_fixed",
            schedule_rules={"installment_count": 10},
            total_ttc=Decimal("1000.00"),
            fixed_fees_ttc=Decimal("120.00"),
            monthly_service_amounts_ttc={
                "2026-09": Decimal("300.00"),
                "2026-10": Decimal("100.00"),
                "2026-12": Decimal("600.00"),
            },
            registration_date=date(2026, 5, 20),
        )
    )

    amounts = _amounts(schedule)
    assert amounts == [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")]
    assert sum(amounts) == Decimal("1000.00")
    assert [item["due_date"] for item in schedule] == ["2026-09-01", "2026-10-01", "2026-12-01"]
    assert all(item["payment_method"] == "CB mensuel fixe" for item in schedule)


def test_monthly_fixed_card_schedule_fallback_starts_on_first_course_month() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY_FIXED",
            payment_method_label="CB mensuel fixe",
            schedule_type="monthly_fixed",
            schedule_rules={"installment_count": 3},
            total_ttc=Decimal("100.00"),
            fixed_fees_ttc=Decimal("50.00"),
            monthly_start_month="2026-09",
            registration_date=date(2026, 5, 20),
        )
    )

    assert [item["due_date"] for item in schedule] == ["2026-09-01", "2026-10-01", "2026-11-01"]
    assert _amounts(schedule) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_monthly_card_schedule_applies_credit_to_earliest_service_months() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CARD_MONTHLY",
            payment_method_label="Carte bancaire mensuelle",
            schedule_type="monthly",
            schedule_rules={"installment_count": 3},
            total_ttc=Decimal("100.00"),
            monthly_service_amounts_ttc={
                "2026-09": Decimal("50.00"),
                "2026-10": Decimal("50.00"),
                "2026-11": Decimal("50.00"),
            },
            registration_date=date(2026, 5, 20),
        )
    )

    amounts = _amounts(schedule)
    assert amounts == [Decimal("0.00"), Decimal("50.00"), Decimal("50.00")]
    assert sum(amounts) == Decimal("100.00")


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


def test_check_split_2_respects_configured_deferred_month() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CHECK",
            payment_method_label="Cheque",
            schedule_type="split_2",
            schedule_rules={"installment_count": 2, "deferred_due_months": [2]},
            total_ttc=Decimal("3610.00"),
            registration_date=date(2026, 5, 21),
        )
    )

    assert schedule[0]["label"] == "1er cheque"
    assert schedule[0]["due_label"] == "avant le démarrage du 1er cours"
    assert schedule[1]["label"] == "2e cheque"
    assert schedule[1]["due_month"] == 2
    assert schedule[1]["due_label"] == "fevrier"


def test_check_split_4_uses_december_february_april_deposits() -> None:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code="CHECK",
            payment_method_label="Cheque",
            schedule_type="split_4",
            schedule_rules={"installment_count": 4, "deferred_due_months": [2, 2, 4]},
            total_ttc=Decimal("1246.00"),
            registration_date=date(2026, 5, 21),
        )
    )

    assert [item["label"] for item in schedule] == ["1er cheque", "2e cheque", "3e cheque", "4e cheque"]
    assert schedule[0]["due_label"] == "avant le démarrage du 1er cours"
    assert [schedule[index]["due_month"] for index in range(1, 4)] == [12, 2, 4]
    assert [schedule[index]["due_label"] for index in range(1, 4)] == ["decembre", "fevrier", "avril"]
