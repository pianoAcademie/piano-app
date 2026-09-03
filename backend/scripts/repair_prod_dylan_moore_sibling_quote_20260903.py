"""Repair the stale sibling-clone pricing/planning state for Dylan Adeline Moore.

Dry-run by default. Pass ``--apply`` only after deploying the sibling-clone and
live-series hardening that this repair relies on.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal

from sqlalchemy import select

from app.api.routes.quotes import (
    ANNUAL_REVIEW_KEY,
    _build_payment_terms_snapshot_for_quote,
    _calendar_snapshot_with_line_recommendation_keys,
    _calendar_snapshot_with_planning_sessions,
    _load_quote_lines,
    _q2,
    _quote_lines_total_ttc,
    _quote_total_with_adjustment,
    _sync_typeform_planned_quote_line_quantities,
    _utcnow,
)
from app.db.session import SessionLocal
from app.models.quote import Quote, QuoteEvent


QUOTE_NUMBER = "DV-20260903142130-E29B"
EXPECTED_CLIENT_ID = "3638f897-8035-4291-9e94-015d7e5f3f84"
EXPECTED_TUESDAY_ACTIVITY_ID = "4bdf5d1e-fe55-4f95-80d4-0cafd3ce7683"


def repair(*, apply: bool) -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).with_for_update())
        if quote is None:
            raise RuntimeError(f"Quote {QUOTE_NUMBER} not found")
        if str(quote.client_id) != EXPECTED_CLIENT_ID:
            raise RuntimeError(f"Unexpected quote client: {quote.client_id}")
        if str(quote.status or "").lower() != "created":
            raise RuntimeError(f"Refusing to repair non-draft quote in status {quote.status}")

        lines = _load_quote_lines(db, quote.id)
        before_total = _q2(Decimal(quote.total_ttc or 0))
        before_quantities = [(str(line.id), line.title, str(line.quantity)) for line in lines]

        quote_meta = deepcopy(quote.meta or {})
        quote_meta.pop(ANNUAL_REVIEW_KEY, None)
        quote.meta = quote_meta

        for line in lines:
            line_meta = deepcopy(line.meta or {})
            line_meta.pop("annual_decision", None)
            line_meta.pop("annual_course_key", None)
            if line_meta.pop("annual_auto_discount", None) is not None:
                line_meta.pop("target_course_key", None)
            line.meta = line_meta
            db.add(line)

        snapshot = _calendar_snapshot_with_line_recommendation_keys(
            db,
            deepcopy(quote.calendar_snapshot or {}),
            lines=lines,
        )
        snapshot = _calendar_snapshot_with_planning_sessions(db, snapshot)
        quote.calendar_snapshot = snapshot
        _sync_typeform_planned_quote_line_quantities(lines, calendar_snapshot=snapshot)
        db.flush()

        tuesday_lines = [
            line
            for line in lines
            if str(line.activity_id or "") == EXPECTED_TUESDAY_ACTIVITY_ID
            and str((line.meta or {}).get("recommendation_key") or "") == EXPECTED_TUESDAY_ACTIVITY_ID
        ]
        if len(tuesday_lines) != 1 or Decimal(tuesday_lines[0].quantity or 0) != Decimal("33"):
            raise RuntimeError(
                "Tuesday live planning did not resolve to exactly one 33-session billing line: "
                f"{[(str(line.id), str(line.quantity)) for line in tuesday_lines]}"
            )

        lines_total = _quote_lines_total_ttc(db, quote_id=quote.id)
        quote.total_ttc = _quote_total_with_adjustment(lines_total_ttc=lines_total, meta=quote.meta or {})
        quote.price_snapshot = {
            "catalog_id": str(quote.pricing_catalog_id) if quote.pricing_catalog_id else None,
            "currency": quote.currency,
            "lines_total_ttc": str(lines_total),
            "total_ttc": str(_q2(Decimal(quote.total_ttc or 0))),
        }
        quote.payment_terms_snapshot = _build_payment_terms_snapshot_for_quote(
            db,
            quote,
            total_ttc=_q2(Decimal(quote.total_ttc or 0)),
        )
        quote.document_status = "stale"
        quote.updated_at = _utcnow()
        db.add(quote)

        after_quantities = [(str(line.id), line.title, str(line.quantity)) for line in lines]
        after_total = _q2(Decimal(quote.total_ttc or 0))
        print({
            "quote": QUOTE_NUMBER,
            "mode": "apply" if apply else "dry-run",
            "before_total": str(before_total),
            "after_total": str(after_total),
            "before_quantities": before_quantities,
            "after_quantities": after_quantities,
            "snapshot_sessions": len(snapshot.get("sessions") or []),
        })

        if not apply:
            db.rollback()
            return

        db.add(
            QuoteEvent(
                quote_id=quote.id,
                event_type="quote_sibling_clone_repaired",
                actor_type="system",
                payload={
                    "quote_number": QUOTE_NUMBER,
                    "reason": "stale sibling pricing audit and live-series session cap",
                    "before_total": str(before_total),
                    "after_total": str(after_total),
                },
            )
        )
        db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    repair(apply=parser.parse_args().apply)
