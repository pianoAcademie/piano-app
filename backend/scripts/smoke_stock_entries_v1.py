from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"
PASSWORD = "Password123X"


@dataclass
class ApiResult:
    status: int
    data: Any


class SmokeFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: Any | None = None, token: str | None = None, *, timeout: int = 30) -> ApiResult:
        headers: dict[str, str] = {}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read().decode()
                data = json.loads(raw) if raw else None
                return ApiResult(status=response.status, data=data)
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                data = json.loads(raw) if raw else None
            except Exception:
                data = raw
            return ApiResult(status=exc.code, data=data)


api = ApiClient(BASE_URL)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def step(message: str) -> None:
    print(f"[SMOKE-STOCK] {message}", flush=True)


def wait_backend_ready(timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "unreachable"
    while time.time() < deadline:
        try:
            health = api.call("GET", "/health")
            if health.status == 200 and isinstance(health.data, dict) and health.data.get("ok") is True:
                return
            last_error = f"status={health.status}"
        except URLError as exc:
            last_error = str(exc)
        time.sleep(1.5)
    raise SmokeFailure(f"backend not ready: {last_error}")


def register_user(email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Stock",
        "last_name": "Smoke",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": "Europe/Paris",
    }
    res = api.call("POST", "/api/v1/auth/register", payload)
    ensure(res.status == 201, f"register failed: {res.status} {res.data}")


def promote_user_role(email: str, role: UserRole) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(User).where(User.email == email))
        ensure(row is not None, f"user not found for role promotion: {email}")
        row.role = role
        db.add(row)
        db.commit()


def login(email: str, password: str) -> str:
    res = api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(res.status == 200 and isinstance(res.data, dict), f"login failed: {res.status} {res.data}")
    token = res.data.get("access_token")
    ensure(isinstance(token, str) and token, "missing access token")
    return token


def ensure_catalog_category(admin_token: str, *, suffix: str) -> str:
    categories = api.call("GET", "/api/v1/admin/config/catalog/categories?include_inactive=true", token=admin_token)
    ensure(categories.status == 200 and isinstance(categories.data, list), f"load categories failed: {categories.status}")
    if categories.data:
        first = categories.data[0]
        ensure(isinstance(first, dict) and isinstance(first.get("id"), str), "invalid category payload")
        return first["id"]

    created = api.call(
        "POST",
        "/api/v1/admin/config/catalog/categories",
        {"name": f"Smoke stock {suffix}", "description": "Smoke category", "active": True},
        token=admin_token,
    )
    ensure(created.status == 201 and isinstance(created.data, dict), f"create category failed: {created.status} {created.data}")
    category_id = created.data.get("id")
    ensure(isinstance(category_id, str), f"missing category id: {created.data}")
    return category_id


def ensure_stockable_product(admin_token: str, *, category_id: str, location_id: str, suffix: str) -> str:
    products = api.call("GET", "/api/v1/admin/config/catalog/products?include_inactive=true", token=admin_token)
    ensure(products.status == 200 and isinstance(products.data, list), f"load products failed: {products.status}")
    for row in products.data:
        if isinstance(row, dict) and not bool(row.get("is_virtual")) and bool(row.get("active")):
            product_id = row.get("id")
            if isinstance(product_id, str):
                return product_id

    payload = {
        "category_id": category_id,
        "primary_location_id": location_id,
        "title": f"Smoke stockable {suffix}",
        "barcode": None,
        "price_excl_vat": 10.0,
        "price_incl_vat": 12.0,
        "vat_rate": 20.0,
        "reserve_stock": 2,
        "reorder_status": "NORMAL",
        "image_url": None,
        "short_description": "Smoke stock product",
        "long_description": None,
        "web_link": None,
        "is_virtual": False,
        "purchasable_online": False,
        "is_public": False,
        "active": True,
    }
    created = api.call("POST", "/api/v1/admin/config/catalog/products", payload, token=admin_token)
    ensure(created.status == 201 and isinstance(created.data, dict), f"create product failed: {created.status} {created.data}")
    product_id = created.data.get("id")
    ensure(isinstance(product_id, str), f"missing product id: {created.data}")
    return product_id


def get_locations(admin_token: str) -> list[dict[str, Any]]:
    res = api.call("GET", "/api/v1/locations?active=false", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list), f"load locations failed: {res.status} {res.data}")
    locations = [row for row in res.data if isinstance(row, dict) and isinstance(row.get("id"), str)]
    ensure(locations, "no locations available")
    return locations


def get_stock_snapshot(admin_token: str, product_id: str) -> dict[str, Any]:
    res = api.call("GET", f"/api/v1/admin/config/catalog/products/{product_id}/stock", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, dict), f"load stock snapshot failed: {res.status} {res.data}")
    return res.data


