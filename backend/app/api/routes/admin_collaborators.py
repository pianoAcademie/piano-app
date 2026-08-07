from __future__ import annotations

import hashlib
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.catalog import CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.ops import (
    AppSetting,
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationSenderCategory,
    MessageFormat,
    PasswordResetToken,
)
from app.models.payout import PayoutStatus, ProfessorHourlyRate, ProfessorSalaryPayment, ProfessorSessionPayout
from app.models.professor_access import ProfessorPermission
from app.models.professor_contract import (
    ProfessorContractGrid,
    ProfessorContractGridLine,
    ProfessorContractGridLineRule,
    ProfessorContractLineMode,
)
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminProfessorContractGridLineInput,
    AdminProfessorContractGridLineOut,
    AdminProfessorContractGridOut,
    AdminProfessorContractGridRuleInput,
    AdminProfessorContractGridRuleOut,
    AdminProfessorContractGridUpsertRequest,
    AdminProfessorContractLocationOptionOut,
    AdminCollaboratorMessageOut,
    AdminCollaboratorMessageRequest,
    AdminCollaboratorSendPasswordOut,
    AdminProfessorContractDeleteOut,
    AdminProfessorContractOut,
    AdminProfessorCreateRequest,
    AdminProfessorDetailOut,
    AdminProfessorPayoutLedgerOut,
    AdminProfessorPayoutLedgerRowOut,
    AdminProfessorRateOut,
    AdminProfessorRateRuleInput,
    AdminProfessorRateRuleOut,
    AdminProfessorRatesUpdateRequest,
    AdminProfessorSalaryPaymentCreateRequest,
    AdminProfessorSalaryPaymentOut,
    AdminProfessorUpdateRequest,
    AdminProfessorUpdateResult,
    ProfessorPermissionOut,
    ProfessorPermissionUpdateRequest,
)
from app.services.i18n import normalize_language
from app.services.professor_activation import (
    generate_temporary_password,
)
from app.services.professor_contracts import (
    CONTRACT_LOCATION_OPTIONS,
    contract_mode_from_course_type,
    label_for_contract_location,
    normalize_contract_location_code,
)
from app.services.professor_default_grid import load_default_professor_grid
from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET,
    resolve_predefined_template,
    resolve_sender_profile,
)
from app.services.email_delivery import send_email
from app.services.professor_permissions import (
    DEFAULT_PROFESSOR_PERMISSIONS,
    PERMISSION_FIELDS,
    ensure_permissions_row,
    permissions_dict,
)
from app.services.payouts import resolve_hourly_rate_for_session
from app.services.communication_journal import COMMUNICATION_TYPE_OPERATIONAL, log_communication
from app.services.session_notifications import send_session_operation_email
from app.services.providers.sms import send_provider_sms
from app.services.security import hash_password

router = APIRouter(prefix="/admin/collaborators")
SUPPORTED_RATE_CURRENCIES = {"EUR", "USD"}
ACCOUNT_ALLOWED_CURRENCIES_KEY = "config_account_allowed_currencies"
ACCOUNT_DEFAULT_CURRENCY_KEY = "config_account_default_currency"
MAX_CONTRACT_FILE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTRACT_MIME_TYPES = {"application/pdf", "application/x-pdf"}
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
PHONE_CLEAN_RE = re.compile(r"[^\d+]+")
DEFAULT_RESET_SUBJECT = "Activation de votre acces collaborateur Piano Academie"
DEFAULT_RESET_BODY = (
    "Bonjour {full_name},\n\n"
    "Votre acces collaborateur est pret.\n"
    "Pour definir votre mot de passe, utilisez ce lien (valable 24h):\n"
    "{reset_url}\n\n"
    "Piano Academie"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_required(value: str | None, field_name: str) -> str:
    if value is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} is required")
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} is required")
    return normalized


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_phone_recipient(value: str | None) -> str | None:
    candidate = PHONE_CLEAN_RE.sub("", (value or "").strip())
    if candidate.startswith("00"):
        candidate = f"+{candidate[2:]}"
    if not candidate:
        return None
    if candidate.startswith("+"):
        digits = candidate[1:]
        if (not digits.isdigit()) or len(digits) < 8:
            return None
        return f"+{digits}"
    if (not candidate.isdigit()) or len(candidate) < 8:
        return None
    return candidate


def _normalize_languages(values: list[str] | None) -> list[str]:
    if values is None:
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = raw.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)

    return deduped


def _serialize_languages(values: list[str]) -> str | None:
    if not values:
        return None
    return ", ".join(values)


def _deserialize_languages(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _currency_settings(db: Session) -> tuple[list[str], str]:
    raw_allowed = db.scalar(select(AppSetting.value).where(AppSetting.key == ACCOUNT_ALLOWED_CURRENCIES_KEY))
    allowed_codes: list[str] = []
    seen: set[str] = set()
    for raw in (raw_allowed or "EUR,USD").split(","):
        code = raw.strip().upper()
        if not code or code in seen or code not in SUPPORTED_RATE_CURRENCIES:
            continue
        seen.add(code)
        allowed_codes.append(code)
    if not allowed_codes:
        allowed_codes = ["EUR"]

    raw_default = db.scalar(select(AppSetting.value).where(AppSetting.key == ACCOUNT_DEFAULT_CURRENCY_KEY))
    default_code = (raw_default or "EUR").strip().upper()
    if default_code not in SUPPORTED_RATE_CURRENCIES:
        default_code = "EUR"
    if default_code not in allowed_codes:
        default_code = allowed_codes[0]

    return allowed_codes, default_code


def _setting_value(db: Session, key: str, default: str) -> str:
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == key))
    if value is None:
        return default
    candidate = value.strip()
    return candidate or default


def _activation_login_url(db: Session) -> str:
    website = _setting_value(db, "config_account_website", "")
    if not website:
        return "http://localhost:3000/login"
    if website.startswith("http://") or website.startswith("https://"):
        return website.rstrip("/") + "/login"
    return f"https://{website.rstrip('/')}/login"


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        return normalized.strip()


def _send_professor_password_reset_link(
    db: Session,
    *,
    user: User,
    first_name: str,
    last_name: str,
) -> tuple[str, datetime]:
    now = _utcnow()
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
    expires_at = now + timedelta(hours=24)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_reset_token(raw_token),
            expires_at=expires_at,
        )
    )

    login_url = _activation_login_url(db)
    reset_url = f"{login_url}?reset_token={raw_token}"
    full_name = f"{first_name} {last_name}".strip() or user.email
    context = {
        "first_name": first_name or user.email,
        "last_name": last_name,
        "full_name": full_name,
        "email": user.email,
        "reset_url": reset_url,
        "login_url": login_url,
    }

    try:
        template = resolve_predefined_template(
            db,
            code=PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET,
            language=normalize_language(user.preferred_language),
        )
        subject_template = str(template.get("subject") or "").strip() or DEFAULT_RESET_SUBJECT
        body_template = str(template.get("body") or "").strip() or DEFAULT_RESET_BODY
        body_format = "HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT"
    except Exception:
        subject_template = DEFAULT_RESET_SUBJECT
        body_template = DEFAULT_RESET_BODY
        body_format = "TEXT"

    sender = resolve_sender_profile(db, sender_kind="TEACHER")
    message_id = send_email(
        to_email=user.email,
        subject=_render_template(subject_template, context),
        body=_render_template(body_template, context),
        body_format=body_format,
        context="PROFESSOR_PASSWORD_RESET",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        # Avoid FK lock contention on users during locked collaborator updates.
        recipient_user_id=None,
    )
    return message_id, expires_at


def _validate_currency(code: str, *, allowed_codes: list[str]) -> str:
    normalized = code.strip().upper()
    if normalized not in allowed_codes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Currency not allowed: {normalized}",
        )
    return normalized


def _permission_out(row: ProfessorPermission | None, *, legacy_if_missing: bool = False) -> ProfessorPermissionOut:
    payload = permissions_dict(row, legacy_if_missing=legacy_if_missing)
    return ProfessorPermissionOut(**payload)


def _contract_out(professor: Professor) -> AdminProfessorContractOut | None:
    if not professor.contract_file_name or not professor.contract_file_data or not professor.contract_uploaded_at:
        return None
    return AdminProfessorContractOut(
        file_name=professor.contract_file_name,
        content_type=professor.contract_content_type or "application/pdf",
        size_bytes=len(professor.contract_file_data),
        uploaded_at=professor.contract_uploaded_at,
    )


