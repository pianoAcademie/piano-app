from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ops import PasswordResetToken
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.i18n import normalize_language
from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_CLIENT_PORTAL_ACCESS,
    render_template_content,
    resolve_frontend_base_url,
    resolve_predefined_template,
    resolve_sender_profile,
)


def _frontend_url(db: Session, path: str) -> str:
    base_url = resolve_frontend_base_url(db).strip() or "http://localhost:3000"
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    return f"{base_url.rstrip('/')}{path}"


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_password_setup_url(db: Session, *, user: User) -> str:
    """Create a single-use password setup URL without exposing a password by email."""

    now = datetime.now(timezone.utc)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(48)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_reset_token(raw_token),
            expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
        )
    )
    return f"{_frontend_url(db, '/login')}?reset_token={raw_token}"


def send_client_portal_access_email(
    db: Session,
    *,
    user: User,
    password_setup_required: bool,
    source: str = "CLIENT_PORTAL_WELCOME",
    raise_on_failure: bool = False,
) -> str | None:
    """Send the bilingual client access email and optionally create a setup token.

    The caller owns the surrounding database transaction. When a setup token is
    requested, it is added to that transaction before the message is sent.
    """

    language = normalize_language(user.preferred_language)
    login_url = _frontend_url(db, "/login")
    if password_setup_required:
        primary_url = create_password_setup_url(db, user=user)
        if language == "en":
            access_intro = "Choose your password securely, then sign in with your email address."
            primary_label = "Choose my password"
        else:
            access_intro = "Choisissez votre mot de passe de manière sécurisée, puis connectez-vous avec votre adresse e-mail."
            primary_label = "Choisir mon mot de passe"
    else:
        primary_url = login_url
        if language == "en":
            access_intro = "Your account has been created. Sign in with the password you chose during registration."
            primary_label = "Open my client portal"
        else:
            access_intro = "Votre compte a bien été créé. Connectez-vous avec le mot de passe choisi lors de votre inscription."
            primary_label = "Ouvrir mon espace client"

    first_name = (user.first_name or "").strip()
    last_name = (user.last_name or "").strip()
    full_name = f"{first_name} {last_name}".strip() or user.email
    context = {
        "first_name": first_name or user.email,
        "last_name": last_name,
        "full_name": full_name,
        "email": user.email,
        "access_intro": access_intro,
        "primary_url": primary_url,
        "primary_label": primary_label,
        "login_url": login_url,
    }
    template = resolve_predefined_template(
        db,
        code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_PORTAL_ACCESS,
        language=language,
    )
    subject = render_template_content(str(template.get("subject") or ""), context)
    body = render_template_content(str(template.get("body") or ""), context)
    body_format = "HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT"
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    return send_email(
        to_email=user.email,
        subject=subject,
        body=body,
        body_format=body_format,
        context=source,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        recipient_user_id=user.id,
        raise_on_failure=raise_on_failure,
        db=db,
    )


__all__ = ["create_password_setup_url", "send_client_portal_access_email"]
