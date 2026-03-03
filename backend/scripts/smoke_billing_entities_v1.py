from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as dt_time, timedelta
from typing import Any
from urllib.error import URLError
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, Location, Professor
from app.models.ops import LegalEntity
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

    def call_bytes(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
    ) -> ApiResult:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(f"{self.base_url}{path}", headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
                return ApiResult(status=response.status, data=payload, headers=dict(response.headers.items()))
        except HTTPError as exc:
            payload = exc.read()
            return ApiResult(status=exc.code, data=payload, headers=dict(exc.headers.items()))


api = ApiClient(BASE_URL)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def step(message: str) -> None:
    print(f"[SMOKE-BILLING] {message}", flush=True)


def register_user(email: str, password: str, *, timezone: str = "Europe/Paris") -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Billing",
        "last_name": "Smoke",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": timezone,
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


def get_online_location_and_professor() -> tuple[str, str]:
    with SessionLocal() as db:
        location = db.scalar(select(Location).where(Location.code == "ONLINE"))
        professor = db.scalar(select(Professor).where(Professor.email == "prof.demo@piano-academie.local"))
        ensure(location is not None, "ONLINE location not found")
        ensure(professor is not None, "demo professor not found")
        return str(location.id), str(professor.id)


def create_session_as_admin(
    admin_token: str,
    *,
    title: str,
    start_at: datetime,
    course_type_id: str,
    location_id: str,
    professor_id: str,
    capacity: int = 8,
) -> str:
    payload = {
        "course_type_id": course_type_id,
        "location_id": location_id,
        "professor_id": professor_id,
        "title": title,
        "description": "Smoke billing entities session",
        "start_at_utc": start_at.isoformat(),
        "end_at_utc": (start_at + timedelta(hours=1)).isoformat(),
        "capacity_max": capacity,
        "auto_cancel_deadline_utc": (start_at - timedelta(hours=2)).isoformat(),
        "zoom_link": "https://zoom.us/j/smoke-billing",
    }
    res = api.call_json("POST", "/api/v1/admin/sessions", payload, admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"admin create session failed: {res.status} {res.data}")
    session_id = res.data.get("id")
    ensure(isinstance(session_id, str), "missing session id after admin create")
    return session_id


def create_activity(
    admin_token: str,
    *,
    code: str,
    name: str,
    credit_type_id: str,
    seller_legal_entity_id: str,
) -> str:
    payload = {
        "code": code,
        "name": name,
        "description": "Smoke multi-entity activity",
        "service_code": "ACTIVITY",
        "seller_legal_entity_id": seller_legal_entity_id,
        "credit_type_id": credit_type_id,
        "duration_minutes": 60,
        "color_hex": "#94C973",
        "mode": "ANY",
        "default_capacity": 8,
        "active": True,
    }
    res = api.call_json("POST", "/api/v1/admin/activities", payload, admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create activity failed: {res.status} {res.data}")
    course_type_id = res.data.get("id")
    ensure(isinstance(course_type_id, str), f"missing activity id: {res.data}")
    return course_type_id


def list_active_activities(admin_token: str) -> list[dict[str, Any]]:
    res = api.call_json("GET", "/api/v1/admin/activities?include_inactive=false", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list), f"list activities failed: {res.status} {res.data}")
    return [row for row in res.data if isinstance(row, dict)]


def patch_activity_seller_legal_entity(admin_token: str, *, activity_id: str, seller_legal_entity_id: str) -> None:
    res = api.call_json(
        "PATCH",
        f"/api/v1/admin/activities/{activity_id}",
        {"seller_legal_entity_id": seller_legal_entity_id},
        admin_token,
    )
    ensure(res.status == 200 and isinstance(res.data, dict), f"patch activity legal entity failed: {res.status} {res.data}")


def create_pack_formula(
    admin_token: str,
    *,
    name: str,
    credit_type_id: str,
    entitlement_course_type_ids: list[str],
    payment_methods: list[str],
) -> str:
    payload = {
        "name": name,
        "kind": "PACK",
        "active": True,
        "is_private": False,
        "description": "Smoke multi-entity formula",
        "credits_count": 20,
        "pack_validity_months": 6,
        "credit_grants": [
            {
                "credit_type_id": credit_type_id,
                "credits_count": 20,
            }
        ],
        "credit_grants_relation": "OR",
        "monthly_price_excl_vat": 199.0,
        "currency_code": "EUR",
        "signup_fee_excl_vat": 0.0,
        "options": [],
        "payment_methods": payment_methods,
        "entitlement_course_type_ids": entitlement_course_type_ids,
        "restrictions": [],
    }
    res = api.call_json("POST", "/api/v1/admin/formulas", payload, admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create formula failed: {res.status} {res.data}")
    formula_id = res.data.get("id")
    ensure(isinstance(formula_id, str), f"missing formula id: {res.data}")
    return formula_id


def buy_plan_as_admin(admin_token: str, *, client_id: str, plan_id: str) -> str:
    res = api.call_json("POST", f"/api/v1/admin/clients/{client_id}/plans/{plan_id}/purchase", token=admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"admin purchase plan failed: {res.status} {res.data}")
    sub_id = res.data.get("id")
    ensure(isinstance(sub_id, str), f"missing subscription id: {res.data}")
    return sub_id


def book_session(client_token: str, session_id: str, subscription_id: str) -> str:
    payload = {"client_plan_subscription_id": subscription_id}
    res = api.call_json("POST", f"/api/v1/sessions/{session_id}/book", payload, client_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"book session failed: {res.status} {res.data}")
    booking_id = res.data.get("id")
    ensure(isinstance(booking_id, str), f"missing booking id: {res.data}")
    return booking_id


def session_snapshot_seller_legal_entity_id(session_id: str) -> str | None:
    with SessionLocal() as db:
        session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id))
        ensure(session_obj is not None, f"session not found in DB: {session_id}")
        if session_obj.snapshot_seller_legal_entity_id is None:
            return None
        return str(session_obj.snapshot_seller_legal_entity_id)


