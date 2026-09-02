from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from app.db.session import SessionLocal


SCRIPT_PREFIX = "PROD_PARTITION_PIECES_20260902"

TARGET_PIECES: dict[int, tuple[str, ...]] = {
    1: (
        "Old MacDonald had a Farm",
        "Ainsi font, font, font",
        "Petit Escargot",
        "Tourne, tourne, petit moulin",
        "Les petits poissons",
        "Meunier, tu dors",
    ),
    2: (
        "Marche de Radetzky — J. Strauss",
        "Marche — P. I. Tchaïkovski",
        "Le Messie — G. F. Haendel",
        "Musette — J. S. Bach",
        "Symphonie n° 9 — A. Dvořák",
        "Lac des cygnes — P. I. Tchaïkovski",
    ),
    8: (
        "Dans l’antre du roi de la montagne — E. Grieg",
        "Danse hongroise — J. Brahms",
        "Marche de Radetzky — J. Strauss",
        "Prélude — J. S. Bach",
        "Étude op. 25 n° 1 — F. Chopin",
        "Marche turque — W. A. Mozart",
    ),
    10: (
        "7 Years — L. Graham",
        "Mariage d’amour — P. de Senneville",
        "Expérience — L. Einaudi",
        "Comptine d’un autre été — Y. Tiersen",
        "Symphonie n° 25 — W. A. Mozart",
        "El Zapateado — D. Alexander",
    ),
}

EXPECTED_PRODUCT_TITLES = {
    1: "partition degre 1",
    2: "partition degre 2 mon 1er piano",
    8: "partition degre 8",
    10: "partition degre 10",
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
    pieces: tuple[str, ...]


def _ensure_repertoire_table(db) -> None:
    table_name = db.execute(text("SELECT to_regclass('public.sheet_music_pieces')")).scalar_one()
    if table_name is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] sheet_music_pieces_table_missing")


def _resolve_targets(db) -> list[ProductTarget]:
    rows = db.execute(
        text(
            """
            SELECT id, title
            FROM catalog_products
            WHERE active IS TRUE
            ORDER BY title ASC
            """
        )
    ).mappings().all()

    resolved: list[ProductTarget] = []
    for degree, expected_title in EXPECTED_PRODUCT_TITLES.items():
        matches = [row for row in rows if _normalize(row["title"]) == expected_title]
        if len(matches) != 1:
            possible = [row["title"] for row in rows if f"degre {degree}" in _normalize(row["title"])]
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] product_resolution_failed degree={degree}|"
                f"matches={len(matches)}|possible={possible}"
            )
        match = matches[0]
        resolved.append(
            ProductTarget(
                degree=degree,
                product_id=match["id"],
                product_title=match["title"],
                pieces=TARGET_PIECES[degree],
            )
        )
    return sorted(resolved, key=lambda item: item.degree)


def _current_pieces(db, product_id: UUID, *, lock: bool = False):
    suffix = " FOR UPDATE" if lock else ""
    return db.execute(
        text(
            """
            SELECT id, title, position, video_url, active
            FROM sheet_music_pieces
            WHERE product_id = :product_id
            ORDER BY position ASC
            """
            + suffix
        ),
        {"product_id": product_id},
    ).mappings().all()


def _print_plan(db, targets: list[ProductTarget]) -> None:
    for target in targets:
        current = _current_pieces(db, target.product_id)
        print(
            f"[{SCRIPT_PREFIX}] partition degree={target.degree}|product_id={target.product_id}|"
            f"title={target.product_title}|current_count={len(current)}|target_count={len(target.pieces)}"
        )
        current_by_position = {int(row["position"]): row for row in current}
        for position, title in enumerate(target.pieces, 1):
            previous = current_by_position.get(position)
            before = previous["title"] if previous else "<missing>"
            action = "unchanged" if previous and previous["title"] == title and previous["active"] else "update"
            print(
                f"[{SCRIPT_PREFIX}] piece degree={target.degree}|position={position}|"
                f"action={action}|before={before}|after={title}"
            )
        for row in current:
            if int(row["position"]) > len(target.pieces) and row["active"]:
                print(
                    f"[{SCRIPT_PREFIX}] piece degree={target.degree}|position={row['position']}|"
                    f"action=deactivate|before={row['title']}"
                )


def _apply_target(db, target: ProductTarget) -> None:
    current = _current_pieces(db, target.product_id, lock=True)
    by_position = {int(row["position"]): row for row in current}

    for position, title in enumerate(target.pieces, 1):
        existing = by_position.get(position)
        if existing is None:
            db.execute(
                text(
                    """
                    INSERT INTO sheet_music_pieces (product_id, title, position, active)
                    VALUES (:product_id, :title, :position, TRUE)
                    """
                ),
                {"product_id": target.product_id, "title": title, "position": position},
            )
            continue

        title_changed = existing["title"] != title
        db.execute(
            text(
                """
                UPDATE sheet_music_pieces
                SET title = :title,
                    active = TRUE,
                    video_url = CASE WHEN :title_changed THEN NULL ELSE video_url END,
                    updated_at = now()
                WHERE id = :piece_id
                """
            ),
            {"piece_id": existing["id"], "title": title, "title_changed": title_changed},
        )

    db.execute(
        text(
            """
            UPDATE sheet_music_pieces
            SET active = FALSE, updated_at = now()
            WHERE product_id = :product_id
              AND position > :last_position
              AND active IS TRUE
            """
        ),
        {"product_id": target.product_id, "last_position": len(target.pieces)},
    )


def _verify(db, targets: list[ProductTarget]) -> None:
    for target in targets:
        active = [row for row in _current_pieces(db, target.product_id) if row["active"]]
        actual = [(int(row["position"]), row["title"]) for row in active]
        expected = list(enumerate(target.pieces, 1))
        if actual != expected:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] verification_failed degree={target.degree}|"
                f"actual={actual}|expected={expected}"
            )
        print(f"[{SCRIPT_PREFIX}] verified degree={target.degree}|active_pieces={len(active)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace the piece lists for four production partitions.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded update. Default is dry-run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        _ensure_repertoire_table(db)
        targets = _resolve_targets(db)
        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}|partitions={len(targets)}")
        _print_plan(db, targets)

        if not args.apply:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")
            return

        for target in targets:
            _apply_target(db, target)
        _verify(db, targets)
        db.commit()
        print(f"[{SCRIPT_PREFIX}] committed=true")

        _verify(db, _resolve_targets(db))
        print(f"[{SCRIPT_PREFIX}] postcheck=true")


if __name__ == "__main__":
    main()
