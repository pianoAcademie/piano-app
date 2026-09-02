from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal


SCRIPT_PREFIX = "PROD_PARTITION_STATUSES_20260902"
TARGET_TITLES = {
    1: "partition degre 1",
    2: "partition degre 2 mon 1er piano",
}


def _normalize(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


@dataclass(frozen=True)
class ProductTarget:
    degree: int
    product_id: UUID
    product_title: str


def _ensure_tables(db) -> None:
    for table in ("student_sheet_music", "student_sheet_music_events"):
        table_name = db.execute(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table}"}).scalar_one()
        if table_name is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] missing_table={table}")


def _resolve_targets(db) -> list[ProductTarget]:
    products = db.execute(
        text("SELECT id, title FROM catalog_products WHERE active IS TRUE ORDER BY title ASC")
    ).mappings().all()
    targets: list[ProductTarget] = []
    for degree, expected_title in TARGET_TITLES.items():
        matches = [row for row in products if _normalize(row["title"]) == expected_title]
        if len(matches) != 1:
            possible = [row["title"] for row in products if f"degre {degree}" in _normalize(row["title"])]
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] product_resolution_failed degree={degree}|"
                f"matches={len(matches)}|possible={possible}"
            )
        target = matches[0]
        targets.append(ProductTarget(degree=degree, product_id=target["id"], product_title=target["title"]))
    return targets


def _assignment_counts(db, target: ProductTarget) -> dict[str, int]:
    rows = db.execute(
        text(
            """
            SELECT status, count(*) AS count
            FROM student_sheet_music
            WHERE product_id = :product_id
            GROUP BY status
            ORDER BY status
            """
        ),
        {"product_id": target.product_id},
    ).mappings().all()
    return {str(row["status"]): int(row["count"]) for row in rows}


def _print_plan(db, targets: list[ProductTarget]) -> None:
    for target in targets:
        counts = _assignment_counts(db, target)
        change_count = sum(count for status, count in counts.items() if status not in {"TO_DELIVER", "COMPLETED"})
        print(
            f"[{SCRIPT_PREFIX}] degree={target.degree}|product_id={target.product_id}|"
            f"title={target.product_title}|statuses={counts}|to_change={change_count}|"
            f"completed_preserved={counts.get('COMPLETED', 0)}"
        )


def _apply_target(db, target: ProductTarget) -> int:
    assignments = db.execute(
        text(
            """
            SELECT id, status
            FROM student_sheet_music
            WHERE product_id = :product_id
              AND status NOT IN ('TO_DELIVER', 'COMPLETED')
            ORDER BY id
            FOR UPDATE
            """
        ),
        {"product_id": target.product_id},
    ).mappings().all()
    for assignment in assignments:
        db.execute(
            text(
                """
                INSERT INTO student_sheet_music_events
                    (assignment_id, event_type, old_status, new_status, note)
                VALUES
                    (:assignment_id, 'STATUS_INITIALIZED', :old_status, 'TO_DELIVER', :note)
                """
            ),
            {
                "assignment_id": assignment["id"],
                "old_status": assignment["status"],
                "note": "Initialisation des partitions degrés 1 et 2 à remettre",
            },
        )
    if assignments:
        db.execute(
            text(
                """
                UPDATE student_sheet_music
                SET status = 'TO_DELIVER', updated_at = now()
                WHERE product_id = :product_id
                  AND status NOT IN ('TO_DELIVER', 'COMPLETED')
                """
            ),
            {"product_id": target.product_id},
        )
    return len(assignments)


def _verify(db, targets: list[ProductTarget]) -> None:
    for target in targets:
        invalid_count = int(
            db.execute(
                text(
                    """
                    SELECT count(*)
                    FROM student_sheet_music
                    WHERE product_id = :product_id
                      AND status NOT IN ('TO_DELIVER', 'COMPLETED')
                    """
                ),
                {"product_id": target.product_id},
            ).scalar_one()
        )
        if invalid_count:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] verification_failed degree={target.degree}|remaining={invalid_count}"
            )
        print(f"[{SCRIPT_PREFIX}] verified degree={target.degree}|statuses={_assignment_counts(db, target)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize degree 1 and 2 sheet-music assignments as ready to deliver.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded update. Default is dry-run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        _ensure_tables(db)
        targets = _resolve_targets(db)
        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}|partitions={len(targets)}")
        _print_plan(db, targets)
        if not args.apply:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")
            return

        changed = sum(_apply_target(db, target) for target in targets)
        _verify(db, targets)
        db.commit()
        print(f"[{SCRIPT_PREFIX}] committed=true|changed={changed}")
        _verify(db, _resolve_targets(db))
        print(f"[{SCRIPT_PREFIX}] postcheck=true")


if __name__ == "__main__":
    main()
