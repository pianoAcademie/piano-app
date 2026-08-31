from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, Location, Professor
from app.models.ops import AppSetting, EmailReminder
from app.models.plan import Plan, PlanEntitlement, PlanKind
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


def step(message: str) -> None:
    print(f"[SMOKE] {message}", flush=True)


def wait_backend_ready(timeout_seconds: int = 45, interval_seconds: float = 1.5) -> None:
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
        except Exception as exc:  # pragma: no cover - defensive for smoke runtime
            last_error = str(exc)
        time.sleep(interval_seconds)
    raise SmokeFailure(f"backend not ready after {timeout_seconds}s: {last_error}")


def register_user(email: str, password: str, *, timezone: str = "Europe/Paris") -> None:
    payload = {
        "email": email,
        "password": password,
        "first_name": "Smoke",
        "last_name": "User",
        "address_line": "1 Rue Test",
        "postal_code": "75016",
        "city": "Paris",
        "address_country": "FR",
        "phone": "+33100000000",
        "residence_country": "FR",
        "preferred_currency": "EUR",
        "timezone": timezone,
    }
    res = api.call("POST", "/api/v1/auth/register", payload)
    ensure(res.status == 201, f"register failed for {email}: {res.status} {res.data}")


def promote_user_role(email: str, role: UserRole) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, f"user not found for role promotion: {email}")
        user.role = role
        db.add(user)
        db.commit()


def login(email: str, password: str) -> str:
    res = api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(res.status == 200, f"login failed for {email}: {res.status} {res.data}")
    token = res.data.get("access_token") if isinstance(res.data, dict) else None
    ensure(isinstance(token, str) and token, f"missing access token for {email}")
    return token


def get_pack_plan_and_course_type() -> tuple[str, str]:
    with SessionLocal() as db:
        row = db.execute(
            select(Plan.id, PlanEntitlement.course_type_id)
            .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
            .where(Plan.kind == PlanKind.PACK, Plan.active.is_(True), Plan.is_private.is_(False))
            .limit(1)
        ).first()
        ensure(row is not None, "no active PACK plan entitlement found")
        return str(row.id), str(row.course_type_id)


def get_subscription_plan_purchase() -> tuple[str, str | None]:
    with SessionLocal() as db:
        plan = db.scalar(
            select(Plan)
            .where(Plan.kind == PlanKind.SUBSCRIPTION, Plan.active.is_(True))
            .limit(1)
        )
        ensure(plan is not None, "no active SUBSCRIPTION plan found")
        methods = {
            str(value).strip().upper()
            for value in (plan.payment_methods_json or [])
            if str(value).strip()
        }
        compatible_method = "CARD_ONLINE" if "CARD_ONLINE" in methods else "SEPA_DEBIT" if "SEPA_DEBIT" in methods else None
        return str(plan.id), compatible_method


def get_private_plan_id() -> str | None:
    with SessionLocal() as db:
        row = db.scalar(
            select(Plan.id)
            .where(Plan.active.is_(True), Plan.is_private.is_(True))
            .limit(1)
        )
        return str(row) if row is not None else None


def get_online_location_and_professor() -> tuple[str, str, str]:
    with SessionLocal() as db:
        location = db.scalar(select(Location).where(Location.code == "ONLINE"))
        professor = db.scalar(select(Professor).where(Professor.email == "prof.demo@piano-academie.local"))
        ensure(location is not None, "ONLINE location not found")
        ensure(professor is not None, "demo professor not found")
        return str(location.id), str(professor.id), location.timezone


def force_local_hour(base_start_utc: datetime, *, timezone_name: str, hour: int = 15) -> datetime:
    tz = ZoneInfo(timezone_name)
    local_target = base_start_utc.astimezone(tz).replace(hour=hour, minute=0, second=0, microsecond=0)
    return local_target.astimezone(UTC)


def create_session_as_admin(
    admin_token: str,
    *,
    title: str,
    start_at: datetime,
    course_type_id: str,
    location_id: str,
    professor_id: str,
    capacity: int,
    deadline_hours_before: int = 6,
) -> str:
    payload = {
        "course_type_id": course_type_id,
        "location_id": location_id,
        "professor_id": professor_id,
        "title": title,
        "description": "Smoke test session",
        "start_at_utc": start_at.isoformat(),
        "end_at_utc": (start_at + timedelta(hours=1)).isoformat(),
        "capacity_max": capacity,
        "child_bookings_enabled": False,
        "adult_bookings_enabled": True,
        "adult_capacity_max": capacity,
        "auto_cancel_deadline_utc": (start_at - timedelta(hours=deadline_hours_before)).isoformat(),
        "zoom_link": "https://zoom.us/j/smoke-test",
    }
    res = api.call("POST", "/api/v1/admin/sessions", payload, admin_token)
    ensure(res.status == 201, f"admin create session failed: {res.status} {res.data}")
    session_id = res.data.get("id") if isinstance(res.data, dict) else None
    ensure(isinstance(session_id, str), "missing session id after admin create")
    return session_id


