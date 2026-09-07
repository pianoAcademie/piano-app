from datetime import date, datetime, timezone

from app.api.routes.quotes import _quote_monthly_rule_next_run_date
from app.services.auto_invoice_billing import _compute_due_date


def test_quote_monthly_rule_keeps_first_school_month_for_late_transformation() -> None:
    assert _quote_monthly_rule_next_run_date(
        today=date(2026, 9, 6),
        first_cycle_already_processed=False,
        last_generated_at=None,
    ) == date(2026, 9, 1)


def test_quote_monthly_rule_advances_after_first_cycle_was_processed() -> None:
    assert _quote_monthly_rule_next_run_date(
        today=date(2026, 9, 6),
        first_cycle_already_processed=True,
        last_generated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    ) == date(2026, 10, 1)


def test_monthly_due_date_fallback_is_never_before_issue_date() -> None:
    assert _compute_due_date(
        issued_date=date(2026, 9, 1),
        due_date_rule_type="X_DAYS_AFTER_ISSUE",
        due_date_days_offset=1,
    ) == date(2026, 9, 2)
