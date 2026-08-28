from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.services.quote_planning_audit import audit_quote_planning, repair_safe_quote_planning_mismatches


SCHOOL_YEAR = "2026-2027"
EXPECTED_APPROVED_ITEMS = 19
EXPECTED_APPROVED_SERIES = 9


def _admin_actor(db):
    return db.scalar(
        select(User)
        .where(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
            func.lower(User.email) == "admin@piano-academie.com",
        )
        .limit(1)
    )


def _validate_preflight(audit: dict[str, object]) -> list[dict[str, object]]:
    items = [item for item in audit.get("items", []) if item.get("approved_for_automatic_repair")]
    series_ids = {item["series_id"] for item in items}
    if len(items) != EXPECTED_APPROVED_ITEMS:
        raise RuntimeError(
            f"Preflight refused: expected {EXPECTED_APPROVED_ITEMS} reviewed quote/student items, got {len(items)}"
        )
    if len(series_ids) != EXPECTED_APPROVED_SERIES:
        raise RuntimeError(
            f"Preflight refused: expected {EXPECTED_APPROVED_SERIES} reviewed series, got {len(series_ids)}"
        )
    without_complete_invoice = [
        item
        for item in items
        if int(item.get("invoiced_sessions") or 0) != int(item.get("booked_sessions") or 0)
    ]
    if without_complete_invoice:
        labels = ", ".join(str(item.get("quote_number")) for item in without_complete_invoice)
        raise RuntimeError(f"Preflight refused: incomplete invoice lines for {labels}")
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        audit = audit_quote_planning(db, school_year=SCHOOL_YEAR)
        approved_items = _validate_preflight(audit)
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry-run",
                    "school_year": SCHOOL_YEAR,
                    "checked_quotes": audit["checked_quotes"],
                    "all_issues": audit["issue_count"],
                    "approved_items": len(approved_items),
                    "approved_series": len({item["series_id"] for item in approved_items}),
                    "approved_students": [
                        {"quote": item["quote_number"], "student": item["student_name"]}
                        for item in approved_items
                    ],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        if not args.apply:
            return 0

        actor = _admin_actor(db)
        if actor is None:
            raise RuntimeError("Active production admin actor not found")
        result = repair_safe_quote_planning_mismatches(
            db,
            actor=actor,
            school_year=SCHOOL_YEAR,
        )
        if int(result["repaired_quotes"]) != EXPECTED_APPROVED_ITEMS:
            raise RuntimeError(f"Unexpected repaired quote count: {result['repaired_quotes']}")
        if int(result["remaining_approved_repairable"]) != 0:
            raise RuntimeError(
                f"Post-check failed: {result['remaining_approved_repairable']} reviewed item(s) still need repair"
            )
        print(json.dumps({"result": result}, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
