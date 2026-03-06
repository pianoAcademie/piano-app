from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, Location, Professor
from app.models.ops import LegalEntity
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

    def call(self, method: str, path: str, payload: Any | None = None, token: str | None = None) -> ApiResult:
        headers: dict[str, str] = {}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                data = json.loads(raw) if raw else None
                return ApiResult(status=resp.status, data=data)
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                data = json.loads(raw) if raw else None
            except Exception:
                data = raw
            return ApiResult(status=exc.code, data=data)


api = ApiClient(BASE_URL)


def step(message: str) -> None:
    print(f"[SMOKE-TEACHER] {message}", flush=True)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def register_user(email: str, password: str, *, timezone: str = "Europe/Paris") -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Smoke",
        "last_name": "Teacher",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": timezone,
    }
    res = api.call("POST", "/api/v1/auth/register", payload)
    ensure(res.status == 201, f"register failed for {email}: {res.status} {res.data}")


def login(email: str, password: str) -> str:
    res = api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(res.status == 200 and isinstance(res.data, dict), f"login failed for {email}: {res.status} {res.data}")
    token = res.data.get("access_token")
    ensure(isinstance(token, str) and token, f"missing token for {email}")
    return token


def promote_user_role(email: str, role: UserRole) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        user.role = role
        user.is_active = True
        db.add(user)
        db.commit()


def get_first_credit_type_id(admin_token: str) -> str:
    res = api.call("GET", "/api/v1/admin/credit-types", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list) and len(res.data) > 0, f"credit types failed: {res.status} {res.data}")
    first = res.data[0]
    ensure(isinstance(first, dict) and isinstance(first.get("id"), str), f"invalid credit type payload: {first}")
    return first["id"]


def list_legal_entities(admin_token: str) -> list[dict[str, Any]]:
    res = api.call("GET", "/api/v1/admin/legal-entities?include_inactive=true", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list), f"legal entities failed: {res.status} {res.data}")
    return [row for row in res.data if isinstance(row, dict)]


