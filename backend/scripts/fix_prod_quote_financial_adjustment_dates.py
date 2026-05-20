from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.admin_clients import _invoice_issued_at_for_date
from app.db.session import SessionLocal
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction
from app.models.quote import Quote

SCRIPT_PREFIX = "PROD_QUOTE_ADJUSTMENT_DATE_FIX"
ADJUSTMENT_REFERENCE_RE = re.compile(
    r"^QUOTE:(?P<quote_id>[0-9a-fA-F-]{36}):ROW:quote-financial-adjustment$"
)


def _quote_adjustment_effective_date(quote: Quote) -> date | None:
    meta = quote.meta if isinstance(quote.meta, dict) else {}
    adjustment = meta.get("financial_adjustment")
    if not isinstance(adjustment, dict):
        return None
    raw = str(adjustment.get("effective_date") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix production quote financial adjustment transaction dates.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    scanned = 0
    candidates = 0
    changed_transactions = 0
    changed_invoice_lines = 0
    samples: list[str] = []

    with SessionLocal() as db:
        rows = db.scalars(
            select(ClientManualTransaction)
            .where(ClientManualTransaction.reference.like("QUOTE:%:ROW:quote-financial-adjustment"))
            .order_by(ClientManualTransaction.created_at.asc(), ClientManualTransaction.id.asc())
        ).all()
        scanned = len(rows)

        for transaction in rows:
            match = ADJUSTMENT_REFERENCE_RE.match(str(transaction.reference or "").strip())
            if match is None:
                continue
            quote_id = UUID(match.group("quote_id"))
            quote = db.scalar(select(Quote).where(Quote.id == quote_id))
            if quote is None:
                continue
            effective_date = _quote_adjustment_effective_date(quote)
            if effective_date is None:
                continue
            candidates += 1
            target_occurred_at = _invoice_issued_at_for_date(issued_date=effective_date, now=now)
            current_date = transaction.occurred_at.astimezone(timezone.utc).date()
            target_date = target_occurred_at.astimezone(timezone.utc).date()
            samples.append(
                f"quote={quote.quote_number}|transaction={transaction.id}|current={current_date.isoformat()}|target={target_date.isoformat()}|label={transaction.label}"
            )
            if current_date != target_date:
                changed_transactions += 1
                if args.apply:
                    transaction.occurred_at = target_occurred_at
                    transaction.updated_at = now
                    db.add(transaction)

            invoice_lines = db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.source == "MANUAL",
                    ClientInvoiceLine.source_payment_id == transaction.id,
                )
            ).all()
            for line in invoice_lines:
                line_date = line.occurred_at.astimezone(timezone.utc).date()
                if line_date == target_date:
                    continue
                changed_invoice_lines += 1
                if args.apply:
                    line.occurred_at = target_occurred_at
                    db.add(line)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] scanned_transactions={scanned}")
    print(f"[{SCRIPT_PREFIX}] candidate_adjustments={candidates}")
    print(f"[{SCRIPT_PREFIX}] changed_transactions={changed_transactions}")
    print(f"[{SCRIPT_PREFIX}] changed_invoice_lines={changed_invoice_lines}")
    for sample in samples[:30]:
        print(f"[{SCRIPT_PREFIX}] sample={sample}")


if __name__ == "__main__":
    main()
