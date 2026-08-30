"""Run against a disposable PostgreSQL database migrated to head (no production data)."""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.catalog import Location
from app.models.product_catalog import CatalogProduct, ProductLocationStock, ProductReorderStatus, ProductStockMovement
from app.models.supply_order import ProductSupplyOrder, ProductSupplyOrderLine
from app.schemas.supply_order import SupplyOrderCreate, SupplyOrderItemIn
from app.services.product_catalog import PARIS_TIMEZONE, utcnow
from app.services.supply_orders import complete_supply_order, create_supply_order, order_lines


@unittest.skipUnless(os.getenv("SUPPLY_ORDER_TEST_DATABASE_URL"), "Disposable database URL required")
class SupplyOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(os.environ["SUPPLY_ORDER_TEST_DATABASE_URL"])

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(self.connection)
        self.today = utcnow().astimezone(PARIS_TIMEZONE).date()
        self.location = Location(name=f"Richelieu test {uuid4()}", code=str(uuid4())[:8], is_online=False, active=True,
                                 timezone="Europe/Paris", address_line="1 rue de test", city="Paris", country_code="FR")
        self.products = [CatalogProduct(title=f"Partition test degré {n}", active=True, is_virtual=False) for n in (2, 8)]
        self.db.add_all([self.location, *self.products])
        self.db.flush()
        self.payload = SupplyOrderCreate(submission_id=uuid4(), location_id=self.location.id,
            ordered_date=self.today, expected_delivery_date=self.today + timedelta(days=8),
            reference="TEST", items=[SupplyOrderItemIn(product_id=p.id, quantity=q) for p, q in zip(self.products, (150, 100))])

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def count_movements(self):
        return self.db.scalar(select(func.count()).select_from(ProductStockMovement).where(ProductStockMovement.product_id.in_([p.id for p in self.products])))

    def test_create_does_not_change_available_or_estimated_stock(self):
        row = create_supply_order(self.db, self.payload, None)
        self.assertEqual(row.status, "ORDERED")
        self.assertEqual(sum(line.quantity for line in order_lines(self.db, row.id)), 250)
        self.assertEqual(self.count_movements(), 0)
        self.assertEqual([p.stock_global_quantity for p in self.products], [0, 0])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProductLocationStock).where(ProductLocationStock.product_id.in_([p.id for p in self.products]))), 0)
        self.assertTrue(all(p.reorder_status == ProductReorderStatus.ORDERED for p in self.products))

    def test_create_retry_is_idempotent_and_content_change_is_rejected(self):
        row = create_supply_order(self.db, self.payload, None)
        self.assertEqual(create_supply_order(self.db, self.payload, None).id, row.id)
        self.assertEqual(len(order_lines(self.db, row.id)), 2)
        with self.assertRaises(ValueError):
            create_supply_order(self.db, self.payload.model_copy(update={"reference": "different"}), None)

    def test_receipt_creates_exact_stock_once_and_links_movements(self):
        row = create_supply_order(self.db, self.payload, None)
        complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today)
        complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today)
        self.assertEqual(self.count_movements(), 2)
        self.assertEqual([p.stock_global_quantity for p in self.products], [150, 100])
        for line in order_lines(self.db, row.id):
            stock = self.db.scalar(select(ProductLocationStock).where(ProductLocationStock.product_id == line.product_id, ProductLocationStock.location_id == self.location.id))
            self.assertEqual((stock.real_quantity, stock.estimated_quantity), (line.quantity, line.quantity))
            self.assertEqual(stock.inventory_quantity, 0)
            self.assertIsNotNone(line.stock_movement_id)
        self.assertEqual(row.status, "RECEIVED")

    def test_cancellation_is_idempotent_without_stock_and_cannot_receive(self):
        row = create_supply_order(self.db, self.payload, None)
        complete_supply_order(self.db, row.id, actor_id=None, cancel=True)
        complete_supply_order(self.db, row.id, actor_id=None, cancel=True)
        self.assertEqual(self.count_movements(), 0)
        with self.assertRaises(ValueError):
            complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today)

    def test_cannot_cancel_received_order(self):
        row = create_supply_order(self.db, self.payload, None)
        complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today)
        with self.assertRaises(ValueError):
            complete_supply_order(self.db, row.id, actor_id=None, cancel=True)

    def test_future_or_preorder_receipt_rejected(self):
        row = create_supply_order(self.db, self.payload, None)
        for value in (self.today + timedelta(days=1), self.today - timedelta(days=1), None):
            with self.assertRaises(ValueError):
                complete_supply_order(self.db, row.id, actor_id=None, received_date=value)
        self.assertEqual(row.status, "ORDERED")
        self.assertEqual(self.count_movements(), 0)

    def test_other_pending_order_keeps_product_ordered(self):
        first = create_supply_order(self.db, self.payload, None)
        second = create_supply_order(self.db, self.payload.model_copy(update={"submission_id": uuid4()}), None)
        complete_supply_order(self.db, first.id, actor_id=None, received_date=self.today)
        self.assertTrue(all(p.reorder_status == ProductReorderStatus.ORDERED for p in self.products))
        complete_supply_order(self.db, second.id, actor_id=None, cancel=True)
        self.assertEqual([p.stock_global_quantity for p in self.products], [150, 100])

    def test_physical_location_and_products_required(self):
        self.location.is_online = True
        self.db.flush()
        with self.assertRaises(ValueError): create_supply_order(self.db, self.payload, None)
        self.location.is_online = False
        self.products[0].is_virtual = True
        self.db.flush()
        with self.assertRaises(ValueError): create_supply_order(self.db, self.payload, None)
        self.assertIsNone(self.db.get(ProductSupplyOrder, self.payload.submission_id))

    def test_failed_receipt_rolls_back_all_lines(self):
        row = create_supply_order(self.db, self.payload, None)
        from app.services.product_catalog import create_stock_movement
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: raise ValueError("test rollback")
            return create_stock_movement(*args, **kwargs)
        with self.assertRaises(ValueError), self.db.begin_nested(), patch("app.services.supply_orders.create_stock_movement", side_effect=fail_second):
            complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today)
        self.db.expire_all()
        self.assertEqual(row.status, "ORDERED")
        self.assertEqual(self.count_movements(), 0)
        self.assertEqual([p.stock_global_quantity for p in self.products], [0, 0])

    def test_invalid_lines_and_dates(self):
        for quantity in (0, -1, 1.5, True, 1000001):
            with self.assertRaises(ValidationError): SupplyOrderItemIn(product_id=uuid4(), quantity=quantity)
        for update in ({"items": []}, {"items": [self.payload.items[0], self.payload.items[0]]},
                       {"expected_delivery_date": self.today - timedelta(days=1)}):
            with self.assertRaises(ValidationError): SupplyOrderCreate.model_validate({**self.payload.model_dump(), **update})

    def test_unlisted_product_requires_catalog_link_before_receipt(self):
        payload = self.payload.model_copy(update={"items": [SupplyOrderItemIn(product_title="Cahier de travail degré 2", quantity=150)]})
        row = create_supply_order(self.db, payload, None)
        self.assertEqual(create_supply_order(self.db, payload, None).id, row.id)
        line = order_lines(self.db, row.id)[0]
        self.assertIsNone(line.product_id)
        with self.assertRaises(ValueError): complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today)
        self.assertEqual(self.count_movements(), 0)
        complete_supply_order(self.db, row.id, actor_id=None, received_date=self.today, product_links={line.id: self.products[0].id})
        self.assertEqual(self.products[0].stock_global_quantity, 150)
        self.assertEqual(line.product_id, self.products[0].id)

    def test_unlisted_products_can_be_cancelled_without_stock(self):
        payload = self.payload.model_copy(update={"items": [SupplyOrderItemIn(product_title="Cahier de travail", quantity=150)]})
        row = create_supply_order(self.db, payload, None)
        complete_supply_order(self.db, row.id, actor_id=None, cancel=True)
        self.assertEqual(row.status, "CANCELLED")
        self.assertEqual(self.count_movements(), 0)

    def test_api_requires_admin_and_validates_payload(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from app.api.deps import get_current_user, get_db
        from app.api.routes.admin_supply_orders import router
        from app.models.user import UserRole
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        with TestClient(app) as client:
            self.assertEqual(client.get("/admin/config/catalog/supply-orders").status_code, 401)
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=None, role=UserRole.CLIENT)
            self.assertEqual(client.post("/admin/config/catalog/supply-orders", json=self.payload.model_dump(mode="json")).status_code, 403)
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=None, role=UserRole.ADMIN)
            self.assertEqual(client.post("/admin/config/catalog/supply-orders", json={}).status_code, 422)
            response = client.post("/admin/config/catalog/supply-orders", json=self.payload.model_dump(mode="json"))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "ORDERED")
            self.assertIn(str(self.payload.submission_id), [row["id"] for row in client.get("/admin/config/catalog/supply-orders").json()])

    def test_concurrent_creation_and_receipt_do_not_duplicate_stock(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        # Committed fixtures visible from independent connections in this disposable DB.
        with Session(self.engine) as seed:
            location = Location(code=str(uuid4()), name="Concurrency test", timezone="Europe/Paris", is_online=False,
                                active=True, address_line="Test", city="Paris", country_code="FR")
            product = CatalogProduct(title="Concurrent receipt test", active=True, is_virtual=False)
            seed.add_all([location, product])
            seed.flush()
            payload = SupplyOrderCreate(submission_id=uuid4(), location_id=location.id, ordered_date=self.today,
                expected_delivery_date=self.today, items=[SupplyOrderItemIn(product_id=product.id, quantity=150)])
            seed.commit()
        barrier = Barrier(2)
        def create():
            with Session(self.engine) as db:
                barrier.wait(timeout=5)
                row = create_supply_order(db, payload, None)
                db.commit()
                return row.id
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(list(executor.map(lambda _: create(), range(2))), [payload.submission_id] * 2)
        barrier = Barrier(2)
        def receive():
            with Session(self.engine) as db:
                barrier.wait(timeout=5)
                complete_supply_order(db, payload.submission_id, actor_id=None, received_date=self.today)
                db.commit()
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: receive(), range(2)))
        with Session(self.engine) as db:
            self.assertEqual(db.get(CatalogProduct, payload.items[0].product_id).stock_global_quantity, 150)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductStockMovement).where(ProductStockMovement.product_id == payload.items[0].product_id)), 1)


if __name__ == "__main__":
    unittest.main()
