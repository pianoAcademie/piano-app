from __future__ import annotations

import argparse
import os
import sys
from calendar import monthrange
from datetime import date, datetime, time, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client_record import ClientAutoInvoiceRule, ClientInvoiceLine, ClientManualTransaction
from app.models.quote import Quote, QuoteAcceptanceFollowup
from app.models.user import User

SCRIPT_PREFIX = "PROD_REPAIR_MONTHLY_CARD_QUOTE_BILLING"
EXECUTION_KEY = "quote_to_enrollment_execution"
START_DATE = date(2026, 9, 1)
DUE_DAYS_OFFSET = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: object | None) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _parse_uuid(value: object | None) -> UUID | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _object_mentions_monthly_card_payment(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().upper() == "CARD_MONTHLY"
    if isinstance(value, dict):
        return any(_object_mentions_monthly_card_payment(item) for item in value.values())
    if isinstance(value, list):
        return any(_object_mentions_monthly_card_payment(item) for item in value)
    return False


def _followup_execution(followup: QuoteAcceptanceFollowup) -> dict[str, object]:
    return _json_object(_json_object(followup.payload).get(EXECUTION_KEY))


def _set_followup_execution(followup: QuoteAcceptanceFollowup, execution: dict[str, object]) -> None:
    payload = _json_object(followup.payload)
    payload[EXECUTION_KEY] = execution
    followup.payload = payload
    followup.updated_at = _utcnow()


def _uses_monthly_card_payment(quote: Quote, followup: QuoteAcceptanceFollowup) -> bool:
    payload = _json_object(followup.payload)
    terms = _json_object(quote.payment_terms_snapshot)
    for source in (payload, terms):
        for key in ("payment_method_code", "paymentMethodCode", "payment_method", "paymentMethod"):
            if str(source.get(key) or "").strip().upper() == "CARD_MONTHLY":
                return True
    return _object_mentions_monthly_card_payment(payload) or _object_mentions_monthly_card_payment(terms)


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _next_run_date(today: date) -> date:
    next_date = START_DATE
    while next_date < today:
        next_date = _add_months(next_date, 1)
    return next_date


def _issued_at_for_start_date() -> datetime:
    return datetime.combine(START_DATE, time.min, tzinfo=timezone.utc)


def _is_deposit_transaction(transaction: ClientManualTransaction) -> bool:
    reference = str(transaction.reference or "").upper()
    label = str(transaction.label or "").casefold()
    return ":DEPOSIT" in reference or "acompte" in label


def _transaction_is_invoiced(db, transaction: ClientManualTransaction) -> bool:
    return db.scalar(
        select(ClientInvoiceLine.id)
        .where(
            ClientInvoiceLine.source == "MANUAL",
            ClientInvoiceLine.source_payment_id == transaction.id,
        )
        .limit(1)
    ) is not None


def _upsert_auto_invoice_rule(db, *, billing: User, quote: Quote, actor_user_id: UUID | None, apply: bool) -> UUID | None:
    if quote.legal_entity_id is None:
        _print(f"skip_rule_no_legal_entity quote={quote.quote_number}")
        return None

    now = _utcnow()
    rule = db.scalar(
        select(ClientAutoInvoiceRule)
        .where(
            ClientAutoInvoiceRule.user_id == billing.id,
            ClientAutoInvoiceRule.legal_entity_id == quote.legal_entity_id,
            ClientAutoInvoiceRule.status.in_(["ACTIVE", "PAUSED"]),
        )
        .order_by(ClientAutoInvoiceRule.updated_at.desc(), ClientAutoInvoiceRule.created_at.desc())
        .with_for_update()
        .limit(1)
    )
    created = rule is None
    desired_next_run_date = _next_run_date(now.date())
    if rule is None:
        rule = ClientAutoInvoiceRule(
            user_id=billing.id,
            legal_entity_id=quote.legal_entity_id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        needs_update = True
    else:
        needs_update = any(
            [
                rule.cycle_start_date != START_DATE,
                rule.frequency != "MONTHLY",
                rule.billing_timing != "UPCOMING_LESSONS",
                rule.due_date_rule_type != "X_DAYS_AFTER_ISSUE",
                rule.due_date_days_offset != DUE_DAYS_OFFSET,
                not bool(rule.include_pending_lines),
                bool(rule.include_cancelled_lines),
                rule.next_run_date != desired_next_run_date,
                rule.status != "ACTIVE",
            ]
        )

    if needs_update:
        rule.cycle_start_date = START_DATE
        rule.frequency = "MONTHLY"
        rule.billing_timing = "UPCOMING_LESSONS"
        rule.due_date_rule_type = "X_DAYS_AFTER_ISSUE"
        rule.due_date_days_offset = DUE_DAYS_OFFSET
        rule.include_pending_lines = True
        rule.include_cancelled_lines = False
        rule.next_run_date = desired_next_run_date
        rule.status = "ACTIVE"
        rule.updated_by_user_id = actor_user_id
        rule.updated_at = now

    if apply and (created or needs_update):
        db.add(rule)
        db.flush()

    _print(
        "auto_rule_"
        f"{'create' if created else 'update'} quote={quote.quote_number}|billing={billing.id}|"
        f"legal_entity={quote.legal_entity_id}|cycle_start={START_DATE.isoformat()}|"
        f"next_run={desired_next_run_date.isoformat()}|due_offset={DUE_DAYS_OFFSET}|"
        f"needs_update={needs_update}"
    )

    archived_rules = db.scalars(
        select(ClientAutoInvoiceRule)
        .where(
            ClientAutoInvoiceRule.user_id == billing.id,
            ClientAutoInvoiceRule.legal_entity_id == quote.legal_entity_id,
            ClientAutoInvoiceRule.id != rule.id,
            ClientAutoInvoiceRule.status.in_(["ACTIVE", "PAUSED"]),
        )
        .with_for_update()
    ).all()
    for archived_rule in archived_rules:
        _print(f"archive_duplicate_rule={archived_rule.id}|billing={billing.id}|legal_entity={quote.legal_entity_id}")
        if apply:
            archived_rule.status = "ARCHIVED"
            archived_rule.updated_by_user_id = actor_user_id
            archived_rule.updated_at = now
            db.add(archived_rule)

    return rule.id if rule.id is not None else quote.id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the repair. Without it, only prints a dry-run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        actor_id = db.scalar(select(User.id).where(User.email == "admin@piano-academie.com").limit(1))
        rows = db.execute(
            select(QuoteAcceptanceFollowup, Quote)
            .join(Quote, Quote.id == QuoteAcceptanceFollowup.quote_id)
            .where(QuoteAcceptanceFollowup.status == "completed")
            .order_by(QuoteAcceptanceFollowup.updated_at.asc())
        ).all()

        inspected = 0
        candidates = 0
        transactions_updated = 0
        transactions_skipped_deposit = 0
        transactions_skipped_invoiced = 0
        transactions_already_on_start_date = 0
        transactions_missing = 0
        rules_touched = 0

        for followup, quote in rows:
            inspected += 1
            execution = _followup_execution(followup)
            if str(execution.get("status") or "").strip().lower() != "executed":
                continue
            if not _uses_monthly_card_payment(quote, followup):
                continue

            billing_id = _parse_uuid(execution.get("billing_client_id"))
            billing = db.scalar(select(User).where(User.id == billing_id).with_for_update().limit(1)) if billing_id else None
            if billing is None:
                _print(f"skip_missing_billing quote={quote.quote_number}|billing_id={billing_id or '-'}")
                continue

            candidates += 1
            _print(f"candidate quote={quote.quote_number}|followup={followup.id}|billing={billing.id}|client={billing.email}")

            touched_transaction_ids: list[str] = []
            for raw_id in _json_list(execution.get("created_transaction_ids")):
                transaction_id = _parse_uuid(raw_id)
                if transaction_id is None:
                    continue
                transaction = db.scalar(
                    select(ClientManualTransaction)
                    .where(ClientManualTransaction.id == transaction_id)
                    .with_for_update()
                    .limit(1)
                )
                if transaction is None:
                    transactions_missing += 1
                    _print(f"missing_transaction quote={quote.quote_number}|transaction={transaction_id}")
                    continue
                if _is_deposit_transaction(transaction):
                    transactions_skipped_deposit += 1
                    _print(f"skip_deposit_transaction quote={quote.quote_number}|transaction={transaction.id}|label={transaction.label}")
                    continue
                if _transaction_is_invoiced(db, transaction):
                    transactions_skipped_invoiced += 1
                    _print(f"skip_already_invoiced quote={quote.quote_number}|transaction={transaction.id}|label={transaction.label}")
                    continue
                if transaction.occurred_at.date() == START_DATE:
                    transactions_already_on_start_date += 1
                    _print(
                        f"ok_transaction_date quote={quote.quote_number}|transaction={transaction.id}|"
                        f"label={transaction.label}|date={START_DATE.isoformat()}"
                    )
                    touched_transaction_ids.append(str(transaction.id))
                    continue

                _print(
                    "update_transaction_date "
                    f"quote={quote.quote_number}|transaction={transaction.id}|label={transaction.label}|"
                    f"type={transaction.transaction_type}|old={transaction.occurred_at.isoformat()}|new={START_DATE.isoformat()}"
                )
                transactions_updated += 1
                touched_transaction_ids.append(str(transaction.id))
                if args.apply:
                    transaction.occurred_at = _issued_at_for_start_date()
                    transaction.updated_at = _utcnow()
                    db.add(transaction)

            rule_id = _upsert_auto_invoice_rule(db, billing=billing, quote=quote, actor_user_id=actor_id, apply=args.apply)
            if rule_id is not None:
                rules_touched += 1

            if args.apply:
                execution["monthly_card_existing_quote_repair"] = {
                    "repaired_at": _utcnow().isoformat(),
                    "fixed_fee_date": START_DATE.isoformat(),
                    "auto_invoice_rule_id": str(rule_id) if rule_id is not None else None,
                    "updated_transaction_ids": touched_transaction_ids,
                    "deposit_policy": "untouched",
                    "invoiced_transaction_policy": "untouched",
                }
                _set_followup_execution(followup, execution)
                db.add(followup)

        if args.apply:
            db.commit()
        else:
            db.rollback()

        summary = (
            f"apply={args.apply}|inspected={inspected}|candidates={candidates}|"
            f"transactions_updated={transactions_updated}|transactions_already_on_start_date={transactions_already_on_start_date}|"
            f"transactions_skipped_deposit={transactions_skipped_deposit}|"
            f"transactions_skipped_invoiced={transactions_skipped_invoiced}|transactions_missing={transactions_missing}|"
            f"rules_touched={rules_touched}|start_date={START_DATE.isoformat()}|due_date=2026-09-02"
        )
        _print(f"summary {summary}")
        print(f"::notice title=Monthly card billing repair::{summary}")


if __name__ == "__main__":
    main()
