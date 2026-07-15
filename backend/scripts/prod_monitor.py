from __future__ import annotations

import json
import os
import smtplib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(os.getenv("PIANO_APP_ROOT", "/home/ubuntu/piano-app"))
ENV_PATH = ROOT / ".env"
STATE_PATH = Path(os.getenv("PROD_MONITOR_STATE_PATH", "/var/tmp/piano_prod_monitor_state.json"))
PUBLIC_LOGIN_URL = os.getenv("PROD_MONITOR_PUBLIC_LOGIN_URL", "https://app.piano-academie.com/login")
EXPECTED_TEXT = os.getenv("PROD_MONITOR_EXPECTED_TEXT", "Piano Academie")
ALERT_TO_DEFAULT = "admin@piano-academie.com,administration@piano-academie.com"
ALERT_REPEAT_SECONDS = int(os.getenv("PROD_MONITOR_ALERT_REPEAT_SECONDS", "1800"))


@dataclass
class CheckResult:
    ok: bool
    detail: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "COMPOSE_PROJECT_NAME": "piano-app"},
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _read_url(url: str, *, timeout: int = 20) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "PianoAcademieProdMonitor/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(300_000)
            return int(response.status), raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read(30_000)
        return int(exc.code), raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def _public_check() -> CheckResult:
    attempts: list[str] = []
    for attempt in range(1, 4):
        status, body = _read_url(PUBLIC_LOGIN_URL)
        if status == 200 and "502 Bad Gateway" not in body and EXPECTED_TEXT in body:
            return CheckResult(True, f"public login OK on attempt {attempt} ({status})")
        excerpt = body[:500].replace("\n", " ")
        attempts.append(f"attempt {attempt}: status={status}, body={excerpt!r}")
        time.sleep(20)
    return CheckResult(False, "public login failed: " + " | ".join(attempts))


def _vps_check() -> CheckResult:
    required = {
        "db",
        "redis",
        "backend",
        "frontend",
        "notifications-feedback-worker",
        "notifications-immediate-worker",
        "notifications-scheduled-worker",
    }
    ps = _run(["docker", "compose", "ps", "--services", "--status", "running"])
    if ps.returncode != 0:
        return CheckResult(False, f"docker compose ps failed: {ps.stderr or ps.stdout}")
    running = {line.strip() for line in ps.stdout.splitlines() if line.strip()}
    missing = sorted(required - running)
    if missing:
        return CheckResult(False, f"missing running services: {', '.join(missing)}")

    backend = _read_url("http://127.0.0.1:8000/health", timeout=10)
    if backend[0] != 200:
        return CheckResult(False, f"backend health failed: status={backend[0]}, body={backend[1][:500]!r}")

    frontend = _read_url("http://127.0.0.1:3000/login", timeout=15)
    if frontend[0] != 200 or EXPECTED_TEXT not in frontend[1] or "502 Bad Gateway" in frontend[1]:
        return CheckResult(False, f"frontend login failed: status={frontend[0]}, body={frontend[1][:500]!r}")

    return CheckResult(True, "VPS services, backend health and frontend login OK")


def _diagnostics() -> str:
    commands = [
        ["docker", "ps", "--format", "{{.ID}} {{.Names}} {{.Status}} {{.Ports}}"],
        ["docker", "compose", "ps"],
        ["docker", "compose", "logs", "--tail=80", "backend"],
        ["docker", "compose", "logs", "--tail=80", "frontend"],
    ]
    parts: list[str] = []
    for command in commands:
        result = _run(command, timeout=30)
        parts.append(f"$ {' '.join(command)}\n{result.stdout}{result.stderr}")
    nginx_error = Path("/var/log/nginx/error.log")
    if nginx_error.exists():
        try:
            lines = nginx_error.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
            parts.append("$ tail -n 80 /var/log/nginx/error.log\n" + "\n".join(lines))
        except PermissionError:
            parts.append("$ tail -n 80 /var/log/nginx/error.log\npermission denied")
    return "\n\n".join(parts)


def _load_state() -> dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict[str, object]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(STATE_PATH.parent)) as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name
    Path(temp_name).replace(STATE_PATH)


def _send_email(*, subject: str, body: str, env: dict[str, str]) -> None:
    host = env.get("SMTP_HOST") or ("smtp-relay.brevo.com" if env.get("EMAIL_PROVIDER", "").upper() == "BREVO" else "")
    username = env.get("SMTP_USERNAME", "")
    password = env.get("SMTP_PASSWORD", "")
    sender = env.get("EMAIL_FROM", "no-reply@app.piano-academie.com")
    recipients = [
        item.strip()
        for item in os.getenv("PROD_MONITOR_ALERT_TO", env.get("PROD_MONITOR_ALERT_TO", ALERT_TO_DEFAULT)).split(",")
        if item.strip()
    ]
    if not host or not username or not password or not recipients:
        raise RuntimeError("SMTP alert configuration is incomplete")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    port = int(env.get("SMTP_PORT", "587"))
    timeout = int(env.get("SMTP_TIMEOUT_SECONDS", "15"))
    use_ssl = env.get("SMTP_USE_SSL", "").lower() in {"1", "true", "yes", "on"}
    use_tls = env.get("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}

    if use_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    with smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


def main() -> int:
    env = _load_env(ENV_PATH)
    checks = [_public_check(), _vps_check()]
    ok = all(check.ok for check in checks)
    now = _now()
    state = _load_state()
    previous_status = str(state.get("status") or "unknown")
    last_alert_at_raw = state.get("last_alert_at")
    last_alert_at = None
    if isinstance(last_alert_at_raw, str):
        try:
            last_alert_at = datetime.fromisoformat(last_alert_at_raw)
        except ValueError:
            last_alert_at = None

    details = "\n".join(f"- {'OK' if check.ok else 'FAIL'}: {check.detail}" for check in checks)
    hostname = socket.gethostname()

    if ok:
        if previous_status == "down":
            body = (
                f"Production recovered on {hostname} at {now.isoformat()}.\n\n"
                f"{details}\n"
            )
            _send_email(subject="[Piano Academie] Production recovered", body=body, env=env)
        _save_state({"status": "up", "last_ok_at": now.isoformat(), "last_alert_at": state.get("last_alert_at")})
        print("OK")
        print(details)
        return 0

    should_alert = previous_status != "down"
    if not should_alert and last_alert_at is not None:
        should_alert = (now - last_alert_at).total_seconds() >= ALERT_REPEAT_SECONDS
    if should_alert:
        body = (
            f"Production monitor detected a failure on {hostname} at {now.isoformat()}.\n\n"
            f"{details}\n\n"
            f"Diagnostics:\n{_diagnostics()}"
        )
        _send_email(subject="[Piano Academie] Production monitor alert", body=body, env=env)
        state["last_alert_at"] = now.isoformat()
    state.update({"status": "down", "last_failure_at": now.isoformat(), "last_details": details})
    _save_state(state)
    print("FAILED")
    print(details)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
