"""Record the authorized 500-unit order, without increasing available stock.

Dry-run by default. Expected products are resolved using IDs verified in the admin
catalog. Workbooks have no catalog record yet: retain their exact names and require
an explicit catalog link at receipt instead of inventing prices or mixing solfege.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.catalog import Location
from app.models.product_catalog import CatalogProduct, ProductLocationStock
from app.models.user import User, UserRole
from app.schemas.supply_order import SupplyOrderCreate, SupplyOrderItemIn
from app.services.supply_orders import create_supply_order, order_lines

ORDER_ID = UUID("c13c9007-14cd-479d-a24c-6f85dd0b9212")
PARTITIONS = {
    UUID("da2ff4c2-fa6b-4832-8f89-9ce8cbf32364"): ("Partition degré 2 - Mon 1er Piano", 150),
    UUID("1b61311b-a94c-4a10-bcf3-a012b10415e2"): ("Partition degré 8", 100),
}


def stock_snapshot(db):
    return [tuple(row) for row in db.execute(select(
        ProductLocationStock.product_id, ProductLocationStock.location_id,
        ProductLocationStock.real_quantity, ProductLocationStock.estimated_quantity,
        ProductLocationStock.inventory_quantity,
    ).where(ProductLocationStock.product_id.in_(PARTITIONS)).order_by(ProductLocationStock.product_id, ProductLocationStock.location_id))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        location = db.scalars(select(Location).where(Location.active.is_(True), Location.is_online.is_(False), Location.name == "Rue de Richelieu")).one()
        products = db.scalars(select(CatalogProduct).where(CatalogProduct.id.in_(PARTITIONS))).all()
        if len(products) != 2 or any(p.title != PARTITIONS[p.id][0] for p in products):
            raise RuntimeError("Partition IDs/titles no longer match the reviewed catalog")
        actor = db.scalars(select(User).where(User.email == "admin@piano-academie.com", User.role == UserRole.ADMIN, User.is_active.is_(True))).one()
        items = [SupplyOrderItemIn(product_id=pid, quantity=quantity) for pid, (_, quantity) in PARTITIONS.items()]
        items += [SupplyOrderItemIn(product_title="Cahier de travail degré 2", quantity=150),
                  SupplyOrderItemIn(product_title="Cahier de travail degré 8", quantity=100)]
        payload = SupplyOrderCreate(submission_id=ORDER_ID, location_id=location.id,
            ordered_date=date(2026, 8, 30), expected_delivery_date=date(2026, 9, 7),
            reference="Livraison Richelieu 07/09/2026 — degrés 2 et 8",
            note="Commande déclarée le 30/08/2026. Les cahiers de travail ne sont pas des cahiers de solfège ; références catalogue à préciser avant réception.", items=items)
        print(json.dumps({"apply": args.apply, "order": payload.model_dump(mode="json")}, ensure_ascii=False))
        before = stock_snapshot(db)
        row = create_supply_order(db, payload, actor.id)
        lines = order_lines(db, row.id)
        if row.status != "ORDERED" or len(lines) != 4 or sum(line.quantity for line in lines) != 500:
            raise RuntimeError("Unexpected order content/state; no changes committed")
        if before != stock_snapshot(db) or any(line.stock_movement_id for line in lines):
            raise RuntimeError("Stock changed unexpectedly; no changes committed")
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({"committed": args.apply, "order_id": str(ORDER_ID), "status": "ORDERED", "quantity": 500, "stock_unchanged": True}))


if __name__ == "__main__":
    main()
