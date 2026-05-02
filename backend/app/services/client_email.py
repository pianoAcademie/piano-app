from __future__ import annotations

from app.models.user import User

NO_EMAIL_DOMAIN = "no-email.local"


def normalize_contact_email(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate or None


def is_generated_client_email(email: str | None) -> bool:
    normalized = normalize_contact_email(email) or ""
    return bool(normalized) and normalized.endswith(f"@{NO_EMAIL_DOMAIN}")


def visible_client_email(user: User | None) -> str:
    if user is None:
        return ""
    contact = normalize_contact_email(user.contact_email)
    if contact:
        return contact
    raw = normalize_contact_email(user.email)
    if raw and not is_generated_client_email(raw):
        return raw
    return ""


def deliverable_client_email(user: User | None) -> str | None:
    visible = visible_client_email(user)
    return visible or None
