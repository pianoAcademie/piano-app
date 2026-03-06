from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Location, Professor
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
                return ApiResult(status=resp.status, data=json.loads(raw) if raw else None)
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = raw
            return ApiResult(status=exc.code, data=parsed)


api = ApiClient(BASE_URL)


def step(message: str) -> None:
    print(f"[SMOKE-SUBSTITUTE] {message}", flush=True)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def register_user(email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Smoke",
        "last_name": "Substitute",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": "Europe/Paris",
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


def ensure_professor_profile(*, email: str, first_name: str, last_name: str) -> str:
    with SessionLocal() as db:
        row = db.scalar(select(Professor).where(Professor.email == email))
        if row is None:
            row = Professor(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_coach=True,
                active=True,
                payout_currency="EUR",
                teacher_invoice_counter=5000,
                teacher_is_vat_applicable=False,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return str(row.id)


def get_online_location_id() -> str:
    with SessionLocal() as db:
        row = db.scalar(select(Location).where(Location.code == "ONLINE"))
        ensure(row is not None, "ONLINE location not found")
        return str(row.id)


def get_first_credit_type_id(admin_token: str) -> str:
    res = api.call("GET", "/api/v1/admin/credit-types", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list) and len(res.data) > 0, f"credit types failed: {res.status} {res.data}")
    first = res.data[0] if isinstance(res.data[0], dict) else {}
    credit_type_id = first.get("id")
    ensure(isinstance(credit_type_id, str), f"invalid credit type payload: {res.data}")
    return credit_type_id


def get_pa_legal_entity_id(admin_token: str) -> str:
    res = api.call("GET", "/api/v1/admin/legal-entities?include_inactive=true", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, list), f"legal entities failed: {res.status} {res.data}")
    for row in res.data:
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").strip().casefold() == "piano academie":
            entity_id = row.get("id")
            ensure(isinstance(entity_id, str), f"invalid entity payload: {row}")
            return entity_id
    raise SmokeFailure("PIANO ACADEMIE legal entity not found")


