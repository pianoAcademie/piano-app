from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseType, Location
from app.models.quote import PaymentPlan, PricingCatalog, QuoteType
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"


@dataclass
class ApiResult:
    status: int
    data: Any


class SmokeFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: Any | None = None, token: str | None = None) -> ApiResult:
        headers: dict[str, str] = {}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                text = raw.decode() if raw else ""
                data = json.loads(text) if text else None
                return ApiResult(status=response.status, data=data)
        except HTTPError as exc:
            raw = exc.read()
            text = raw.decode() if raw else ""
            try:
                data = json.loads(text) if text else None
            except Exception:
                data = text
            return ApiResult(status=exc.code, data=data)

    def call_bytes(self, method: str, path: str, token: str | None = None) -> tuple[int, bytes]:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(f"{self.base_url}{path}", data=None, headers=headers, method=method)
        try:
            with urlopen(request, timeout=45) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()


api = ApiClient(BASE_URL)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def step(message: str) -> None:
    print(f"[SMOKE-QUOTE] {message}", flush=True)


def wait_backend_ready(timeout_seconds: int = 60, interval_seconds: float = 1.5) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "unknown"
    while time.time() < deadline:
        try:
            health = api.call("GET", "/health")
            if health.status == 200 and isinstance(health.data, dict) and health.data.get("ok") is True:
                return
            last_error = f"status={health.status} data={health.data}"
        except URLError as exc:
            last_error = str(exc)
        except Exception as exc:  # pragma: no cover - smoke
            last_error = str(exc)
        time.sleep(interval_seconds)
    raise SmokeFailure(f"backend not ready after {timeout_seconds}s: {last_error}")


def register_user(email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Smoke",
        "last_name": "Quote",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": "Europe/Paris",
    }
    result = api.call("POST", "/api/v1/auth/register", payload)
    ensure(result.status == 201, f"register failed: {result.status} {result.data}")


def promote_admin(email: str) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found for promotion: {email}")
        user.role = UserRole.ADMIN
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def login(email: str, password: str) -> str:
    result = api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(result.status == 200, f"login failed: {result.status} {result.data}")
    token = result.data.get("access_token") if isinstance(result.data, dict) else None
    ensure(isinstance(token, str) and bool(token), "missing access_token")
    return token


@dataclass
class QuoteRuntimeRefs:
    quote_type_id: str
    pricing_catalog_id: str | None
    payment_plan_single_id: str | None
    payment_plan_multi_id: str | None
    location_id: str | None
    activity_ids: list[str]


def pick_runtime_refs() -> QuoteRuntimeRefs:
    with SessionLocal() as db:
        quote_type = db.scalar(select(QuoteType).where(QuoteType.is_active.is_(True)).order_by(QuoteType.created_at.asc()))
        ensure(quote_type is not None, "no active quote type")
        catalog = db.scalar(
            select(PricingCatalog).where(PricingCatalog.is_active.is_(True)).order_by(PricingCatalog.is_default.desc(), PricingCatalog.created_at.asc())
        )
        plans = db.scalars(select(PaymentPlan).where(PaymentPlan.is_active.is_(True)).order_by(PaymentPlan.created_at.asc())).all()
        location = db.scalar(select(Location).order_by(Location.created_at.asc()))
        activities = db.scalars(
            select(CourseType).where(CourseType.active.is_(True)).order_by(CourseType.created_at.asc())
        ).all()
        ensure(len(activities) >= 2, "need at least 2 active activities for smoke")

        single_plan = next((p for p in plans if (p.schedule_type or "").strip().lower() in {"single", "one_time", "payment_single"}), None)
        multi_plan = next((p for p in plans if (p.schedule_type or "").strip().lower() in {"fixed_months", "monthly", "split"}), None)
        if multi_plan is None:
            multi_plan = next((p for p in plans if "2 fois" in (p.name or "").lower() or "4 fois" in (p.name or "").lower()), None)

        return QuoteRuntimeRefs(
            quote_type_id=str(quote_type.id),
            pricing_catalog_id=str(catalog.id) if catalog is not None else None,
            payment_plan_single_id=str(single_plan.id) if single_plan is not None else (str(plans[0].id) if plans else None),
            payment_plan_multi_id=str(multi_plan.id) if multi_plan is not None else (str(plans[0].id) if plans else None),
            location_id=str(location.id) if location is not None else None,
            activity_ids=[str(activities[0].id), str(activities[1].id)],
        )


def create_prospect(token: str, *, first_name: str, last_name: str, email: str, prospect_type: str, parent_id: str | None = None, meta_extra: dict[str, object] | None = None) -> dict[str, Any]:
    meta = {"prospect_type": prospect_type}
    if meta_extra:
        meta.update(meta_extra)
    payload: dict[str, Any] = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": "+33102030405",
        "meta": meta,
    }
    if parent_id:
        payload["parent_prospect_id"] = parent_id
    result = api.call("POST", "/api/v1/prospects", payload, token)
    ensure(result.status == 201, f"create prospect failed: {result.status} {result.data}")
    ensure(isinstance(result.data, dict) and result.data.get("id"), "missing prospect id")
    return result.data


