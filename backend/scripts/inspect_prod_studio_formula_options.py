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


def _json_list(value: object | None) -> list[object]:
    return value if isinstance(value, list) else []


def _uuid_values(value: object | None) -> list[UUID]:
    out: list[UUID] = []
    for item in _json_list(value):
        try:
            out.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return out


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


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


def _user_label(user: User | None) -> str:
    if user is None:
        return "-"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return f"{name or '-'} <{user.email}> id={user.id} kind={getattr(user.client_kind, 'value', user.client_kind)}"


def main() -> None:
    with SessionLocal() as db:
        users = db.scalars(
            select(User)
            .where(
                or_(
                    User.email.ilike("%thuilliez%"),
                    User.first_name.ilike("%emilie%"),
                    User.first_name.ilike("%emilie%"),
                    User.last_name.ilike("%thuilliez%"),
                )
            )
            .order_by(User.created_at.desc())
        ).all()
        users = [
            user for user in users
            if "thuilliez" in f"{user.first_name or ''} {user.last_name or ''} {user.email or ''}".casefold()
            or "emilie" in f"{user.first_name or ''} {user.last_name or ''} {user.email or ''}".casefold()
        ]
        _print(f"user_matches={len(users)}")
        for user in users:
            _print(f"user={_user_label(user)} created_at={user.created_at} status={getattr(user.client_status, 'value', user.client_status)}")

        quote_rows = db.execute(
            select(Quote, QuoteAcceptanceFollowup)
            .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id, isouter=True)
            .where(
                or_(
                    cast(Quote.meta, JSONB).cast(String).ilike("%Thuilliez%"),
                    cast(Quote.meta, JSONB).cast(String).ilike("%Emilie%"),
                    cast(QuoteAcceptanceFollowup.payload, JSONB).cast(String).ilike("%Thuilliez%"),
                    cast(QuoteAcceptanceFollowup.payload, JSONB).cast(String).ilike("%Emilie%"),
                    Quote.client_id.in_([user.id for user in users]) if users else false(),
                )
            )
            .order_by(Quote.updated_at.desc())
            .limit(10)
        ).all()
        _print(f"quote_matches={len(quote_rows)}")

        relevant_user_ids = {user.id for user in users}
        relevant_subscription_ids: set[UUID] = set()
        for quote, followup in quote_rows:
            payload = _json_object(followup.payload if followup is not None else None)
            execution = _json_object(payload.get("quote_to_enrollment_execution"))
            subscription_id_raw = str(execution.get("subscription_id") or "").strip()
            created_subscription_ids = _uuid_values(execution.get("created_subscription_ids"))
            for subscription_id in created_subscription_ids:
                relevant_subscription_ids.add(subscription_id)
            if subscription_id_raw:
                try:
                    relevant_subscription_ids.add(UUID(subscription_id_raw))
                except ValueError:
                    pass
            student_id = str(execution.get("student_client_id") or "").strip()
            billing_id = str(execution.get("billing_client_id") or "").strip()
            for raw in [student_id, billing_id]:
                try:
                    relevant_user_ids.add(UUID(raw))
                except ValueError:
                    pass
            _print(
                "quote="
                f"{quote.quote_number}|id={quote.id}|status={quote.status}|total_ttc={quote.total_ttc}|"
                f"approved_at={quote.approved_at}|updated_at={quote.updated_at}|"
                f"followup_status={followup.status if followup else '-'}|"
                f"payment_method_status={followup.payment_method_status if followup else '-'}|"
                f"execution_status={execution.get('status') or '-'}|executed_at={execution.get('executed_at') or '-'}|"
                f"subscription_id={subscription_id_raw or '-'}|student_id={student_id or '-'}|billing_id={billing_id or '-'}"
            )

        subscriptions = []
        if relevant_subscription_ids:
            subscriptions.extend(
                db.execute(
                    select(ClientPlanSubscription, Plan)
                    .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                    .where(ClientPlanSubscription.id.in_(relevant_subscription_ids))
                    .order_by(ClientPlanSubscription.created_at.desc())
                ).all()
            )
        if relevant_user_ids:
            existing_subscription_ids = {subscription.id for subscription, _ in subscriptions}
            subscriptions.extend(
                row for row in db.execute(
                    select(ClientPlanSubscription, Plan)
                    .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                    .where(
                        or_(
                            ClientPlanSubscription.user_id.in_(relevant_user_ids),
                            ClientPlanSubscription.payer_contact_id.in_(relevant_user_ids),
                        )
                    )
                    .order_by(ClientPlanSubscription.created_at.desc())
                    .limit(20)
                ).all()
                if row[0].id not in existing_subscription_ids
            )

        _print(f"subscriptions={len(subscriptions)}")
        for subscription, plan in subscriptions:
            relevant_subscription_ids.add(subscription.id)
            relevant_user_ids.add(subscription.user_id)
            if subscription.payer_contact_id:
                relevant_user_ids.add(subscription.payer_contact_id)
            student = db.get(User, subscription.user_id)
            payer = db.get(User, subscription.payer_contact_id) if subscription.payer_contact_id else None
            _print(
                "subscription="
                f"{subscription.id}|plan={plan.name}|plan_kind={getattr(plan.kind, 'value', plan.kind)}|"
                f"student={_user_label(student)}|payer={_user_label(payer)}|"
                f"status={getattr(subscription.status, 'value', subscription.status)}|billing_method={subscription.billing_method_code or '-'}|"
                f"started_at={subscription.started_at}|ends_at={subscription.ends_at}|"
                f"next_payment_at={subscription.next_payment_at}|current_period_start={subscription.current_period_start}|"
                f"current_period_end={subscription.current_period_end}|auto_renew={subscription.auto_renew}"
            )

        if relevant_user_ids:
            rules = db.scalars(
                select(ClientAutoInvoiceRule)
                .where(ClientAutoInvoiceRule.user_id.in_(relevant_user_ids))
                .order_by(ClientAutoInvoiceRule.updated_at.desc(), ClientAutoInvoiceRule.created_at.desc())
            ).all()
        else:
            rules = []
        _print(f"auto_invoice_rules={len(rules)}")
        for rule in rules:
            period_start, period_end = _period_for_rule(rule)
            due_date = _due_date_for_rule(rule)
            _print(
                "auto_invoice_rule="
                f"{rule.id}|client_id={rule.user_id}|legal_entity_id={rule.legal_entity_id}|status={rule.status}|"
                f"cycle_start_date={rule.cycle_start_date}|frequency={rule.frequency}|billing_timing={rule.billing_timing}|"
                f"next_run_date={rule.next_run_date}|preview_period={period_start}->{period_end}|"
                f"due_rule={rule.due_date_rule_type}|due_offset={rule.due_date_days_offset}|preview_due_date={due_date}|"
                f"include_pending={rule.include_pending_lines}|include_cancelled={rule.include_cancelled_lines}|"
                f"last_generated_at={rule.last_generated_at}"
            )

            occurrences = db.scalars(
                select(ClientAutoInvoiceOccurrence)
                .where(ClientAutoInvoiceOccurrence.rule_id == rule.id)
                .order_by(ClientAutoInvoiceOccurrence.generated_at.desc())
                .limit(10)
            ).all()
            _print(f"auto_invoice_occurrences_for_rule_{rule.id}={len(occurrences)}")
            for occurrence in occurrences:
                _print(
                    "auto_invoice_occurrence="
                    f"{occurrence.id}|cycle_key={occurrence.cycle_key}|period={occurrence.period_start_date}->{occurrence.period_end_date}|"
                    f"status={occurrence.status}|note_id={occurrence.note_id or '-'}|generated_at={occurrence.generated_at}"
                )

        if relevant_user_ids:
            notes = db.scalars(
                select(ClientNoteEntry)
                .where(ClientNoteEntry.user_id.in_(relevant_user_ids))
                .order_by(ClientNoteEntry.created_at.desc())
                .limit(80)
            ).all()
        else:
            notes = []
        invoice_matches = []
        for note in notes:
            metadata = _parse_invoice_range_note_entry(note)
            if not metadata:
                continue
            if (
                str(metadata.get("issued_date") or "").startswith("2026-09")
                or str(metadata.get("start_date") or "").startswith("2026-09")
                or str(metadata.get("auto_cycle_start_date") or "").startswith("2026-09")
                or str(metadata.get("generation_mode") or "").upper() == "AUTO"
            ):
                invoice_matches.append((note, metadata))
        _print(f"invoice_note_matches={len(invoice_matches)}")
        for note, metadata in invoice_matches[:20]:
            _print(
                "invoice_note="
                f"{note.id}|client_id={note.user_id}|created_at={note.created_at}|invoice_number={metadata.get('invoice_number') or '-'}|"
                f"generation_mode={metadata.get('generation_mode') or '-'}|issued_date={metadata.get('issued_date') or '-'}|"
                f"due_date={metadata.get('due_date') or '-'}|no_due_date={metadata.get('no_due_date')}|"
                f"period={metadata.get('start_date') or '-'}->{metadata.get('end_date') or '-'}|"
                f"auto_cycle_start_date={metadata.get('auto_cycle_start_date') or '-'}|"
                f"total={metadata.get('total_incl_vat') or '-'} {metadata.get('currency') or ''}"
            )


if __name__ == "__main__":
    main()
