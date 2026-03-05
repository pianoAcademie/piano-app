from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.catalog import Location, Professor
from app.models.plan import Plan, PlanEntitlement, PlanKind
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"
PASSWORD = "Password123X"


class SmokeFailure(RuntimeError):
    pass


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def call(method: str, path: str, payload: Any | None = None, token: str | None = None) -> tuple[int, Any]:
    headers: dict[str, str] = {}
    body = None

    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = raw
        return exc.code, parsed


def register_user(email: str) -> None:
    status, data = call(
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": PASSWORD,
            "first_name": "Series",
            "last_name": "Smoke",
            "address_line": "1 Rue Test",
            "phone": "+33100000000",
            "residence_country": "FR",
            "preferred_currency": "EUR",
            "timezone": "Europe/Paris",
        },
    )
    ensure(status == 201, f"register failed for {email}: {status} {data}")


def login(email: str) -> str:
    status, data = call("POST", "/api/v1/auth/login", {"email": email, "password": PASSWORD})
    ensure(status == 200 and isinstance(data, dict), f"login failed for {email}: {status} {data}")
    token = data.get("access_token")
    ensure(isinstance(token, str) and token, f"missing token for {email}")
    return token


def promote_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        user.role = UserRole.ADMIN
        db.add(user)
        db.commit()


