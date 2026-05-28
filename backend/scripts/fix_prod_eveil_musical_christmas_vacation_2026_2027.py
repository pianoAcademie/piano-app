from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text

from app.db.session import SessionLocal

SCRIPT_PREFIX = "PROD_REPAIR_NORAH_ONLINE_PIANO_ACTIVE_QUOTE"
QUOTE_NUMBER = "DV-20260528085256-71AF"
LINE_TITLE = "Cours de piano collectif en ligne - enfants (1h)"
TARGET_QUANTITY = Decimal("33.00")


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the active quote line quantity repair.")
    args = parser.parse_args()

    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                select
                    q.id as quote_id,
                    q.quote_number,
                    q.status,
                    q.total_ttc as quote_total_ttc,
                    l.id as line_id,
                    l.quantity as old_quantity,
                    l.amount_ttc as old_amount_ttc,
                    l.unit_price_ht,
                    l.unit_vat_amount,
                    l.unit_price_ttc
                from quotes q
                join quote_lines l on l.quote_id = q.id
                where q.quote_number = :quote_number
                  and l.title = :line_title
                limit 1
                """
            ),
            {"quote_number": QUOTE_NUMBER, "line_title": LINE_TITLE},
        ).mappings().first()
        if row is None:
            raise RuntimeError(f"Quote line not found: {QUOTE_NUMBER} / {LINE_TITLE}")

        target_amount_ht = Decimal(row["unit_price_ht"] or 0) * TARGET_QUANTITY
        target_amount_vat = Decimal(row["unit_vat_amount"] or 0) * TARGET_QUANTITY
        target_amount_ttc = Decimal(row["unit_price_ttc"] or 0) * TARGET_QUANTITY
        _print(
            "line_update "
            f"quote={row['quote_number']}|status={row['status']}|line={row['line_id']}|"
            f"old_quantity={row['old_quantity']}|new_quantity={TARGET_QUANTITY}|"
            f"old_amount_ttc={row['old_amount_ttc']}|new_amount_ttc={target_amount_ttc}|apply={args.apply}"
        )

        quote_total_ttc = None
        if args.apply:
            db.execute(
                text(
                    """
                    update quote_lines
                    set quantity = :quantity,
                        amount_ht = round((unit_price_ht * :quantity)::numeric, 2),
                        amount_vat = round((unit_vat_amount * :quantity)::numeric, 2),
                        amount_ttc = round((unit_price_ttc * :quantity)::numeric, 2),
                        updated_at = now()
                    where id = :line_id
                    """
                ),
                {
                    "quantity": TARGET_QUANTITY,
                    "line_id": row["line_id"],
                },
            )
            quote_total_ttc = db.execute(
                text(
                    """
                    update quotes q
                    set total_ttc = totals.total_ttc,
                        price_snapshot = jsonb_build_object(
                            'catalog_id', case when q.pricing_catalog_id is null then null else q.pricing_catalog_id::text end,
                            'currency', q.currency,
                            'lines_total_ttc', totals.total_ttc::text,
                            'total_ttc', totals.total_ttc::text
                        ),
                        document_status = 'stale',
                        document_hash = null,
                        document_generated_at = null,
                        document_snapshot_id = null,
                        updated_at = now()
                    from (
                        select quote_id, round(sum(amount_ttc)::numeric, 2) as total_ttc
                        from quote_lines
                        where quote_id = :quote_id
                        group by quote_id
                    ) totals
                    where q.id = totals.quote_id
                    returning q.total_ttc
                    """
                ),
                {"quote_id": row["quote_id"]},
            ).scalar_one()
            db.commit()
        else:
            db.rollback()

        summary = (
            f"apply={args.apply}|quote={row['quote_number']}|status={row['status']}|line={row['line_id']}|"
            f"old_quantity={row['old_quantity']}|target_quantity={TARGET_QUANTITY}|"
            f"old_amount_ttc={row['old_amount_ttc']}|target_amount_ttc={target_amount_ttc}|"
            f"quote_total_ttc={quote_total_ttc if quote_total_ttc is not None else '-'}"
        )
        _print(f"summary {summary}")
        print(f"::notice title=Norah active quote online piano repair::{summary}")


if __name__ == "__main__":
    main()
