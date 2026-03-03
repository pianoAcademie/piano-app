from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.ops import LegalEntity
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"
PASSWORD = "Password123X"
INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::"


class SmokeFailure(RuntimeError):
    pass


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def step(message: str) -> None:
    print(f"[SMOKE-SAP] {message}", flush=True)


def call_json(method: str, path: str, payload: object | None = None, token: str | None = None) -> tuple[int, object | None]:
    headers: dict[str, str] = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = raw
        return exc.code, parsed


def call_text(method: str, path: str, token: str | None = None) -> tuple[int, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{BASE_URL}{path}", headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def wait_for_health(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "unavailable"
    while time.time() < deadline:
        try:
            status, payload = call_json("GET", "/health")
            if status == 200 and isinstance(payload, dict) and payload.get("ok") is True:
                return
            last_error = f"status={status} payload={payload}"
        except URLError as exc:
            last_error = str(exc)
        time.sleep(1)
    raise SmokeFailure(f"health check timeout: {last_error}")


def register_user(email: str, password: str, *, first_name: str, last_name: str) -> None:
    status, payload = call_json(
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
            "address_line": "12 Rue Export",
            "postal_code": "75011",
            "city": "Paris",
            "phone": "+33100000000",
            "residence_country": "FR",
            "preferred_currency": "EUR",
            "timezone": "Europe/Paris",
        },
    )
    ensure(status == 201, f"register failed for {email}: {status} {payload}")


def promote_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        user.role = UserRole.ADMIN
        db.add(user)
        db.commit()


def login(email: str, password: str) -> str:
    status, payload = call_json("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(status == 200 and isinstance(payload, dict), f"login failed for {email}: {status} {payload}")
    token = payload.get("access_token")
    ensure(isinstance(token, str) and token, f"missing token for {email}")
    return token


def get_user_by_email(email: str) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        db.expunge(user)
        return user


def get_services_legal_entity() -> LegalEntity:
    with SessionLocal() as db:
        entity = db.scalar(
            select(LegalEntity).where(LegalEntity.name == "PIANO ACADEMIE SERVICES").limit(1)
        )
        ensure(entity is not None, "PIANO ACADEMIE SERVICES legal entity not found")
        db.expunge(entity)
        return entity


def inject_services_invoice_lines(
    *,
    client_id: str,
    admin_id: str,
    services_entity_id: str,
    year: int,
    totals: list[Decimal],
) -> None:
    with SessionLocal() as db:
        invoice_number = f"PAS-SMOKE-{year}-{int(time.time())}"
        metadata = {
            "kind": "INVOICE_RANGE",
            "invoice_number": invoice_number,
            "invoice_status": "PAID",
        }
        note = ClientNoteEntry(
            user_id=client_id,
            author_user_id=admin_id,
            entry_type="MANUAL",
            message=f"Facture {invoice_number}\n{INVOICE_RANGE_NOTE_PREFIX}{json.dumps(metadata, separators=(',', ':'))}",
        )
        db.add(note)
        db.flush()

        for idx, total in enumerate(totals, start=1):
            occurred_at = datetime(year, min(idx, 12), 10, 12, 0, tzinfo=UTC)
            line = ClientInvoiceLine(
                note_id=note.id,
                user_id=client_id,
                source="MANUAL",
                source_payment_id=uuid4(),
                occurred_at=occurred_at,
                label=f"Cours a domicile #{idx}",
                amount_excl_vat=total,
                vat_rate=Decimal("0.00"),
                vat_amount=Decimal("0.00"),
                total_incl_vat=total,
                currency="EUR",
                billing_entity="PIANO ACADEMIE SERVICES",
                seller_legal_entity_id=services_entity_id,
            )
            db.add(line)
        db.commit()


def parse_decimal(value: str) -> Decimal:
    return Decimal((value or "0").strip() or "0").quantize(Decimal("0.01"))


def main() -> None:
    started = time.time()
    ts = int(started)

    step("health")
    wait_for_health(timeout_seconds=60)

    admin_email = f"smoke.sap.admin.{ts}@example.com"
    client_email = f"smoke.sap.client.{ts}@example.com"

    step("register users")
    register_user(admin_email, PASSWORD, first_name="Sap", last_name="Admin")
    register_user(client_email, PASSWORD, first_name="Sap", last_name="Client")
    promote_admin(admin_email)

    step("login admin")
    admin_token = login(admin_email, PASSWORD)
    admin_user = get_user_by_email(admin_email)
    client_user = get_user_by_email(client_email)

    step("inject services invoice lines")
    services = get_services_legal_entity()
    year = datetime.now(UTC).year
    inserted_totals = [Decimal("25.50"), Decimal("74.50")]
    expected_total = sum(inserted_totals, Decimal("0.00")).quantize(Decimal("0.01"))
    inject_services_invoice_lines(
        client_id=str(client_user.id),
        admin_id=str(admin_user.id),
        services_entity_id=str(services.id),
        year=year,
        totals=inserted_totals,
    )

    step("download sap csv")
    status, csv_text = call_text("GET", f"/api/v1/admin/reports/sap/{year}/csv", token=admin_token)
    ensure(status == 200, f"SAP CSV export failed: {status} {csv_text[:300]}")

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    ensure(len(rows) > 0, "SAP CSV returned no rows")

    client_rows = [row for row in rows if row.get("client_id") == str(client_user.id)]
    ensure(len(client_rows) > 0, "No exported SAP rows for injected client")

    detail_rows = [row for row in client_rows if row.get("row_type") == "DETAIL"]
    summary_rows = [row for row in client_rows if row.get("row_type") == "SUMMARY"]
    ensure(len(detail_rows) >= 1, "Expected at least one DETAIL line for services")
    ensure(len(summary_rows) == 1, f"Expected exactly one SUMMARY row, got {len(summary_rows)}")

    detail_total = sum((parse_decimal(row.get("total_incl_vat") or "0") for row in detail_rows), Decimal("0.00")).quantize(
        Decimal("0.01")
    )
    summary_total = parse_decimal(summary_rows[0].get("total_paid_ttc") or "0")
    ensure(detail_total == summary_total, f"Grouped total mismatch detail={detail_total} summary={summary_total}")
    ensure(summary_total >= expected_total, f"Summary total lower than injected expected total {expected_total}")

    duration = round(time.time() - started, 2)
    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "sap_export_v1",
                "duration_seconds": duration,
                "checks": {
                    "at_least_one_services_row_exported": True,
                    "grouped_totals_consistent": True,
                },
                "year": year,
                "client_id": str(client_user.id),
                "summary_total": f"{summary_total:.2f}",
            }
        )
    )


if __name__ == "__main__":
    main()
