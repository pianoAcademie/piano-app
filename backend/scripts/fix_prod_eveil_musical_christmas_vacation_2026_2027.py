from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.quote import Quote, QuoteLine

SCRIPT_PREFIX = "PROD_REPAIR_NORAH_ONLINE_PIANO_ACTIVE_QUOTE"
QUOTE_NUMBER = "DV-20260528085256-71AF"
LINE_TITLE = "Cours de piano collectif en ligne - enfants (1h)"
TARGET_QUANTITY = Decimal("33.00")


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _q2(value: Decimal) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the active quote line quantity repair.")
    args = parser.parse_args()

    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).with_for_update().limit(1))
        if quote is None:
            raise RuntimeError(f"Quote not found: {QUOTE_NUMBER}")

        line = db.scalar(
            select(QuoteLine)
            .where(QuoteLine.quote_id == quote.id, QuoteLine.title == LINE_TITLE)
            .with_for_update()
            .limit(1)
        )
        if line is None:
            raise RuntimeError(f"Quote line not found: {QUOTE_NUMBER} / {LINE_TITLE}")

        old_quantity = Decimal(line.quantity or 0)
        old_amount_ttc = Decimal(line.amount_ttc or 0)
        new_amount_ht = _q2(Decimal(line.unit_price_ht or 0) * TARGET_QUANTITY)
        new_amount_vat = _q2(Decimal(line.unit_vat_amount or 0) * TARGET_QUANTITY)
        new_amount_ttc = _q2(Decimal(line.unit_price_ttc or 0) * TARGET_QUANTITY)

        _print(
            "line_update "
            f"quote={quote.quote_number}|status={quote.status}|line={line.id}|"
            f"old_quantity={old_quantity}|new_quantity={TARGET_QUANTITY}|"
            f"old_amount_ttc={old_amount_ttc}|new_amount_ttc={new_amount_ttc}|apply={args.apply}"
        )

        if args.apply:
            line.quantity = TARGET_QUANTITY
            line.amount_ht = new_amount_ht
            line.amount_vat = new_amount_vat
            line.amount_ttc = new_amount_ttc
            meta = dict(line.meta or {})
            meta["planning_session_limit"] = int(TARGET_QUANTITY)
            meta["norah_online_piano_quantity_repair"] = {
                "repaired_at": _utcnow().isoformat(),
                "old_quantity": str(old_quantity),
                "new_quantity": str(TARGET_QUANTITY),
                "reason": "Live planning series contains 33 scheduled sessions through 2027-06-15.",
            }
            line.meta = meta
            line.updated_at = _utcnow()
            db.add(line)
            db.flush()

            lines_total = db.scalar(
                select(func.coalesce(func.sum(QuoteLine.amount_ttc), Decimal("0"))).where(QuoteLine.quote_id == quote.id)
            )
            lines_total_ttc = _q2(Decimal(lines_total or 0))
            quote.total_ttc = lines_total_ttc
            quote.price_snapshot = {
                "catalog_id": str(quote.pricing_catalog_id) if quote.pricing_catalog_id else None,
                "currency": quote.currency,
                "lines_total_ttc": str(lines_total_ttc),
                "total_ttc": str(_q2(Decimal(quote.total_ttc or 0))),
            }
            quote.document_status = "stale"
            quote.document_hash = None
            quote.document_generated_at = None
            quote.document_snapshot_id = None
            quote.updated_at = _utcnow()
            db.add(quote)
            db.commit()
        else:
            db.rollback()

        summary = (
            f"apply={args.apply}|quote={quote.quote_number}|status={quote.status}|line={line.id}|"
            f"old_quantity={old_quantity}|target_quantity={TARGET_QUANTITY}|old_amount_ttc={old_amount_ttc}|"
            f"target_amount_ttc={new_amount_ttc}|quote_total_ttc={_q2(Decimal(quote.total_ttc or 0)) if args.apply else '-'}"
        )
        _print(f"summary {summary}")
        print(f"::notice title=Norah active quote online piano repair::{summary}")


if __name__ == "__main__":
    main()