def _load_professor_or_404(db: Session, professor_id: UUID, *, lock: bool = False) -> Professor:
    stmt = select(Professor).where(Professor.id == professor_id)
    if lock:
        stmt = stmt.with_for_update()

    professor = db.scalar(stmt)
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor not found")
    return professor


def _find_user_by_email(db: Session, email: str, *, lock: bool = False) -> User | None:
    stmt = select(User).where(User.email == email)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _validate_headcount_rules(line: AdminProfessorContractGridLineInput, *, line_index: int) -> None:
    ranges: list[tuple[int, int | None]] = []
    for idx, rule in enumerate(line.rules):
        if rule.max_students is not None and rule.max_students < rule.min_students:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Line {line_index + 1} rule {idx + 1}: max_students must be >= min_students",
            )
        ranges.append((rule.min_students, rule.max_students))

    ranges.sort(key=lambda item: (item[0], item[1] if item[1] is not None else 10**9))
    for idx, (min_students, max_students) in enumerate(ranges):
        if idx == 0:
            continue
        previous_min, previous_max = ranges[idx - 1]
        if previous_max is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Line {line_index + 1}: overlapping headcount rules",
            )
        if min_students <= previous_max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Line {line_index + 1}: overlapping headcount rules",
            )


def _normalize_professor_rate_rules(rules: list[AdminProfessorRateRuleInput], *, rate_label: str) -> list[dict[str, object]]:
    if not rules:
        return []

    ranges: list[tuple[int, int | None]] = []
    normalized: list[dict[str, object]] = []
    for idx, rule in enumerate(rules):
        max_students = rule.max_students
        if max_students is not None and max_students < rule.min_students:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{rate_label} rule {idx + 1}: max_students must be >= min_students",
            )
        ranges.append((rule.min_students, max_students))
        normalized.append(
            {
                "min_students": int(rule.min_students),
                "max_students": int(max_students) if max_students is not None else None,
                "hourly_rate": str(_quantize_money(Decimal(rule.hourly_rate))),
            }
        )

    ranges.sort(key=lambda item: (item[0], item[1] if item[1] is not None else 10**9))
    for idx, (min_students, _) in enumerate(ranges):
        if idx == 0:
            continue
        previous_min, previous_max = ranges[idx - 1]
        if previous_max is None or min_students <= previous_max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{rate_label}: overlapping headcount rules",
            )
    return normalized


def _serialize_professor_rate_rules(raw_rules: object) -> list[AdminProfessorRateRuleOut]:
    if not isinstance(raw_rules, list):
        return []

    rows: list[AdminProfessorRateRuleOut] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        try:
            min_students = int(raw_rule.get("min_students"))
        except (TypeError, ValueError):
            continue
        if min_students < 0:
            continue

        max_students_raw = raw_rule.get("max_students")
        if max_students_raw is None:
            max_students: int | None = None
        else:
            try:
                max_students = int(max_students_raw)
            except (TypeError, ValueError):
                continue
            if max_students < min_students:
                continue

        try:
            hourly_rate = _quantize_money(Decimal(str(raw_rule.get("hourly_rate"))))
        except Exception:
            continue
        if hourly_rate < 0:
            continue
        rows.append(
            AdminProfessorRateRuleOut(
                min_students=min_students,
                max_students=max_students,
                hourly_rate=hourly_rate,
            )
        )

    rows.sort(key=lambda row: (row.min_students, row.max_students if row.max_students is not None else 10**9))
    return rows


def _validate_contract_payload(payload: AdminProfessorContractGridUpsertRequest) -> tuple[str | None, str | None]:
    if payload.valid_to is not None and payload.valid_to < payload.valid_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="valid_to must be >= valid_from")
    try:
        location_code = normalize_contract_location_code(payload.location_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    notes = _normalize_optional(payload.notes)
    if not payload.lines and payload.clone_from_grid_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one contract line is required")

    return location_code, notes


def _load_course_types_for_contract_lines(
    db: Session,
    *,
    lines: list[AdminProfessorContractGridLineInput],
) -> dict[UUID, CourseType]:
    course_type_ids: list[UUID] = []
    seen: set[UUID] = set()
    for line in lines:
        if line.course_type_id in seen:
            continue
        seen.add(line.course_type_id)
        course_type_ids.append(line.course_type_id)

    if not course_type_ids:
        return {}

    rows = db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all()
    by_id = {row.id: row for row in rows}
    missing = [str(course_type_id) for course_type_id in course_type_ids if course_type_id not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course type(s) not found: {', '.join(missing)}",
        )
    return by_id


def _validate_contract_line(
    line: AdminProfessorContractGridLineInput,
    *,
    line_index: int,
    location_code: str | None,
    course_type: CourseType,
) -> None:
    if contract_mode_from_course_type(course_type) == ProfessorContractLineMode.PRESENTIEL and location_code is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Line {line_index + 1}: location_code is required for PRESENTIEL",
        )
    if line.default_hourly_rate is None and not line.rules:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Line {line_index + 1}: default_hourly_rate or at least one headcount rule is required",
        )
    _validate_headcount_rules(line, line_index=line_index)


def _serialize_contract_grid_lines(
    db: Session,
    *,
    grid_id: UUID,
) -> list[AdminProfessorContractGridLineOut]:
    lines = db.scalars(
        select(ProfessorContractGridLine)
        .where(ProfessorContractGridLine.grid_id == grid_id)
        .order_by(ProfessorContractGridLine.display_order.asc(), ProfessorContractGridLine.created_at.asc())
    ).all()
    if not lines:
        return []

    line_ids = [line.id for line in lines]
    course_type_ids = sorted({line.course_type_id for line in lines if line.course_type_id is not None})
    course_types = (
        db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all()
        if course_type_ids
        else []
    )
    course_type_name_by_id = {row.id: row.name for row in course_types}
    rules_rows = db.scalars(
        select(ProfessorContractGridLineRule)
        .where(ProfessorContractGridLineRule.line_id.in_(line_ids))
        .order_by(
            ProfessorContractGridLineRule.line_id.asc(),
            ProfessorContractGridLineRule.display_order.asc(),
            ProfessorContractGridLineRule.min_students.asc(),
            ProfessorContractGridLineRule.created_at.asc(),
        )
    ).all()
    rules_by_line: dict[UUID, list[AdminProfessorContractGridRuleOut]] = {line_id: [] for line_id in line_ids}
    for rule in rules_rows:
        rules_by_line.setdefault(rule.line_id, []).append(
            AdminProfessorContractGridRuleOut(
                id=rule.id,
                min_students=rule.min_students,
                max_students=rule.max_students,
                hourly_rate=rule.hourly_rate,
                display_order=rule.display_order,
            )
        )

    return [
        AdminProfessorContractGridLineOut(
            id=line.id,
            course_type_id=line.course_type_id,
            course_type_name=course_type_name_by_id.get(line.course_type_id, line.service_type),
            service_type=line.service_type,
            mode=line.mode,
            reference_duration_minutes=line.reference_duration_minutes,
            default_hourly_rate=line.default_hourly_rate,
            display_order=line.display_order,
            rules=rules_by_line.get(line.id, []),
        )
        for line in lines
    ]


def _serialize_contract_grid(
    db: Session,
    *,
    grid: ProfessorContractGrid,
    on_date: date,
) -> AdminProfessorContractGridOut:
    is_active_today = grid.valid_from <= on_date and (grid.valid_to is None or grid.valid_to >= on_date)
    return AdminProfessorContractGridOut(
        id=grid.id,
        professor_id=grid.professor_id,
        valid_from=grid.valid_from,
        valid_to=grid.valid_to,
        location_code=grid.location_code,
        location_label=label_for_contract_location(grid.location_code),
        notes=grid.notes,
        is_active_today=is_active_today,
        lines=_serialize_contract_grid_lines(db, grid_id=grid.id),
        created_at=grid.created_at,
        updated_at=grid.updated_at,
    )


