from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.catalog import Location
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"


class SmokeFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: Any | None = None, token: str | None = None) -> tuple[int, Any]:
        headers: dict[str, str] = {}
        body = None

        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()

        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)

        try:
            with urlopen(req, timeout=20) as response:
                raw = response.read().decode()
                return response.status, json.loads(raw) if raw else None
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                payload = json.loads(raw) if raw else None
            except Exception:
                payload = raw
            return exc.code, payload


api = ApiClient(BASE_URL)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def register_user(email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Smoke",
        "last_name": "User",
        "address_line": "1 Rue Test",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": "Europe/Paris",
    }
    status, data = api.call("POST", "/api/v1/auth/register", payload)
    ensure(status == 201, f"register failed for {email}: {status} {data}")


def login(email: str, password: str) -> tuple[int, Any]:
    return api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})


def promote_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found: {email}")
        user.role = UserRole.ADMIN
        db.add(user)
        db.commit()


def main() -> None:
    ts = int(time.time())
    admin_email = f"collab.admin.{ts}@example.com"
    admin_password = "Password123X"

    register_user(admin_email, admin_password)
    promote_admin(admin_email)

    status, data = login(admin_email, admin_password)
    ensure(status == 200 and isinstance(data, dict), f"admin login failed: {status} {data}")
    admin_token = data["access_token"]

    with SessionLocal() as db:
        online = db.scalar(select(Location).where(Location.code == "ONLINE"))
        ensure(online is not None, "ONLINE location missing")

    status, course_types = api.call("GET", "/api/v1/course-types", token=admin_token)
    ensure(status == 200 and isinstance(course_types, list) and len(course_types) > 0, f"course types failed: {status}")

    collaborator_email = f"coach.{ts}@example.com"
    collaborator_password = "CoachInit123!"

    create_payload = {
        "email": collaborator_email,
        "password": collaborator_password,
        "first_name": "Ana",
        "last_name": "Coach",
        "phone": "+33600000000",
        "zoom_link": "https://zoom.us/j/coach",
        "spoken_languages": ["Francais", "Anglais"],
        "payout_currency": "EUR",
        "is_coach": True,
        "is_admin": False,
        "permissions": {
            "can_view_planning": True,
            "can_edit_planning": False,
            "can_force_booking": False,
        },
    }

    status, created = api.call("POST", "/api/v1/admin/collaborators", create_payload, admin_token)
    ensure(status == 201 and isinstance(created, dict), f"create collaborator failed: {status} {created}")
    ensure(created["activation_email_sent"] is False, "activation email should not be sent on create")
    professor_id = created["professor"]["id"]

    status, _ = login(collaborator_email, collaborator_password)
    ensure(status == 403, f"inactive collaborator should not login: {status}")

    activate_password = "CoachActive123!"
    status, updated = api.call(
        "PATCH",
        f"/api/v1/admin/collaborators/{professor_id}",
        {
            "active": True,
            "password": activate_password,
        },
        admin_token,
    )
    ensure(status == 200 and isinstance(updated, dict), f"activate collaborator failed: {status} {updated}")
    ensure(updated["activation_email_sent"] is True, "activation email must be sent on activation")

    status, prof_login = login(collaborator_email, activate_password)
    ensure(status == 200 and isinstance(prof_login, dict), f"active collaborator login failed: {status} {prof_login}")
    prof_token = prof_login["access_token"]

    status, prof_me = api.call("GET", "/api/v1/professors/me", token=prof_token)
    ensure(status == 200 and isinstance(prof_me, dict), f"prof me failed: {status} {prof_me}")

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start_at = now + timedelta(days=3, hours=2)

    status, session_payload = api.call(
        "POST",
        "/api/v1/admin/sessions",
        {
            "course_type_id": course_types[0]["id"],
            "location_id": str(online.id),
            "professor_id": professor_id,
            "title": f"Session coach {ts}",
            "start_at_utc": start_at.isoformat(),
            "end_at_utc": (start_at + timedelta(hours=1)).isoformat(),
            "capacity_max": 4,
            "auto_cancel_deadline_utc": (start_at - timedelta(hours=1)).isoformat(),
        },
        admin_token,
    )
    ensure(status == 201, f"session create for collaborator failed: {status} {session_payload}")

    planning_query = urlencode({"from": now.isoformat(), "to": (now + timedelta(days=15)).isoformat()})

    status, prof_sessions = api.call(
        "GET",
        f"/api/v1/professors/me/sessions?{planning_query}",
        token=prof_token,
    )
    ensure(status == 200 and isinstance(prof_sessions, list) and len(prof_sessions) >= 1, f"prof sessions failed: {status} {prof_sessions}")

    status, _ = api.call(
        "PUT",
        f"/api/v1/admin/collaborators/{professor_id}/permissions",
        {
            "can_view_planning": False,
            "can_edit_planning": False,
            "can_force_booking": False,
        },
        admin_token,
    )
    ensure(status == 200, f"permissions update failed: {status}")

    status, _ = api.call(
        "GET",
        f"/api/v1/professors/me/sessions?{planning_query}",
        token=prof_token,
    )
    ensure(status == 403, f"planning should be forbidden after permission revoke: {status}")

    status, _ = api.call(
        "PATCH",
        f"/api/v1/admin/collaborators/{professor_id}",
        {"active": False},
        admin_token,
    )
    ensure(status == 200, f"deactivate collaborator failed: {status}")

    status, _ = login(collaborator_email, activate_password)
    ensure(status == 403, f"deactivated collaborator should not login: {status}")

    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "collaborators_v1",
                "checks": {
                    "create_no_email": True,
                    "activation_email_on_activate": True,
                    "prof_login_when_active": True,
                    "permission_gate_planning": True,
                    "deactivation_blocks_login": True,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