def quote_lines_for(activity_ids: list[str], *, base_price: Decimal) -> list[dict[str, Any]]:
    return [
        {
            "line_category": "service",
            "line_type": "item",
            "master_item_type": "activity",
            "activity_id": activity_ids[0],
            "title": "Cours principal",
            "quantity": "4.00",
            "vat_rate": "0.00",
            "unit_price_ttc": str(base_price),
            "pricing_unit": "session",
            "sort_order": 10,
        },
        {
            "line_category": "service",
            "line_type": "item",
            "master_item_type": "activity",
            "activity_id": activity_ids[1],
            "title": "Atelier complementaire",
            "quantity": "2.00",
            "vat_rate": "0.00",
            "unit_price_ttc": str((base_price / Decimal("2")).quantize(Decimal("0.01"))),
            "pricing_unit": "session",
            "sort_order": 20,
        },
    ]


def create_quote(
    token: str,
    refs: QuoteRuntimeRefs,
    *,
    prospect_id: str,
    payment_plan_id: str | None,
    adjustment_type: str,
    adjustment_amount: Decimal = Decimal("0.00"),
    adjustment_label: str = "",
    school_year_label: str = "2026-2027",
) -> dict[str, Any]:
    payload = {
        "context_type": "acquisition",
        "quote_type": "forfait",
        "quote_type_id": refs.quote_type_id,
        "pricing_catalog_id": refs.pricing_catalog_id,
        "prospect_id": prospect_id,
        "location_id": refs.location_id,
        "payment_plan_id": payment_plan_id,
        "school_year_label": school_year_label,
        "currency": "EUR",
        "language": "fr",
        "expiry_days": 15,
        "meta": {
            "financial_adjustment": {
                "type": adjustment_type,
                "amount_ttc": str(adjustment_amount.quantize(Decimal("0.01"))),
                "effective_date": date.today().isoformat(),
                "label": adjustment_label or None,
            }
        },
        "lines": quote_lines_for(refs.activity_ids, base_price=Decimal("80.00")),
    }
    result = api.call("POST", "/api/v1/quotes", payload, token)
    ensure(result.status == 201, f"create quote failed: {result.status} {result.data}")
    ensure(isinstance(result.data, dict) and isinstance(result.data.get("quote"), dict), "invalid create quote payload")
    return result.data


def regenerate_quote(token: str, quote_id: str) -> dict[str, Any]:
    result = api.call("POST", f"/api/v1/quotes/{quote_id}/document/regenerate", None, token)
    ensure(result.status == 200, f"regenerate failed: {result.status} {result.data}")
    ensure(isinstance(result.data, dict), "invalid regenerate payload")
    return result.data


def preview_quote(token: str, quote_id: str, audience: str = "admin_preview") -> dict[str, Any]:
    result = api.call("GET", f"/api/v1/quotes/{quote_id}/document-preview?audience={audience}", None, token)
    ensure(result.status == 200, f"preview failed: {result.status} {result.data}")
    ensure(isinstance(result.data, dict), "invalid preview payload")
    return result.data


def download_pdf(token: str, quote_id: str) -> bytes:
    status_code, content = api.call_bytes("GET", f"/api/v1/quotes/{quote_id}/pdf", token)
    ensure(status_code == 200, f"pdf download failed: status={status_code}")
    ensure(content.startswith(b"%PDF"), "pdf content is not a valid PDF signature")
    ensure(len(content) > 3000, f"pdf too small ({len(content)} bytes)")
    return content


