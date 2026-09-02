from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.product_catalog import CatalogProduct


SCRIPT_PREFIX = "PROD_PARTITION_SUMMARIES_20260902"


@dataclass(frozen=True)
class ProductSummaryUpdate:
    product_id: UUID
    expected_title: str
    expected_previous_description: str | None
    description: str


UPDATES = (
    ProductSummaryUpdate(
        product_id=UUID("b2134816-4b89-499e-8372-712e77716202"),
        expected_title="Partition degré 4 - BAMI",
        expected_previous_description="Partition avec son cahier de travail",
        description="""Partition avec son cahier de travail.

Sommaire :
- Yankee Doodle
- Au clair de la lune
- Row, Row, Row Your Boat
- Lavender’s Blue
- We Wish You a Merry Christmas
- Joyeux anniversaire""",
    ),
    ProductSummaryUpdate(
        product_id=UUID("30b78789-a805-4873-8eee-e1f8ebe5e5de"),
        expected_title="Partition degré 5",
        expected_previous_description="Partition avec son cahier de travail",
        description="""Partition avec son cahier de travail.

Sommaire :
- Le Lac des cygnes — P. I. Tchaïkovski
- Symphonie n° 9, Hymne à la joie — L. van Beethoven
- Le Carnaval des animaux – Le Lion — C. Saint-Saëns
- Alouette, gentille alouette — chanson française
- Skip to My Lou — chanson américaine
- Head, Shoulders, Knees and Feet — chanson anglaise""",
    ),
    ProductSummaryUpdate(
        product_id=UUID("c3e888ce-4909-448d-8135-e57f9dfac99e"),
        expected_title="Partition degré 9",
        expected_previous_description=None,
        description="""Sommaire :
- Shallow
- Pirates des Caraïbes
- Château dans le ciel
- Passacaglia
- River Flows in You
- Greensleeves""",
    ),
    ProductSummaryUpdate(
        product_id=UUID("b4cfca76-aa71-4f0d-a3b5-78ff83758379"),
        expected_title="Partitions Ados",
        expected_previous_description="Avec son cahier de travail",
        description="""Avec son cahier de travail.

Sommaire :
- I Will Survive — Gloria Gaynor
- What’s Up? — 4 Non Blondes
- Another Love — Tom Odell
- Don’t Stop Me Now — Queen
- Someone You Loved — Lewis Capaldi
- The Winner Takes It All — ABBA""",
    ),
)


def run(*, apply: bool) -> None:
    with SessionLocal() as db:
        rows = db.scalars(
            select(CatalogProduct)
            .where(CatalogProduct.id.in_([update.product_id for update in UPDATES]))
            .with_for_update()
        ).all()
        products_by_id = {row.id: row for row in rows}

        for update in UPDATES:
            product = products_by_id.get(update.product_id)
            if product is None:
                raise SystemExit(f"[{SCRIPT_PREFIX}] missing_product id={update.product_id}")
            if product.title != update.expected_title:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] unexpected_title id={product.id} "
                    f"expected={update.expected_title!r} actual={product.title!r}"
                )
            if product.long_description not in (update.expected_previous_description, update.description):
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] unexpected_existing_description id={product.id} "
                    f"title={product.title!r} actual={product.long_description!r}"
                )

            changed = product.long_description != update.description
            print(
                f"[{SCRIPT_PREFIX}] product_id={product.id}|title={product.title}|"
                f"changed={str(changed).lower()}|mode={'apply' if apply else 'dry-run'}"
            )
            if apply and changed:
                product.long_description = update.description
                product.updated_at = datetime.now(timezone.utc)
                db.add(product)

        if apply:
            db.commit()
            print(f"[{SCRIPT_PREFIX}] committed={len(UPDATES)}")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] dry_run_complete={len(UPDATES)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the production partition table-of-contents descriptions.")
    parser.add_argument("--apply", action="store_true", help="Commit the updates. Without this flag, run read-only.")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
