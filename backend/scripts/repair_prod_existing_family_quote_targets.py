from __future__ import annotations

import argparse
import os
import sys
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.quote import Quote, QuoteAcceptanceFollowup
from app.models.user import ClientKind, User

SCRIPT_PREFIX = "PROD_EXISTING_FAMILY_QUOTE_TARGET_REPAIR"


def _uuid(value: object | None) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    changed = 0
    inspected = 0
    with SessionLocal() as db:
        quotes = db.scalars(select(Quote).where(Quote.context_type == "active_client")).all()
        for quote in quotes:
            meta = quote.meta or {}
            typeform = meta.get("typeform_intake") if isinstance(meta.get("typeform_intake"), dict) else {}
            resolution = typeform.get("resolution") if isinstance(typeform.get("resolution"), dict) else {}
            client_resolution = resolution.get("client_resolution") if isinstance(resolution.get("client_resolution"), dict) else {}
            if str(client_resolution.get("mode") or "").strip() != "existing_family":
                continue

            inspected += 1
            child_id = _uuid(client_resolution.get("selected_family_child_client_id"))
            adult_id = _uuid(client_resolution.get("selected_family_adult_client_id"))
            billing_id = _uuid(client_resolution.get("selected_family_billing_client_id")) or adult_id
            if child_id is None:
                print(f"{SCRIPT_PREFIX}|skip|quote={quote.quote_number}|reason=missing_child_id")
                continue

            child = db.get(User, child_id)
            if child is None or child.client_kind != ClientKind.CHILD:
                print(f"{SCRIPT_PREFIX}|skip|quote={quote.quote_number}|reason=invalid_child|child_id={child_id}")
                continue

            billing = db.get(User, billing_id) if billing_id is not None else None
            if quote.client_id == child.id:
                print(f"{SCRIPT_PREFIX}|ok|quote={quote.quote_number}|child={child.first_name} {child.last_name}")
                continue

            print(
                f"{SCRIPT_PREFIX}|repair|quote={quote.quote_number}|from={quote.client_id}|to={child.id}|child={child.first_name} {child.last_name}"
            )
            changed += 1
            if args.apply:
                next_meta = dict(meta)
                next_meta["typeform_selected_family_adult_client_id"] = str(adult_id) if adult_id else None
                next_meta["typeform_selected_family_child_client_id"] = str(child.id)
                next_meta["typeform_selected_family_billing_client_id"] = str(billing_id) if billing_id else None
                if billing is not None and billing.email:
                    next_meta["recipient_email"] = billing.email.strip().lower()
                quote.client_id = child.id
                quote.meta = next_meta
                quote.document_status = "stale"
                db.add(quote)

                followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id))
                if followup is not None:
                    followup.target_client_id = child.id
                    db.add(followup)

        if args.apply:
            db.commit()
        else:
            db.rollback()

    print(f"{SCRIPT_PREFIX}|summary|inspected={inspected}|changed={changed}|applied={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
