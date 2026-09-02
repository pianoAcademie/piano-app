from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.product_catalog import CatalogProduct
from app.models.repertoire import SheetMusicPiece


SCRIPT_PREFIX = "PROD_ADOS_DERNIERE_DANSE_20260902"
PRODUCT_ID = UUID("b4cfca76-aa71-4f0d-a3b5-78ff83758379")
EXPECTED_TITLE = "Partitions Ados"
NEW_PIECE = "Dernière Danse"
OLD_PIECES = (
    "I Will Survive — Gloria Gaynor",
    "What’s Up? — 4 Non Blondes",
    "Another Love — Tom Odell",
    "Don’t Stop Me Now — Queen",
    "Someone You Loved — Lewis Capaldi",
    "The Winner Takes It All — ABBA",
)
NEW_PIECES = (*OLD_PIECES, NEW_PIECE)
OLD_DESCRIPTION = """Avec son cahier de travail.

Sommaire :
- I Will Survive — Gloria Gaynor
- What’s Up? — 4 Non Blondes
- Another Love — Tom Odell
- Don’t Stop Me Now — Queen
- Someone You Loved — Lewis Capaldi
- The Winner Takes It All — ABBA"""
NEW_DESCRIPTION = f"{OLD_DESCRIPTION}\n- {NEW_PIECE}"


def _active_titles(db) -> tuple[str, ...]:
    rows = db.scalars(
        select(SheetMusicPiece)
        .where(SheetMusicPiece.product_id == PRODUCT_ID, SheetMusicPiece.active.is_(True))
        .order_by(SheetMusicPiece.position)
    ).all()
    return tuple(row.title for row in rows)


def run(*, apply: bool) -> None:
    with SessionLocal() as db:
        product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == PRODUCT_ID).with_for_update())
        if product is None or product.title != EXPECTED_TITLE:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] unexpected_product id={PRODUCT_ID}|"
                f"title={getattr(product, 'title', None)!r}"
            )

        current_pieces = _active_titles(db)
        if current_pieces not in (OLD_PIECES, NEW_PIECES):
            raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected_piece_list pieces={current_pieces!r}")
        if product.long_description not in (OLD_DESCRIPTION, NEW_DESCRIPTION):
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] unexpected_description description={product.long_description!r}"
            )

        pieces_changed = current_pieces == OLD_PIECES
        description_changed = product.long_description == OLD_DESCRIPTION
        print(
            f"[{SCRIPT_PREFIX}] mode={'apply' if apply else 'dry-run'}|"
            f"pieces_changed={str(pieces_changed).lower()}|"
            f"description_changed={str(description_changed).lower()}"
        )

        if apply:
            if pieces_changed:
                db.add(
                    SheetMusicPiece(
                        product_id=PRODUCT_ID,
                        title=NEW_PIECE,
                        position=len(NEW_PIECES),
                        active=True,
                    )
                )
            if description_changed:
                product.long_description = NEW_DESCRIPTION
                product.updated_at = datetime.now(timezone.utc)
                db.add(product)
            db.commit()
            if _active_titles(db) != NEW_PIECES:
                raise SystemExit(f"[{SCRIPT_PREFIX}] postcheck_piece_list_failed")
            db.refresh(product)
            if product.long_description != NEW_DESCRIPTION:
                raise SystemExit(f"[{SCRIPT_PREFIX}] postcheck_description_failed")
            print(f"[{SCRIPT_PREFIX}] committed=true|active_pieces={len(NEW_PIECES)}")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")


def main() -> None:
    parser = argparse.ArgumentParser(description="Append Dernière Danse to the teen sheet-music repertoire.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded update. Default is dry-run.")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
