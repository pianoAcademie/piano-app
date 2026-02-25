from __future__ import annotations

import secrets
import string

from app.services.email_delivery import send_email

DEFAULT_PROFESSOR_ACTIVATION_SUBJECT = "Activation de votre compte professeur Piano Academie"
DEFAULT_PROFESSOR_ACTIVATION_BODY = (
    "Bonjour {full_name},\n\n"
    "Votre compte professeur est active.\n"
    "Identifiant: {email}\n"
    "Mot de passe temporaire: {temporary_password}\n"
    "Connexion: {login_url}\n\n"
    "Merci de vous connecter puis de changer ce mot de passe.\n\n"
    "Piano Academie"
)


def generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(max(8, length - 2)))
    return f"{core}A!"


def render_professor_activation_email(
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
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "temporary_password": temporary_password,
        "login_url": login_url,
    }
    try:
        subject = subject_template.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        subject = subject_template.strip()
    try:
        body = body_template.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        body = body_template.strip()
    return subject, body


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def send_professor_activation_email(
    *,
    to_email: str,
    full_name: str,
    temporary_password: str,
    login_url: str = "http://localhost:3000/login",
    subject_template: str = DEFAULT_PROFESSOR_ACTIVATION_SUBJECT,
    body_template: str = DEFAULT_PROFESSOR_ACTIVATION_BODY,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    subject_prefix: str | None = None,
) -> str:
    first_name = full_name.strip().split(" ")[0] if full_name.strip() else ""
    last_name = " ".join(full_name.strip().split(" ")[1:]) if full_name.strip() else ""
    subject, body = render_professor_activation_email(
        subject_template=subject_template,
        body_template=body_template,
        first_name=first_name,
        last_name=last_name,
        email=to_email,
        temporary_password=temporary_password,
        login_url=login_url,
    )

    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="PROFESSOR_ACTIVATION",
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        subject_prefix=subject_prefix,
    )