def list_legal_entities(admin_token: str) -> list[dict[str, Any]]:
    res = api.call_json("GET", "/api/v1/admin/legal-entities?include_inactive=true", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list), f"list legal entities failed: {res.status} {res.data}")
    return res.data


def find_legal_entity_by_name(rows: list[dict[str, Any]], expected_name: str) -> dict[str, Any]:
    target = expected_name.strip().casefold()
    for row in rows:
        if str(row.get("name") or "").strip().casefold() == target:
            return row
    raise SmokeFailure(f"legal entity not found: {expected_name}")


def patch_legal_entity_counter(admin_token: str, legal_entity_id: str, next_number: int) -> None:
    res = api.call_json(
        "PATCH",
        f"/api/v1/admin/legal-entities/{legal_entity_id}",
        {"invoice_next_number": next_number},
        admin_token,
    )
    ensure(res.status == 200 and isinstance(res.data, dict), f"patch legal entity failed: {res.status} {res.data}")


def get_first_credit_type_id(admin_token: str) -> str:
    res = api.call_json("GET", "/api/v1/admin/credit-types", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list) and len(res.data) > 0, f"list credit types failed: {res.status} {res.data}")
    first = res.data[0]
    credit_type_id = first.get("id") if isinstance(first, dict) else None
    ensure(isinstance(credit_type_id, str), f"invalid credit type payload: {first}")
    return credit_type_id


def get_enabled_payment_methods(admin_token: str) -> list[str]:
    res = api.call_json("GET", "/api/v1/admin/config/payment-methods", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, dict), f"get payment methods failed: {res.status} {res.data}")
    methods = res.data.get("methods")
    ensure(isinstance(methods, list), f"unexpected payment methods payload: {res.data}")
    allowed = {"CARD_ONLINE", "CARD_TERMINAL", "CASH", "BANK_TRANSFER", "SEPA_DIRECT_DEBIT"}
    enabled: list[str] = []
    for row in methods:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip().upper()
        if code and code in allowed:
            enabled.append(code)
    ensure(len(enabled) > 0, "no payment method available for formula")
    return enabled