def user_id_by_email(email: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        return str(user.id)


def catalog_ids() -> tuple[str, str, str, str]:
    with SessionLocal() as db:
        row = db.execute(
            select(Plan.id, PlanEntitlement.course_type_id)
            .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
            .where(Plan.kind == PlanKind.PACK, Plan.active.is_(True))
            .limit(1)
        ).first()
        ensure(row is not None, "no active pack plan found")

        location = db.scalar(select(Location).where(Location.code == "ONLINE"))
        professor = db.scalar(select(Professor).where(Professor.email == "prof.demo@piano-academie.local"))
        ensure(location is not None, "ONLINE location not found")
        ensure(professor is not None, "demo professor not found")

        return str(row.id), str(row.course_type_id), str(location.id), str(professor.id)


def create_series(
    admin_token: str,
    course_type_id: str,
    location_id: str,
    professor_id: str,
    title: str,
    start_at_utc: datetime,
) -> str:
    payload = {
        "course_type_id": course_type_id,
        "location_id": location_id,
        "professor_id": professor_id,
        "title": title,
        "description": "series scope smoke",
        "start_at_utc": start_at_utc.isoformat(),
        "end_at_utc": (start_at_utc + timedelta(hours=1)).isoformat(),
        "capacity_max": 3,
        "auto_cancel_deadline_utc": (start_at_utc - timedelta(hours=6)).isoformat(),
        "recurrence": {"frequency": "WEEKLY", "until_date": (start_at_utc.date() + timedelta(days=14)).isoformat()},
    }
    status, data = call("POST", "/api/v1/admin/sessions", payload, token=admin_token)
    ensure(status == 201 and isinstance(data, dict), f"series create failed: {status} {data}")
    recurrence_group_id = data.get("recurrence_group_id")
    ensure(isinstance(recurrence_group_id, str), f"missing recurrence_group_id: {data}")
    return recurrence_group_id


def list_series_sessions(admin_token: str, recurrence_group_id: str) -> list[dict[str, Any]]:
    status, data = call("GET", "/api/v1/admin/sessions", token=admin_token)
    ensure(status == 200 and isinstance(data, list), f"admin list sessions failed: {status} {data}")
    rows = [row for row in data if row.get("recurrence_group_id") == recurrence_group_id]
    rows.sort(key=lambda row: row["start_at_utc"])
    return rows


def list_session_bookings(admin_token: str, session_id: str) -> list[dict[str, Any]]:
    status, data = call("GET", f"/api/v1/admin/sessions/{session_id}/bookings", token=admin_token)
    ensure(status == 200 and isinstance(data, list), f"list bookings failed: {status} {data}")
    return data


def main() -> None:
    ts = int(time.time())

    admin_email = f"series.admin.{ts}@example.com"
    client_email = f"series.client.{ts}@example.com"

    register_user(admin_email)
    register_user(client_email)
    promote_admin(admin_email)

    admin_token = login(admin_email)
    client_token = login(client_email)
    client_id = user_id_by_email(client_email)

    plan_id, course_type_id, location_id, professor_id = catalog_ids()

    start_at = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=8, hours=2)
    recurrence_group_id = create_series(
        admin_token,
        course_type_id,
        location_id,
        professor_id,
        title=f"Scope Series {ts}",
        start_at_utc=start_at,
    )

    series = list_series_sessions(admin_token, recurrence_group_id)
    ensure(len(series) == 3, f"expected 3 sessions in series, got {len(series)}")

    anchor = series[0]
    old_starts = [datetime.fromisoformat(row["start_at_utc"].replace("Z", "+00:00")) for row in series]

    anchor_new_start = old_starts[0] + timedelta(hours=1)
    anchor_new_end = datetime.fromisoformat(anchor["end_at_utc"].replace("Z", "+00:00")) + timedelta(hours=1)

    status, _ = call(
        "PATCH",
        f"/api/v1/admin/sessions/{anchor['id']}?apply_scope=SERIES_FUTURE",
        {
            "start_at_utc": anchor_new_start.isoformat(),
            "end_at_utc": anchor_new_end.isoformat(),
            "title": f"Scope Series Shifted {ts}",
        },
        token=admin_token,
    )
    ensure(status == 200, f"series patch failed: {status}")

    shifted = list_series_sessions(admin_token, recurrence_group_id)
    ensure(len(shifted) == 3, f"expected 3 sessions after shift, got {len(shifted)}")

    shifted_starts = [datetime.fromisoformat(row["start_at_utc"].replace("Z", "+00:00")) for row in shifted]
    for idx in range(3):
        ensure(shifted_starts[idx] - old_starts[idx] == timedelta(hours=1), f"session {idx} not shifted by +1h")

    status, add_scope = call(
        "POST",
        f"/api/v1/admin/sessions/{shifted[0]['id']}/bookings?scope=SERIES_FUTURE",
        {"client_id": client_id},
        token=admin_token,
    )
    ensure(status == 200 and isinstance(add_scope, dict), f"admin booking scope failed: {status} {add_scope}")
    ensure(add_scope.get("processed_count") == 3, f"scope add should process 3 sessions: {add_scope}")

    bookings_per_session = [list_session_bookings(admin_token, row["id"]) for row in shifted]
    ensure(all(len(rows) == 1 for rows in bookings_per_session), "scope add should create one booking on each future session")
    anchor_booking_id = bookings_per_session[0][0]["id"]

    status, _ = call(
        "DELETE",
        f"/api/v1/admin/sessions/{shifted[0]['id']}/bookings/{anchor_booking_id}?scope=SERIES_FUTURE",
        token=admin_token,
    )
    ensure(status == 204, f"admin booking removal with scope failed: {status}")

    post_remove = [list_session_bookings(admin_token, row["id"]) for row in shifted]
    ensure(all(len(rows) == 0 for rows in post_remove), "scope remove should cancel bookings on whole future series")

    status, purchased = call("POST", f"/api/v1/plans/{plan_id}/purchase", token=client_token)
    ensure(status == 201 and isinstance(purchased, dict), f"client purchase failed: {status} {purchased}")

    status, booking = call(
        "POST",
        f"/api/v1/sessions/{shifted[0]['id']}/book",
        {"client_plan_subscription_id": purchased["id"]},
        token=client_token,
    )
    ensure(status == 201 and isinstance(booking, dict) and booking.get("status") == "BOOKED", f"booking failed: {status} {booking}")

    status, _ = call("DELETE", f"/api/v1/admin/sessions/{shifted[0]['id']}?apply_scope=SERIES_ALL", token=admin_token)
    ensure(status == 409, f"delete guard should return 409, got {status}")

    clean_group_id = create_series(
        admin_token,
        course_type_id,
        location_id,
        professor_id,
        title=f"Delete Series {ts}",
        start_at_utc=start_at + timedelta(days=2),
    )
    clean_series = list_series_sessions(admin_token, clean_group_id)
    ensure(len(clean_series) == 3, f"expected 3 sessions in clean series, got {len(clean_series)}")

    status, _ = call("DELETE", f"/api/v1/admin/sessions/{clean_series[0]['id']}?apply_scope=SERIES_ALL", token=admin_token)
    ensure(status == 204, f"clean series delete should return 204, got {status}")

    remaining = list_series_sessions(admin_token, clean_group_id)
    ensure(len(remaining) == 0, f"clean series should be removed, got {len(remaining)} sessions")

    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "admin_series_scope",
                "checks": {
                    "series_shift_future": True,
                    "booking_scope_series_future": True,
                    "delete_guard_with_booking": True,
                    "delete_clean_series": True,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
