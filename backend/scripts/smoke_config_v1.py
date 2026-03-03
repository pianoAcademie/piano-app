from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.user import User, UserRole

BASE_URL = "http://localhost:8000"
PASSWORD = "Password123X"


class SmokeFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: object | None = None, token: str | None = None) -> tuple[int, object | None]:
        headers: dict[str, str] = {}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
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


api = ApiClient(BASE_URL)


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def register_admin(email: str, password: str) -> None:
    status, data = api.call(
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": password,
            "first_name": "Config",
            "last_name": "Smoke",
            "residence_country": "FR",
            "preferred_currency": "EUR",
            "timezone": "Europe/Paris",
        },
    )
    ensure(status == 201, f"register failed: {status} {data}")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        ensure(user is not None, "registered user missing")
        user.role = UserRole.ADMIN
        db.add(user)
        db.commit()


def login(email: str, password: str) -> str:
    status, data = api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    ensure(status == 200 and isinstance(data, dict), f"login failed: {status} {data}")
    token = data.get("access_token")
    ensure(isinstance(token, str) and token, "token missing")
    return token


def main() -> None:
    ts = int(time.time())
    admin_email = f"config.smoke.admin.{ts}@example.com"

    register_admin(admin_email, PASSWORD)
    token = login(admin_email, PASSWORD)

    status, account = api.call("GET", "/api/v1/admin/config/account", token=token)
    ensure(status == 200 and isinstance(account, dict), f"get account failed: {status} {account}")

    status, account_upd = api.call(
        "PUT",
        "/api/v1/admin/config/account",
        {
            **account,
            "club_name": "Piano Academie Config Smoke",
            "vat_default_rate": "20",
        },
        token,
    )
    ensure(status == 200 and isinstance(account_upd, dict), f"update account failed: {status} {account_upd}")

    status, subs = api.call("GET", "/api/v1/admin/config/subscriptions", token=token)
    ensure(status == 200 and isinstance(subs, dict), f"get subscriptions failed: {status} {subs}")

    status, subs_upd = api.call(
        "PUT",
        "/api/v1/admin/config/subscriptions",
        {
            **subs,
            "direct_debit_day": 7,
            "allow_prorata_card": True,
        },
        token,
    )
    ensure(status == 200 and isinstance(subs_upd, dict), f"update subscriptions failed: {status} {subs_upd}")

    status, payment_methods = api.call("GET", "/api/v1/admin/config/payment-methods", token=token)
    ensure(status == 200 and isinstance(payment_methods, dict), f"get payment methods failed: {status} {payment_methods}")

    status, payment_provider = api.call("GET", "/api/v1/admin/config/payment-provider", token=token)
    ensure(status == 200 and isinstance(payment_provider, dict), f"get payment provider failed: {status} {payment_provider}")

    status, payment_provider_upd = api.call(
        "PUT",
        "/api/v1/admin/config/payment-provider",
        {
            "provider": "STRIPE",
            "mode": "TEST",
            "stripe_test_secret": "sk_test_smoke_config_key",
            "webhook_secret": "whsec_smoke_config",
        },
        token,
    )
    ensure(status == 200 and isinstance(payment_provider_upd, dict), f"update payment provider failed: {status} {payment_provider_upd}")
    ensure(payment_provider_upd.get("provider") == "STRIPE", "provider should be STRIPE")

    status, legal_entities = api.call("GET", "/api/v1/admin/legal-entities?include_inactive=true", token=token)
    ensure(status == 200 and isinstance(legal_entities, list) and len(legal_entities) > 0, f"get legal entities failed: {status} {legal_entities}")
    legal_entity_id = str(legal_entities[0].get("id") or "")
    ensure(legal_entity_id, "first legal entity id missing")
    status, legal_entity_upd = api.call(
        "PATCH",
        f"/api/v1/admin/legal-entities/{legal_entity_id}",
        {"default_payment_provider": "STRIPE"},
        token=token,
    )
    ensure(status == 200 and isinstance(legal_entity_upd, dict), f"patch legal entity failed: {status} {legal_entity_upd}")
    ensure(legal_entity_upd.get("default_payment_provider") == "STRIPE", "legal entity default PSP should be STRIPE")

    enabled_codes = [
        row["code"]
        for row in payment_methods["methods"]
        if row["code"] in {"CARD_ONLINE", "CARD_TERMINAL", "CASH", "BANK_TRANSFER"}
    ]
    status, payment_methods_upd = api.call(
        "PUT",
        "/api/v1/admin/config/payment-methods",
        {"enabled_codes": enabled_codes},
        token,
    )
    ensure(status == 200 and isinstance(payment_methods_upd, dict), f"update payment methods failed: {status} {payment_methods_upd}")

    status, course_types = api.call("GET", "/api/v1/course-types", token=token)
    ensure(status == 200 and isinstance(course_types, list) and len(course_types) >= 2, f"list course types failed: {status} {course_types}")
    course_type_ids = [row["id"] for row in course_types[:2]]

    formula_payload = {
        "name": f"Formule smoke config {ts}",
        "kind": "SUBSCRIPTION",
        "active": True,
        "is_private": False,
        "description": "Smoke formula",
        "monthly_price_excl_vat": 199.0,
        "currency_code": "EUR",
        "signup_fee_excl_vat": 15.0,
        "options": ["Sans engagement"],
        "payment_methods": enabled_codes,
        "entitlement_course_type_ids": course_type_ids,
        "restrictions": [
            {"period": "DAY", "max_bookings": 1, "course_type_ids": [course_type_ids[0]]},
            {"period": "WEEK", "max_bookings": 2, "course_type_ids": course_type_ids},
        ],
    }
    status, created_formula = api.call("POST", "/api/v1/admin/formulas", formula_payload, token)
    ensure(status == 201 and isinstance(created_formula, dict), f"create formula failed: {status} {created_formula}")

    formula_id = created_formula["id"]
    status, updated_formula = api.call(
        "PATCH",
        f"/api/v1/admin/formulas/{formula_id}",
        {
            "name": f"{created_formula['name']} update",
            "is_private": True,
            "restrictions": [
                {"period": "WEEK", "max_bookings": 3, "course_type_ids": course_type_ids},
            ],
        },
        token,
    )
    ensure(status == 200 and isinstance(updated_formula, dict), f"patch formula failed: {status} {updated_formula}")

    status, duplicated_formula = api.call("POST", f"/api/v1/admin/formulas/{formula_id}/duplicate", token=token)
    ensure(status == 201 and isinstance(duplicated_formula, dict), f"duplicate formula failed: {status} {duplicated_formula}")

    duplicated_id = duplicated_formula["id"]
    status, disabled_formula = api.call("POST", f"/api/v1/admin/formulas/{duplicated_id}/disable", token=token)
    ensure(status == 200 and isinstance(disabled_formula, dict), f"disable formula failed: {status} {disabled_formula}")
    ensure(disabled_formula.get("active") is False, "duplicated formula should be inactive after disable")

    status, formulas = api.call("GET", "/api/v1/admin/formulas?include_inactive=true", token=token)
    ensure(status == 200 and isinstance(formulas, list), f"list formulas failed: {status} {formulas}")

    print(
        json.dumps(
            {
                "ok": True,
                "scenario": "config_v1",
                "admin_email": admin_email,
                "formula_id": formula_id,
                "duplicated_formula_id": duplicated_id,
                "formula_count": len(formulas),
            }
        )
    )


if __name__ == "__main__":
    main()