def _load_contract_grid_or_404(db: Session, *, professor_id: UUID, grid_id: UUID, lock: bool = False) -> ProfessorContractGrid:
    stmt = select(ProfessorContractGrid).where(ProfessorContractGrid.id == grid_id, ProfessorContractGrid.professor_id == professor_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract grid not found")
    return row


def _apply_grid_lines(
    db: Session,
    *,
    grid_id: UUID,
    lines: list[AdminProfessorContractGridLineInput],
    course_types_by_id: dict[UUID, CourseType],
) -> None:
    db.execute(
        delete(ProfessorContractGridLineRule).where(
            ProfessorContractGridLineRule.line_id.in_(
                select(ProfessorContractGridLine.id).where(ProfessorContractGridLine.grid_id == grid_id)
            )
        )
    )
    db.execute(delete(ProfessorContractGridLine).where(ProfessorContractGridLine.grid_id == grid_id))

    for line_index, line in enumerate(lines):
        course_type = course_types_by_id[line.course_type_id]
        line_row = ProfessorContractGridLine(
            grid_id=grid_id,
            course_type_id=course_type.id,
            display_order=line_index,
            service_type=course_type.name.strip(),
            mode=contract_mode_from_course_type(course_type),
            reference_duration_minutes=course_type.duration_minutes,
            default_hourly_rate=_quantize_money(Decimal(line.default_hourly_rate)) if line.default_hourly_rate is not None else None,
        )
        db.add(line_row)
        db.flush()

        for rule_index, rule in enumerate(line.rules):
            db.add(
                ProfessorContractGridLineRule(
                    line_id=line_row.id,
                    display_order=rule_index,
                    min_students=rule.min_students,
                    max_students=rule.max_students,
                    hourly_rate=_quantize_money(Decimal(rule.hourly_rate)),
                )
            )


def _clone_grid_payload(
    db: Session,
    *,
    source_grid_id: UUID,
) -> list[AdminProfessorContractGridLineInput]:
    source_grid = db.scalar(select(ProfessorContractGrid).where(ProfessorContractGrid.id == source_grid_id))
    if source_grid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source contract grid not found")

    source_lines = db.scalars(
        select(ProfessorContractGridLine)
        .where(ProfessorContractGridLine.grid_id == source_grid_id)
        .order_by(ProfessorContractGridLine.display_order.asc(), ProfessorContractGridLine.created_at.asc())
    ).all()

    if not source_lines:
        return []

    line_ids = [line.id for line in source_lines]
    source_rules = db.scalars(
        select(ProfessorContractGridLineRule)
        .where(ProfessorContractGridLineRule.line_id.in_(line_ids))
        .order_by(
            ProfessorContractGridLineRule.line_id.asc(),
            ProfessorContractGridLineRule.display_order.asc(),
            ProfessorContractGridLineRule.min_students.asc(),
            ProfessorContractGridLineRule.created_at.asc(),
        )
    ).all()
    rules_by_line: dict[UUID, list[ProfessorContractGridLineRule]] = {line_id: [] for line_id in line_ids}
    for row in source_rules:
        rules_by_line.setdefault(row.line_id, []).append(row)

    course_types = db.scalars(select(CourseType)).all()

    def _normalize_name(value: str) -> str:
        return " ".join(value.strip().casefold().split())

    by_exact_name: dict[str, list[CourseType]] = {}
    for course_type in course_types:
        by_exact_name.setdefault(_normalize_name(course_type.name), []).append(course_type)

    def _infer_course_type_id(line: ProfessorContractGridLine) -> UUID | None:
        if line.course_type_id is not None:
            return line.course_type_id

        candidates = by_exact_name.get(_normalize_name(line.service_type), [])
        if not candidates:
            return None

        expected_mode = line.mode
        for candidate in candidates:
            if contract_mode_from_course_type(candidate) == expected_mode:
                return candidate.id
        return candidates[0].id

    cloned_lines: list[AdminProfessorContractGridLineInput] = []
    for line in source_lines:
        inferred_course_type_id = _infer_course_type_id(line)
        if inferred_course_type_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Source line {line.display_order + 1} is not linked to a known activity",
            )
        cloned_lines.append(
            AdminProfessorContractGridLineInput(
                course_type_id=inferred_course_type_id,
                default_hourly_rate=line.default_hourly_rate,
                rules=[
                    AdminProfessorContractGridRuleInput(
                        min_students=rule.min_students,
                        max_students=rule.max_students,
                        hourly_rate=rule.hourly_rate,
                    )
                    for rule in rules_by_line.get(line.id, [])
                ],
            )
        )

    return cloned_lines


def _to_detail(
    professor: Professor,
    *,
    linked_user: User | None,
    permission_row: ProfessorPermission | None,
    legacy_permissions_if_missing: bool = False,
    payout_balance_amount: Decimal = Decimal("0.00"),
    payout_balance_currency: str | None = None,
    payout_balance_as_of: date | None = None,
) -> AdminProfessorDetailOut:
    return AdminProfessorDetailOut(
        id=professor.id,
        first_name=professor.first_name,
        last_name=professor.last_name,
        email=professor.email,
        phone=professor.phone,
        siret=professor.siret,
        iban=professor.iban,
        address_line=professor.address_line,
        teacher_invoice_counter=max(1, int(professor.teacher_invoice_counter or 1)),
        teacher_is_vat_applicable=bool(professor.teacher_is_vat_applicable),
        teacher_vat_rate=professor.teacher_vat_rate,
        teacher_siret=professor.teacher_siret,
        teacher_iban=professor.teacher_iban,
        teacher_company_name=professor.teacher_company_name,
        teacher_company_address=professor.teacher_company_address,
        zoom_link=professor.zoom_link,
        spoken_languages=_deserialize_languages(professor.spoken_languages),
        payout_currency=professor.payout_currency,
        payout_balance_amount=_quantize_money(Decimal(payout_balance_amount)),
        payout_balance_currency=(payout_balance_currency or professor.payout_currency),
        payout_balance_as_of=payout_balance_as_of,
        role=linked_user.role if linked_user is not None else UserRole.PROF,
        is_coach=professor.is_coach,
        active=professor.active,
        user_is_active=linked_user.is_active if linked_user is not None else False,
        daily_schedule_email_enabled=professor.daily_schedule_email_enabled,
        daily_schedule_email_time=professor.daily_schedule_email_time,
        daily_schedule_skip_if_no_course=professor.daily_schedule_skip_if_no_course,
        contract=_contract_out(professor),
        permissions=_permission_out(permission_row, legacy_if_missing=legacy_permissions_if_missing),
        created_at=professor.created_at,
        updated_at=professor.updated_at,
        last_activation_email_sent_at=professor.last_activation_email_sent_at,
    )


