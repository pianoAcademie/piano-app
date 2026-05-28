from __future__ import annotations

import os
import sys
from calendar import monthrange
from datetime import date, timedelta
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import String, cast, false, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import SessionLocal
from app.models.client_record import ClientAutoInvoiceOccurrence, ClientAutoInvoiceRule, ClientNoteEntry
from app.models.plan import ClientPlanSubscription, Plan
from app.models.quote import Quote, QuoteAcceptanceFollowup
from app.models.user import User
from app.services.payment_receipts import _parse_invoice_range_note_entry

SCRIPT_PREFIX = "PROD_THUILLIEZ_EMILIE_BILLING_INSPECT"


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _json_object(value: object | None) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _uuid_value(value: object | None) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _months_for_frequency(frequency: str) -> int:
    normalized = (frequency or "").strip().upper()
    if normalized == "QUARTERLY":
        return 3
    if normalized == "YEARLY":
        return 12
    return 1


def _period_for_rule(rule: ClientAutoInvoiceRule) -> tuple[date, date]:
    months = _months_for_frequency(rule.frequency)
    if (rule.billing_timing or "").strip().upper() == "PREVIOUS_LESSONS":
        return _add_months(rule.next_run_date, -months), rule.next_run_date
    return rule.next_run_date, _add_months(rule.next_run_date, months)


def _due_date_for_rule(rule: ClientAutoInvoiceRule) -> date:
    if (rule.due_date_rule_type or "").strip().upper() == "X_DAYS_AFTER_ISSUE":
        return rule.next_run_date + timedelta(days=max(0, int(rule.due_date_days_offset or 0)))
    return rule.next_run_date


