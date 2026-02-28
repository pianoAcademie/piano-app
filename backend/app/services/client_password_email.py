from __future__ import annotations

import logging
import re

from app.services.email_delivery import send_email
from app.services.professor_activation import generate_temporary_password

logger = logging.getLogger(__name__)
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

DEFAULT_CLIENT_PASSWORD_EMAIL_SUBJECT = "Activation de votre compte client Piano Academie"
DEFAULT_CLIENT_PASSWORD_EMAIL_BODY = (
    "Bonjour {first_name},\n\n"
    "Votre acces client est pret.\n"
    "Identifiant: {email}\n"
    "Mot de passe temporaire: {temporary_password}\n"
    "Connexion: {login_url}\n\n"
    "Merci de vous connecter puis de modifier ce mot de passe.\n\n"
    "Piano Academie"
)


def render_client_password_email(
    *,
    subject_template: str,
    body_template: str,
    first_name: str,
    last_name: str,
    email: str,
    temporary_password: str,
    login_url: str,
) -> tuple[str, str]:
    full_name = f"{first_name} {last_name}".strip() or email
    context = {
        "first_name": first_name or email,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "temporary_password": temporary_password,
        "login_url": login_url,
    }
    subject = _render_template(subject_template, context)
    body = _render_template(body_template, context)
    return subject, body


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, context: dict[str, str]) -> str:
    # Support both "{first_name}" and "{{ first_name }}" notations in templates.
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        logger.warning("Unable to render client password template, returning raw template")
        return normalized.strip()


def send_client_password_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str = "TEXT",
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    subject_prefix: str | None = None,
) -> str:
    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format=body_format,
        context="CLIENT_PASSWORD",
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        subject_prefix=subject_prefix,
    )


__all__ = [
    "DEFAULT_CLIENT_PASSWORD_EMAIL_BODY",
    "DEFAULT_CLIENT_PASSWORD_EMAIL_SUBJECT",
    "generate_temporary_password",
    "render_client_password_email",
    "send_client_password_email",
]