def create_activity(
    admin_token: str,
    *,
    code: str,
    name: str,
    credit_type_id: str,
    legal_entity_id: str,
) -> str:
    payload = {
        "code": code,
        "name": name,
        "description": "Smoke substitute activity",
        "service_code": "SMOKE_SUBSTITUTE",
        "credit_type_id": credit_type_id,
        "seller_legal_entity_id": legal_entity_id,
        "payor_legal_entity_id": legal_entity_id,
        "duration_minutes": 60,
        "color_hex": "#94C973",
        "mode": "ANY",
        "default_capacity": 6,
        "default_hourly_rate": "42.00",
        "active": True,
    }
    res = api.call("POST", "/api/v1/admin/activities", payload, token=admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create activity failed: {res.status} {res.data}")
    activity_id = res.data.get("id")
    ensure(isinstance(activity_id, str), f"activity id missing: {res.data}")
    return activity_id


def ensure_activity_enabled_for_planning(admin_token: str, *, location_id: str, activity_id: str) -> None:
    res = api.call("GET", f"/api/v1/admin/plannings/{location_id}/activities", token=admin_token)
    ensure(res.status == 200 and isinstance(res.data, dict), f"get planning activities failed: {res.status} {res.data}")
    selected_ids = [str(value) for value in (res.data.get("selected_activity_ids") or []) if value]
    if activity_id not in selected_ids:
        selected_ids.append(activity_id)
    update_res = api.call(
        "PUT",
        f"/api/v1/admin/plannings/{location_id}/activities",
        {"activity_ids": selected_ids},
        token=admin_token,
    )
    ensure(update_res.status == 200, f"update planning activities failed: {update_res.status} {update_res.data}")


def create_session(
    admin_token: str,
    *,
    activity_id: str,
    location_id: str,
    professor_id: str,
    start_at_utc: datetime,
) -> str:
    payload = {
        "course_type_id": activity_id,
        "location_id": location_id,
        "professor_id": professor_id,
        "title": "Smoke substitute session",
        "description": "Smoke substitute",
        "start_at_utc": start_at_utc.isoformat(),
        "end_at_utc": (start_at_utc + timedelta(hours=1)).isoformat(),
        "capacity_max": 4,
        "auto_cancel_deadline_utc": (start_at_utc - timedelta(hours=4)).isoformat(),
        "zoom_link": "https://zoom.us/j/smoke-substitute",
    }
    res = api.call("POST", "/api/v1/admin/sessions", payload, token=admin_token)
    ensure(res.status == 201 and isinstance(res.data, dict), f"create session failed: {res.status} {res.data}")
    session_id = res.data.get("id")
    ensure(isinstance(session_id, str), f"session id missing: {res.data}")
    return session_id


def set_substitute(admin_token: str, *, session_id: str, substitute_teacher_id: str) -> None:
    res = api.call(
        "PATCH",
        f"/api/v1/admin/sessions/{session_id}?apply_scope=ONE",
        {
            "substitute_teacher_id": substitute_teacher_id,
            "substitute_note": "Smoke replacement occurrence",
        },
        token=admin_token,
    )
    ensure(res.status == 200 and isinstance(res.data, dict), f"patch session substitute failed: {res.status} {res.data}")
    ensure(str(res.data.get("effective_teacher_id") or "") == substitute_teacher_id, f"effective teacher mismatch: {res.data}")
    ensure(str(res.data.get("substitute_teacher_id") or "") == substitute_teacher_id, f"substitute teacher mismatch: {res.data}")


def month_window(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, 0, 0, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, 0, 0, tzinfo=UTC)
    return start, end


def main() -> None:
    started = time.time()
    ts = int(started)

    step("health")
    health = api.call("GET", "/health")
    ensure(health.status == 200 and isinstance(health.data, dict) and health.data.get("ok") is True, "health failed")

    admin_email = f"smoke.sub.admin.{ts}@example.com"
    prof_a_email = f"smoke.sub.prof.a.{ts}@example.com"
    prof_b_email = f"smoke.sub.prof.b.{ts}@example.com"

    step("register + promote + login")
    register_user(admin_email, PASSWORD)
    promote_user_role(admin_email, UserRole.ADMIN)
    register_user(prof_a_email, PASSWORD)
    promote_user_role(prof_a_email, UserRole.PROF)
    register_user(prof_b_email, PASSWORD)
    promote_user_role(prof_b_email, UserRole.PROF)
    admin_token = login(admin_email, PASSWORD)
    prof_a_token = login(prof_a_email, PASSWORD)
    prof_b_token = login(prof_b_email, PASSWORD)

    professor_a_id = ensure_professor_profile(email=prof_a_email, first_name="Prof", last_name="A")
    professor_b_id = ensure_professor_profile(email=prof_b_email, first_name="Prof", last_name="B")
    location_id = get_online_location_id()
    credit_type_id = get_first_credit_type_id(admin_token)
    pa_entity_id = get_pa_legal_entity_id(admin_token)

    now = datetime.now(UTC)
    target_month = (now.month % 12) + 1
    target_year = now.year + (1 if target_month == 1 else 0)
    session_start = datetime(target_year, target_month, 15, 10, 0, tzinfo=UTC)

    step("create activity + session (teacher A)")
    activity_id = create_activity(
        admin_token,
        code=f"SMK_SUB_{ts}",
        name=f"Smoke Substitute {ts}",
        credit_type_id=credit_type_id,
        legal_entity_id=pa_entity_id,
    )
    ensure_activity_enabled_for_planning(admin_token, location_id=location_id, activity_id=activity_id)
    session_id = create_session(
        admin_token,
        activity_id=activity_id,
        location_id=location_id,
        professor_id=professor_a_id,
        start_at_utc=session_start,
    )

    step("set substitute teacher B on occurrence")
    set_substitute(admin_token, session_id=session_id, substitute_teacher_id=professor_b_id)

    step("verify planning payload for admin")
    admin_session = api.call("GET", f"/api/v1/admin/sessions/{session_id}", token=admin_token)
    ensure(admin_session.status == 200 and isinstance(admin_session.data, dict), f"admin session read failed: {admin_session.status} {admin_session.data}")
    ensure(str(admin_session.data.get("effective_teacher_id") or "") == professor_b_id, f"admin effective teacher mismatch: {admin_session.data}")

    start_window, end_window = month_window(target_year, target_month)
    from_iso = start_window.isoformat()
    to_iso = (end_window - timedelta(seconds=1)).isoformat()

    step("verify professor planning: A does not see, B sees")
    sessions_a = api.call(
        "GET",
        f"/api/v1/professors/me/sessions?from={from_iso}&to={to_iso}",
        token=prof_a_token,
    )
    sessions_b = api.call(
        "GET",
        f"/api/v1/professors/me/sessions?from={from_iso}&to={to_iso}",
        token=prof_b_token,
    )
    ensure(sessions_a.status == 200 and isinstance(sessions_a.data, list), f"prof A sessions failed: {sessions_a.status} {sessions_a.data}")
    ensure(sessions_b.status == 200 and isinstance(sessions_b.data, list), f"prof B sessions failed: {sessions_b.status} {sessions_b.data}")
    ids_a = {str(row.get("id")) for row in sessions_a.data if isinstance(row, dict)}
    ids_b = {str(row.get("id")) for row in sessions_b.data if isinstance(row, dict)}
    ensure(session_id not in ids_a, f"teacher A should not receive replaced session in planning: {sessions_a.data}")
    ensure(session_id in ids_b, f"teacher B should receive replaced session in planning: {sessions_b.data}")

    step("verify statements + invoicing: A none, B has one and can approve")
    statements_a = api.call("GET", f"/api/v1/teacher/statements?year={target_year}&month={target_month}", token=prof_a_token)
    statements_b = api.call("GET", f"/api/v1/teacher/statements?year={target_year}&month={target_month}", token=prof_b_token)
    ensure(statements_a.status == 200 and isinstance(statements_a.data, list), f"statements A failed: {statements_a.status} {statements_a.data}")
    ensure(statements_b.status == 200 and isinstance(statements_b.data, list), f"statements B failed: {statements_b.status} {statements_b.data}")
    ensure(len(statements_a.data) == 0, f"teacher A should have no statement for replaced session month: {statements_a.data}")
    ensure(len(statements_b.data) >= 1, f"teacher B should have statement for replaced session month: {statements_b.data}")

    approve_a = api.call("POST", f"/api/v1/teacher/statements/{target_year}/{target_month}/approve", token=prof_a_token)
    ensure(approve_a.status == 404, f"teacher A approval should be 404: {approve_a.status} {approve_a.data}")
    approve_b = api.call("POST", f"/api/v1/teacher/statements/{target_year}/{target_month}/approve", token=prof_b_token)
    ensure(approve_b.status == 200 and isinstance(approve_b.data, dict), f"teacher B approval failed: {approve_b.status} {approve_b.data}")
    generated = approve_b.data.get("generated_invoices")
    ensure(isinstance(generated, list) and len(generated) >= 1, f"teacher B generated invoices missing: {approve_b.data}")

    duration = round(time.time() - started, 2)
    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "substitute_teacher_v1",
                "duration_seconds": duration,
                "checks": {
                    "admin_payload_effective_teacher": True,
                    "planning_b_gets_session_a_not": True,
                    "statements_b_gets_session_a_not": True,
                    "approve_month_for_b": True,
                },
                "sample": {
                    "session_id": session_id,
                    "teacher_a_id": professor_a_id,
                    "teacher_b_id": professor_b_id,
                },
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)
