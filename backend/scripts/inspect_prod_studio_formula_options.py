from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quote import Quote
from app.services.quotes.quote_documents import _json_list, _json_object

PREFIX = "PROD_QUOTE_CALENDAR_INSPECT"
QUOTE_NUMBER = "DV-20260521044742-9E89"


def p(line: str) -> None:
    print(f"[{PREFIX}] {line}")


def parse_date(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def main() -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).limit(1))
        if quote is None:
            p(f"quote_not_found={QUOTE_NUMBER}")
            return
        snap = _json_object(quote.calendar_snapshot)
        p(f"quote={quote.quote_number}|status={quote.status}|client_id={quote.client_id}|document_status={quote.document_status}")
        p(f"sessions_count={snap.get('sessions_count')}|blocks={len(_json_list(snap.get('blocks')))}|sessions={len(_json_list(snap.get('sessions')))}")
        for idx, raw_block in enumerate(_json_list(snap.get('blocks')), start=1):
            block = _json_object(raw_block)
            title = str(block.get('title') or block.get('activity_name') or block.get('course_type_name') or '-').strip()
            location = str(block.get('location_label') or block.get('location_name') or block.get('location') or '-').strip()
            start = parse_date(block.get('start_date'))
            end = parse_date(block.get('end_date'))
            weekdays = block.get('weekdays') or block.get('weekday') or block.get('days')
            holidays = sorted(str(x)[:10] for x in _json_list(block.get('holiday_dates')) if str(x).strip())
            closures = sorted(str(x)[:10] for x in _json_list(block.get('closure_dates')) if str(x).strip())
            p(f"block#{idx}|title={title}|location={location}|start={start}|end={end}|weekdays={weekdays}|sessions_count={block.get('sessions_count')}")
            p(f"block#{idx}|holiday_dates={','.join(holidays) or '-'}")
            p(f"block#{idx}|closure_dates={','.join(closures) or '-'}")
            if start and end:
                all_tuesdays=[]; cur=start
                while cur <= end:
                    if cur.weekday()==1:
                        all_tuesdays.append(cur)
                    cur += timedelta(days=1)
                session_dates = sorted({parse_date(item.get('date')) for item in _json_list(snap.get('sessions')) if isinstance(item, dict) and parse_date(item.get('date'))})
                listed = {d for d in session_dates if start <= d <= end}
                missing = [d.isoformat() for d in all_tuesdays if d not in listed]
                p(f"block#{idx}|all_tuesdays={len(all_tuesdays)}|listed_in_snapshot={len([d for d in listed if d.weekday()==1])}|missing_tuesdays={','.join(missing) or '-'}")


if __name__ == "__main__":
    main()