def decimal_sum_line_ttc(lines: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0.00")
    for line in lines:
        total += Decimal(str(line.get("amount_ttc") or "0"))
    return total.quantize(Decimal("0.01"))


def validate_quote_totals(quote_payload: dict[str, Any], *, expected_adjustment_type: str, expected_adjustment_amount: Decimal) -> None:
    quote = quote_payload["quote"]
    lines = quote_payload["lines"]
    lines_total = decimal_sum_line_ttc(lines)
    adjustment = Decimal("0.00")
    if expected_adjustment_type == "credit":
        adjustment = -expected_adjustment_amount
    elif expected_adjustment_type == "debt":
        adjustment = expected_adjustment_amount
    expected_total = (lines_total + adjustment).quantize(Decimal("0.01"))
    if expected_total < Decimal("0.00"):
        expected_total = Decimal("0.00")
    actual_total = Decimal(str(quote.get("total_ttc") or "0")).quantize(Decimal("0.01"))
    ensure(actual_total == expected_total, f"unexpected total_ttc expected={expected_total} actual={actual_total}")

    meta = quote.get("meta") or {}
    adjustment_meta = (meta.get("financial_adjustment") or {}) if isinstance(meta, dict) else {}
    actual_type = str(adjustment_meta.get("type") or "none")
    ensure(actual_type == expected_adjustment_type, f"adjustment type mismatch expected={expected_adjustment_type} actual={actual_type}")

    payment_snapshot = quote.get("payment_terms_snapshot") or {}
    if isinstance(payment_snapshot, dict) and payment_snapshot:
        snapshot_adjustment = payment_snapshot.get("adjustment") or {}
        if isinstance(snapshot_adjustment, dict):
            snapshot_type = str(snapshot_adjustment.get("type") or "none")
            ensure(
                snapshot_type == expected_adjustment_type,
                f"payment snapshot adjustment type mismatch expected={expected_adjustment_type} actual={snapshot_type}",
            )
        snapshot_total = Decimal(str(payment_snapshot.get("total_ttc_after_adjustment") or "0")).quantize(Decimal("0.01"))
        ensure(snapshot_total == actual_total, f"payment snapshot total mismatch expected={actual_total} actual={snapshot_total}")


def validate_preview(preview: dict[str, Any], *, should_have_adjustment: bool) -> None:
    html = str(preview.get("combined_html") or "")
    ensure("{financial_adjustment_block_html}" not in html, "unresolved financial adjustment token in rendered HTML")
    ensure("quote-running-header" in html, "running header not present in rendered HTML")
    ensure("quote-running-footer" in html, "running footer not present in rendered HTML")


def main() -> None:
    random_tag = f"{int(time.time())}{random.randint(100, 999)}"
    admin_email = f"smoke.quote.adjustment.{random_tag}@example.com"
    admin_password = "SmokePass!123"

    step("Attente backend")
    wait_backend_ready()

    step("Creation compte admin smoke")
    register_user(admin_email, admin_password)
    admin = promote_admin(admin_email)
    token = login(admin_email, admin_password)

    step("Chargement referentiels runtime")
    refs = pick_runtime_refs()

    step("Creation prospects (adulte, parent+enfant, parent+enfant avec 2e parent)")
    adult = create_prospect(
        token,
        first_name="SmokeAdult",
        last_name="Quote",
        email=f"smoke.adult.{random_tag}@example.com",
        prospect_type="adult",
        meta_extra={"birth_date": "1987-04-21"},
    )
    parent_1 = create_prospect(
        token,
        first_name="ParentOne",
        last_name="Smoke",
        email=f"smoke.parent1.{random_tag}@example.com",
        prospect_type="adult",
        meta_extra={"address": "1 rue de test, 75001 Paris"},
    )
    child_1 = create_prospect(
        token,
        first_name="ChildOne",
        last_name="Smoke",
        email=f"smoke.child1.{random_tag}@example.com",
        prospect_type="child",
        parent_id=str(parent_1["id"]),
        meta_extra={"birth_date": "2016-09-14"},
    )
    parent_2 = create_prospect(
        token,
        first_name="ParentTwo",
        last_name="Smoke",
        email=f"smoke.parent2.{random_tag}@example.com",
        prospect_type="adult",
    )
    child_2 = create_prospect(
        token,
        first_name="ChildTwo",
        last_name="Smoke",
        email=f"smoke.child2.{random_tag}@example.com",
        prospect_type="child",
        parent_id=str(parent_2["id"]),
        meta_extra={
            "birth_date": "2015-02-08",
            "parent_secondary_first_name": "Second",
            "parent_secondary_last_name": "Parent",
            "parent_secondary_phone": "+33600000000",
        },
    )

    scenarios = [
        {
            "label": "adulte sans ajustement",
            "prospect_id": str(adult["id"]),
            "plan_id": refs.payment_plan_single_id,
            "adjustment_type": "none",
            "adjustment_amount": Decimal("0.00"),
            "adjustment_label": "",
            "expect_adjustment_block": False,
        },
        {
            "label": "enfant avec avoir",
            "prospect_id": str(child_1["id"]),
            "plan_id": refs.payment_plan_multi_id,
            "adjustment_type": "credit",
            "adjustment_amount": Decimal("100.00"),
            "adjustment_label": "Avoir reprise dossier",
            "expect_adjustment_block": True,
        },
        {
            "label": "enfant avec dette",
            "prospect_id": str(child_2["id"]),
            "plan_id": refs.payment_plan_multi_id,
            "adjustment_type": "debt",
            "adjustment_amount": Decimal("65.00"),
            "adjustment_label": "Dette reportee",
            "expect_adjustment_block": True,
        },
    ]

    created_quote_ids: list[str] = []
    for scenario in scenarios:
        step(f"Scenario: {scenario['label']}")
        created = create_quote(
            token,
            refs,
            prospect_id=scenario["prospect_id"],
            payment_plan_id=scenario["plan_id"],
            adjustment_type=scenario["adjustment_type"],
            adjustment_amount=scenario["adjustment_amount"],
            adjustment_label=scenario["adjustment_label"],
        )
        validate_quote_totals(
            created,
            expected_adjustment_type=scenario["adjustment_type"],
            expected_adjustment_amount=scenario["adjustment_amount"],
        )
        quote_id = str(created["quote"]["id"])
        created_quote_ids.append(quote_id)
        regenerate_quote(token, quote_id)
        preview = preview_quote(token, quote_id, audience="admin_preview")
        validate_preview(preview, should_have_adjustment=bool(scenario["expect_adjustment_block"]))
        download_pdf(token, quote_id)

    step("Validation terminee")
    print(json.dumps({"ok": True, "created_quote_ids": created_quote_ids, "admin_user_id": str(admin.id)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
