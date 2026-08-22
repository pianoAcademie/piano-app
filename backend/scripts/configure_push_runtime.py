from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ALLOWED_KEYS = {
    "PUSH_NOTIFICATIONS_ENABLED",
    "APNS_TEAM_ID",
    "APNS_KEY_ID",
    "APNS_PRIVATE_KEY",
    "APNS_CLIENT_BUNDLE_ID",
    "APNS_USE_SANDBOX",
    "FIREBASE_PROJECT_ID",
    "FIREBASE_CLIENT_EMAIL",
    "FIREBASE_PRIVATE_KEY",
}
DEPLOYMENT_PRESENCE_ATTEMPTS = 6
DEPLOYMENT_PRESENCE_RETRY_SECONDS = 20
DEPLOYMENT_PRESENCE_WINDOW_SECONDS = 90
SYSTEM_ADMIN_EMAIL = "admin@piano-academie.com"

_ACTIVE_USER_QUERY = f"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.models.user import User, UserPresence

db = SessionLocal()
try:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds={DEPLOYMENT_PRESENCE_WINDOW_SECONDS})
    count = db.scalar(
        select(func.count(func.distinct(UserPresence.user_id)))
        .join(User, User.id == UserPresence.user_id)
        .where(
            UserPresence.last_seen_at >= cutoff,
            User.is_active.is_(True),
            func.lower(User.email) != {SYSTEM_ADMIN_EMAIL!r},
        )
    )
    print(int(count or 0))
finally:
    db.close()
""".strip()


def _active_non_system_user_count() -> int:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-c", _ACTIVE_USER_QUERY],
        check=True,
        capture_output=True,
        text=True,
    )
    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise RuntimeError("the production presence query returned no result")
    try:
        return int(output_lines[-1])
    except ValueError as exc:
        raise RuntimeError("the production presence query returned an invalid result") from exc


def _wait_until_no_real_user_is_online() -> None:
    for attempt in range(1, DEPLOYMENT_PRESENCE_ATTEMPTS + 1):
        active_count = _active_non_system_user_count()
        if active_count == 0:
            print("[OK] No active non-system user. Deployment is allowed.")
            return
        print(
            f"Deployment delayed: {active_count} active non-system user(s) "
            f"(attempt {attempt}/{DEPLOYMENT_PRESENCE_ATTEMPTS})."
        )
        if attempt < DEPLOYMENT_PRESENCE_ATTEMPTS:
            time.sleep(DEPLOYMENT_PRESENCE_RETRY_SECONDS)
    raise RuntimeError("deployment refused because a non-system user is still active")


def _read_payload() -> dict[str, str]:
    encoded = sys.stdin.buffer.read().strip()
    if not encoded:
        raise ValueError("empty configuration payload")

    decoded = base64.b64decode(encoded, validate=True)
    raw_payload = json.loads(decoded)
    if not isinstance(raw_payload, dict):
        raise ValueError("configuration payload must be an object")

    payload: dict[str, str] = {}
    for key, value in raw_payload.items():
        if key not in ALLOWED_KEYS:
            raise ValueError(f"unsupported environment key: {key}")
        if not isinstance(value, str) or not value:
            raise ValueError(f"missing value for environment key: {key}")
        if any(character in value for character in ("\n", "\r", "\x00")):
            raise ValueError(f"unsafe value for environment key: {key}")
        payload[key] = value
    return payload


def _update_env_file(path: Path, payload: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(payload)
    output: list[str] = []

    for line in existing_lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key not in remaining:
            output.append(line)
            continue

        output.append(f"{key}={remaining.pop(key)}")

    if remaining:
        if output and output[-1]:
            output.append("")
        output.append("# Native mobile push notifications")
        output.extend(f"{key}={value}" for key, value in remaining.items())

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            temporary_file.write("\n".join(output) + "\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    try:
        _wait_until_no_real_user_is_online()
        payload = _read_payload()
        _update_env_file(Path(".env"), payload)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"[ERROR] Unable to configure push environment: {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Push environment configured ({len(payload)} protected values).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