def put_account_marker(admin_token: str, marker: str) -> None:
    get_res = api.call_json("GET", "/api/v1/admin/config/account", token=admin_token)
    ensure(get_res.status == 200 and isinstance(get_res.data, dict), f"get account config failed: {get_res.status} {get_res.data}")
    payload = dict(get_res.data)
    payload["club_name"] = marker
    payload["company_name"] = marker
    put_res = api.call_json("PUT", "/api/v1/admin/config/account", payload, admin_token)
    ensure(put_res.status == 200 and isinstance(put_res.data, dict), f"put account config failed: {put_res.status} {put_res.data}")


def create_ltd_legal_entity_in_db(ts: int, *, next_number: int) -> dict[str, str]:
    prefix = f"LTD{ts % 1000}"
    name = f"SMOKE LTD {ts}"
    siren = f"{900000000 + (ts % 99999999):09d}"
    siret = f"{siren}{(ts % 100000):05d}"[:14]
    vat = f"GBSMOKE{ts % 1000000}"
    with SessionLocal() as db:
        entity = LegalEntity(
            name=name,
            siren=siren,
            siret=siret,
            vat_number=vat,
            address_text="221B Baker Street, London",
            country_code="GB",
            invoice_prefix=prefix,
            invoice_next_number=next_number,
            is_active=True,
            updated_at=datetime.now(UTC),
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return {
            "id": str(entity.id),
            "name": entity.name,
            "siren": entity.siren or "",
            "invoice_prefix": entity.invoice_prefix,
            "invoice_next_number": str(entity.invoice_next_number),
        }


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
    res = api.call_json(
        "POST",
        f"/api/v1/admin/clients/{client_id}/payments/invoice-range",
        payload,
        admin_token,
    )
    ensure(res.status == 201 and isinstance(res.data, dict), f"create period invoice failed: {res.status} {res.data}")
    return res.data


def download_invoice_pdf(admin_token: str, *, client_id: str, note_id: str) -> bytes:
    res = api.call_bytes(
        "GET",
        f"/api/v1/admin/clients/{client_id}/invoices/range/{note_id}/pdf?inline=true",
        token=admin_token,
    )
    ensure(res.status == 200 and isinstance(res.data, (bytes, bytearray)), f"download invoice pdf failed: {res.status}")
    content = bytes(res.data)
    ensure(content.startswith(b"%PDF"), "downloaded payload is not a PDF")
    return content


def extract_sequence(invoice_number: str) -> int:
    match = re.search(r"(\d+)$", invoice_number)
    ensure(match is not None, f"cannot extract trailing sequence from invoice number: {invoice_number}")
    return int(match.group(1))


def is_legacy_suffix(invoice_number: str) -> bool:
    return re.search(r"-(PA|PAS)$", invoice_number) is not None


def at_utc(day: date, hour: int) -> datetime:
    return datetime.combine(day, dt_time(hour=hour, minute=0, second=0, microsecond=0, tzinfo=UTC))


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


def main() -> None:
    started = time.time()
    ts = int(started)

    admin_email = f"smoke.billing.admin.{ts}@example.com"
    client_email = f"smoke.billing.client.{ts}@example.com"

    step("health")
    wait_for_health(timeout_seconds=60)

    step("register + login")
    register_user(admin_email, PASSWORD)
    register_user(client_email, PASSWORD)
    promote_user_role(admin_email, UserRole.ADMIN)
    admin_token = login(admin_email, PASSWORD)
    client_token = login(client_email, PASSWORD)
    client_id = user_id_from_email(client_email)

    step("load legal entities + initialize counters")
    legal_entities = list_legal_entities(admin_token)
    pa_entity = find_legal_entity_by_name(legal_entities, "PIANO ACADEMIE")
    pas_entity = find_legal_entity_by_name(legal_entities, "PIANO ACADEMIE SERVICES")
    pa_id = str(pa_entity["id"])
    pas_id = str(pas_entity["id"])
    pa_prefix = str(pa_entity.get("invoice_prefix") or "")
    pas_prefix = str(pas_entity.get("invoice_prefix") or "")
    ensure(pa_prefix.startswith("PA"), f"unexpected PA invoice prefix: {pa_prefix}")
    ensure(pas_prefix.startswith("PAS"), f"unexpected PAS invoice prefix: {pas_prefix}")

    pa_next_start = 5000 + (ts % 1000)
    pas_next_start = 9000 + (ts % 1000)
    ltd_next_start = 12000 + (ts % 1000)
    patch_legal_entity_counter(admin_token, pa_id, pa_next_start)
    patch_legal_entity_counter(admin_token, pas_id, pas_next_start)

    step("configure account marker for legacy app_settings")
    app_settings_marker = f"APP_SETTINGS_SHOULD_NOT_APPEAR_{ts}"
    put_account_marker(admin_token, app_settings_marker)

    step("create 3rd legal entity via DB (LTD)")
    ltd = create_ltd_legal_entity_in_db(ts, next_number=ltd_next_start)
    ltd_id = ltd["id"]
    ltd_prefix = ltd["invoice_prefix"]
    ltd_name = ltd["name"]
    ltd_siren = ltd["siren"]

    step("create activities + formula")
    credit_type_id = get_first_credit_type_id(admin_token)
    payment_methods_all = get_enabled_payment_methods(admin_token)
    offline_methods = [code for code in payment_methods_all if code in {"CASH", "BANK_TRANSFER", "CARD_TERMINAL"}]
    payment_methods = offline_methods[:1] if offline_methods else payment_methods_all[:1]
    ensure(len(payment_methods) > 0, "no usable payment method for smoke formula")

    activities = list_active_activities(admin_token)
    ensure(len(activities) >= 3, f"need at least 3 active activities, found {len(activities)}")
    pa_course_type_id = str(activities[0]["id"])
    pas_course_type_id = str(activities[1]["id"])
    ltd_course_type_id = str(activities[2]["id"])
    patch_activity_seller_legal_entity(admin_token, activity_id=pa_course_type_id, seller_legal_entity_id=pa_id)
    patch_activity_seller_legal_entity(admin_token, activity_id=pas_course_type_id, seller_legal_entity_id=pas_id)
    patch_activity_seller_legal_entity(admin_token, activity_id=ltd_course_type_id, seller_legal_entity_id=ltd_id)

    formula_id = create_pack_formula(
        admin_token,
        name=f"Smoke Multi Entity Formula {ts}",
        credit_type_id=credit_type_id,
        entitlement_course_type_ids=[pa_course_type_id, pas_course_type_id, ltd_course_type_id],
        payment_methods=payment_methods,
    )
    subscription_id = buy_plan_as_admin(admin_token, client_id=client_id, plan_id=formula_id)

    location_id, professor_id = get_online_location_and_professor()
    base_day = (datetime.now(UTC) + timedelta(days=9)).date()
    day1 = base_day
    day2 = base_day + timedelta(days=1)
    day3 = base_day + timedelta(days=2)
    day4 = base_day + timedelta(days=3)

    step("create sessions")
    pa_session_day1 = create_session_as_admin(
        admin_token,
        title=f"Smoke PA day1 {ts}",
        start_at=at_utc(day1, 14),
        course_type_id=pa_course_type_id,
        location_id=location_id,
        professor_id=professor_id,
    )
    pa_session_day2 = create_session_as_admin(
        admin_token,
        title=f"Smoke PA day2 {ts}",
        start_at=at_utc(day2, 14),
        course_type_id=pa_course_type_id,
        location_id=location_id,
        professor_id=professor_id,
    )
    pa_session_day3 = create_session_as_admin(
        admin_token,
        title=f"Smoke PA day3 {ts}",
        start_at=at_utc(day3, 13),
        course_type_id=pa_course_type_id,
        location_id=location_id,
        professor_id=professor_id,
    )
    pas_session_day3 = create_session_as_admin(
        admin_token,
        title=f"Smoke PAS day3 {ts}",
        start_at=at_utc(day3, 16),
        course_type_id=pas_course_type_id,
        location_id=location_id,
        professor_id=professor_id,
    )
    ltd_session_day4 = create_session_as_admin(
        admin_token,
        title=f"Smoke LTD day4 {ts}",
        start_at=at_utc(day4, 15),
        course_type_id=ltd_course_type_id,
        location_id=location_id,
        professor_id=professor_id,
    )

    step("check session snapshot_seller_legal_entity_id")
    ensure(
        session_snapshot_seller_legal_entity_id(pa_session_day1) == pa_id,
        "session snapshot seller legal entity mismatch for PA",
    )
    ensure(
        session_snapshot_seller_legal_entity_id(pas_session_day3) == pas_id,
        "session snapshot seller legal entity mismatch for PAS",
    )
    ensure(
        session_snapshot_seller_legal_entity_id(ltd_session_day4) == ltd_id,
        "session snapshot seller legal entity mismatch for LTD",
    )

    step("book sessions")
    _ = book_session(client_token, pa_session_day1, subscription_id)
    _ = book_session(client_token, pa_session_day2, subscription_id)
    _ = book_session(client_token, pa_session_day3, subscription_id)
    _ = book_session(client_token, pas_session_day3, subscription_id)
    _ = book_session(client_token, ltd_session_day4, subscription_id)

    step("test #1 - PA only invoice x2 sequential")
    inv_pa_1 = create_period_invoice(admin_token, client_id=client_id, day=day1)
    rel_pa_1 = inv_pa_1.get("related_invoices")
    ensure(isinstance(rel_pa_1, list) and len(rel_pa_1) == 1, f"expected 1 invoice for day1, got: {inv_pa_1}")
    pa_num_1 = str(rel_pa_1[0].get("invoice_number") or "")
    ensure(pa_num_1.startswith(pa_prefix), f"PA invoice number should start with '{pa_prefix}': {pa_num_1}")
    pa_seq_1 = extract_sequence(pa_num_1)
    ensure(pa_seq_1 == pa_next_start, f"PA first sequence mismatch: expected {pa_next_start}, got {pa_seq_1}")

    inv_pa_2 = create_period_invoice(admin_token, client_id=client_id, day=day2)
    rel_pa_2 = inv_pa_2.get("related_invoices")
    ensure(isinstance(rel_pa_2, list) and len(rel_pa_2) == 1, f"expected 1 invoice for day2, got: {inv_pa_2}")
    pa_num_2 = str(rel_pa_2[0].get("invoice_number") or "")
    ensure(pa_num_2.startswith(pa_prefix), f"PA second invoice number should start with '{pa_prefix}': {pa_num_2}")
    pa_seq_2 = extract_sequence(pa_num_2)
    ensure(pa_seq_2 == pa_seq_1 + 1, f"PA sequence should increment by 1: {pa_seq_1} -> {pa_seq_2}")

    step("test #2 - mixed PA + PAS split")
    inv_split = create_period_invoice(admin_token, client_id=client_id, day=day3)
    split_refs = inv_split.get("related_invoices")
    ensure(isinstance(split_refs, list) and len(split_refs) == 2, f"expected 2 split invoices, got: {inv_split}")

    split_numbers = [str(ref.get("invoice_number") or "") for ref in split_refs]
    ensure(all(not is_legacy_suffix(num) for num in split_numbers), f"legacy suffix detected in split numbers: {split_numbers}")

    pa_split_ref = next((ref for ref in split_refs if str(ref.get("seller_legal_entity_id") or "") == pa_id), None)
    pas_split_ref = next((ref for ref in split_refs if str(ref.get("seller_legal_entity_id") or "") == pas_id), None)
    ensure(pa_split_ref is not None, f"PA split invoice missing: {split_refs}")
    ensure(pas_split_ref is not None, f"PAS split invoice missing: {split_refs}")

    pa_split_num = str(pa_split_ref.get("invoice_number") or "")
    pas_split_num = str(pas_split_ref.get("invoice_number") or "")
    ensure(pa_split_num.startswith(pa_prefix), f"split PA invoice should start with '{pa_prefix}': {pa_split_num}")
    ensure(pas_split_num.startswith(pas_prefix), f"split PAS invoice should start with '{pas_prefix}': {pas_split_num}")
    ensure(extract_sequence(pa_split_num) == pa_seq_2 + 1, "PA split sequence should continue PA sequence")
    ensure(extract_sequence(pas_split_num) == pas_next_start, "PAS split sequence should use PAS own counter")

    step("test #4 - PDF uses legal_entities (not app_settings)")
    pa_note_id = str(inv_pa_1.get("note_id") or "")
    ensure(pa_note_id, "missing PA note_id")
    pa_pdf = download_invoice_pdf(admin_token, client_id=client_id, note_id=pa_note_id)
    pa_pdf_text = pa_pdf.decode("latin-1", errors="ignore")
    ensure(str(pa_entity.get("name") or "") in pa_pdf_text, "PA PDF should contain legal entity name from DB")
    ensure(app_settings_marker not in pa_pdf_text, "PA PDF should not use account app_settings marker")

    step("test #5 - 3rd entity LTD invoice + PDF identity")
    inv_ltd = create_period_invoice(admin_token, client_id=client_id, day=day4)
    ltd_refs = inv_ltd.get("related_invoices")
    ensure(isinstance(ltd_refs, list) and len(ltd_refs) == 1, f"expected 1 LTD invoice, got: {inv_ltd}")
    ltd_ref = ltd_refs[0]
    ensure(str(ltd_ref.get("seller_legal_entity_id") or "") == ltd_id, f"LTD seller id mismatch: {ltd_ref}")
    ltd_num = str(ltd_ref.get("invoice_number") or "")
    ensure(ltd_num.startswith(ltd_prefix), f"LTD invoice number should start with '{ltd_prefix}': {ltd_num}")
    ensure(extract_sequence(ltd_num) == ltd_next_start, "LTD sequence should use LTD own counter")

    ltd_note_id = str(inv_ltd.get("note_id") or "")
    ensure(ltd_note_id, "missing LTD note_id")
    ltd_pdf = download_invoice_pdf(admin_token, client_id=client_id, note_id=ltd_note_id)
    ltd_pdf_text = ltd_pdf.decode("latin-1", errors="ignore")
    ensure(ltd_name in ltd_pdf_text, "LTD PDF should contain LTD legal entity name")
    ensure(ltd_siren in ltd_pdf_text, "LTD PDF should contain LTD legal entity siren")
    ensure(app_settings_marker not in ltd_pdf_text, "LTD PDF should not use account app_settings marker")

    duration = round(time.time() - started, 2)
    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "billing_entities_v1",
                "duration_seconds": duration,
                "checks": {
                    "case_1_pa_single_and_sequential": True,
                    "case_2_pa_pas_split_independent": True,
                    "case_3_session_snapshot_copy": True,
                    "case_4_pdf_uses_legal_entities": True,
                    "case_5_third_entity_ltd_without_code_change": True,
                },
                "invoices": {
                    "pa_day1": pa_num_1,
                    "pa_day2": pa_num_2,
                    "split": split_numbers,
                    "ltd": ltd_num,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
