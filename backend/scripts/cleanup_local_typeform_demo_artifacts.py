from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.db.session import SessionLocal


DEMO_FORM_IDS = (
    "tf_bld_adult_2025",
    "tf_bld_child_2025",
    "tf_bld_eveil_2025",
    "tf_paris_adult_2025_pompe",
    "tf_paris_child_2025_richelieu",
    "tf_paris_eveil_2025_pompe",
    "tf_paris_teen_2025_richelieu",
)

DEMO_SOURCE_CODES = (
    "TYPEFORM_BLD_ADULT_2025",
    "TYPEFORM_BLD_CHILD_2025",
    "TYPEFORM_BLD_EVEIL_2025",
    "TYPEFORM_PARIS_ADULT_2025_POMPE",
    "TYPEFORM_PARIS_CHILD_2025_RICHELIEU",
    "TYPEFORM_PARIS_EVEIL_2025_POMPE",
    "TYPEFORM_PARIS_TEEN_2025_RICHELIEU",
)

DEMO_ACTIVITY_PREFIX = "TF_DEMO_"


@dataclass
class CleanupSummary:
    demo_intakes: int
    demo_quotes: int
    demo_form_configs: int
    demo_sessions: int
    demo_pricing_rows: int
    demo_activity_types: int


COUNT_SQL = text(
    """
    WITH demo_activities AS (
        SELECT id
        FROM course_types
        WHERE code LIKE :demo_prefix
    ),
    demo_quotes AS (
        SELECT DISTINCT q.id
        FROM quotes q
        LEFT JOIN typeform_intakes i ON i.related_quote_id = q.id
        LEFT JOIN quote_lines ql ON ql.quote_id = q.id
        WHERE i.source_form_id = ANY(:demo_form_ids)
           OR ql.activity_id IN (SELECT id FROM demo_activities)
    )
    SELECT
        (SELECT count(*) FROM typeform_intakes WHERE source_form_id = ANY(:demo_form_ids)) AS demo_intakes,
        (SELECT count(*) FROM demo_quotes) AS demo_quotes,
        (SELECT count(*) FROM typeform_form_configs WHERE typeform_form_id = ANY(:demo_form_ids) OR source_code = ANY(:demo_source_codes)) AS demo_form_configs,
        (SELECT count(*) FROM course_sessions WHERE course_type_id IN (SELECT id FROM demo_activities)) AS demo_sessions,
        (SELECT count(*) FROM pricing_activity_prices WHERE activity_id IN (SELECT id FROM demo_activities)) AS demo_pricing_rows,
        (SELECT count(*) FROM course_types WHERE code LIKE :demo_prefix) AS demo_activity_types
    """
)


DELETE_INTAKES_SQL = text(
    """
    DELETE FROM typeform_intakes
    WHERE source_form_id = ANY(:demo_form_ids)
    """
)

DELETE_QUOTES_SQL = text(
    """
    DELETE FROM quotes
    WHERE id IN (
        SELECT DISTINCT q.id
        FROM quotes q
        JOIN quote_lines ql ON ql.quote_id = q.id
        JOIN course_types ct ON ct.id = ql.activity_id
        WHERE ct.code LIKE :demo_prefix
    )
    """
)

DELETE_FORM_CONFIGS_SQL = text(
    """
    DELETE FROM typeform_form_configs
    WHERE typeform_form_id = ANY(:demo_form_ids)
       OR source_code = ANY(:demo_source_codes)
    """
)

DELETE_SESSIONS_SQL = text(
    """
    DELETE FROM course_sessions
    WHERE course_type_id IN (
        SELECT id
        FROM course_types
        WHERE code LIKE :demo_prefix
    )
    """
)

DELETE_PRICING_SQL = text(
    """
    DELETE FROM pricing_activity_prices
    WHERE activity_id IN (
        SELECT id
        FROM course_types
        WHERE code LIKE :demo_prefix
    )
    """
)

DELETE_COURSE_TYPES_SQL = text(
    """
    DELETE FROM course_types
    WHERE code LIKE :demo_prefix
    """
)


def fetch_summary(session) -> CleanupSummary:
    row = session.execute(
        COUNT_SQL,
        {
            "demo_form_ids": list(DEMO_FORM_IDS),
            "demo_source_codes": list(DEMO_SOURCE_CODES),
            "demo_prefix": f"{DEMO_ACTIVITY_PREFIX}%",
        },
    ).mappings().one()
    return CleanupSummary(**row)


def print_summary(title: str, summary: CleanupSummary) -> None:
    print(title)
    print(f"  demo intakes           : {summary.demo_intakes}")
    print(f"  demo quotes            : {summary.demo_quotes}")
    print(f"  demo form configs      : {summary.demo_form_configs}")
    print(f"  demo sessions          : {summary.demo_sessions}")
    print(f"  demo pricing rows      : {summary.demo_pricing_rows}")
    print(f"  demo activity types    : {summary.demo_activity_types}")


def run_cleanup(apply: bool) -> None:
    session = SessionLocal()
    try:
        before = fetch_summary(session)
        print_summary("Before cleanup:", before)
        if not apply:
            print("\nDry-run only. Re-run with --apply to delete demo Typeform artifacts.")
            return

        session.rollback()
        with session.begin():
            session.execute(DELETE_INTAKES_SQL, {"demo_form_ids": list(DEMO_FORM_IDS)})
            session.execute(DELETE_QUOTES_SQL, {"demo_prefix": f"{DEMO_ACTIVITY_PREFIX}%"})
            session.execute(
                DELETE_FORM_CONFIGS_SQL,
                {
                    "demo_form_ids": list(DEMO_FORM_IDS),
                    "demo_source_codes": list(DEMO_SOURCE_CODES),
                },
            )
            session.execute(DELETE_SESSIONS_SQL, {"demo_prefix": f"{DEMO_ACTIVITY_PREFIX}%"})
            session.execute(DELETE_PRICING_SQL, {"demo_prefix": f"{DEMO_ACTIVITY_PREFIX}%"})
            session.execute(DELETE_COURSE_TYPES_SQL, {"demo_prefix": f"{DEMO_ACTIVITY_PREFIX}%"})

        after = fetch_summary(session)
        print_summary("\nAfter cleanup:", after)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove local Typeform demo activities/configs/intakes.")
    parser.add_argument("--apply", action="store_true", help="Actually delete the demo artifacts.")
    args = parser.parse_args()
    run_cleanup(apply=args.apply)


if __name__ == "__main__":
    main()