def location_stock(snapshot: dict[str, Any], location_id: str) -> int:
    rows = snapshot.get("stock_by_location")
    if not isinstance(rows, list):
        return 0
    for row in rows:
        if isinstance(row, dict) and row.get("location_id") == location_id:
            value = row.get("real_quantity")
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
    return 0


def main() -> None:
    started = time.time()
    now = datetime.now(UTC)
    stamp = int(started)

    step("health")
    wait_backend_ready()

    admin_email = f"smoke.stock.admin.{stamp}@example.com"
    step("register+promote admin")
    register_user(admin_email, PASSWORD)
    promote_user_role(admin_email, UserRole.ADMIN)
    admin_token = login(admin_email, PASSWORD)

    step("resolve location/product")
    locations = get_locations(admin_token)
    primary_location = locations[0]
    primary_location_id = str(primary_location["id"])
    category_id = ensure_catalog_category(admin_token, suffix=str(stamp))
    product_id = ensure_stockable_product(
        admin_token,
        category_id=category_id,
        location_id=primary_location_id,
        suffix=str(stamp),
    )

    before = get_stock_snapshot(admin_token, product_id)
    before_global = int(before.get("stock_global") or 0)
    before_loc = location_stock(before, primary_location_id)

    step("post stock entry +10")
    entry_payload = {
        "product_id": product_id,
        "location_id": primary_location_id,
        "quantity": 10,
        "occurred_at": now.isoformat(),
        "source_type": "delivery",
        "source_reference": f"BL-{stamp}",
        "note": "Smoke stock entry",
    }
    created_entry = api.call("POST", "/api/v1/admin/stock/entries", entry_payload, token=admin_token)
    ensure(created_entry.status == 201 and isinstance(created_entry.data, dict), f"create entry failed: {created_entry.status} {created_entry.data}")
    movement_id = created_entry.data.get("movement_id")
    ensure(isinstance(movement_id, str), "missing movement id")

    after_entry = get_stock_snapshot(admin_token, product_id)
    after_global = int(after_entry.get("stock_global") or 0)
    after_loc = location_stock(after_entry, primary_location_id)
    ensure(after_global == before_global + 10, f"global stock mismatch: {before_global} -> {after_global}")
    ensure(after_loc == before_loc + 10, f"location stock mismatch: {before_loc} -> {after_loc}")

    transfer_check_ok = True
    if len(locations) > 1:
        step("transfer flow check")
        secondary_location_id = str(locations[1]["id"])
        transfer_created = api.call(
            "POST",
            "/api/v1/admin/config/catalog/transfers",
            {
                "product_id": product_id,
                "source_location_id": primary_location_id,
                "target_location_id": secondary_location_id,
                "quantity": 1,
                "planned_transfer_date": now.date().isoformat(),
            },
            token=admin_token,
        )
        ensure(transfer_created.status == 201 and isinstance(transfer_created.data, dict), f"create transfer failed: {transfer_created.status} {transfer_created.data}")
        transfer_id = transfer_created.data.get("id")
        ensure(isinstance(transfer_id, str), "missing transfer id")

        transfer_done = api.call(
            "POST",
            f"/api/v1/admin/config/catalog/transfers/{transfer_id}/complete",
            {"completed_transfer_date": now.date().isoformat()},
            token=admin_token,
        )
        ensure(transfer_done.status == 200, f"complete transfer failed: {transfer_done.status} {transfer_done.data}")

        after_transfer = get_stock_snapshot(admin_token, product_id)
        src_after = location_stock(after_transfer, primary_location_id)
        dst_after = location_stock(after_transfer, secondary_location_id)
        transfer_check_ok = (src_after == after_loc - 1) and (dst_after >= 1)

    step("list entries")
    entries_list = api.call(
        "GET",
        f"/api/v1/admin/stock/entries?product_id={product_id}&location_id={primary_location_id}&page=1&page_size=30",
        token=admin_token,
    )
    ensure(entries_list.status == 200 and isinstance(entries_list.data, dict), f"list entries failed: {entries_list.status} {entries_list.data}")
    items = entries_list.data.get("items")
    ensure(isinstance(items, list) and len(items) >= 1, "stock entries list is empty")
    movement_found = any(isinstance(row, dict) and row.get("id") == movement_id for row in items)
    ensure(movement_found, "new stock movement not found in list")

    print(
        json.dumps(
            {
                "ok": True,
                "checks": {
                    "entry_created": True,
                    "stock_incremented": True,
                    "transfer_check": transfer_check_ok,
                    "entry_listed": True,
                },
            }
        )
    )
    print(f"[SMOKE-STOCK] done in {round(time.time() - started, 2)}s", flush=True)


if __name__ == "__main__":
    main()
