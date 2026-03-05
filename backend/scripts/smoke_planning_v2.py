from __future__ import annotations

import json
import time
from dataclasses import dataclass
import os
import sys
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from sqlalchemy import func, select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, Professor
from app.models.plan import Plan, PlanEntitlement, PlanKind
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"


@dataclass
class ApiResult:
    status: int
    data: object


class SmokeFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: object | None = None, token: str | None = None) -> ApiResult:
        headers: dict[str, str] = {}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
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


def register_user(email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Planning",
        "last_name": "Smoke",
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
    ensure(isinstance(token, str) and token, f"access token missing for {email}")
    return token


def main() -> None:
    ts = int(time.time())
    password = "Password123X"
    admin_email = f"smoke.plan.admin.{ts}@example.com"
    client_email = f"smoke.plan.client.{ts}@example.com"

    register_user(admin_email, password)
    register_user(client_email, password)

    with SessionLocal() as db:
        admin_user = db.scalar(select(User).where(User.email == admin_email))
        ensure(admin_user is not None, "admin user not found")
        admin_user.role = UserRole.ADMIN
        db.add(admin_user)

        location = db.scalar(select(Location).where(Location.active.is_(True)).order_by(Location.created_at.asc()))
        professor = db.scalar(select(Professor).where(Professor.active.is_(True)).order_by(Professor.created_at.asc()))
        entitlement = db.execute(
            select(Plan.id, CourseType.id)
            .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
            .join(CourseType, CourseType.id == PlanEntitlement.course_type_id)
            .where(Plan.kind == PlanKind.PACK, Plan.active.is_(True), CourseType.active.is_(True))
            .limit(1)
        ).first()

        ensure(location is not None, "no active location found")
        ensure(professor is not None, "no active professor found")
        ensure(entitlement is not None, "no active pack entitlement found")

        location_id = str(location.id)
        professor_id = str(professor.id)
        plan_id = str(entitlement.id)
        course_type_id = str(entitlement.id_1)

        db.commit()

    admin_token = login(admin_email, password)
    client_token = login(client_email, password)

    settings_get = api.call("GET", f"/api/v1/admin/plannings/{location_id}/settings", token=admin_token)
    ensure(settings_get.status == 200, f"GET planning settings failed: {settings_get.status} {settings_get.data}")

    settings_put = api.call(
        "PUT",
        f"/api/v1/admin/plannings/{location_id}/settings",
        {
            "description": "Smoke planning settings",
            "min_booking_notice_hours": 2,
            "max_booking_horizon_months": 9,
            "cancellation_deadline_hours": 3,
            "max_bookings_per_client": 4,
            "allow_negative_credits": False,
            "waitlist_capacity": 5,
            "auto_cancel_if_booked_less_than": 1,
            "auto_cancel_hours_before_start": 2,
            "is_private": False,
            "allow_force_booking": True,
            "allow_multi_booking": True,
            "notify_coach": True,
            "notify_admins": True,
            "hide_booking_count": False,
            "block_client_cancellation": False,
        },
        token=admin_token,
    )
    ensure(settings_put.status == 200, f"PUT planning settings failed: {settings_put.status} {settings_put.data}")

    start = datetime.now(UTC) + timedelta(hours=40)
    end = start + timedelta(hours=1)
    deadline = start - timedelta(hours=6)

    create_res = api.call(
        "POST",
        "/api/v1/admin/sessions",
        {
            "course_type_id": course_type_id,
            "location_id": location_id,
            "professor_id": professor_id,
            "title": f"Smoke planning recurring private {ts}",
            "description": "smoke planning",
            "start_at_utc": start.isoformat(),
            "end_at_utc": end.isoformat(),
            "capacity_max": 2,
            "auto_cancel_deadline_utc": deadline.isoformat(),
            "is_private": True,
            "recurrence": {"frequency": "WEEKLY", "until_date": (start.date() + timedelta(days=14)).isoformat()},
        },
        token=admin_token,
    )
    ensure(create_res.status == 201 and isinstance(create_res.data, dict), f"create recurring session failed: {create_res.status} {create_res.data}")
    ensure(create_res.data.get("is_private") is True, "created recurring session should be private")
    ensure(create_res.data.get("recurrence_rule") == "WEEKLY", "recurrence rule should be WEEKLY")

    session_id = str(create_res.data["id"])
    recurrence_group_id = create_res.data.get("recurrence_group_id")
    ensure(recurrence_group_id is not None, "recurrence_group_id missing")

    with SessionLocal() as db:
        rec_count = db.scalar(select(func.count(CourseSession.id)).where(CourseSession.recurrence_group_id == recurrence_group_id))
        ensure(int(rec_count or 0) == 3, f"expected 3 sessions in recurrence, got {rec_count}")

    from_q = quote(start.isoformat())
    to_q = quote((start + timedelta(days=20)).isoformat())
    catalog = api.call("GET", f"/api/v1/sessions?location_id={location_id}&from={from_q}&to={to_q}")
    ensure(catalog.status == 200 and isinstance(catalog.data, list), f"catalog fetch failed: {catalog.status} {catalog.data}")

    private_title = str(create_res.data.get("title"))
    ensure(all(item.get("title") != private_title for item in catalog.data), "private session should not appear in public catalog")

    purchase = api.call("POST", f"/api/v1/plans/{plan_id}/purchase", token=client_token)
    ensure(purchase.status == 201 and isinstance(purchase.data, dict), f"purchase failed: {purchase.status} {purchase.data}")

    private_book = api.call(
        "POST",
        f"/api/v1/sessions/{session_id}/book",
        {"client_plan_subscription_id": purchase.data["id"]},
        token=client_token,
    )
    ensure(private_book.status == 403, f"private booking should fail with 403: {private_book.status} {private_book.data}")

    print(
        json.dumps(
            {
                "ok": True,
                "checks": {
                    "planning_settings": True,
                    "recurrence": True,
                    "private_hidden_catalog": True,
                    "private_booking_blocked": True,
                },
                "session_id": session_id,
                "recurrence_group_id": recurrence_group_id,
            }
        )
    )


if __name__ == "__main__":
    main()