def main() -> None:
    with SessionLocal() as db:
        emilie = db.scalar(
            select(User)
            .where(
                User.last_name.ilike("%thuilliez%"),
                or_(User.first_name.ilike("%emilie%"), User.email.ilike("%boulmimienoah%")),
            )
            .order_by(User.created_at.desc())
            .limit(1)
        )
        if emilie is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] emilie_thuilliez_not_found")
        _print(f"user={emilie.id}|{emilie.first_name} {emilie.last_name}|{emilie.email}|status={getattr(emilie.client_status, 'value', emilie.client_status)}")

        quote_rows = db.execute(
            select(Quote, QuoteAcceptanceFollowup)
            .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id, isouter=True)
            .where(
                or_(
                    Quote.client_id == emilie.id,
                    cast(Quote.meta, JSONB).cast(String).ilike("%Thuilliez%"),
                    cast(QuoteAcceptanceFollowup.payload, JSONB).cast(String).ilike("%Thuilliez%"),
                )
            )
            .order_by(Quote.updated_at.desc())
            .limit(5)
        ).all()

        relevant_user_ids = {emilie.id}
        subscription_id: UUID | None = None
        for quote, followup in quote_rows:
            payload = _json_object(followup.payload if followup is not None else None)
            execution = _json_object(payload.get("quote_to_enrollment_execution"))
            candidate_subscription_id = _uuid_value(execution.get("subscription_id"))
            student_id = _uuid_value(execution.get("student_client_id"))
            billing_id = _uuid_value(execution.get("billing_client_id"))
            if student_id:
                relevant_user_ids.add(student_id)
            if billing_id:
                relevant_user_ids.add(billing_id)
            if quote.quote_number == "DV-20260520080553-B33C" or (candidate_subscription_id and quote.client_id == emilie.id):
                subscription_id = candidate_subscription_id
            _print(
                "quote="
                f"{quote.quote_number}|status={quote.status}|total={quote.total_ttc}|approved_at={quote.approved_at}|"
                f"followup={followup.status if followup else '-'}|payment_status={followup.payment_method_status if followup else '-'}|"
                f"executed_at={execution.get('executed_at') or '-'}|subscription_id={candidate_subscription_id or '-'}|"
                f"student_id={student_id or '-'}|billing_id={billing_id or '-'}"
            )

        if subscription_id is None:
            _print("target_subscription=missing")
            return

        row = db.execute(
            select(ClientPlanSubscription, Plan)
            .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
            .where(ClientPlanSubscription.id == subscription_id)
            .limit(1)
        ).first()
        if row is None:
            _print(f"subscription_missing={subscription_id}")
            return
        subscription, plan = row
        relevant_user_ids.add(subscription.user_id)
        if subscription.payer_contact_id:
            relevant_user_ids.add(subscription.payer_contact_id)
        student = db.get(User, subscription.user_id)
        payer = db.get(User, subscription.payer_contact_id) if subscription.payer_contact_id else None
        _print(
            "subscription="
            f"{subscription.id}|plan={plan.name}|kind={getattr(plan.kind, 'value', plan.kind)}|"
            f"student={student.first_name if student else '-'} {student.last_name if student else ''}|"
            f"payer={payer.first_name if payer else '-'} {payer.last_name if payer else ''}|"
            f"status={getattr(subscription.status, 'value', subscription.status)}|billing_method={subscription.billing_method_code or '-'}|"
            f"started_at={subscription.started_at}|next_payment_at={subscription.next_payment_at}|"
            f"current_period={subscription.current_period_start}->{subscription.current_period_end}|auto_renew={subscription.auto_renew}"
        )

        rules = db.scalars(
            select(ClientAutoInvoiceRule)
            .where(ClientAutoInvoiceRule.user_id.in_(relevant_user_ids), ClientAutoInvoiceRule.status.in_(["ACTIVE", "PAUSED"]))
            .order_by(ClientAutoInvoiceRule.updated_at.desc(), ClientAutoInvoiceRule.created_at.desc())
        ).all()
        _print(f"auto_invoice_rules={len(rules)}")
        for rule in rules:
            period_start, period_end = _period_for_rule(rule)
            due_date = _due_date_for_rule(rule)
            _print(
                "auto_rule="
                f"{rule.id}|client_id={rule.user_id}|status={rule.status}|cycle_start={rule.cycle_start_date}|"
                f"frequency={rule.frequency}|timing={rule.billing_timing}|next_run={rule.next_run_date}|"
                f"period={period_start}->{period_end}|due_rule={rule.due_date_rule_type}|offset={rule.due_date_days_offset}|due_date={due_date}"
            )
            occurrences = db.scalars(
                select(ClientAutoInvoiceOccurrence)
                .where(ClientAutoInvoiceOccurrence.rule_id == rule.id)
                .order_by(ClientAutoInvoiceOccurrence.generated_at.desc())
                .limit(3)
            ).all()
            for occurrence in occurrences:
                _print(
                    "occurrence="
                    f"{occurrence.cycle_key}|period={occurrence.period_start_date}->{occurrence.period_end_date}|"
                    f"status={occurrence.status}|note_id={occurrence.note_id or '-'}|generated_at={occurrence.generated_at}"
                )

        notes = db.scalars(
            select(ClientNoteEntry)
            .where(ClientNoteEntry.user_id.in_(relevant_user_ids))
            .order_by(ClientNoteEntry.created_at.desc())
            .limit(80)
        ).all()
        september_invoices = []
        for note in notes:
            metadata = _parse_invoice_range_note_entry(note)
            if not metadata:
                continue
            if (
                str(metadata.get("issued_date") or "").startswith("2026-09")
                or str(metadata.get("start_date") or "").startswith("2026-09")
                or str(metadata.get("auto_cycle_start_date") or "").startswith("2026-09")
            ):
                september_invoices.append((note, metadata))
        _print(f"september_invoice_notes={len(september_invoices)}")
        for note, metadata in september_invoices[:5]:
            _print(
                "invoice="
                f"{metadata.get('invoice_number') or '-'}|mode={metadata.get('generation_mode') or '-'}|"
                f"issued={metadata.get('issued_date') or '-'}|due={metadata.get('due_date') or '-'}|"
                f"period={metadata.get('start_date') or '-'}->{metadata.get('end_date') or '-'}|"
                f"auto_cycle={metadata.get('auto_cycle_start_date') or '-'}|note_id={note.id}"
            )


if __name__ == "__main__":
    main()