def find_entity(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    target = name.strip().casefold()
    for row in rows:
        if str(row.get("name") or "").strip().casefold() == target:
            return row
    raise SmokeFailure(f"entity not found: {name}")


def get_online_location_id() -> str:
    with SessionLocal() as db:
        location = db.scalar(select(Location).where(Location.code == "ONLINE"))
        ensure(location is not None, "ONLINE location not found")
        return str(location.id)


def ensure_professor_profile(*, email: str, first_name: str, last_name: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found for professor profile: {email}")
        professor = db.scalar(select(Professor).where(Professor.email == email))
        if professor is None:
            professor = Professor(
                first_name=first_name,
                last_name=last_name,
                email=email,
                active=True,
                is_coach=True,
                payout_currency="EUR",
            )
            db.add(professor)
            db.commit()
            db.refresh(professor)
        return str(professor.id)


def create_activity(
    admin_token: str,
    *,
    code: str,
    name: str,
    credit_type_id: str,
    seller_legal_entity_id: str,
    payor_legal_entity_id: str,
    default_hourly_rate: Decimal,
) -> str:
    payload = {
        "code": code,
        "name": name,
        "description": "Smoke teacher invoice activity",
        "service_code": "ACTIVITY",
        "seller_legal_entity_id": seller_legal_entity_id,
        "payor_legal_entity_id": payor_legal_entity_id,
        "credit_type_id": credit_type_id,
        "duration_minutes": 60,
        "color_hex": "#94C973",
        "mode": "ANY",
        "default_capacity": 8,
        "default_hourly_rate": f"{default_hourly_rate}",
        "active": True,
    }
    res = api.call("POST", "/api/v1/admin/activities", payload, admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create activity failed: {res.status} {res.data}")
    activity_id = res.data.get("id")
    ensure(isinstance(activity_id, str), f"missing activity id: {res.data}")
    return activity_id


def ensure_activity_enabled_for_planning(admin_token: str, *, location_id: str, activity_id: str) -> None:
    res = api.call("GET", f"/api/v1/admin/plannings/{location_id}/activities", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, dict), f"get planning activities failed: {res.status} {res.data}")
    selected = res.data.get("selected_activity_ids")
    ensure(isinstance(selected, list), f"invalid planning activities payload: {res.data}")
    merged_ids: list[str] = []
    seen: set[str] = set()
    for value in [*selected, activity_id]:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged_ids.append(item)
    update_res = api.call(
        "PUT",
        f"/api/v1/admin/plannings/{location_id}/activities",
        {"activity_ids": merged_ids},
        admin_token,
    )
    ensure(
        update_res.status == 200 and isinstance(update_res.data, dict),
        f"update planning activities failed: {update_res.status} {update_res.data}",
    )


def create_session(
    admin_token: str,
    *,
    title: str,
    start_at_utc: datetime,
    activity_id: str,
    location_id: str,
    professor_id: str,
) -> str:
    payload = {
        "course_type_id": activity_id,
        "location_id": location_id,
        "professor_id": professor_id,
        "title": title,
        "description": "Smoke teacher invoicing",
        "start_at_utc": start_at_utc.isoformat(),
        "end_at_utc": (start_at_utc + timedelta(hours=1)).isoformat(),
        "capacity_max": 8,
        "auto_cancel_deadline_utc": (start_at_utc - timedelta(hours=4)).isoformat(),
        "zoom_link": "https://zoom.us/j/smoke-teacher",
    }
    res = api.call("POST", "/api/v1/admin/sessions", payload, admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create session failed: {res.status} {res.data}")
    session_id = res.data.get("id")
    ensure(isinstance(session_id, str), f"missing session id: {res.data}")
    return session_id


def set_professor_billing_fields(
    professor_id: str,
    *,
    counter: int,
    vat_applicable: bool,
    vat_rate: Decimal | None,
    siret: str | None,
    iban: str,
) -> None:
    with SessionLocal() as db:
        professor = db.scalar(select(Professor).where(Professor.id == professor_id))
        ensure(professor is not None, "professor not found for billing fields")
        professor.teacher_invoice_counter = counter
        professor.teacher_is_vat_applicable = vat_applicable
        professor.teacher_vat_rate = vat_rate
        professor.teacher_siret = siret
        professor.teacher_iban = iban
        professor.teacher_company_name = "Smoke Teacher EI"
        professor.teacher_company_address = "1 rue Facture, 75001 Paris"
        db.add(professor)
        db.commit()


def create_booked_attendance(session_id: str, *, unique_email: str) -> None:
    with SessionLocal() as db:
        user = User(
            email=unique_email,
            hashed_password="x",
            role=UserRole.CLIENT,
            first_name="Pending",
            last_name="Attendance",
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            Booking(
                session_id=session_id,
                user_id=user.id,
                status=BookingStatus.BOOKED,
            )
        )
        db.commit()


def mark_all_attendance_done(session_id: str) -> None:
    with SessionLocal() as db:
        bookings = db.scalars(select(Booking).where(Booking.session_id == session_id)).all()
        for booking in bookings:
            booking.status = BookingStatus.ATTENDED
            db.add(booking)
        db.commit()


def approve_month(prof_token: str, *, year: int, month: int) -> ApiResult:
    return api.call("POST", f"/api/v1/teacher/statements/{year}/{month}/approve", token=prof_token)


def parse_counter(invoice_number: str) -> int:
    try:
        return int(invoice_number.rsplit("-", 1)[1])
    except Exception as exc:
        raise SmokeFailure(f"invalid teacher invoice number format: {invoice_number}") from exc


def add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + offset
    return idx // 12, (idx % 12) + 1


def fixed_start(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=UTC)


def main() -> None:
    started = time.time()
    ts = int(started)

    step("health")
    health = api.call("GET", "/health")
    ensure(health.status == 200 and isinstance(health.data, dict) and health.data.get("ok") is True, "health failed")

    admin_email = f"smoke.teacher.admin.{ts}@example.com"
    prof_email = f"smoke.teacher.prof.{ts}@example.com"

    step("register + login")
    register_user(admin_email, PASSWORD)
    promote_user_role(admin_email, UserRole.ADMIN)
    register_user(prof_email, PASSWORD)
    promote_user_role(prof_email, UserRole.PROF)
    admin_token = login(admin_email, PASSWORD)
    prof_token = login(prof_email, PASSWORD)

    location_id = get_online_location_id()
    professor_id = ensure_professor_profile(email=prof_email, first_name="Smoke", last_name="Teacher")
    credit_type_id = get_first_credit_type_id(admin_token)
    entities = list_legal_entities(admin_token)
    pa = find_entity(entities, "PIANO ACADEMIE")
    pas = find_entity(entities, "PIANO ACADEMIE SERVICES")

    now = datetime.now(UTC)
    y1, m1 = now.year, now.month
    y2, m2 = add_months(y1, m1, 1)
    if now.day > 1:
        y3, m3 = y1, m1
        case3_day = now.day - 1
    else:
        y3, m3 = add_months(y1, m1, -1)
        case3_day = 1
    counter_start = 9000

    step("prepare professor billing profile (VAT off)")
    set_professor_billing_fields(
        professor_id,
        counter=counter_start,
        vat_applicable=False,
        vat_rate=None,
        siret=None,
        iban="FR7612345678901234567890123",
    )

    step("case1: one-entity month")
    pa_activity_m1 = create_activity(
        admin_token,
        code=f"SMK_TEACHER_PA_{ts}",
        name=f"Smoke Teacher PA {ts}",
        credit_type_id=credit_type_id,
        seller_legal_entity_id=str(pa["id"]),
        payor_legal_entity_id=str(pa["id"]),
        default_hourly_rate=Decimal("40.00"),
    )
    ensure_activity_enabled_for_planning(admin_token, location_id=location_id, activity_id=pa_activity_m1)
    create_session(
        admin_token,
        title=f"Teacher PA m1 {ts}",
        start_at_utc=fixed_start(y1, m1, 10, 10),
        activity_id=pa_activity_m1,
        location_id=location_id,
        professor_id=professor_id,
    )
    approve_m1 = approve_month(prof_token, year=y1, month=m1)
    ensure(approve_m1.status == 200 and isinstance(approve_m1.data, dict), f"approve m1 failed: {approve_m1.status} {approve_m1.data}")
    generated_m1 = approve_m1.data.get("generated_invoices", [])
    ensure(isinstance(generated_m1, list) and len(generated_m1) == 1, f"m1 expected 1 invoice: {approve_m1.data}")
    inv1 = generated_m1[0]
    inv1_number = str(inv1.get("invoice_number") or "")
    ensure(parse_counter(inv1_number) == counter_start, f"m1 counter mismatch: {inv1_number}")
    ensure(str(inv1.get("totals_vat")) in {"0.00", "0"}, f"m1 VAT should be 0: {inv1}")
    ensure(str(inv1.get("totals_ttc")) == str(inv1.get("totals_ht")), f"m1 TTC should equal HT when VAT off: {inv1}")

    step("case2: two-entity month + VAT on + missing SIRET display")
    set_professor_billing_fields(
        professor_id,
        counter=counter_start + 1,
        vat_applicable=True,
        vat_rate=Decimal("20.00"),
        siret=None,
        iban="FR7612345678901234567890123",
    )
    pa_activity_m2 = create_activity(
        admin_token,
        code=f"SMK_TEACHER_PA2_{ts}",
        name=f"Smoke Teacher PA2 {ts}",
        credit_type_id=credit_type_id,
        seller_legal_entity_id=str(pa["id"]),
        payor_legal_entity_id=str(pa["id"]),
        default_hourly_rate=Decimal("45.00"),
    )
    pas_activity_m2 = create_activity(
        admin_token,
        code=f"SMK_TEACHER_PAS_{ts}",
        name=f"Smoke Teacher PAS {ts}",
        credit_type_id=credit_type_id,
        seller_legal_entity_id=str(pas["id"]),
        payor_legal_entity_id=str(pas["id"]),
        default_hourly_rate=Decimal("50.00"),
    )
    ensure_activity_enabled_for_planning(admin_token, location_id=location_id, activity_id=pa_activity_m2)
    ensure_activity_enabled_for_planning(admin_token, location_id=location_id, activity_id=pas_activity_m2)
    create_session(
        admin_token,
        title=f"Teacher PA m2 {ts}",
        start_at_utc=fixed_start(y2, m2, 11, 10),
        activity_id=pa_activity_m2,
        location_id=location_id,
        professor_id=professor_id,
    )
    create_session(
        admin_token,
        title=f"Teacher PAS m2 {ts}",
        start_at_utc=fixed_start(y2, m2, 12, 10),
        activity_id=pas_activity_m2,
        location_id=location_id,
        professor_id=professor_id,
    )
    approve_m2 = approve_month(prof_token, year=y2, month=m2)
    ensure(approve_m2.status == 200 and isinstance(approve_m2.data, dict), f"approve m2 failed: {approve_m2.status} {approve_m2.data}")
    generated_m2 = approve_m2.data.get("generated_invoices", [])
    ensure(isinstance(generated_m2, list) and len(generated_m2) == 2, f"m2 expected 2 invoices: {approve_m2.data}")
    counters_m2 = sorted(parse_counter(str(row.get("invoice_number") or "")) for row in generated_m2 if isinstance(row, dict))
    ensure(counters_m2 == [counter_start + 1, counter_start + 2], f"m2 counters mismatch: {generated_m2}")
    payor_ids_m2 = {str(row.get("payor_legal_entity_id")) for row in generated_m2 if isinstance(row, dict)}
    ensure(len(payor_ids_m2) == 2, f"m2 should have 2 different payors: {generated_m2}")
    for row in generated_m2:
        ensure(str(row.get("teacher_siret_display")) == "en cours d'immatriculation", f"siret display mismatch: {row}")
        invoice_date = date.fromisoformat(str(row.get("invoice_date")))
        due_date = date.fromisoformat(str(row.get("due_date")))
        ensure((due_date - invoice_date).days == 30, f"due date mismatch: {row}")
        ensure(Decimal(str(row.get("totals_vat") or "0")) > Decimal("0"), f"m2 VAT should be >0: {row}")

    invoice_for_actions = str(generated_m2[0].get("id"))

    step("case3: attendance incomplete blocks approval")
    pa_activity_m3 = create_activity(
        admin_token,
        code=f"SMK_TEACHER_PA3_{ts}",
        name=f"Smoke Teacher PA3 {ts}",
        credit_type_id=credit_type_id,
        seller_legal_entity_id=str(pa["id"]),
        payor_legal_entity_id=str(pa["id"]),
        default_hourly_rate=Decimal("45.00"),
    )
    ensure_activity_enabled_for_planning(admin_token, location_id=location_id, activity_id=pa_activity_m3)
    session_incomplete = create_session(
        admin_token,
        title=f"Teacher incomplete {ts}",
        start_at_utc=fixed_start(y3, m3, case3_day, 10),
        activity_id=pa_activity_m3,
        location_id=location_id,
        professor_id=professor_id,
    )
    create_booked_attendance(session_incomplete, unique_email=f"smoke.teacher.pending.{ts}@example.com")
    approve_m3 = approve_month(prof_token, year=y3, month=m3)
    ensure(approve_m3.status == 409, f"m3 approval should fail on attendance: {approve_m3.status} {approve_m3.data}")
    ensure(
        isinstance(approve_m3.data, dict)
        and isinstance(approve_m3.data.get("detail"), dict)
        and isinstance(approve_m3.data["detail"].get("missing_sessions"), list)
        and len(approve_m3.data["detail"]["missing_sessions"]) >= 1,
        f"m3 missing sessions not returned: {approve_m3.data}",
    )
    mark_all_attendance_done(session_incomplete)

    step("case7: cancel/uncancel")
    cancel_res = api.call("POST", f"/api/v1/teacher/invoices/{invoice_for_actions}/cancel", token=prof_token)
    ensure(cancel_res.status == 200 and isinstance(cancel_res.data, dict), f"cancel failed: {cancel_res.status} {cancel_res.data}")
    ensure(str(cancel_res.data.get("status")) == "cancelled", f"cancel status mismatch: {cancel_res.data}")
    ensure(cancel_res.data.get("cancelled_at") is not None, f"cancel timestamp missing: {cancel_res.data}")
    uncancel_res = api.call("POST", f"/api/v1/teacher/invoices/{invoice_for_actions}/uncancel", token=prof_token)
    ensure(uncancel_res.status == 200 and isinstance(uncancel_res.data, dict), f"uncancel failed: {uncancel_res.status} {uncancel_res.data}")
    ensure(str(uncancel_res.data.get("status")) == "generated", f"uncancel status mismatch: {uncancel_res.data}")
    ensure(uncancel_res.data.get("cancelled_at") in (None, ""), f"uncancel timestamp mismatch: {uncancel_res.data}")

    step("case8: send to accounting")
    send_res = api.call("POST", f"/api/v1/teacher/invoices/{invoice_for_actions}/send-to-accounting", token=prof_token)
    ensure(send_res.status == 200 and isinstance(send_res.data, dict), f"send-to-accounting failed: {send_res.status} {send_res.data}")
    ensure(str(send_res.data.get("status")) == "sent_to_accounting", f"status mismatch after send: {send_res.data}")
    ensure(send_res.data.get("sent_to_accounting_at") is not None, f"sent timestamp missing: {send_res.data}")

    duration = round(time.time() - started, 2)
    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "teacher_invoicing_v1",
                "duration_seconds": duration,
                "checks": {
                    "case_1_single_entity_one_invoice_counter_plus_1": True,
                    "case_2_two_entities_two_invoices_counter_plus_2": True,
                    "case_3_attendance_incomplete_blocked": True,
                    "case_4_vat_on_off_totals": True,
                    "case_5_missing_siret_display": True,
                    "case_6_due_date_plus_30_days": True,
                    "case_7_cancel_uncancel": True,
                    "case_8_send_to_accounting": True,
                },
                "samples": {
                    "invoice_m1": inv1_number,
                    "invoice_m2_ids": [row.get("invoice_number") for row in generated_m2],
                    "invoice_action_id": invoice_for_actions,
                },
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        raise