def buy_plan(token: str, plan_id: str) -> str:
    rejected = api.call("POST", f"/api/v1/plans/{plan_id}/purchase", token=token)
    ensure(rejected.status == 422, f"purchase without CGV must be rejected: {rejected.status}")
    res = api.call("POST", f"/api/v1/plans/{plan_id}/purchase", {"legal_terms_accepted": True}, token=token)
    ensure(res.status == 201, f"purchase plan failed: {res.status} {res.data}")
    sub_id = res.data.get("id") if isinstance(res.data, dict) else None
    ensure(isinstance(sub_id, str), "missing subscription id after purchase")
    return sub_id


def book_session(token: str, session_id: str, subscription_id: str) -> dict[str, Any]:
    res = api.call(
        "POST",
        f"/api/v1/sessions/{session_id}/book",
        {"client_plan_subscription_id": subscription_id},
        token,
    )
    ensure(res.status == 201, f"book session failed: {res.status} {res.data}")
    ensure(isinstance(res.data, dict), f"unexpected book payload: {res.data}")
    return res.data


def cancel_booking(token: str, booking_id: str) -> None:
    res = api.call("DELETE", f"/api/v1/bookings/{booking_id}", token=token)
    ensure(res.status == 204, f"cancel booking failed: {res.status} {res.data}")


