from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.admin_clients import create_admin_client_range_invoice
from app.models.client_record import ClientAutoInvoiceOccurrence, ClientAutoInvoiceRule
from app.models.user import User, UserRole
from app.schemas.admin import AdminRangeInvoiceCreateRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoInvoiceBillingJobResult:
    checked: int
    generated: int
    skipped_empty: int
    skipped_duplicate: int
    failed: int


def _months_for_frequency(frequency: str) -> int:
    normalized = (frequency or "").strip().upper()
    if normalized == "QUARTERLY":
        return 3
    if normalized == "YEARLY":
        return 12
    return 1


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _next_cycle_anchor(cycle_anchor: date, *, frequency: str) -> date:
    return _add_months(cycle_anchor, _months_for_frequency(frequency))


def _compute_period_for_occurrence(
    *,
    cycle_anchor: date,
    frequency: str,
    billing_timing: str,
) -> tuple[date, date]:
    months = _months_for_frequency(frequency)
    normalized_timing = (billing_timing or "").strip().upper()
    if normalized_timing == "PREVIOUS_LESSONS":
        period_start = _add_months(cycle_anchor, -months)
        period_end = cycle_anchor
        return period_start, period_end
    period_start = cycle_anchor
    period_end = _add_months(cycle_anchor, months)
    return period_start, period_end


def _compute_due_date(
    *,
    issued_date: date,
    due_date_rule_type: str,
    due_date_days_offset: int | None,
) -> date:
    if (due_date_rule_type or "").strip().upper() == "X_DAYS_AFTER_ISSUE":
        return issued_date + timedelta(days=max(0, int(due_date_days_offset or 0)))
    return issued_date


def _auto_period_scope_from_timing(billing_timing: str) -> str:
    return "PAST" if (billing_timing or "").strip().upper() == "PREVIOUS_LESSONS" else "FUTURE"


def run_auto_invoice_billing_job(db: Session, *, now: datetime, limit: int = 200) -> AutoInvoiceBillingJobResult:
    today = now.date()
    rules = db.scalars(
        select(ClientAutoInvoiceRule)
        .where(
            ClientAutoInvoiceRule.status == "ACTIVE",
            ClientAutoInvoiceRule.next_run_date <= today,
        )
        .order_by(ClientAutoInvoiceRule.next_run_date.asc(), ClientAutoInvoiceRule.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).all()
    actor = db.scalar(
        select(User)
        .where(User.role == UserRole.ADMIN)
        .order_by(User.created_at.asc())
        .limit(1)
    )

    checked = 0
    generated = 0
    skipped_empty = 0
    skipped_duplicate = 0
    failed = 0

    if actor is None:
        return AutoInvoiceBillingJobResult(
            checked=len(rules),
            generated=0,
            skipped_empty=0,
            skipped_duplicate=0,
            failed=len(rules),
        )

    for rule in rules:
        checked += 1
        try:
            while rule.next_run_date <= today:
                cycle_anchor = rule.next_run_date
                cycle_key = f"{cycle_anchor.isoformat()}::{rule.frequency}::{rule.billing_timing}"
                existing_occurrence = db.scalar(
                    select(ClientAutoInvoiceOccurrence.id)
                    .where(
                        ClientAutoInvoiceOccurrence.rule_id == rule.id,
                        ClientAutoInvoiceOccurrence.cycle_key == cycle_key,
                    )
                    .limit(1)
                )
                if existing_occurrence is not None:
                    skipped_duplicate += 1
                    rule.next_run_date = _next_cycle_anchor(cycle_anchor, frequency=rule.frequency)
                    db.add(rule)
                    db.commit()
                    continue

                period_start, period_end = _compute_period_for_occurrence(
                    cycle_anchor=cycle_anchor,
                    frequency=rule.frequency,
                    billing_timing=rule.billing_timing,
                )
                due_date = _compute_due_date(
                    issued_date=cycle_anchor,
                    due_date_rule_type=rule.due_date_rule_type,
                    due_date_days_offset=rule.due_date_days_offset,
                )

                occurrence = ClientAutoInvoiceOccurrence(
                    rule_id=rule.id,
                    cycle_key=cycle_key,
                    period_start_date=period_start,
                    period_end_date=period_end,
                    status="PROCESSING",
                    note_id=None,
                    generated_at=now,
                )
                db.add(occurrence)
                db.flush()

                try:
                    invoice_out = create_admin_client_range_invoice(
                        client_id=rule.user_id,
                        payload=AdminRangeInvoiceCreateRequest(
                            issued_date=cycle_anchor,
                            start_date=period_start,
                            end_date=period_end,
                            due_date=due_date,
                            no_due_date=False,
                            include_pending=bool(rule.include_pending_lines),
                            include_cancelled=bool(rule.include_cancelled_lines),
                            layout="COMPILED",
                            generation_mode="AUTO",
                            group_adjustments_by_type=False,
                            include_discount_adjustments=True,
                            include_supplement_adjustments=True,
                            auto_cycle_start_date=cycle_anchor,
                            auto_period_scope=_auto_period_scope_from_timing(rule.billing_timing),
                            auto_frequency="MONTHLY",
                            auto_repeat_every=_months_for_frequency(rule.frequency),
                            auto_layout_style="CONDENSED",
                            auto_include_previous_balance=True,
                            auto_send_email=False,
                            auto_footer_note=None,
                            auto_exclude_pack_subscription_lines=False,
                            invoice_number=None,
                            public_note=None,
                            private_note=None,
                        ),
                        db=db,
                        actor=actor,
                    )
                except HTTPException as exc:
                    if exc.status_code == 404:
                        occurrence.status = "SKIPPED_EMPTY"
                        occurrence.note_id = None
                        occurrence.generated_at = now
                        rule.next_run_date = _next_cycle_anchor(cycle_anchor, frequency=rule.frequency)
                        db.add(occurrence)
                        db.add(rule)
                        db.commit()
                        skipped_empty += 1
                        continue
                    db.rollback()
                    failed += 1
                    logger.exception("Auto invoice generation failed | rule_id=%s | detail=%s", rule.id, exc.detail)
                    break
                except Exception:
                    db.rollback()
                    failed += 1
                    logger.exception("Unexpected auto invoice generation error | rule_id=%s", rule.id)
                    break

                occurrence.status = "GENERATED"
                occurrence.note_id = invoice_out.note_id
                occurrence.generated_at = now
                rule.last_generated_at = now
                rule.next_run_date = _next_cycle_anchor(cycle_anchor, frequency=rule.frequency)
                db.add(occurrence)
                db.add(rule)
                db.commit()
                generated += 1
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("Auto invoice rule loop failed | rule_id=%s", rule.id)

    return AutoInvoiceBillingJobResult(
        checked=checked,
        generated=generated,
        skipped_empty=skipped_empty,
        skipped_duplicate=skipped_duplicate,
        failed=failed,
    )
