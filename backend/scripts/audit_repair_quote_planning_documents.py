from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quote import Quote, QuoteDocumentSnapshot, QuoteEvent, QuoteLine
from app.services.quotes.quote_documents import (
    AUDIENCE_CLIENT_PDF,
    _calendar_snapshot_with_line_recommendation_keys,
    _calendar_snapshot_with_planning_sessions,
    render_quote_parts_html,
)

SCRIPT_PREFIX = "QUOTE_PLANNING_DOCUMENT_AUDIT"
DEFAULT_STATUSES = ("sent", "approved")


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, default=str, ensure_ascii=False) == json.dumps(
        right,
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )


def _block_limit(block: dict[str, Any]) -> int:
    try:
        return int(str(block.get("planning_session_limit") or "").strip())
    except (TypeError, ValueError):
        return 0


def _limited_blocks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in _json_list(snapshot.get("blocks"))
        if isinstance(item, dict) and _block_limit(item) > 0 and str(item.get("activity_id") or "").strip()
    ]


def _session_matches_block(session: dict[str, Any], block: dict[str, Any]) -> bool:
    if str(session.get("activity_id") or "").strip() != str(block.get("activity_id") or "").strip():
        return False
    block_location_id = str(block.get("location_id") or "").strip()
    if block_location_id and str(session.get("location_id") or "").strip() != block_location_id:
        return False
    block_start_time = str(block.get("start_time") or "").strip()
    if block_start_time and str(session.get("start_time") or "").strip() != block_start_time:
        return False
    block_series_key = str(block.get("series_key") or "").strip()
    if block_series_key and str(session.get("series_key") or "").strip() != block_series_key:
        return False
    block_recommendation_key = str(block.get("recommendation_key") or "").strip()
    if block_recommendation_key and str(session.get("recommendation_key") or "").strip() != block_recommendation_key:
        return False
    return True


def _block_signature(block: dict[str, Any]) -> str:
    parts = [
        str(block.get("activity_id") or ""),
        str(block.get("recommendation_key") or ""),
        str(block.get("series_key") or ""),
        str(block.get("start_time") or ""),
        str(block.get("location_id") or ""),
    ]
    return "|".join(parts)


def _block_label(block: dict[str, Any]) -> str:
    chunks = [
        str(block.get("activity_label") or block.get("title") or "Activite").strip(),
        str(block.get("weekday_label") or "").strip(),
        str(block.get("start_time") or "").strip(),
        str(block.get("location_label") or "").strip(),
    ]
    return " / ".join(item for item in chunks if item) or _block_signature(block)


