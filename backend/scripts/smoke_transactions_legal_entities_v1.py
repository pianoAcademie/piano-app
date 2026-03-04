from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
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
    headers: dict[str, str]


class SmokeFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call_json(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        token: str | None = None,
    ) -> ApiResult:
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
                raw = response.read().decode()
                data = json.loads(raw) if raw else None
                return ApiResult(status=response.status, data=data, headers=dict(response.headers.items()))
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                data = json.loads(raw) if raw else None
            except Exception:
                data = raw
            return ApiResult(status=exc.code, data=data, headers=dict(exc.headers.items()))


api = ApiClient(BASE_URL)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def step(message: str) -> None:
    print(f"[SMOKE-TX-LE] {message}", flush=True)


def wait_for_health(*, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            health = api.call_json("GET", "/health")
            if health.status == 200 and isinstance(health.data, dict) and health.data.get("ok") is True:
                return
            last_error = f"status={health.status} payload={health.data}"
        except URLError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise SmokeFailure(f"health check timeout: {last_error}")


def register_user(email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Tx",
        "last_name": "Smoke",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": "Europe/Paris",
    }
    res = api.call_json("POST", "/api/v1/auth/register", payload)
    ensure(res.status == 201, f"register failed for {email}: {res.status} {res.data}")


def promote_user_role(email: str, role: UserRole) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found for role promotion: {email}")
        user.role = role
        db.add(user)
        db.commit()


def login(email: str, password: str) -> str:
    res = api.call_json("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(res.status == 200 and isinstance(res.data, dict), f"login failed for {email}: {res.status} {res.data}")
    token = res.data.get("access_token")
    ensure(isinstance(token, str) and token, f"missing access token for {email}")
    return token


def user_id_from_email(email: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        return str(user.id)


def list_legal_entities(admin_token: str) -> list[dict[str, Any]]:
    res = api.call_json("GET", "/api/v1/admin/legal-entities?include_inactive=false", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list), f"list legal entities failed: {res.status} {res.data}")
    return [row for row in res.data if isinstance(row, dict)]


def find_legal_entity_id(rows: list[dict[str, Any]], name: str) -> str:
    target = name.strip().casefold()
    for row in rows:
        if str(row.get("name") or "").strip().casefold() == target:
            entity_id = str(row.get("id") or "").strip()
            ensure(entity_id, f"missing legal entity id for {name}")
            return entity_id
    raise SmokeFailure(f"legal entity not found: {name}")


def create_manual_transaction(
    admin_token: str,
    *,
    client_id: str,
    payload: dict[str, Any],
) -> ApiResult:
    return api.call_json("POST", f"/api/v1/admin/clients/{client_id}/manual-transactions", payload, admin_token)


def create_period_invoice(
    admin_token: str,
    *,
    client_id: str,
    day: date,
) -> dict[str, Any]:
    payload = {
        "issued_date": day.isoformat(),
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
        "due_date": day.isoformat(),
        "no_due_date": False,
        "include_pending": True,
        "include_cancelled": False,
        "layout": "DETAILED",
        "generation_mode": "MANUAL",
    }
    res = api.call_json("POST", f"/api/v1/admin/clients/{client_id}/payments/invoice-range", payload, admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create period invoice failed: {res.status} {res.data}")
    return res.data


def main() -> None:
    started = time.time()
    ts = int(started)

    admin_email = f"smoke.txle.admin.{ts}@example.com"
    client_email = f"smoke.txle.client.{ts}@example.com"

    step("health")
    wait_for_health(timeout_seconds=60)

    step("register + login")
    register_user(admin_email, PASSWORD)
    register_user(client_email, PASSWORD)
    promote_user_role(admin_email, UserRole.ADMIN)
    admin_token = login(admin_email, PASSWORD)
    client_id = user_id_from_email(client_email)

    step("load legal entities")
    legal_entities = list_legal_entities(admin_token)
    pa_id = find_legal_entity_id(legal_entities, "PIANO ACADEMIE")
    pas_id = find_legal_entity_id(legal_entities, "PIANO ACADEMIE SERVICES")

    base_day = (datetime.now(UTC) + timedelta(days=5)).date()
    day1 = base_day
    day2 = base_day + timedelta(days=1)
    day3 = base_day + timedelta(days=2)
    day4 = base_day + timedelta(days=3)

    step("case #1 create payment without invoice and without legal entity => error")
    payment_without_entity = create_manual_transaction(
        admin_token,
        client_id=client_id,
        payload={
            "transaction_type": "PAYMENT",
            "occurred_at": datetime.combine(day1, datetime.min.time(), tzinfo=UTC).isoformat(),
            "label": "Smoke payment without legal entity",
            "amount_incl_vat": 10.00,
            "vat_rate": 0,
            "currency": "EUR",
            "payment_method_code": "CARD_TERMINAL",
        },
    )
    ensure(payment_without_entity.status == 422, f"expected 422 for missing legal entity: {payment_without_entity.status} {payment_without_entity.data}")

    step("prepare invoices for case #2 same legal entity")
    for day, amount in ((day1, 35.00), (day2, 40.00)):
        charge = create_manual_transaction(
            admin_token,
            client_id=client_id,
            payload={
                "transaction_type": "CHARGE",
                "occurred_at": datetime.combine(day, datetime.min.time(), tzinfo=UTC).isoformat(),
                "label": f"Smoke charge PA {day.isoformat()}",
                "amount_incl_vat": amount,
                "vat_rate": 20.0,
                "currency": "EUR",
                "legal_entity_id": pa_id,
            },
        )
        ensure(charge.status == 201, f"charge creation failed for PA: {charge.status} {charge.data}")

    pa_inv_1 = create_period_invoice(admin_token, client_id=client_id, day=day1)
    pa_inv_2 = create_period_invoice(admin_token, client_id=client_id, day=day2)
    pa_note_1 = str(pa_inv_1.get("note_id") or "")
    pa_note_2 = str(pa_inv_2.get("note_id") or "")
    ensure(pa_note_1 and pa_note_2, f"missing PA note ids: {pa_inv_1} / {pa_inv_2}")

    step("case #2 reconcile payment with 2 invoices same legal entity => ok")
    payment_same_entity = create_manual_transaction(
        admin_token,
        client_id=client_id,
        payload={
            "transaction_type": "PAYMENT",
            "occurred_at": datetime.combine(day2, datetime.min.time(), tzinfo=UTC).isoformat(),
            "label": "Smoke payment reconcile PA x2",
            "amount_incl_vat": 100.00,
            "vat_rate": 0,
            "currency": "EUR",
            "payment_method_code": "CARD_TERMINAL",
            "reconciled_invoice_note_ids": [pa_note_1, pa_note_2],
            "mark_reconciled_invoices_paid": False,
        },
    )
    ensure(payment_same_entity.status == 201 and isinstance(payment_same_entity.data, dict), f"payment reconcile same entity failed: {payment_same_entity.status} {payment_same_entity.data}")
    ensure(
        str(payment_same_entity.data.get("seller_legal_entity_id") or "") == pa_id,
        f"expected PA seller_legal_entity_id on reconciled payment: {payment_same_entity.data}",
    )

    step("prepare invoices for case #3 mixed legal entities")
    pa_charge_3 = create_manual_transaction(
        admin_token,
        client_id=client_id,
        payload={
            "transaction_type": "CHARGE",
            "occurred_at": datetime.combine(day3, datetime.min.time(), tzinfo=UTC).isoformat(),
            "label": "Smoke charge PA mixed",
            "amount_incl_vat": 28.00,
            "vat_rate": 20.0,
            "currency": "EUR",
            "legal_entity_id": pa_id,
        },
    )
    ensure(pa_charge_3.status == 201, f"PA charge for mixed case failed: {pa_charge_3.status} {pa_charge_3.data}")
    pas_charge_1 = create_manual_transaction(
        admin_token,
        client_id=client_id,
        payload={
            "transaction_type": "CHARGE",
            "occurred_at": datetime.combine(day4, datetime.min.time(), tzinfo=UTC).isoformat(),
            "label": "Smoke charge PAS mixed",
            "amount_incl_vat": 31.00,
            "vat_rate": 20.0,
            "currency": "EUR",
            "legal_entity_id": pas_id,
        },
    )
    ensure(pas_charge_1.status == 201, f"PAS charge for mixed case failed: {pas_charge_1.status} {pas_charge_1.data}")

    pa_inv_3 = create_period_invoice(admin_token, client_id=client_id, day=day3)
    pas_inv_1 = create_period_invoice(admin_token, client_id=client_id, day=day4)
    pa_note_3 = str(pa_inv_3.get("note_id") or "")
    pas_note_1 = str(pas_inv_1.get("note_id") or "")
    ensure(pa_note_3 and pas_note_1, f"missing mixed-case note ids: {pa_inv_3} / {pas_inv_1}")

    step("case #3 reconcile payment with invoices from different legal entities => explicit error")
    payment_mixed_entities = create_manual_transaction(
        admin_token,
        client_id=client_id,
        payload={
            "transaction_type": "PAYMENT",
            "occurred_at": datetime.combine(day4, datetime.min.time(), tzinfo=UTC).isoformat(),
            "label": "Smoke payment reconcile mixed entities",
            "amount_incl_vat": 99.00,
            "vat_rate": 0,
            "currency": "EUR",
            "payment_method_code": "CARD_TERMINAL",
            "reconciled_invoice_note_ids": [pa_note_3, pas_note_1],
            "mark_reconciled_invoices_paid": False,
        },
    )
    ensure(payment_mixed_entities.status == 422, f"expected 422 on mixed entities reconcile: {payment_mixed_entities.status} {payment_mixed_entities.data}")
    mixed_error = str(
        (payment_mixed_entities.data or {}).get("detail")
        if isinstance(payment_mixed_entities.data, dict)
        else payment_mixed_entities.data
    )
    ensure("Créer un paiement par entité" in mixed_error, f"unexpected mixed-entity error: {mixed_error}")

    duration = round(time.time() - started, 2)
    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "transactions_legal_entities_v1",
                "duration_seconds": duration,
                "checks": {
                    "case_1_manual_payment_without_invoice_requires_entity": True,
                    "case_2_reconcile_two_invoices_same_entity_ok": True,
                    "case_3_reconcile_two_invoices_different_entities_blocked": True,
                },
                "notes": {
                    "same_entity_invoice_note_ids": [pa_note_1, pa_note_2],
                    "mixed_entity_invoice_note_ids": [pa_note_3, pas_note_1],
                },
            }
        )
    )


if __name__ == "__main__":
    main()
