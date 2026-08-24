from datetime import date
from pathlib import Path

from app.api.routes.admin_clients import (
    _compute_auto_invoice_next_run_date,
    _compute_auto_invoice_period,
    _months_for_auto_invoice_frequency,
)
from app.services.auto_invoice_billing import (
    _compute_period_for_occurrence,
    _months_for_frequency,
    _next_cycle_anchor,
)


def test_bimonthly_frequency_is_two_months_in_preview_and_worker() -> None:
    assert _months_for_auto_invoice_frequency("BIMONTHLY") == 2
    assert _months_for_frequency("BIMONTHLY") == 2


def test_bimonthly_upcoming_period_and_next_anchor() -> None:
    cycle_anchor = date(2026, 9, 1)

    assert _compute_auto_invoice_period(
        cycle_anchor=cycle_anchor,
        frequency="BIMONTHLY",
        billing_timing="UPCOMING_LESSONS",
    ) == (date(2026, 9, 1), date(2026, 11, 1))
    assert _compute_period_for_occurrence(
        cycle_anchor=cycle_anchor,
        frequency="BIMONTHLY",
        billing_timing="UPCOMING_LESSONS",
    ) == (date(2026, 9, 1), date(2026, 11, 1))
    assert _next_cycle_anchor(cycle_anchor, frequency="BIMONTHLY") == date(2026, 11, 1)


def test_bimonthly_previous_period_includes_catch_up_window() -> None:
    cycle_anchor = date(2026, 9, 1)

    assert _compute_auto_invoice_period(
        cycle_anchor=cycle_anchor,
        frequency="BIMONTHLY",
        billing_timing="PREVIOUS_LESSONS",
    ) == (date(2026, 7, 1), date(2026, 9, 1))
    assert _compute_period_for_occurrence(
        cycle_anchor=cycle_anchor,
        frequency="BIMONTHLY",
        billing_timing="PREVIOUS_LESSONS",
    ) == (date(2026, 7, 1), date(2026, 9, 1))


def test_bimonthly_next_run_advances_by_two_months() -> None:
    assert _compute_auto_invoice_next_run_date(
        cycle_start_date=date(2026, 9, 1),
        frequency="BIMONTHLY",
        today=date(2027, 2, 15),
    ) == date(2027, 3, 1)


def test_bimonthly_frequency_is_allowed_by_database_migration() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260824_0207_allow_bimonthly_auto_invoice_rules.py"
    )

    source = migration_path.read_text(encoding="utf-8")

    assert "frequency IN ('MONTHLY','BIMONTHLY','QUARTERLY','YEARLY')" in source
