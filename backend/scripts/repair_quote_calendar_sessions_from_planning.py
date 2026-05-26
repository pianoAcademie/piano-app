from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quote import Quote, QuoteLine
from app.services.quotes.quote_documents import (
    _calendar_snapshot_with_line_recommendation_keys,
    _calendar_snapshot_with_planning_sessions,
)

SCRIPT_PREFIX = "QUOTE_CALENDAR_SESSIONS_PLANNING_REPAIR"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-number", help="Limit repair to one quote number.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    inspected = 0
    changed = 0
    with SessionLocal() as db:
        query = select(Quote).where(Quote.calendar_snapshot.isnot(None)).order_by(Quote.created_at.desc())
        if args.quote_number:
            query = query.where(Quote.quote_number == args.quote_number)
        quotes = db.scalars(query).all()
        for quote in quotes:
            inspected += 1
            before = quote.calendar_snapshot or {}
            before_count = len(before.get("sessions") or []) if isinstance(before, dict) else 0
            lines = db.scalars(
                select(QuoteLine)
                .where(QuoteLine.quote_id == quote.id)
                .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
            ).all()
            after = _calendar_snapshot_with_line_recommendation_keys(
                db,
                before if isinstance(before, dict) else {},
                lines=lines,
            )
            after = _calendar_snapshot_with_planning_sessions(db, after)
            after_count = len(after.get("sessions") or []) if isinstance(after, dict) else 0
            if after_count <= before_count:
                print(f"{SCRIPT_PREFIX}|ok|quote={quote.quote_number}|sessions={before_count}")
                continue
            changed += 1
            print(f"{SCRIPT_PREFIX}|repair|quote={quote.quote_number}|sessions={before_count}->{after_count}")
            if args.apply:
                quote.calendar_snapshot = after
                quote.document_status = "stale"
                quote.document_snapshot_id = None
                db.add(quote)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    print(f"{SCRIPT_PREFIX}|summary|inspected={inspected}|changed={changed}|applied={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
