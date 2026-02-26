from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.ops import AppSetting, PasswordResetToken
from app.models.user import User, UserRole
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
)
from app.schemas.user import UserOut
from app.services.email_delivery import send_email
from app.services.messaging_templates import PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET, resolve_predefined_template, resolve_sender_profile
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter()
logger = logging.getLogger(__name__)
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

DEFAULT_FORGOT_PASSWORD_MESSAGE = "Si ce compte existe, un email de reinitialisation vient d etre envoye."
DEFAULT_PASSWORD_RESET_SUBJECT = "Reinitialisation de votre mot de passe Piano Academie"
DEFAULT_PASSWORD_RESET_BODY = (
    "Bonjour {first_name},\n\n"
    "Nous avons recu une demande de reinitialisation de mot de passe.\n"
    "Pour definir un nouveau mot de passe, cliquez sur ce lien:\n"
    "{reset_url}\n\n"
    "Si vous n etes pas a l origine de cette demande, ignorez simplement cet email.\n\n"
    "Piano Academie"
)


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_timezone(value: str) -> str:
    timezone_name = value.strip()
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc
    return timezone_name


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        logger.warning("Unable to render password reset template, returning raw template")
        return normalized.strip()


def _setting_value(db: Session, key: str, default: str) -> str:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        return default
    return setting.value


def _frontend_url(db: Session, *, path: str) -> str:
    candidate = _setting_value(db, "config_account_website", "").strip()
    if not candidate:
        candidate = (settings.frontend_base_url or "").strip()
    if not candidate:
        candidate = "http://localhost:3000"
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _password_reset_template(db: Session) -> tuple[str, str]:
    try:
        template = resolve_predefined_template(db, code=PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET)
        if not template.get("active", True):
            return DEFAULT_PASSWORD_RESET_SUBJECT, DEFAULT_PASSWORD_RESET_BODY
        subject = str(template.get("subject") or "").strip() or DEFAULT_PASSWORD_RESET_SUBJECT
        body = str(template.get("body") or "").strip() or DEFAULT_PASSWORD_RESET_BODY
        return subject, body
    except Exception:
        return DEFAULT_PASSWORD_RESET_SUBJECT, DEFAULT_PASSWORD_RESET_BODY


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    normalized_email = payload.email.strip().lower()
    residence_country = payload.residence_country.upper()
    preferred_currency = payload.preferred_currency.upper()
    timezone_name = _validate_timezone(payload.timezone)

    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=normalized_email,
        hashed_password=hash_password(payload.password),
        role=UserRole.CLIENT,
        first_name=_normalize_optional(payload.first_name),
        last_name=_normalize_optional(payload.last_name),
        address_line=_normalize_optional(payload.address_line),
        address_country=residence_country,
        phone=_normalize_optional(payload.phone),
        mobile_phone_1=_normalize_optional(payload.phone),
        residence_country=residence_country,
        preferred_currency=preferred_currency,
        timezone=timezone_name,
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc.__class__.__name__}",
        ) from exc

    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    normalized_email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    return TokenResponse(access_token=access_token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    normalized_email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active:
        return ForgotPasswordResponse(message=DEFAULT_FORGOT_PASSWORD_MESSAGE)

    now = datetime.now(timezone.utc)
    try:
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

        login_url = _frontend_url(db, path="/login")
        reset_url = f"{login_url}?reset_token={raw_token}"
        first_name = (user.first_name or "").strip()
        last_name = (user.last_name or "").strip()
        full_name = f"{first_name} {last_name}".strip() or user.email
        context = {
            "first_name": first_name or user.email,
            "last_name": last_name,
            "full_name": full_name,
            "email": user.email,
            "reset_url": reset_url,
            "login_url": login_url,
        }
        subject_template, body_template = _password_reset_template(db)
        subject = _render_template(subject_template, context)
        body = _render_template(body_template, context)
        sender = resolve_sender_profile(db, sender_kind="STUDIO")
        send_email(
            to_email=user.email,
            subject=subject,
            body=body,
            body_format="TEXT",
            context="PASSWORD_RESET",
            from_email=sender.from_email,
            from_name=sender.from_name,
            reply_to=sender.reply_to,
            subject_prefix=sender.subject_prefix,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Unable to process forgot-password flow")

    return ForgotPasswordResponse(message=DEFAULT_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> ResetPasswordResponse:
    token = payload.token.strip()
    now = datetime.now(timezone.utc)
    token_hash = _hash_reset_token(token)

    token_row = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at >= now,
        )
    )
    if token_row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token invalide ou expire",
        )

    user = db.scalar(select(User).where(User.id == token_row.user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token invalide ou expire",
        )

    user.hashed_password = hash_password(payload.password)
    user.updated_at = now
    token_row.used_at = now

    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.id != token_row.id,
        )
        .values(used_at=now)
    )

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc.__class__.__name__}",
        ) from exc

    return ResetPasswordResponse(message="Mot de passe mis a jour")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return current_user
