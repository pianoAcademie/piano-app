from __future__ import annotations

import json
import os
import subprocess
import time
from urllib import error, request

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DEFAULT_PASSWORD = os.getenv("SMOKE_PASSWORD", "Password123X")


def call(method: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict | list | str | None]:
    headers: dict[str, str] = {}
    data: bytes | None = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = raw
        return exc.code, parsed


def assert_status(got: int, expected: int, body: object, step: str) -> None:
    if got != expected:
        raise RuntimeError(f"{step}: expected {expected}, got {got}, body={body}")


def promote_as_admin(email: str) -> None:
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "piano",
        "-d",
        "piano_academie",
        "-c",
        f"UPDATE users SET role='admin' WHERE email='{email}';",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def create_client(token: str, email: str, client_kind: str, first_name: str, last_name: str, phone: str, address_line: str) -> dict:
    status, body = call(
        "POST",
        "/api/v1/admin/clients",
        {
            "email": email,
            "password": DEFAULT_PASSWORD,
            "client_kind": client_kind,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "address_line": address_line,
            "residence_country": "FR",
            "preferred_currency": "EUR",
            "timezone": "Europe/Paris",
        },
        token,
    )
    assert_status(status, 201, body, f"create client {email}")
    assert isinstance(body, dict)
    return body


def main() -> None:
    suffix = str(int(time.time()))

    admin_email = f"family.admin.{suffix}@example.com"
    status, body = call(
        "POST",
        "/api/v1/auth/register",
        {"email": admin_email, "password": DEFAULT_PASSWORD},
    )
    assert_status(status, 201, body, "register admin user")
    promote_as_admin(admin_email)

    status, body = call(
        "POST",
        "/api/v1/auth/login",
        {"email": admin_email, "password": DEFAULT_PASSWORD},
    )
    assert_status(status, 200, body, "login admin")
    assert isinstance(body, dict)
    admin_token = body["access_token"]

    adult_1 = create_client(
        admin_token,
        f"parent1.{suffix}@example.com",
        "ADULT",
        "Maman",
        "Dupont",
        "+33101010101",
        "1 rue A",
    )
    adult_2 = create_client(
        admin_token,
        f"parent2.{suffix}@example.com",
        "ADULT",
        "Papa",
        "Dupont",
        "+33101010102",
        "2 rue B",
    )
    child = create_client(
        admin_token,
        f"child.{suffix}@example.com",
        "CHILD",
        "Lina",
        "Dupont",
        "+33101010103",
        "1 rue A",
    )

    status, body = call(
        "POST",
        "/api/v1/admin/clients/family/links",
        {
            "adult_client_id": adult_1["id"],
            "child_client_id": child["id"],
            "relationship_label": "Mere",
            "is_billing_recipient": True,
        },
        admin_token,
    )
    assert_status(status, 201, body, "link mother -> child")

    status, body = call(
        "POST",
        "/api/v1/admin/clients/family/links",
        {
            "adult_client_id": adult_2["id"],
            "child_client_id": child["id"],
            "relationship_label": "Pere",
            "is_billing_recipient": False,
        },
        admin_token,
    )
    assert_status(status, 201, body, "link father -> child")
    assert isinstance(body, dict)
    second_link_id = body["id"]

    status, body = call(
        "PATCH",
        f"/api/v1/admin/clients/family/links/{second_link_id}",
        {"is_billing_recipient": True},
        admin_token,
    )
    assert_status(status, 200, body, "switch billing recipient")
    assert isinstance(body, dict)
    if body.get("is_billing_recipient") is not True:
        raise RuntimeError("switch billing recipient did not persist")

    status, body = call(
        "GET",
        f"/api/v1/admin/clients/{child['id']}/family",
        token=admin_token,
    )
    assert_status(status, 200, body, "read child family")
    assert isinstance(body, dict)
    links_as_child = body["links_as_child"]
    billed = [item for item in links_as_child if item["is_billing_recipient"]]
    if len(links_as_child) != 2 or len(billed) != 1 or billed[0]["adult"]["id"] != adult_2["id"]:
        raise RuntimeError(f"unexpected family state: {body}")

    status, body = call(
        "POST",
        "/api/v1/auth/login",
        {"email": adult_2["email"], "password": DEFAULT_PASSWORD},
    )
    assert_status(status, 200, body, "login adult_2")
    assert isinstance(body, dict)
    adult_2_token = body["access_token"]

    status, body = call("GET", "/api/v1/clients/me/family", token=adult_2_token)
    assert_status(status, 200, body, "adult overview")
    assert isinstance(body, dict)
    if child["id"] not in body.get("managed_client_ids", []):
        raise RuntimeError(f"child not visible from parent account: {body}")

    print("SMOKE_FAMILY_OK")
    print(
        json.dumps(
            {
                "admin": admin_email,
                "adult_1": adult_1["email"],
                "adult_2": adult_2["email"],
                "child": child["email"],
            }
        )
    )


if __name__ == "__main__":
    main()
