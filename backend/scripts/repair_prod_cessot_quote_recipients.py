from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.quotes import _freeze_quote_document_snapshot
from app.db.session import SessionLocal
from app.models.family import ClientFamilyLink
from app.models.quote import Quote, QuoteDocumentSnapshot, QuoteEvent, QuoteLine
from app.models.user import ClientKind, User
from app.services.quotes.quote_documents import render_quote_parts_html

SCRIPT_PREFIX = "PROD_REPAIR_CESSOT_QUOTE_RECIPIENTS"
TARGET_QUOTE_NUMBERS = (
    "DV-20260720092911-D6BE",
    "DV-20260720093211-951D",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _name(user: User) -> str:
    return " ".join(part for part in [user.first_name or "", user.last_name or ""] if part).strip()


def _current_address(user: User) -> str:
    return " ".join(
        part.strip()
        for part in [user.address_line or "", user.postal_code or "", user.city or ""]
        if str(part or "").strip()
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        parents = db.scalars(
            select(User).where(
                func.lower(User.first_name) == "charles",
                func.lower(User.last_name) == "cessot",
                User.client_kind == ClientKind.ADULT,
            )
        ).all()
        if len(parents) != 1:
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=charles_match_count|count={len(parents)}")
        parent = parents[0]
        parent_name = _name(parent)
        parent_address = _current_address(parent)
        if parent_name != "Charles Cessot" or not parent_address:
            raise SystemExit(
                f"{SCRIPT_PREFIX}|abort|reason=invalid_parent_profile|name={parent_name}|has_address={bool(parent_address)}"
            )

        quotes = db.scalars(
            select(Quote)
            .where(Quote.quote_number.in_(TARGET_QUOTE_NUMBERS))
            .order_by(Quote.quote_number.asc())
            .with_for_update()
        ).all()
        if len(quotes) != len(TARGET_QUOTE_NUMBERS):
            found = ",".join(sorted(quote.quote_number for quote in quotes))
            raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=quote_match_count|found={found}")

        prepared: list[tuple[Quote, list[QuoteLine], str, str]] = []
        for quote in quotes:
            child = db.get(User, quote.client_id) if quote.client_id else None
            if (
                child is None
                or child.client_kind != ClientKind.CHILD
                or str(child.last_name or "").strip().casefold() != "cessot"
            ):
                raise SystemExit(
                    f"{SCRIPT_PREFIX}|abort|reason=invalid_quote_child|quote={quote.quote_number}|client={quote.client_id}"
                )
            billing_link = db.scalar(
                select(ClientFamilyLink).where(
                    ClientFamilyLink.child_user_id == child.id,
                    ClientFamilyLink.adult_user_id == parent.id,
                    ClientFamilyLink.is_billing_recipient.is_(True),
                )
            )
            if billing_link is None:
                raise SystemExit(
                    f"{SCRIPT_PREFIX}|abort|reason=charles_not_billing_recipient|quote={quote.quote_number}"
                )

            lines = db.scalars(
                select(QuoteLine).where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.sort_order.asc())
            ).all()
            _body_html, _terms_html, combined_html = render_quote_parts_html(
                db=db,
                quote=quote,
                lines=lines,
                audience="client_pdf",
            )
            if parent_name not in combined_html or parent_address not in combined_html:
                raise SystemExit(
                    f"{SCRIPT_PREFIX}|abort|reason=rendered_identity_missing|quote={quote.quote_number}"
                )
            next_hash = hashlib.sha256(combined_html.encode("utf-8")).hexdigest()
            current_snapshot = db.get(QuoteDocumentSnapshot, quote.document_snapshot_id) if quote.document_snapshot_id else None
            current_hash = current_snapshot.document_hash if current_snapshot is not None else "-"
            prepared.append((quote, lines, current_hash, next_hash))
            print(
                f"{SCRIPT_PREFIX}|ready|quote={quote.quote_number}|child={_name(child)}|parent={parent_name}|"
                f"address={parent_address}|old_hash={current_hash}|new_hash={next_hash}|changed={current_hash != next_hash}"
            )

        if not args.apply:
            db.rollback()
            print(f"{SCRIPT_PREFIX}|summary|quotes={len(prepared)}|applied=False")
            return 0

        for quote, lines, old_hash, _next_hash in prepared:
            state = "frozen" if str(quote.document_status or "").strip().lower() == "frozen" else "generated"
            snapshot = _freeze_quote_document_snapshot(
                db,
                quote=quote,
                lines=lines,
                state=state,
                audience="client_pdf",
            )
            db.add(
                QuoteEvent(
                    quote_id=quote.id,
                    event_type="quote_document_regenerated",
                    actor_type="system",
                    payload={
                        "reason": "cessot_billing_parent_identity_refresh",
                        "previous_document_hash": old_hash,
                        "snapshot_id": str(snapshot.id),
                        "document_hash": snapshot.document_hash,
                    },
                    created_at=_utcnow(),
                )
            )
            print(
                f"{SCRIPT_PREFIX}|applied|quote={quote.quote_number}|state={state}|"
                f"snapshot={snapshot.id}|hash={snapshot.document_hash}"
            )

        db.commit()

        for quote, _lines, _old_hash, _next_hash in prepared:
            db.refresh(quote)
            snapshot = db.get(QuoteDocumentSnapshot, quote.document_snapshot_id)
            html = snapshot.combined_html_snapshot if snapshot is not None else ""
            if parent_name not in html or parent_address not in html:
                raise SystemExit(f"{SCRIPT_PREFIX}|abort|reason=post_commit_verification|quote={quote.quote_number}")

        print(f"{SCRIPT_PREFIX}|summary|quotes={len(prepared)}|applied=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