def _block_summary(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sessions = [dict(item) for item in _json_list(snapshot.get("sessions")) if isinstance(item, dict)]
    summary: dict[str, dict[str, Any]] = {}
    for block in _limited_blocks(snapshot):
        matched = [item for item in sessions if _session_matches_block(item, block)]
        dates = sorted(str(item.get("date") or "").strip() for item in matched if str(item.get("date") or "").strip())
        summary[_block_signature(block)] = {
            "label": _block_label(block),
            "limit": _block_limit(block),
            "count": len(matched),
            "start": dates[0] if dates else "",
            "end": dates[-1] if dates else str(block.get("end_date") or ""),
        }
    return summary


def _changed_blocks(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_summary = _block_summary(before)
    after_summary = _block_summary(after)
    out: list[str] = []
    for signature, after_item in after_summary.items():
        before_item = before_summary.get(signature)
        if before_item is None:
            out.append(
                f"{after_item['label']} new={after_item['count']}/{after_item['limit']} end={after_item['end']}"
            )
            continue
        if before_item["count"] != after_item["count"] or before_item["end"] != after_item["end"]:
            out.append(
                f"{after_item['label']} {before_item['count']}->{after_item['count']}"
                f"/{after_item['limit']} end {before_item['end'] or '-'}->{after_item['end'] or '-'}"
            )
    return out


def _quote_lines(db, quote: Quote) -> list[QuoteLine]:
    return db.scalars(
        select(QuoteLine)
        .where(QuoteLine.quote_id == quote.id)
        .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
    ).all()


def _document_snapshot(db, quote: Quote) -> QuoteDocumentSnapshot | None:
    if not quote.document_snapshot_id:
        return None
    return db.scalar(select(QuoteDocumentSnapshot).where(QuoteDocumentSnapshot.id == quote.document_snapshot_id))


def _render_current_hash(db, quote: Quote, lines: list[QuoteLine]) -> tuple[str, str, str, str]:
    body_html, terms_html, combined_html = render_quote_parts_html(
        db=db,
        quote=quote,
        lines=lines,
        audience=AUDIENCE_CLIENT_PDF,
    )
    return body_html, terms_html, combined_html, hashlib.sha256(combined_html.encode("utf-8")).hexdigest()


def _freeze_document_snapshot(
    db,
    *,
    quote: Quote,
    body_html: str,
    terms_html: str,
    combined_html: str,
    document_hash: str,
    state: str,
) -> QuoteDocumentSnapshot:
    snapshot = db.scalar(
        select(QuoteDocumentSnapshot)
        .where(
            QuoteDocumentSnapshot.quote_id == quote.id,
            QuoteDocumentSnapshot.snapshot_kind == "combined",
            QuoteDocumentSnapshot.document_hash == document_hash,
        )
        .order_by(QuoteDocumentSnapshot.created_at.desc())
        .limit(1)
    )
    now = datetime.now(timezone.utc)
    if snapshot is None:
        snapshot = QuoteDocumentSnapshot(
            quote_id=quote.id,
            snapshot_kind="combined",
            language=quote.language,
            currency=quote.currency,
            vat_rate=quote.vat_rate,
            quote_template_id=quote.quote_template_id,
            quote_template_version_id=quote.quote_template_version_id,
            terms_template_id=quote.terms_template_id,
            terms_template_version_id=quote.terms_template_version_id,
            quote_body_snapshot=body_html,
            terms_body_snapshot=terms_html,
            combined_html_snapshot=combined_html,
            document_hash=document_hash,
            created_at=now,
        )
        db.add(snapshot)
        db.flush()

    quote.document_snapshot_id = snapshot.id
    quote.document_hash = snapshot.document_hash
    quote.document_generated_at = now
    quote.document_status = state
    quote.updated_at = now
    db.add(quote)
    return snapshot


def _repair_state(quote: Quote) -> str:
    document_status = str(quote.document_status or "").strip().lower()
    if document_status == "generated":
        return "generated"
    return "frozen"


def _quote_label(quote: Quote) -> str:
    meta = _json_object(getattr(quote, "meta", None))
    for key in ("student_full_name", "recipient_name", "customer_name", "prospect_name"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return "-"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--quote-number", help="Limit audit to one quote number.")
    parser.add_argument(
        "--statuses",
        default=",".join(DEFAULT_STATUSES),
        help="Comma-separated quote statuses to inspect. Defaults to sent,approved.",
    )
    args = parser.parse_args()

    statuses = {item.strip().lower() for item in str(args.statuses or "").split(",") if item.strip()}
    inspected = 0
    candidates = 0
    impacted = 0
    snapshot_repairs = 0
    document_repairs = 0

    with SessionLocal() as db:
        query = select(Quote).where(Quote.calendar_snapshot.isnot(None)).order_by(Quote.created_at.desc())
        if statuses:
            query = query.where(Quote.status.in_(sorted(statuses)))
        if args.quote_number:
            query = query.where(Quote.quote_number == args.quote_number)

        for quote in db.scalars(query).all():
            inspected += 1
            before = _json_object(quote.calendar_snapshot)
            if not _limited_blocks(before):
                continue
            candidates += 1
            lines = _quote_lines(db, quote)
            after = _calendar_snapshot_with_line_recommendation_keys(db, before, lines=lines)
            after = _calendar_snapshot_with_planning_sessions(db, after)

            snapshot_changed = not _json_equal(before, after)
            if snapshot_changed:
                quote.calendar_snapshot = after
                db.add(quote)

            body_html, terms_html, combined_html, current_hash = _render_current_hash(db, quote, lines)
            existing_snapshot = _document_snapshot(db, quote)
            existing_hash = str(getattr(existing_snapshot, "document_hash", "") or str(quote.document_hash or "")).strip()
            document_changed = current_hash != existing_hash
            if not snapshot_changed and not document_changed:
                continue

            impacted += 1
            details = "; ".join(_changed_blocks(before, after)) or "document snapshot changed"
            print(
                f"{SCRIPT_PREFIX}|impact|quote={quote.quote_number}|status={quote.status}|"
                f"student={_quote_label(quote)}|snapshot_changed={snapshot_changed}|"
                f"document_changed={document_changed}|details={details}"
            )

            if args.apply:
                if snapshot_changed:
                    snapshot_repairs += 1
                if document_changed:
                    _freeze_document_snapshot(
                        db,
                        quote=quote,
                        body_html=body_html,
                        terms_html=terms_html,
                        combined_html=combined_html,
                        document_hash=current_hash,
                        state=_repair_state(quote),
                    )
                    document_repairs += 1
                db.add(
                    QuoteEvent(
                        quote_id=quote.id,
                        event_type="quote_planning_document_repaired",
                        actor_type="system",
                        payload={
                            "script": "audit_repair_quote_planning_documents",
                            "snapshot_changed": snapshot_changed,
                            "document_changed": document_changed,
                            "details": details,
                        },
                    )
                )
                db.flush()
            else:
                if snapshot_changed:
                    db.refresh(quote)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    print(
        f"{SCRIPT_PREFIX}|summary|inspected={inspected}|candidates={candidates}|"
        f"impacted={impacted}|snapshot_repairs={snapshot_repairs}|"
        f"document_repairs={document_repairs}|applied={args.apply}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