def _session_duration_hours(session_obj: CourseSession) -> Decimal:
    return _quantize_money(
        Decimal((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds()) / Decimal(3600)
    )


def _calculate_professor_due_amount(
    db: Session,
    *,
    professor: Professor,
    as_of_exclusive: datetime,
    default_grid_lines: list[object] | None,
) -> Decimal:
    rows = db.execute(
        select(CourseSession, ProfessorSessionPayout)
        .outerjoin(ProfessorSessionPayout, ProfessorSessionPayout.session_id == CourseSession.id)
        .where(
            CourseSession.professor_id == professor.id,
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.end_at_utc < as_of_exclusive,
        )
        .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
    ).all()

    cumulative_due = Decimal("0.00")
    for session_obj, payout in rows:
        amount: Decimal | None = None
        payout_status = payout.payout_status if payout is not None else None

        if payout is not None:
            amount = _quantize_money(Decimal(payout.amount_snapshot))
        else:
            resolved_rate = resolve_hourly_rate_for_session(
                db,
                session_obj=session_obj,
                on_date=session_obj.start_at_utc.date(),
                default_grid_lines=default_grid_lines,
            )
            if resolved_rate is not None:
                duration_hours = _session_duration_hours(session_obj)
                hourly_rate = _quantize_money(Decimal(resolved_rate.hourly_rate))
                amount = _quantize_money(duration_hours * hourly_rate)

        counted_in_due = False
        if amount is not None:
            if payout_status in (PayoutStatus.PENDING, PayoutStatus.APPROVED):
                counted_in_due = True
            elif payout_status is None:
                counted_in_due = True
        if counted_in_due and amount is not None:
            cumulative_due = _quantize_money(cumulative_due + amount)

    return _quantize_money(cumulative_due)


def _ensure_professor_payout_rows_until_reference(
    db: Session,
    *,
    professor: Professor,
    as_of_exclusive: datetime,
    default_grid_lines: list[object] | None,
) -> None:
    sessions = db.scalars(
        select(CourseSession)
        .where(
            CourseSession.professor_id == professor.id,
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.end_at_utc < as_of_exclusive,
        )
        .order_by(CourseSession.end_at_utc.asc(), CourseSession.id.asc())
        .with_for_update()
    ).all()

    for session_obj in sessions:
        existing = db.scalar(
            select(ProfessorSessionPayout)
            .where(ProfessorSessionPayout.session_id == session_obj.id)
            .with_for_update()
        )
        if existing is not None:
            continue

        resolved_rate = resolve_hourly_rate_for_session(
            db,
            session_obj=session_obj,
            on_date=session_obj.start_at_utc.date(),
            default_grid_lines=default_grid_lines,
        )
        if resolved_rate is None:
            continue

        duration_hours = _session_duration_hours(session_obj)
        hourly_rate = _quantize_money(Decimal(resolved_rate.hourly_rate))
        amount = _quantize_money(duration_hours * hourly_rate)

        db.add(
            ProfessorSessionPayout(
                session_id=session_obj.id,
                professor_id=professor.id,
                duration_hours=duration_hours,
                hourly_rate_snapshot=hourly_rate,
                currency_snapshot=(
                    (resolved_rate.currency_code or professor.payout_currency or "EUR").strip().upper()[:3] or "EUR"
                ),
                amount_snapshot=amount,
                payout_status=PayoutStatus.PENDING,
            )
        )


def _serialize_salary_payment(
    *,
    payment: ProfessorSalaryPayment,
    professor: Professor,
) -> AdminProfessorSalaryPaymentOut:
    return AdminProfessorSalaryPaymentOut(
        id=payment.id,
        professor_id=payment.professor_id,
        professor_first_name=professor.first_name,
        professor_last_name=professor.last_name,
        professor_email=professor.email,
        reference_date=payment.reference_date,
        payment_date=payment.payment_date,
        invoice_number=payment.invoice_number,
        payment_method=payment.payment_method,
        amount_excl_vat=_quantize_money(Decimal(payment.amount_excl_vat)),
        amount_incl_vat=_quantize_money(Decimal(payment.amount_incl_vat)),
        currency_code=payment.currency_code,
        settled_payout_count=int(payment.settled_payout_count or 0),
        actor_user_id=payment.actor_user_id,
        created_at=payment.created_at,
    )


@router.get("", response_model=list[AdminProfessorDetailOut])
def list_collaborators(
    search: str | None = Query(default=None, min_length=1, max_length=255),
    active_only: bool = False,
    payout_as_of: date | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_access_collaborators")),
) -> list[AdminProfessorDetailOut]:
    stmt = select(Professor)

    if active_only:
        stmt = stmt.where(Professor.active.is_(True))

    for search_token in [token for token in (search or "").strip().split() if token]:
        pattern = f"%{search_token}%"
        stmt = stmt.where(
            or_(
                Professor.email.ilike(pattern),
                Professor.first_name.ilike(pattern),
                Professor.last_name.ilike(pattern),
            )
        )

    professors = db.scalars(stmt.order_by(Professor.last_name.asc(), Professor.first_name.asc()).limit(limit)).all()
    if not professors:
        return []

    emails = [prof.email for prof in professors]
    ids = [prof.id for prof in professors]

    users = db.scalars(select(User).where(User.email.in_(emails))).all()
    users_by_email = {row.email: row for row in users}

    permissions = db.scalars(select(ProfessorPermission).where(ProfessorPermission.professor_id.in_(ids))).all()
    permissions_by_professor = {row.professor_id: row for row in permissions}

    as_of_date = payout_as_of or date.today()
    as_of_exclusive = datetime.combine(as_of_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    default_grid_lines, _ = load_default_professor_grid(db)

    return [
        _to_detail(
            prof,
            linked_user=users_by_email.get(prof.email),
            permission_row=permissions_by_professor.get(prof.id),
            legacy_permissions_if_missing=True,
            payout_balance_amount=_calculate_professor_due_amount(
                db,
                professor=prof,
                as_of_exclusive=as_of_exclusive,
                default_grid_lines=default_grid_lines,
            ),
            payout_balance_currency=prof.payout_currency,
            payout_balance_as_of=as_of_date,
        )
        for prof in professors
    ]


@router.post("/messages", response_model=AdminCollaboratorMessageOut)
def send_collaborators_message(
    payload: AdminCollaboratorMessageRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCollaboratorMessageOut:
    requested_ids: list[UUID] = []
    seen: set[UUID] = set()
    for collaborator_id in payload.collaborator_ids:
        if collaborator_id in seen:
            continue
        seen.add(collaborator_id)
        requested_ids.append(collaborator_id)

    if not requested_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No collaborator selected")

    channel = payload.channel.value
    subject = payload.subject.strip()
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subject and body are required")
    if channel == "EMAIL" and not subject:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subject and body are required")

    professors = db.scalars(select(Professor).where(Professor.id.in_(requested_ids))).all()
    professor_by_id = {prof.id: prof for prof in professors}
    professor_emails = {(prof.email or "").strip().lower() for prof in professors if (prof.email or "").strip()}
    linked_users = db.scalars(
        select(User).where(func.lower(User.email).in_(professor_emails))
    ).all() if professor_emails else []
    linked_user_by_email = {(row.email or "").strip().lower(): row for row in linked_users}
    sender_label = f"{(actor.first_name or '').strip()} {(actor.last_name or '').strip()}".strip() or actor.email

    sent_count = 0
    skipped_count = 0
    details: list[str] = []

    if channel == "SMS":
        sms_body = body
        if payload.body_format.value == "HTML":
            sms_body = re.sub(r"<[^>]+>", " ", sms_body)
        sms_body = re.sub(r"\s{2,}", " ", sms_body).strip()
        if not sms_body:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SMS vide apres normalisation")

    for collaborator_id in requested_ids:
        professor = professor_by_id.get(collaborator_id)
        if professor is None:
            skipped_count += 1
            details.append(f"{collaborator_id}: collaborator not found")
            continue

        linked_user = linked_user_by_email.get((professor.email or "").strip().lower())

        if channel == "EMAIL":
            email = (professor.email or "").strip().lower()
            if not email:
                skipped_count += 1
                details.append(f"{collaborator_id}: missing email")
                continue

            send_session_operation_email(
                to_email=email,
                subject=subject,
                body=body,
                body_format=payload.body_format.value,
                operation="ADMIN_COLLABORATORS_MESSAGE",
                session_title="COLLABORATORS",
                sender_user_id=actor.id,
                sender_label=sender_label,
                sender_category=CommunicationSenderCategory.OTHER_USER,
                professor_id=professor.id,
                recipient_user_id=linked_user.id if linked_user is not None else None,
            )
        else:
            phone = _normalize_phone_recipient(professor.phone)
            if not phone:
                skipped_count += 1
                details.append(f"{collaborator_id}: missing phone")
                continue
            sms_result = send_provider_sms(
                to_phone=phone,
                message=sms_body,
                context="ADMIN_COLLABORATORS_MESSAGE_SMS",
                subject=subject or "SMS collaborateurs",
                recipient_user_id=linked_user.id if linked_user is not None else None,
                db=db,
            )
            if not sms_result.ok:
                skipped_count += 1
                details.append(f"{collaborator_id}: {sms_result.error_message or 'SMS delivery failed'}")
                continue
        sent_count += 1

    if channel == "SMS":
        db.commit()

    return AdminCollaboratorMessageOut(
        channel=payload.channel,
        requested_count=len(requested_ids),
        sent_count=sent_count,
        skipped_count=skipped_count,
        details=details,
    )


@router.post("", response_model=AdminProfessorUpdateResult, status_code=status.HTTP_201_CREATED)
def create_collaborator(
    payload: AdminProfessorCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorUpdateResult:
    allowed_currencies, default_currency = _currency_settings(db)
    email = payload.email.strip().lower()
    first_name = _normalize_required(payload.first_name, "first_name")
    last_name = _normalize_required(payload.last_name, "last_name")

    existing_prof = db.scalar(select(Professor).where(Professor.email == email))
    if existing_prof is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Professor email already in use")

    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already in use")

    now = _utcnow()
    spoken_languages = _normalize_languages(payload.spoken_languages)
    bootstrap_password = generate_temporary_password()
    teacher_is_vat_applicable = bool(payload.teacher_is_vat_applicable)
    teacher_vat_rate = payload.teacher_vat_rate
    if teacher_is_vat_applicable and teacher_vat_rate is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="teacher_vat_rate is required when VAT applies")
    if (not teacher_is_vat_applicable) and teacher_vat_rate is not None:
        teacher_vat_rate = None

    professor = Professor(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=_normalize_optional(payload.phone),
        siret=_normalize_optional(payload.siret),
        iban=_normalize_optional(payload.iban),
        address_line=_normalize_optional(payload.address_line),
        teacher_invoice_counter=max(1, int(payload.teacher_invoice_counter or 1)),
        teacher_is_vat_applicable=teacher_is_vat_applicable,
        teacher_vat_rate=teacher_vat_rate,
        teacher_siret=_normalize_optional(payload.teacher_siret) or _normalize_optional(payload.siret),
        teacher_iban=_normalize_optional(payload.teacher_iban) or _normalize_optional(payload.iban),
        teacher_company_name=_normalize_optional(payload.teacher_company_name) or f"{first_name} {last_name}".strip(),
        teacher_company_address=_normalize_optional(payload.teacher_company_address) or _normalize_optional(payload.address_line),
        zoom_link=_normalize_optional(payload.zoom_link),
        spoken_languages=_serialize_languages(spoken_languages),
        payout_currency=_validate_currency(payload.payout_currency or default_currency, allowed_codes=allowed_currencies),
        is_coach=payload.is_coach,
        active=True,
        daily_schedule_email_enabled=bool(payload.daily_schedule_email_enabled),
        daily_schedule_email_time=payload.daily_schedule_email_time.strip(),
        daily_schedule_skip_if_no_course=bool(payload.daily_schedule_skip_if_no_course),
        last_activation_email_sent_at=now,
        updated_at=now,
    )
    db.add(professor)
    db.flush()

    linked_user = User(
        email=email,
        hashed_password=hash_password(bootstrap_password),
        role=UserRole.ADMIN if payload.is_admin else UserRole.PROF,
        first_name=first_name,
        last_name=last_name,
        phone=_normalize_optional(payload.phone),
        is_active=True,
        updated_at=now,
    )
    db.add(linked_user)
    db.flush()

    seed_permissions = payload.permissions.model_dump() if payload.permissions is not None else DEFAULT_PROFESSOR_PERMISSIONS
    # Business rule: a collaborator must always be able to see their own planning
    # and record attendance without receiving full planning edit rights.
    seed_permissions["can_view_planning"] = True
    seed_permissions["can_take_attendance"] = True
    permission_row = ensure_permissions_row(db, professor_id=professor.id, defaults=seed_permissions)

    activation_email_message_id, _ = _send_professor_password_reset_link(
        db,
        user=linked_user,
        first_name=professor.first_name,
        last_name=professor.last_name,
    )

    db.commit()
    db.refresh(professor)

    detail = _to_detail(professor, linked_user=linked_user, permission_row=permission_row)
    return AdminProfessorUpdateResult(
        professor=detail,
        activation_email_sent=True,
        activation_email_message_id=activation_email_message_id,
    )


@router.get("/{professor_id}", response_model=AdminProfessorDetailOut)
def get_collaborator(
    professor_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_access_collaborators")),
) -> AdminProfessorDetailOut:
    professor = _load_professor_or_404(db, professor_id)
    linked_user = _find_user_by_email(db, professor.email)
    permission_row = db.scalar(select(ProfessorPermission).where(ProfessorPermission.professor_id == professor_id))
    return _to_detail(professor, linked_user=linked_user, permission_row=permission_row, legacy_permissions_if_missing=True)


@router.post("/{professor_id}/send-password", response_model=AdminCollaboratorSendPasswordOut)
def send_collaborator_password_reset(
    professor_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCollaboratorSendPasswordOut:
    professor = _load_professor_or_404(db, professor_id, lock=True)
    now = _utcnow()
    linked_user = _find_user_by_email(db, professor.email, lock=True)
    if linked_user is None:
        linked_user = User(
            email=professor.email,
            hashed_password=hash_password(generate_temporary_password()),
            role=UserRole.PROF,
            first_name=professor.first_name,
            last_name=professor.last_name,
            phone=professor.phone,
            is_active=bool(professor.active),
            updated_at=now,
        )
        db.add(linked_user)
        db.flush()
    else:
        linked_user.first_name = professor.first_name
        linked_user.last_name = professor.last_name
        linked_user.phone = professor.phone
        linked_user.is_active = bool(professor.active)
        linked_user.updated_at = now
        db.add(linked_user)

    message_id, expires_at = _send_professor_password_reset_link(
        db,
        user=linked_user,
        first_name=professor.first_name,
        last_name=professor.last_name,
    )
    professor.last_activation_email_sent_at = now
    professor.updated_at = now
    db.add(professor)
    db.commit()
    return AdminCollaboratorSendPasswordOut(ok=True, message_id=message_id, expires_at=expires_at)


@router.post("/{professor_id}/contract", response_model=AdminProfessorContractOut)
async def upload_collaborator_contract(
    professor_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorContractOut:
    professor = _load_professor_or_404(db, professor_id, lock=True)

    original_name = Path(file.filename or "").name.strip()
    if not original_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Contract file name is required")
    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only PDF contract files are allowed")

    content_type = (file.content_type or "").strip().lower()
    if content_type and content_type not in ALLOWED_CONTRACT_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid contract content type")

    file_data = await file.read(MAX_CONTRACT_FILE_BYTES + 1)
    if not file_data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Contract file is empty")
    if len(file_data) > MAX_CONTRACT_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Contract file is too large")
    if not file_data.startswith(b"%PDF"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid PDF file")

    professor.contract_file_name = original_name
    professor.contract_content_type = "application/pdf"
    professor.contract_file_data = file_data
    professor.contract_uploaded_at = _utcnow()
    professor.updated_at = professor.contract_uploaded_at
    db.add(professor)
    db.commit()
    db.refresh(professor)

    contract = _contract_out(professor)
    if contract is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Contract could not be stored")
    return contract


@router.get("/{professor_id}/contract")
def download_collaborator_contract(
    professor_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    professor = _load_professor_or_404(db, professor_id)
    if not professor.contract_file_data or not professor.contract_file_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    content_type = professor.contract_content_type or "application/pdf"
    file_name = professor.contract_file_name.replace('"', "")
    return Response(
        content=professor.contract_file_data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{professor_id}/contract", response_model=AdminProfessorContractDeleteOut)
def delete_collaborator_contract(
    professor_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorContractDeleteOut:
    professor = _load_professor_or_404(db, professor_id, lock=True)
    had_contract = bool(professor.contract_file_data and professor.contract_file_name)

    professor.contract_file_name = None
    professor.contract_content_type = None
    professor.contract_file_data = None
    professor.contract_uploaded_at = None
    professor.updated_at = _utcnow()
    db.add(professor)
    db.commit()

    return AdminProfessorContractDeleteOut(deleted=had_contract)


@router.patch("/{professor_id}", response_model=AdminProfessorUpdateResult)
def patch_collaborator(
    professor_id: UUID,
    payload: AdminProfessorUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorUpdateResult:
    professor = _load_professor_or_404(db, professor_id, lock=True)
    allowed_currencies, default_currency = _currency_settings(db)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        linked_user = _find_user_by_email(db, professor.email)
        permission_row = db.scalar(select(ProfessorPermission).where(ProfessorPermission.professor_id == professor_id))
        return AdminProfessorUpdateResult(
            professor=_to_detail(professor, linked_user=linked_user, permission_row=permission_row, legacy_permissions_if_missing=True),
            activation_email_sent=False,
            activation_email_message_id=None,
        )

    now = _utcnow()
    previous_active = bool(professor.active)

    linked_user = _find_user_by_email(db, professor.email, lock=True)

    if "email" in changes:
        new_email = _normalize_required(changes["email"], "email").lower()
        existing_prof = db.scalar(select(Professor).where(Professor.email == new_email, Professor.id != professor.id))
        if existing_prof is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Professor email already in use")

        user_conflict = db.scalar(select(User).where(User.email == new_email))
        if user_conflict is not None and (linked_user is None or user_conflict.id != linked_user.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already in use")

        professor.email = new_email

    if "first_name" in changes:
        professor.first_name = _normalize_required(changes["first_name"], "first_name")

    if "last_name" in changes:
        professor.last_name = _normalize_required(changes["last_name"], "last_name")

    if "phone" in changes:
        professor.phone = _normalize_optional(changes["phone"])

    if "siret" in changes:
        professor.siret = _normalize_optional(changes["siret"])

    if "iban" in changes:
        professor.iban = _normalize_optional(changes["iban"])

    if "address_line" in changes:
        professor.address_line = _normalize_optional(changes["address_line"])

    if "teacher_invoice_counter" in changes and changes["teacher_invoice_counter"] is not None:
        professor.teacher_invoice_counter = max(1, int(changes["teacher_invoice_counter"]))

    if "teacher_is_vat_applicable" in changes:
        professor.teacher_is_vat_applicable = bool(changes["teacher_is_vat_applicable"])

    if "teacher_vat_rate" in changes:
        professor.teacher_vat_rate = changes["teacher_vat_rate"]

    if "teacher_siret" in changes:
        professor.teacher_siret = _normalize_optional(changes["teacher_siret"])

    if "teacher_iban" in changes:
        professor.teacher_iban = _normalize_optional(changes["teacher_iban"])

    if "teacher_company_name" in changes:
        professor.teacher_company_name = _normalize_optional(changes["teacher_company_name"])

    if "teacher_company_address" in changes:
        professor.teacher_company_address = _normalize_optional(changes["teacher_company_address"])

    if "zoom_link" in changes:
        professor.zoom_link = _normalize_optional(changes["zoom_link"])

    if "spoken_languages" in changes:
        professor.spoken_languages = _serialize_languages(_normalize_languages(changes["spoken_languages"]))

    if "payout_currency" in changes:
        requested_payout_currency = _normalize_required(changes["payout_currency"], "payout_currency").upper()
        professor.payout_currency = _validate_currency(
            requested_payout_currency or default_currency,
            allowed_codes=allowed_currencies,
        )

    if "is_coach" in changes:
        professor.is_coach = bool(changes["is_coach"])

    if "daily_schedule_email_enabled" in changes:
        professor.daily_schedule_email_enabled = bool(changes["daily_schedule_email_enabled"])

    if "daily_schedule_email_time" in changes and changes["daily_schedule_email_time"] is not None:
        professor.daily_schedule_email_time = str(changes["daily_schedule_email_time"]).strip()

    if "daily_schedule_skip_if_no_course" in changes:
        professor.daily_schedule_skip_if_no_course = bool(changes["daily_schedule_skip_if_no_course"])

    if bool(professor.teacher_is_vat_applicable) and professor.teacher_vat_rate is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="teacher_vat_rate is required when VAT applies")
    if (not bool(professor.teacher_is_vat_applicable)) and professor.teacher_vat_rate is not None:
        professor.teacher_vat_rate = None

    if linked_user is None:
        bootstrap_password = generate_temporary_password()
        linked_user = User(
            email=professor.email,
            hashed_password=hash_password(str(bootstrap_password)),
            role=UserRole.ADMIN if bool(changes.get("is_admin", False)) else UserRole.PROF,
            first_name=professor.first_name,
            last_name=professor.last_name,
            phone=professor.phone,
            is_active=False,
            updated_at=now,
        )
        db.add(linked_user)
        db.flush()
    else:
        linked_user.email = professor.email

    if "is_admin" in changes:
        linked_user.role = UserRole.ADMIN if bool(changes["is_admin"]) else UserRole.PROF

    linked_user.first_name = professor.first_name
    linked_user.last_name = professor.last_name
    linked_user.phone = professor.phone

    activation_email_sent = False
    activation_email_message_id: str | None = None

    if "active" in changes:
        target_active = bool(changes["active"])
        professor.active = target_active

        if target_active and not previous_active:
            linked_user.is_active = True
            professor.last_activation_email_sent_at = now
            activation_email_message_id, _ = _send_professor_password_reset_link(
                db,
                user=linked_user,
                first_name=professor.first_name,
                last_name=professor.last_name,
            )
            activation_email_sent = True
        elif not target_active:
            linked_user.is_active = False
    else:
        linked_user.is_active = professor.active

    professor.updated_at = now
    linked_user.updated_at = now

    permission_row = ensure_permissions_row(db, professor_id=professor.id, lock=True)

    db.commit()
    db.refresh(professor)

    return AdminProfessorUpdateResult(
        professor=_to_detail(professor, linked_user=linked_user, permission_row=permission_row),
        activation_email_sent=activation_email_sent,
        activation_email_message_id=activation_email_message_id,
    )


@router.put("/{professor_id}/permissions", response_model=ProfessorPermissionOut)
def update_collaborator_permissions(
    professor_id: UUID,
    payload: ProfessorPermissionUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProfessorPermissionOut:
    professor = _load_professor_or_404(db, professor_id, lock=True)
    row = ensure_permissions_row(db, professor_id=professor_id, lock=True)
    linked_user = _find_user_by_email(db, professor.email, lock=True)

    values = payload.model_dump()
    is_admin = values.pop("is_admin", None)
    teacher_profile = bool(values.pop("teacher_profile", False))
    manager_profile = bool(values.pop("manager_profile", False))
    planning_simulation_location_id = values.pop("planning_simulation_location_id", None)
    check_deposits_location_id = values.pop("check_deposits_location_id", None)

    can_take_attendance = bool(values.get("can_take_attendance"))
    can_edit_own_sessions = bool(values.get("can_edit_own_sessions"))
    can_manage_other_teachers = bool(values.get("can_manage_other_teachers_students_and_sessions"))
    can_view_other_sessions = bool(values.get("can_view_other_teachers_sessions")) or can_manage_other_teachers

    can_manage_students = bool(
        values.get("can_view_student_parent_addresses_phones")
        or values.get("can_view_student_parent_emails")
        or values.get("can_view_student_attachments")
        or can_manage_other_teachers
    )
    can_manage_invoices = bool(values.get("can_manage_invoices_and_accounts"))
    can_manage_website_news = bool(values.get("can_manage_website_and_news"))
    can_view_reports = bool(values.get("can_create_and_view_reports"))

    # Compatibility bridge: keep legacy permission flags coherent with the
    # new privilege matrix used in the BackOffice.
    values["can_view_planning"] = can_take_attendance or can_edit_own_sessions or can_view_other_sessions
    values["can_edit_planning"] = can_edit_own_sessions or can_manage_other_teachers
    values["can_view_all_school_sessions"] = can_view_other_sessions
    values["can_force_booking"] = can_manage_other_teachers
    values["can_view_clients"] = can_manage_students
    values["can_export_clients"] = bool(values.get("can_view_student_attachments"))
    values["can_message_clients"] = bool(values.get("can_message_clients"))
    values["can_edit_payments"] = bool(values.get("can_record_payments_with_attendance")) or can_manage_invoices
    values["can_list_payments"] = can_manage_invoices
    values["can_access_cash_menu"] = bool(values.get("can_manage_expenses_and_other_income"))
    values["can_manage_mobile_news"] = can_manage_website_news
    values["can_configure_app"] = can_manage_website_news
    values["can_view_admin_dashboard"] = can_view_reports
    values["can_access_collaborators"] = bool(values.get("can_view_other_teachers_contacts")) or can_view_other_sessions
    values["can_manage_events"] = can_edit_own_sessions or can_manage_other_teachers
    values["can_view_dashboard"] = bool(values.get("can_view_pay_details")) or can_view_reports
    values["can_view_admin_reservations"] = can_view_other_sessions

    if teacher_profile:
        for field in PERMISSION_FIELDS:
            values[field] = False
        values["can_view_dashboard"] = True
        values["can_view_planning"] = True
        values["can_take_attendance"] = True
        values["can_message_clients"] = True
        values["can_view_pay_details"] = True
        if is_admin is None:
            is_admin = False

    if manager_profile:
        values["can_view_planning"] = True
        values["can_edit_planning"] = True
        values["can_view_all_school_sessions"] = True
        values["can_view_planning_simulation"] = True
        values["can_view_clients"] = True
        values["can_access_collaborators"] = True
        values["can_view_intakes"] = True
        values["can_view_quotes"] = True
        if is_admin is None:
            is_admin = False

    for field in PERMISSION_FIELDS:
        setattr(row, field, bool(values[field]))
    if planning_simulation_location_id is not None:
        if db.scalar(select(Location.id).where(Location.id == planning_simulation_location_id).limit(1)) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
        row.planning_simulation_location_id = planning_simulation_location_id
    else:
        row.planning_simulation_location_id = None
    if check_deposits_location_id is not None:
        if db.scalar(select(Location.id).where(Location.id == check_deposits_location_id).limit(1)) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
        row.check_deposits_location_id = check_deposits_location_id
    else:
        row.check_deposits_location_id = None

    row.updated_at = _utcnow()
    db.add(row)

    if is_admin is not None and linked_user is not None:
        linked_user.role = UserRole.ADMIN if bool(is_admin) else UserRole.PROF
        linked_user.updated_at = _utcnow()
        db.add(linked_user)

    db.commit()
    db.refresh(row)

    return ProfessorPermissionOut(**permissions_dict(row))


@router.get("/{professor_id}/rates", response_model=list[AdminProfessorRateOut])
def list_collaborator_rates(
    professor_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorRateOut]:
    _load_professor_or_404(db, professor_id)

    rows = db.execute(
        select(ProfessorHourlyRate, CourseType)
        .outerjoin(CourseType, CourseType.id == ProfessorHourlyRate.course_type_id)
        .where(ProfessorHourlyRate.professor_id == professor_id)
        .order_by(ProfessorHourlyRate.valid_to.is_(None).desc(), ProfessorHourlyRate.valid_from.desc(), CourseType.name.asc())
    ).all()

    return [
        AdminProfessorRateOut(
            id=rate.id,
            course_type_id=rate.course_type_id,
            course_type_name=course_type.name if course_type is not None else "Global",
            currency_code=rate.currency_code,
            hourly_rate=_quantize_money(Decimal(rate.hourly_rate)) if rate.hourly_rate is not None else None,
            rules=_serialize_professor_rate_rules(rate.headcount_rules_json),
            valid_from=rate.valid_from,
            valid_to=rate.valid_to,
        )
        for rate, course_type in rows
    ]


@router.put("/{professor_id}/rates", response_model=list[AdminProfessorRateOut])
def update_collaborator_rates(
    professor_id: UUID,
    payload: AdminProfessorRatesUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorRateOut]:
    professor = _load_professor_or_404(db, professor_id)
    allowed_currencies, default_currency = _currency_settings(db)
    effective_from = payload.effective_from or date.today()
    clear_course_type_ids = {course_type_id for course_type_id in payload.clear_course_type_ids}

    if not payload.rates and not clear_course_type_ids:
        return list_collaborator_rates(professor_id=professor_id, db=db, _=_)

    unique_rates: dict[str, tuple[UUID | None, Decimal | None, str, list[dict[str, object]], date, date | None]] = {}
    for row_index, row in enumerate(payload.rates):
        fallback_currency = professor.payout_currency if professor.payout_currency in allowed_currencies else default_currency
        currency = _validate_currency((row.currency_code or fallback_currency), allowed_codes=allowed_currencies)
        normalized_rules = _normalize_professor_rate_rules(
            row.rules,
            rate_label=f"Rate {row_index + 1}",
        )
        if row.course_type_id is None and normalized_rules:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rate {row_index + 1}: global headcount rules are not supported",
            )
        hourly_rate = _quantize_money(Decimal(row.hourly_rate)) if row.hourly_rate is not None else None
        if hourly_rate is not None and hourly_rate < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rate {row_index + 1}: hourly_rate must be >= 0",
            )
        if hourly_rate is None and not normalized_rules:
            continue
        row_valid_from = row.valid_from or effective_from
        row_valid_to = row.valid_to
        if row_valid_to is not None and row_valid_to < row_valid_from:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rate {row_index + 1}: valid_to must be >= valid_from",
            )
        dedupe_key = (
            f"{row.course_type_id or '__GLOBAL__'}:{row_valid_from.isoformat()}:{row_valid_to.isoformat() if row_valid_to else ''}"
        )
        unique_rates[dedupe_key] = (row.course_type_id, hourly_rate, currency, normalized_rules, row_valid_from, row_valid_to)

    if not unique_rates:
        unique_rate_course_type_ids = set()
    else:
        unique_rate_course_type_ids = {course_type_id for course_type_id, *_ in unique_rates.values() if course_type_id is not None}

    course_type_ids = [course_type_id for course_type_id, *_ in unique_rates.values() if course_type_id is not None]
    course_type_ids.extend(clear_course_type_ids)
    course_type_ids = list(dict.fromkeys(course_type_ids))
    course_types = db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all() if course_type_ids else []
    found_ids = {row.id for row in course_types}
    missing = [str(course_type_id) for course_type_id in course_type_ids if course_type_id not in found_ids]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course type(s) not found: {', '.join(missing)}")

    def _truncate_overlapping_rows(
        *,
        course_type_id: UUID | None,
        start_date: date,
        end_date: date | None,
    ) -> None:
        stmt = (
            select(ProfessorHourlyRate)
            .where(
                ProfessorHourlyRate.professor_id == professor_id,
                ProfessorHourlyRate.course_type_id == course_type_id,
                ProfessorHourlyRate.location_id.is_(None),
                or_(ProfessorHourlyRate.valid_to.is_(None), ProfessorHourlyRate.valid_to >= start_date),
            )
            .with_for_update()
            .order_by(ProfessorHourlyRate.valid_from.asc(), ProfessorHourlyRate.created_at.asc())
        )
        if end_date is not None:
            stmt = stmt.where(ProfessorHourlyRate.valid_from <= end_date)
        overlapping_rows = db.scalars(stmt).all()

        for row in overlapping_rows:
            row_start = row.valid_from
            row_end = row.valid_to
            if end_date is not None and row_start > end_date:
                continue
            if row_start < start_date:
                split_tail = (
                    end_date is not None
                    and row_end is not None
                    and row_end > end_date
                ) or (
                    end_date is not None
                    and row_end is None
                )
                previous_end = row_end
                row.valid_to = start_date - timedelta(days=1)
                if split_tail:
                    db.add(
                        ProfessorHourlyRate(
                            professor_id=row.professor_id,
                            course_type_id=row.course_type_id,
                            location_id=row.location_id,
                            currency_code=row.currency_code,
                            hourly_rate=row.hourly_rate,
                            headcount_rules_json=row.headcount_rules_json,
                            valid_from=end_date + timedelta(days=1),
                            valid_to=previous_end,
                        )
                    )
                continue
            db.delete(row)

    clear_only_course_type_ids = clear_course_type_ids - unique_rate_course_type_ids
    for course_type_id in clear_only_course_type_ids:
        _truncate_overlapping_rows(
            course_type_id=course_type_id,
            start_date=effective_from,
            end_date=None,
        )

    for course_type_id, hourly_rate, currency_code, normalized_rules, row_valid_from, row_valid_to in unique_rates.values():
        _truncate_overlapping_rows(
            course_type_id=course_type_id,
            start_date=row_valid_from,
            end_date=row_valid_to,
        )

        db.add(
            ProfessorHourlyRate(
                professor_id=professor_id,
                course_type_id=course_type_id,
                location_id=None,
                currency_code=currency_code,
                hourly_rate=hourly_rate,
                headcount_rules_json=normalized_rules,
                valid_from=row_valid_from,
                valid_to=row_valid_to,
            )
        )

    db.commit()

    return list_collaborator_rates(professor_id=professor_id, db=db, _=_)


@router.get("/{professor_id}/payout-ledger", response_model=AdminProfessorPayoutLedgerOut)
def get_collaborator_payout_ledger(
    professor_id: UUID,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorPayoutLedgerOut:
    professor = _load_professor_or_404(db, professor_id)
    as_of_date = as_of or date.today()
    as_of_exclusive = datetime.combine(as_of_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    rows = db.execute(
        select(CourseSession, CourseType, Location, ProfessorSessionPayout)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(ProfessorSessionPayout, ProfessorSessionPayout.session_id == CourseSession.id)
        .where(
            CourseSession.professor_id == professor_id,
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.end_at_utc < as_of_exclusive,
        )
        .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
    ).all()

    default_grid_lines, _ = load_default_professor_grid(db)
    cumulative_due = Decimal("0.00")
    ledger_rows: list[AdminProfessorPayoutLedgerRowOut] = []

    for session_obj, course_type, location, payout in rows:
        duration_hours = _session_duration_hours(session_obj)
        hourly_rate: Decimal | None = None
        amount: Decimal | None = None
        currency: str | None = None
        payout_status = payout.payout_status if payout is not None else None

        if payout is not None:
            hourly_rate = _quantize_money(Decimal(payout.hourly_rate_snapshot))
            amount = _quantize_money(Decimal(payout.amount_snapshot))
            currency = payout.currency_snapshot
        else:
            resolved_rate = resolve_hourly_rate_for_session(
                db,
                session_obj=session_obj,
                on_date=session_obj.start_at_utc.date(),
                default_grid_lines=default_grid_lines,
            )
            if resolved_rate is not None:
                hourly_rate = _quantize_money(Decimal(resolved_rate.hourly_rate))
                amount = _quantize_money(duration_hours * hourly_rate)
                currency = resolved_rate.currency_code

        counted_in_due = False
        if amount is not None:
            if payout_status in (PayoutStatus.PENDING, PayoutStatus.APPROVED):
                counted_in_due = True
            elif payout_status is None:
                counted_in_due = True

        if counted_in_due and amount is not None:
            cumulative_due = _quantize_money(cumulative_due + amount)

        ledger_rows.append(
            AdminProfessorPayoutLedgerRowOut(
                session_id=session_obj.id,
                start_at_utc=session_obj.start_at_utc,
                end_at_utc=session_obj.end_at_utc,
                course_type_name=course_type.name,
                location_name=location.name,
                duration_hours=duration_hours,
                hourly_rate=hourly_rate,
                amount=amount,
                currency=currency,
                payout_status=payout_status,
                counted_in_due=counted_in_due,
                cumulative_due=cumulative_due,
            )
        )

    ledger_rows.reverse()

    return AdminProfessorPayoutLedgerOut(
        professor_id=professor_id,
        as_of_date=as_of_date,
        currency=(professor.payout_currency or "EUR").strip().upper() or "EUR",
        total_due=_quantize_money(cumulative_due),
        rows=ledger_rows,
    )


@router.get("/salary/payments", response_model=list[AdminProfessorSalaryPaymentOut])
def list_salary_payments(
    reference_date: date | None = None,
    professor_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorSalaryPaymentOut]:
    stmt = (
        select(ProfessorSalaryPayment, Professor)
        .join(Professor, Professor.id == ProfessorSalaryPayment.professor_id)
        .order_by(ProfessorSalaryPayment.payment_date.desc(), ProfessorSalaryPayment.created_at.desc())
        .limit(limit)
    )
    if reference_date is not None:
        stmt = stmt.where(ProfessorSalaryPayment.reference_date == reference_date)
    if professor_id is not None:
        stmt = stmt.where(ProfessorSalaryPayment.professor_id == professor_id)

    rows = db.execute(stmt).all()
    return [
        _serialize_salary_payment(payment=payment, professor=professor)
        for payment, professor in rows
    ]


@router.post("/{professor_id}/salary-payments", response_model=AdminProfessorSalaryPaymentOut, status_code=status.HTTP_201_CREATED)
def create_salary_payment(
    professor_id: UUID,
    payload: AdminProfessorSalaryPaymentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorSalaryPaymentOut:
    professor = _load_professor_or_404(db, professor_id)
    invoice_number = _normalize_required(payload.invoice_number, "invoice_number")
    amount_excl_vat = _quantize_money(Decimal(payload.amount_excl_vat))
    amount_incl_vat = _quantize_money(Decimal(payload.amount_incl_vat))
    if amount_incl_vat < amount_excl_vat:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount_incl_vat must be greater than or equal to amount_excl_vat",
        )

    reference_exclusive = datetime.combine(payload.reference_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    default_grid_lines, _ = load_default_professor_grid(db)
    _ensure_professor_payout_rows_until_reference(
        db,
        professor=professor,
        as_of_exclusive=reference_exclusive,
        default_grid_lines=default_grid_lines,
    )

    payouts = db.scalars(
        select(ProfessorSessionPayout)
        .join(CourseSession, CourseSession.id == ProfessorSessionPayout.session_id)
        .where(
            ProfessorSessionPayout.professor_id == professor_id,
            ProfessorSessionPayout.payout_status.in_((PayoutStatus.PENDING, PayoutStatus.APPROVED)),
            CourseSession.end_at_utc < reference_exclusive,
        )
        .with_for_update()
    ).all()

    paid_at = datetime.combine(payload.payment_date, datetime.min.time(), tzinfo=timezone.utc)
    for payout in payouts:
        payout.payout_status = PayoutStatus.PAID
        payout.paid_at = paid_at
        db.add(payout)

    currency_code = (professor.payout_currency or "EUR").strip().upper() or "EUR"
    payment = ProfessorSalaryPayment(
        professor_id=professor_id,
        reference_date=payload.reference_date,
        payment_date=payload.payment_date,
        invoice_number=invoice_number,
        payment_method=payload.payment_method,
        amount_excl_vat=amount_excl_vat,
        amount_incl_vat=amount_incl_vat,
        currency_code=currency_code,
        settled_payout_count=len(payouts),
        actor_user_id=current_user.id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return _serialize_salary_payment(payment=payment, professor=professor)


@router.get("/contract-grid/locations", response_model=list[AdminProfessorContractLocationOptionOut])
def list_contract_grid_locations(
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorContractLocationOptionOut]:
    return [AdminProfessorContractLocationOptionOut(code=code, label=label) for code, label in CONTRACT_LOCATION_OPTIONS]


@router.get("/{professor_id}/contract-grids", response_model=list[AdminProfessorContractGridOut])
def list_collaborator_contract_grids(
    professor_id: UUID,
    on_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorContractGridOut]:
    _load_professor_or_404(db, professor_id)
    reference_date = on_date or date.today()
    grids = db.scalars(
        select(ProfessorContractGrid)
        .where(ProfessorContractGrid.professor_id == professor_id)
        .order_by(ProfessorContractGrid.valid_from.desc(), ProfessorContractGrid.created_at.desc())
    ).all()
    return [_serialize_contract_grid(db, grid=grid, on_date=reference_date) for grid in grids]


@router.post("/{professor_id}/contract-grids", response_model=AdminProfessorContractGridOut, status_code=status.HTTP_201_CREATED)
def create_collaborator_contract_grid(
    professor_id: UUID,
    payload: AdminProfessorContractGridUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorContractGridOut:
    _load_professor_or_404(db, professor_id)
    location_code, notes = _validate_contract_payload(payload)

    lines = payload.lines
    if not lines and payload.clone_from_grid_id is not None:
        lines = _clone_grid_payload(db, source_grid_id=payload.clone_from_grid_id)
    if not lines:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No contract lines to persist")
    course_types_by_id = _load_course_types_for_contract_lines(db, lines=lines)
    for line_index, line in enumerate(lines):
        _validate_contract_line(
            line,
            line_index=line_index,
            location_code=location_code,
            course_type=course_types_by_id[line.course_type_id],
        )

    now = _utcnow()
    grid = ProfessorContractGrid(
        professor_id=professor_id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        location_code=location_code,
        notes=notes,
        updated_at=now,
    )
    db.add(grid)
    db.flush()

    _apply_grid_lines(db, grid_id=grid.id, lines=lines, course_types_by_id=course_types_by_id)
    db.commit()
    db.refresh(grid)

    return _serialize_contract_grid(db, grid=grid, on_date=date.today())


@router.put("/{professor_id}/contract-grids/{grid_id}", response_model=AdminProfessorContractGridOut)
def update_collaborator_contract_grid(
    professor_id: UUID,
    grid_id: UUID,
    payload: AdminProfessorContractGridUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorContractGridOut:
    _load_professor_or_404(db, professor_id)
    grid = _load_contract_grid_or_404(db, professor_id=professor_id, grid_id=grid_id, lock=True)
    location_code, notes = _validate_contract_payload(payload)

    lines = payload.lines
    if not lines and payload.clone_from_grid_id is not None:
        lines = _clone_grid_payload(db, source_grid_id=payload.clone_from_grid_id)
    if not lines:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No contract lines to persist")
    course_types_by_id = _load_course_types_for_contract_lines(db, lines=lines)
    for line_index, line in enumerate(lines):
        _validate_contract_line(
            line,
            line_index=line_index,
            location_code=location_code,
            course_type=course_types_by_id[line.course_type_id],
        )

    grid.valid_from = payload.valid_from
    grid.valid_to = payload.valid_to
    grid.location_code = location_code
    grid.notes = notes
    grid.updated_at = _utcnow()
    db.add(grid)
    db.flush()

    _apply_grid_lines(db, grid_id=grid.id, lines=lines, course_types_by_id=course_types_by_id)
    db.commit()
    db.refresh(grid)

    return _serialize_contract_grid(db, grid=grid, on_date=date.today())