def main() -> None:
    started = time.time()
    ts = int(started)
    now = datetime.now(UTC)

    step("health")
    wait_backend_ready()

    # The stock disposable Compose stack uses these exact development values.
    # Never provision synthetic terms against a configured production database.
    stock_dev_stack = (
        os.environ.get("DATABASE_URL") == "postgresql+psycopg://piano:piano@db:5432/piano_academie"
        and os.environ.get("JWT_SECRET_KEY") == "dev-secret-change-me"
    )
    if os.environ.get("SMOKE_ALLOW_TEST_FIXTURES") == "1" or stock_dev_stack:
        with SessionLocal() as db:
            terms = db.get(AppSetting, "config_account_legal_terms")
            if terms is None:
                db.add(AppSetting(key="config_account_legal_terms", value="Conditions fictives du test automatisé — aucun achat réel."))
                db.commit()

    client_email = f"smoke.client.{ts}@example.com"
    wait_email = f"smoke.wait.{ts}@example.com"
    admin_email = f"smoke.admin.{ts}@example.com"
    prof_email = "prof.demo@piano-academie.local"
    password = "Password123X"

    step("register users")
    register_user(client_email, password)
    register_user(wait_email, password)
    register_user(admin_email, password)

    with SessionLocal() as db:
        prof_user = db.scalar(select(User).where(User.email == prof_email))
    if prof_user is None:
        register_user(prof_email, password)

    promote_user_role(admin_email, UserRole.ADMIN)
    promote_user_role(prof_email, UserRole.PROF)

    step("login users")
    client_token = login(client_email, password)
    wait_token = login(wait_email, password)
    admin_token = login(admin_email, password)
    prof_token = login(prof_email, password)

    step("client profile")
    me_client = api.call("GET", "/api/v1/clients/me", token=client_token)
    ensure(me_client.status == 200, f"GET /clients/me failed: {me_client.status} {me_client.data}")

    patch_client = api.call(
        "PATCH",
        "/api/v1/clients/me",
        {"timezone": "Europe/London", "residence_country": "GB", "preferred_currency": "EUR"},
        client_token,
    )
    ensure(patch_client.status == 200, f"PATCH /clients/me failed: {patch_client.status} {patch_client.data}")

    plan_id, course_type_id = get_pack_plan_and_course_type()
    sub_plan_id, sub_plan_billing_method = get_subscription_plan_purchase()
    location_id, professor_id, location_timezone = get_online_location_and_professor()

    step("school event registration and waitlist")
    event_slug = f"smoke-event-{ts}"
    event_start = force_local_hour(now + timedelta(days=3), timezone_name=location_timezone, hour=18)
    create_event = api.call(
        "POST",
        "/api/v1/admin/events",
        {
            "slug": event_slug,
            "title_fr": "Concert smoke",
            "title_en": "Smoke concert",
            "description_fr": "Verification du parcours evenement.",
            "description_en": "Event flow verification.",
            "category": "CONCERT",
            "status": "PUBLISHED",
            "audience": "PUBLIC",
            "registration_mode": "GROUP_SESSION",
            "payment_mode": "FREE",
            "location_id": location_id,
            "booking_opens_at": (now - timedelta(hours=1)).isoformat(),
            "booking_closes_at": (event_start - timedelta(hours=1)).isoformat(),
            "price_ttc": "0",
            "currency": "EUR",
            "max_per_family": 4,
            "waitlist_enabled": True,
            "cancellation_deadline_hours": 24,
            "collect_piece_info": True,
            "collect_photo_consent": False,
        },
        admin_token,
    )
    ensure(create_event.status == 201, f"event creation failed: {create_event.status} {create_event.data}")
    event_id = create_event.data.get("id") if isinstance(create_event.data, dict) else None
    ensure(isinstance(event_id, str), "missing school event id")

    create_event_slot = api.call(
        "POST",
        f"/api/v1/admin/events/{event_id}/slots",
        {
            "start_at_utc": event_start.isoformat(),
            "end_at_utc": (event_start + timedelta(hours=1)).isoformat(),
            "timezone": location_timezone,
            "capacity_max": 1,
            "location_id": location_id,
            "label": "Passage smoke",
        },
        admin_token,
    )
    ensure(
        create_event_slot.status == 201,
        f"event slot creation failed: {create_event_slot.status} {create_event_slot.data}",
    )
    event_slot_id = create_event_slot.data.get("id") if isinstance(create_event_slot.data, dict) else None
    ensure(isinstance(event_slot_id, str), "missing school event slot id")

    public_events = api.call("GET", "/api/v1/events")
    ensure(public_events.status == 200, f"public event list failed: {public_events.status} {public_events.data}")
    ensure(
        any(isinstance(row, dict) and row.get("slug") == event_slug for row in public_events.data),
        "published school event missing from public list",
    )

    first_event_registration = api.call(
        "POST",
        f"/api/v1/clients/me/events/{event_slug}/register",
        {"slot_id": event_slot_id, "participant_user_ids": [], "guest_names": [], "piece_info": "Smoke piece"},
        client_token,
    )
    ensure(
        first_event_registration.status == 200
        and isinstance(first_event_registration.data, dict)
        and first_event_registration.data.get("status") == "CONFIRMED",
        f"event confirmation failed: {first_event_registration.status} {first_event_registration.data}",
    )
    first_event_group_id = first_event_registration.data.get("group_id")
    ensure(isinstance(first_event_group_id, str), "missing first event registration group")

    wait_event_registration = api.call(
        "POST",
        f"/api/v1/clients/me/events/{event_slug}/register",
        {"slot_id": event_slot_id, "participant_user_ids": [], "guest_names": []},
        wait_token,
    )
    ensure(
        wait_event_registration.status == 200
        and isinstance(wait_event_registration.data, dict)
        and wait_event_registration.data.get("status") == "WAITLISTED",
        f"event waitlist failed: {wait_event_registration.status} {wait_event_registration.data}",
    )

    cancel_event_registration = api.call(
        "POST",
        f"/api/v1/clients/me/event-registrations/{first_event_group_id}/cancel",
        token=client_token,
    )
    ensure(
        cancel_event_registration.status == 204,
        f"event cancellation failed: {cancel_event_registration.status} {cancel_event_registration.data}",
    )
    wait_event_rows = api.call("GET", "/api/v1/clients/me/event-registrations", token=wait_token)
    ensure(wait_event_rows.status == 200, f"event registrations list failed: {wait_event_rows.status} {wait_event_rows.data}")
    ensure(
        any(
            isinstance(row, dict)
            and row.get("event_slug") == event_slug
            and row.get("status") == "CONFIRMED"
            for row in wait_event_rows.data
        ),
        "event waitlist registration was not promoted after cancellation",
    )

    step("waitlist scenario")
    waitlist_session_id = create_session_as_admin(
        admin_token,
        title=f"Smoke waitlist {ts}",
        start_at=force_local_hour(now + timedelta(hours=30), timezone_name=location_timezone),
        course_type_id=course_type_id,
        location_id=location_id,
        professor_id=professor_id,
        capacity=1,
    )

    sub_client = buy_plan(client_token, plan_id)
    sub_wait = buy_plan(wait_token, plan_id)

    step("purchase guards")
    duplicate_pack = api.call("POST", f"/api/v1/plans/{plan_id}/purchase", {"legal_terms_accepted": True}, token=client_token)
    ensure(duplicate_pack.status == 409, f"duplicate pack purchase should fail: {duplicate_pack.status} {duplicate_pack.data}")

    if sub_plan_billing_method:
        first_monthly = api.call(
            "POST",
            f"/api/v1/plans/{sub_plan_id}/purchase",
            {"billing_method_code": sub_plan_billing_method, "legal_terms_accepted": True},
            client_token,
        )
        ensure(first_monthly.status == 201, f"first monthly purchase failed: {first_monthly.status} {first_monthly.data}")

        duplicate_monthly = api.call(
            "POST",
            f"/api/v1/plans/{sub_plan_id}/purchase",
            {"billing_method_code": sub_plan_billing_method, "legal_terms_accepted": True},
            client_token,
        )
        ensure(
            duplicate_monthly.status == 409,
            f"duplicate monthly purchase should fail: {duplicate_monthly.status} {duplicate_monthly.data}",
        )
    else:
        step("monthly purchase guard skipped: no online billing method configured")

    private_plan_id = get_private_plan_id()
    if private_plan_id is not None:
        step("private plans hidden from clients")
        plans_for_client = api.call("GET", "/api/v1/plans", token=client_token)
        ensure(plans_for_client.status == 200, f"client list plans failed: {plans_for_client.status} {plans_for_client.data}")
        ensure(isinstance(plans_for_client.data, list), f"client plans payload is not a list: {plans_for_client.data}")
        visible_plan_ids = {row.get("id") for row in plans_for_client.data if isinstance(row, dict)}
        ensure(private_plan_id not in visible_plan_ids, "private plan should be hidden from client list")

        private_preview = api.call("GET", f"/api/v1/plans/{private_plan_id}/price-preview", token=client_token)
        ensure(
            private_preview.status == 404,
            f"private plan preview should fail with 404: {private_preview.status} {private_preview.data}",
        )
        private_purchase = api.call("POST", f"/api/v1/plans/{private_plan_id}/purchase", {"legal_terms_accepted": True}, token=client_token)
        ensure(
            private_purchase.status == 404,
            f"private plan purchase should fail with 404: {private_purchase.status} {private_purchase.data}",
        )

    booking_client = book_session(client_token, waitlist_session_id, sub_client)
    booking_wait = book_session(wait_token, waitlist_session_id, sub_wait)

    ensure(booking_client.get("status") == "BOOKED", f"expected BOOKED, got {booking_client.get('status')}")
    ensure(booking_wait.get("status") == "WAITLISTED", f"expected WAITLISTED, got {booking_wait.get('status')}")

    step("capacity increase promotes waitlist")
    capacity_upgrade = api.call(
        "PATCH",
        f"/api/v1/admin/sessions/{waitlist_session_id}",
        {"capacity_max": 5, "adult_capacity_max": 5},
        admin_token,
    )
    ensure(
        capacity_upgrade.status == 200,
        f"session capacity update failed: {capacity_upgrade.status} {capacity_upgrade.data}",
    )

    with SessionLocal() as db:
        wait_booking = db.scalar(select(Booking).where(Booking.id == booking_wait["id"]))
        ensure(wait_booking is not None, "waitlist booking missing after capacity update")
        ensure(wait_booking.status.value == "BOOKED", "waitlist booking should be promoted to BOOKED after capacity increase")

    step("attendance scenario")
    attendance_session_id = create_session_as_admin(
        admin_token,
        title=f"Smoke attendance {ts}",
        start_at=force_local_hour(now + timedelta(hours=30), timezone_name=location_timezone),
        course_type_id=course_type_id,
        location_id=location_id,
        professor_id=professor_id,
        capacity=3,
    )
    booking_att = book_session(wait_token, attendance_session_id, sub_wait)
    ensure(booking_att.get("status") == "BOOKED", "attendance booking should be BOOKED")

    step("reminders")
    set_reminder = api.call("PUT", "/api/v1/admin/settings/reminder_hours_before_start", {"value": "48"}, admin_token)
    ensure(set_reminder.status == 200, f"setting reminder hours failed: {set_reminder.status} {set_reminder.data}")

    run_reminders = api.call("POST", "/api/v1/internal/jobs/send-reminders", token=admin_token)
    ensure(run_reminders.status == 200, f"send reminders failed: {run_reminders.status} {run_reminders.data}")

    with SessionLocal() as db:
        reminder = db.scalar(select(EmailReminder).where(EmailReminder.booking_id == booking_att["id"]).order_by(EmailReminder.created_at.desc()))
        ensure(reminder is not None, "reminder record missing")

    attendance = api.call(
        "POST",
        f"/api/v1/bookings/{booking_att['id']}/attendance",
        {"attendance_status": "ATTENDED"},
        prof_token,
    )
    ensure(attendance.status == 200, f"attendance update failed: {attendance.status} {attendance.data}")

    step("auto-cancel job")
    auto_session_id = create_session_as_admin(
        admin_token,
        title=f"Smoke autocancel {ts}",
        start_at=force_local_hour(now + timedelta(hours=10), timezone_name=location_timezone),
        course_type_id=course_type_id,
        location_id=location_id,
        professor_id=professor_id,
        capacity=3,
        deadline_hours_before=1,
    )
    patch_auto = api.call(
        "PATCH",
        f"/api/v1/admin/sessions/{auto_session_id}",
        {"auto_cancel_deadline_utc": (now - timedelta(minutes=5)).isoformat(),
         "auto_cancel_rule_enabled_override": True, "auto_cancel_if_booked_less_than_override": 1,
         "auto_cancel_hours_before_start_override": 48},
        admin_token,
    )
    ensure(patch_auto.status == 200, f"patch auto-cancel deadline failed: {patch_auto.status} {patch_auto.data}")

    auto_job = api.call("POST", "/api/v1/internal/jobs/auto-cancel-empty-sessions", token=admin_token)
    ensure(auto_job.status == 200, f"auto-cancel job failed: {auto_job.status} {auto_job.data}")

    with SessionLocal() as db:
        auto_session = db.scalar(select(CourseSession).where(CourseSession.id == auto_session_id))
        ensure(auto_session is not None and auto_session.status.value == "CANCELLED", "auto-cancel session not cancelled")

    step("admin pricing + vat")
    pp = api.call(
        "POST",
        "/api/v1/admin/pricing/plan-prices",
        {
            "plan_id": plan_id,
            "residence_country": "US",
            "currency_code": "USD",
            "price_excl_vat": "111.11",
            "valid_from": "2026-02-01",
        },
        admin_token,
    )
    ensure(pp.status in {201, 409}, f"plan price create unexpected: {pp.status} {pp.data}")

    ctp = api.call(
        "POST",
        "/api/v1/admin/pricing/course-type-prices",
        {
            "course_type_id": course_type_id,
            "residence_country": "US",
            "currency_code": "USD",
            "price_excl_vat": "33.33",
            "valid_from": "2026-02-01",
        },
        admin_token,
    )
    ensure(ctp.status in {201, 409}, f"course type price create unexpected: {ctp.status} {ctp.data}")

    vat = api.call(
        "POST",
        "/api/v1/admin/vat-rules",
        {
            "country_code": "US",
            "service_code": "PIANO_CLASS",
            "vat_rate": "7.50",
            "valid_from": "2026-02-01",
        },
        admin_token,
    )
    ensure(vat.status in {201, 409}, f"vat create unexpected: {vat.status} {vat.data}")

    pp_list = api.call("GET", "/api/v1/admin/pricing/plan-prices?country=US&currency=USD", token=admin_token)
    ctp_list = api.call("GET", "/api/v1/admin/pricing/course-type-prices?country=US&currency=USD", token=admin_token)
    vat_list = api.call("GET", "/api/v1/admin/vat-rules?country_code=US&service_code=PIANO_CLASS", token=admin_token)
    ensure(pp_list.status == 200 and isinstance(pp_list.data, list), "plan price list failed")
    ensure(ctp_list.status == 200 and isinstance(ctp_list.data, list), "course type price list failed")
    ensure(vat_list.status == 200 and isinstance(vat_list.data, list), "vat list failed")

    step("reports + payouts")
    reports = [
        api.call("GET", "/api/v1/admin/reports/reservations", token=admin_token),
        api.call("GET", "/api/v1/admin/reports/attendance", token=admin_token),
        api.call("GET", "/api/v1/admin/reports/professor-statements", token=admin_token),
    ]
    ensure(all(r.status == 200 for r in reports), "one of report endpoints failed")

    payout = api.call("POST", "/api/v1/internal/jobs/calc-professor-payouts", token=admin_token)
    ensure(payout.status == 200, f"payout job failed: {payout.status} {payout.data}")

    duration = round(time.time() - started, 2)
    print(
        json.dumps(
            {
                "ok": True,
                "duration_seconds": duration,
                "checks": {
                    "health": True,
                    "auth_roles": True,
                    "client_profile": True,
                    "waitlist": True,
                    "purchase_guards": True,
                    "attendance": True,
                    "reminders_job": True,
                    "auto_cancel_job": True,
                    "admin_pricing": True,
                    "reports": True,
                    "payout_job": True,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
