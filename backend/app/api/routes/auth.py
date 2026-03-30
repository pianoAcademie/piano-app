from __future__ import annotations

import hashlib
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.catalog import CourseSession, CourseType
from app.models.client_group import ClientGroup, ClientGroupMembership
from app.models.family import ClientFamilyLink
from app.models.ops import AppSetting, PasswordResetToken
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.schemas.auth import (
    EmailLookupRequest,
    EmailLookupResponse,
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
from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET,
    resolve_frontend_base_url,
    resolve_predefined_template,
    resolve_sender_profile,
)
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


def _synthetic_client_email(*, prefix: str) -> str:
    return f"{prefix}+{uuid4().hex[:16]}@piano-academie.invalid"


def _unique_synthetic_client_email(db: Session, *, prefix: str) -> str:
    email = _synthetic_client_email(prefix=prefix)
    while db.scalar(select(User.id).where(User.email == email)) is not None:
        email = _synthetic_client_email(prefix=prefix)
    return email


def _normalize_match_text(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    collapsed = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    return re.sub(r"\s+", " ", collapsed)


def _resolve_trial_group_label(*, course_type_name: str, is_child_registration: bool) -> str | None:
    normalized = _normalize_match_text(course_type_name)
    if not normalized:
        return None
    tokens = set(normalized.split(" "))
    if "eveil" in normalized and "musical" in normalized:
        return "eveil musical" if is_child_registration else None
    if "collectif" not in normalized:
        return None
    if "enfant" in normalized:
        return "collectif enfant" if is_child_registration else None
    if tokens.intersection({"ado", "ados", "adolescent", "adolescents"}):
        return "collectif ado" if is_child_registration else "collectif adulte"
    if tokens.intersection({"adulte", "adultes", "adult", "adults"}):
        return "collectif ado" if is_child_registration else "collectif adulte"
    return None


def _find_active_group_id(db: Session, *, label: str) -> UUID | None:
    normalized_target = _normalize_match_text(label)
    if not normalized_target:
        return None
    target_tokens = [token for token in normalized_target.split(" ") if token]
    groups = db.scalars(select(ClientGroup).where(ClientGroup.active.is_(True)).order_by(ClientGroup.name.asc())).all()

    exact_match: UUID | None = None
    partial_matches: list[tuple[int, UUID]] = []
    for group in groups:
        candidates = {
            _normalize_match_text(group.name),
            _normalize_match_text(group.code),
        }
        if normalized_target in candidates:
            exact_match = group.id
            break
        for candidate in candidates:
            if candidate and all(token in candidate for token in target_tokens):
                partial_matches.append((len(candidate), group.id))
                break
    if exact_match is not None:
        return exact_match
    if partial_matches:
        partial_matches.sort(key=lambda item: (item[0], str(item[1])))
        return partial_matches[0][1]
    return None


def _ensure_group_membership(db: Session, *, user_id: UUID, group_id: UUID) -> None:
    existing = db.scalar(
        select(ClientGroupMembership.id).where(
            ClientGroupMembership.user_id == user_id,
            ClientGroupMembership.group_id == group_id,
        )
    )
    if existing is None:
        db.add(ClientGroupMembership(user_id=user_id, group_id=group_id))


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
        candidate = resolve_frontend_base_url(db)
    if not candidate:
        candidate = "http://localhost:3000"
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _password_reset_template(db: Session) -> tuple[str, str, str]:
    try:
        template = resolve_predefined_template(db, code=PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET)
        if not template.get("active", True):
            return DEFAULT_PASSWORD_RESET_SUBJECT, DEFAULT_PASSWORD_RESET_BODY, "TEXT"
        subject = str(template.get("subject") or "").strip() or DEFAULT_PASSWORD_RESET_SUBJECT
        body = str(template.get("body") or "").strip() or DEFAULT_PASSWORD_RESET_BODY
        body_format = "HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT"
        return subject, body, body_format
    except Exception:
        return DEFAULT_PASSWORD_RESET_SUBJECT, DEFAULT_PASSWORD_RESET_BODY, "TEXT"


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    normalized_email = payload.email.strip().lower()
    residence_country = payload.residence_country.upper()
    address_country = (payload.address_country or payload.residence_country).upper()
    preferred_currency = payload.preferred_currency.upper()
    timezone_name = _validate_timezone(payload.timezone)
    parent_first_name = _normalize_optional(payload.first_name)
    parent_last_name = _normalize_optional(payload.last_name)
    phone = _normalize_optional(payload.phone)
    address_line = _normalize_optional(payload.address_line)
    postal_code = _normalize_optional(payload.postal_code)
    city = _normalize_optional(payload.city)
    child_first_name = _normalize_optional(payload.child_first_name)
    child_last_name = _normalize_optional(payload.child_last_name)
    is_child_registration = payload.registration_subject_type == "child"

    if not parent_first_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="First name is required")
    if not parent_last_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Last name is required")
    if not phone:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Phone is required")
    if not address_line:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Address line is required")
    if not postal_code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Postal code is required")
    if not city:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="City is required")
    if len(address_country) != 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Address country is required")
    if is_child_registration and not child_first_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Child first name is required")
    if is_child_registration and not child_last_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Child last name is required")
    if is_child_registration and payload.child_birth_date is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Child birth date is required")

    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    trial_course_type_name: str | None = None
    if payload.trial_session_id is not None:
        trial_row = db.execute(
            select(CourseSession, CourseType)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .where(CourseSession.id == payload.trial_session_id)
        ).first()
        if trial_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trial session not found")
        _, trial_course_type = trial_row
        trial_course_type_name = trial_course_type.name

    primary_status = ClientStatus.TRIAL if payload.trial_session_id is not None else ClientStatus.ACTIVE
    portal_user: User
    now = datetime.now(timezone.utc)
    hashed_password = hash_password(payload.password)
    relationship_label = "parent"

    if is_child_registration:
        parent_user = User(
            email=normalized_email,
            hashed_password=hashed_password,
            role=UserRole.CLIENT,
            first_name=parent_first_name,
            last_name=parent_last_name,
            address_line=address_line,
            postal_code=postal_code,
            city=city,
            address_country=address_country,
            phone=phone,
            mobile_phone_1=phone,
            birth_date=None,
            private_note=None,
            residence_country=residence_country,
            preferred_currency=preferred_currency,
            timezone=timezone_name,
            client_kind=ClientKind.ADULT,
            client_status=ClientStatus.RESPONSABLE,
            is_active=True,
            email_opt_in=bool(payload.transactional_email_opt_in),
            sms_opt_in=bool(payload.transactional_sms_opt_in),
            lesson_reminder_email_opt_in=bool(payload.transactional_email_opt_in),
            lesson_reminder_sms_opt_in=bool(payload.transactional_sms_opt_in),
            updated_at=now,
        )
        parent_label = " ".join(part for part in [parent_first_name, parent_last_name] if part).strip()
        child_private_note = None
        if parent_label:
            child_private_note = f"Responsable legal: {parent_label}"
        child_user = User(
            email=_unique_synthetic_client_email(db, prefix="child"),
            hashed_password=hashed_password,
            role=UserRole.CLIENT,
            first_name=child_first_name,
            last_name=child_last_name,
            address_line=address_line,
            postal_code=postal_code,
            city=city,
            address_country=address_country,
            phone=None,
            mobile_phone_1=None,
            birth_date=payload.child_birth_date,
            private_note=child_private_note,
            residence_country=residence_country,
            preferred_currency=preferred_currency,
            timezone=timezone_name,
            client_kind=ClientKind.CHILD,
            client_status=primary_status,
            is_active=True,
            email_opt_in=False,
            sms_opt_in=False,
            lesson_reminder_email_opt_in=False,
            lesson_reminder_sms_opt_in=False,
            updated_at=now,
        )
        db.add(parent_user)
        db.add(child_user)
        db.flush()
        db.add(
            ClientFamilyLink(
                adult_user_id=parent_user.id,
                child_user_id=child_user.id,
                relationship_label=relationship_label,
                is_billing_recipient=True,
                updated_at=now,
            )
        )
        group_label = _resolve_trial_group_label(
            course_type_name=trial_course_type_name or "",
            is_child_registration=True,
        )
        if group_label is not None:
            group_id = _find_active_group_id(db, label=group_label)
            if group_id is not None:
                _ensure_group_membership(db, user_id=child_user.id, group_id=group_id)
        portal_user = parent_user
    else:
        user = User(
            email=normalized_email,
            hashed_password=hashed_password,
            role=UserRole.CLIENT,
            first_name=parent_first_name,
            last_name=parent_last_name,
            address_line=address_line,
            postal_code=postal_code,
            city=city,
            address_country=address_country,
            phone=phone,
            mobile_phone_1=phone,
            birth_date=None,
            private_note=None,
            residence_country=residence_country,
            preferred_currency=preferred_currency,
            timezone=timezone_name,
            client_kind=ClientKind.ADULT,
            client_status=primary_status,
            is_active=True,
            email_opt_in=bool(payload.transactional_email_opt_in),
            sms_opt_in=bool(payload.transactional_sms_opt_in),
            lesson_reminder_email_opt_in=bool(payload.transactional_email_opt_in),
            lesson_reminder_sms_opt_in=bool(payload.transactional_sms_opt_in),
            updated_at=now,
        )
        db.add(user)
        group_label = _resolve_trial_group_label(
            course_type_name=trial_course_type_name or "",
            is_child_registration=False,
        )
        if group_label is not None:
            db.flush()
            group_id = _find_active_group_id(db, label=group_label)
            if group_id is not None:
                _ensure_group_membership(db, user_id=user.id, group_id=group_id)
        portal_user = user

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

    db.refresh(portal_user)
    return portal_user


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


@router.post("/email-lookup", response_model=EmailLookupResponse)
def email_lookup(payload: EmailLookupRequest, db: Session = Depends(get_db)) -> EmailLookupResponse:
    normalized_email = payload.email.strip().lower()
    user = db.scalar(select(User.id).where(User.email == normalized_email))
    return EmailLookupResponse(email=normalized_email, exists=user is not None)


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
        subject_template, body_template, body_format = _password_reset_template(db)
        subject = _render_template(subject_template, context)
        body = _render_template(body_template, context)
        sender = resolve_sender_profile(db, sender_kind="STUDIO")
        send_email(
            to_email=user.email,
            subject=subject,
            body=body,
            body_format=body_format,
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
