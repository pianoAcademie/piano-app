from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Location
from app.models.product_catalog import CatalogProduct, ProductCategory, ProductLocationStock
from app.services.product_catalog import reset_inventory_stock


SCRIPT_PREFIX = "PROD_RICHELIEU_PARTITION_INVENTORY_20260827"
INVENTORY_DATE = date(2026, 8, 27)
TARGET_QUANTITIES = {
    1: 28,
    2: 30,
    3: 40,
    4: 100,
    5: 110,
    6: 75,
    7: 100,
    8: 4,
    9: 87,
    10: 12,
}
EXPECTED_TITLES = {
    1: "partition degre 1",
    2: "partition degre 2 mon 1er piano",
    3: "partition degre 3",
    4: "partition degre 4 bami",
    5: "partition degre 5",
    6: "partition degre 6",
    7: "partition degre 7",
    8: "partition degre 8",
    9: "partition degre 9",
    10: "partition degre 10",
}


def _normalize(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def _degree_from_title(title: str) -> int | None:
    token = _normalize(title)
    for pattern in (
        r"\bdegre\s*(\d{1,2})\b",
        r"\bniveau\s*(\d{1,2})\b",
        r"\bdegree\s*(\d{1,2})\b",
    ):
        match = re.search(pattern, token)
        if match:
            return int(match.group(1))
    return None


def _is_partition_candidate(product: CatalogProduct, category: ProductCategory | None) -> bool:
    degree = _degree_from_title(product.title)
    return (
        product.active
        and not product.is_virtual
        and degree in EXPECTED_TITLES
        and _normalize(product.title) == EXPECTED_TITLES[degree]
    )


@dataclass(frozen=True)
class ResolvedTarget:
    degree: int
    quantity: int
    product: CatalogProduct
    category: ProductCategory | None
    stock: ProductLocationStock | None


def _resolve_location(db) -> Location:
    rows = db.scalars(
        select(Location).where(Location.active.is_(True), Location.is_online.is_(False)).order_by(Location.name.asc())
    ).all()
    matches = [
        row
        for row in rows
        if "richelieu" in _normalize(" ".join(filter(None, (row.name, row.code, row.address_line))))
    ]
    if len(matches) != 1:
        available = ", ".join(f"{row.name} [{row.code}]" for row in rows)
        raise SystemExit(
            f"[{SCRIPT_PREFIX}] location_resolution_failed matches={len(matches)} available={available}"
        )
    return matches[0]


def _resolve_targets(db, *, location: Location, lock: bool) -> list[ResolvedTarget]:
    statement = (
        select(CatalogProduct, ProductCategory)
        .outerjoin(ProductCategory, ProductCategory.id == CatalogProduct.category_id)
        .order_by(CatalogProduct.title.asc())
    )
    if lock:
        statement = statement.with_for_update(of=CatalogProduct)
    rows = db.execute(statement).all()
    candidates = [(product, category) for product, category in rows if _is_partition_candidate(product, category)]

    print(f"[{SCRIPT_PREFIX}] candidate_count={len(candidates)}")
    for product, category in candidates:
        print(
            f"[{SCRIPT_PREFIX}] candidate product_id={product.id}|title={product.title}|"
            f"category={(category.name if category else '-') }|degree={_degree_from_title(product.title)}"
        )

    by_degree: dict[int, list[tuple[CatalogProduct, ProductCategory | None]]] = {
        degree: [] for degree in TARGET_QUANTITIES
    }
    for product, category in candidates:
        degree = _degree_from_title(product.title)
        if degree in by_degree:
            by_degree[degree].append((product, category))

    failures = {degree: products for degree, products in by_degree.items() if len(products) != 1}
    if failures:
        details = "; ".join(
            f"degree={degree}:count={len(products)}:titles={[product.title for product, _ in products]}"
            for degree, products in failures.items()
        )
        raise SystemExit(f"[{SCRIPT_PREFIX}] product_resolution_failed {details}")

    product_ids = [products[0][0].id for products in by_degree.values()]
    stock_statement = select(ProductLocationStock).where(
        ProductLocationStock.location_id == location.id,
        ProductLocationStock.product_id.in_(product_ids),
    )
    if lock:
        stock_statement = stock_statement.with_for_update()
    stocks = {row.product_id: row for row in db.scalars(stock_statement).all()}

    return [
        ResolvedTarget(
            degree=degree,
            quantity=TARGET_QUANTITIES[degree],
            product=by_degree[degree][0][0],
            category=by_degree[degree][0][1],
            stock=stocks.get(by_degree[degree][0][0].id),
        )
        for degree in sorted(TARGET_QUANTITIES)
    ]


def _stock_values(stock: ProductLocationStock | None) -> str:
    if stock is None:
        return "missing"
    return (
        f"inventory={int(stock.inventory_quantity or 0)},"
        f"real={int(stock.real_quantity or 0)},"
        f"estimated={int(stock.estimated_quantity or 0)},"
        f"date={stock.inventory_date or '-'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Set the physical partition inventory at Rue de Richelieu.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded update. Default is dry-run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        location = _resolve_location(db)
        targets = _resolve_targets(db, location=location, lock=args.apply)
        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}")
        print(f"[{SCRIPT_PREFIX}] location_id={location.id}|name={location.name}|code={location.code}")

        for target in targets:
            print(
                f"[{SCRIPT_PREFIX}] plan degree={target.degree}|product_id={target.product.id}|"
                f"title={target.product.title}|before={_stock_values(target.stock)}|target={target.quantity}"
            )

        if not args.apply:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")
            return

        for target in targets:
            reset_inventory_stock(
                db,
                product_id=target.product.id,
                location_id=location.id,
                inventory_quantity=target.quantity,
                inventory_date=INVENTORY_DATE,
            )
        db.flush()

        verified = _resolve_targets(db, location=location, lock=False)
        for target in verified:
            stock = target.stock
            if stock is None:
                raise SystemExit(f"[{SCRIPT_PREFIX}] verification_missing_stock degree={target.degree}")
            actual = (
                int(stock.inventory_quantity or 0),
                int(stock.real_quantity or 0),
                int(stock.estimated_quantity or 0),
                stock.inventory_date,
            )
            expected = (target.quantity, target.quantity, target.quantity, INVENTORY_DATE)
            if actual != expected:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] verification_failed degree={target.degree}|actual={actual}|expected={expected}"
                )

        db.commit()
        print(f"[{SCRIPT_PREFIX}] committed=true")

        postcheck_targets = _resolve_targets(db, location=location, lock=False)
        for target in postcheck_targets:
            print(
                f"[{SCRIPT_PREFIX}] postcheck degree={target.degree}|product_id={target.product.id}|"
                f"title={target.product.title}|{_stock_values(target.stock)}"
            )


if __name__ == "__main__":
    main()
