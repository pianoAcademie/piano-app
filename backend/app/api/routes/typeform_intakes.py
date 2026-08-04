from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import logging
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.api.routes.quotes import (
    _effective_item_price,
    _extract_vat_rate,
    _normalized_prospect_type,
    _q2,
    _q3,
    _quote_activity_context,
    _resolve_document_templates,
    _split_ttc,
    create_quote_from_payload,
)
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, DeliveryMode, Location, SessionStatus
from app.models.family import ClientFamilyLink
from app.models.ops import LegalEntity
from app.models.product_catalog import CatalogProduct
from app.models.quote import (
    PaymentPlan,
    PricingActivityPrice,
    PricingCatalog,
    PricingKitPrice,
    PricingProductPrice,
    Prospect,
    QuoteTemplate,
    QuoteType,
    SolfegeLevelRule,
    TermsTemplate,
)
from app.models.referral import ReferralReward
from app.models.typeform_intake import TypeformFormConfig, TypeformIntake
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.schemas.quote import QuoteCreateRequest, QuoteLineIn
from app.schemas.typeform_intake import (
    TypeformIntakeAdminCommentRequest,
    TypeformIntakeAdminStateRequest,
    TypeformAnswerOut,
    TypeformDemoSeedOut,
    TypeformDraftQuoteResultOut,
    TypeformFormConfigQuoteDefaultsRequest,
    TypeformFormConfigOut,
    TypeformIntakeDetailOut,
    TypeformIntakeListPageOut,
    TypeformIntakeListOut,
    TypeformIntakeNormalizedPatchRequest,
    TypeformIntakeReferralRequest,
    TypeformIntakeResolutionRequest,
    TypeformMatchCandidateOut,
    TypeformQuotePreviewLineOut,
    TypeformQuotePreviewOut,
    TypeformSessionMatchOptionOut,
    TypeformSessionRecommendationOut,
    TypeformWebhookOut,
)
from app.services.invoice_documents import normalize_billing_entity
from app.services.intake_local_confirmation import (
    ensure_local_confirmation_assignment,
    notify_local_confirmation_assignee,
)
from app.services.professor_activation import generate_temporary_password
from app.services.quotes.quote_documents import _calendar_snapshot_with_planning_sessions
from app.services.referrals import (
    ensure_referral_for_intake,
    link_referral_to_quote,
    manually_validate_referral,
    normalize_referral_text,
    referral_category_for_location,
    referral_summary,
)
from app.services.security import hash_password

router = APIRouter(prefix="/typeform")
logger = logging.getLogger(__name__)

INTAKE_STATUS_NEW = "NEW"
INTAKE_STATUS_NORMALIZED = "NORMALIZED"
INTAKE_STATUS_MATCHING_REQUIRED = "MATCHING_REQUIRED"
INTAKE_STATUS_READY = "READY_FOR_DRAFT_QUOTE"
INTAKE_STATUS_BLOCKED = "BLOCKED"
INTAKE_STATUS_PROCESSED = "PROCESSED"
INTAKE_STATUS_IGNORED = "IGNORED"

SEGMENTS = {"eveil", "child", "teen", "adult"}
CLIENT_MODE_EXISTING = "existing_client"
CLIENT_MODE_EXISTING_FAMILY = "existing_family"
CLIENT_MODE_NEW_ADULT = "new_adult_prospect"
CLIENT_MODE_NEW_PARENT_CHILD = "new_parent_child_prospect"

DAY_ALIASES = {
    "lundi": 0,
    "monday": 0,
    "lun": 0,
    "mardi": 1,
    "tuesday": 1,
    "mar": 1,
    "mercredi": 2,
    "wednesday": 2,
    "mer": 2,
    "jeudi": 3,
    "thursday": 3,
    "jeu": 3,
    "vendredi": 4,
    "friday": 4,
    "ven": 4,
    "samedi": 5,
    "saturday": 5,
    "sam": 5,
    "dimanche": 6,
    "sunday": 6,
    "dim": 6,
}
DAY_LABELS = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}

DOCUMENT_TARGET_ALIASES = {
    "adult": {"adult", "adulte", "adultes"},
    "child": {"child", "children", "enfant", "enfants"},
    "teen": {"teen", "teens", "ado", "ados", "adolescent", "adolescents"},
    "eveil": {"eveil", "initiation", "early_childhood"},
}


def _recurrence_label(value: object | None) -> str | None:
    raw = _text(value).strip().upper()
    if not raw:
        return None
    if "@" in raw:
        raw, _ = raw.split("@", 1)
    frequency_raw, interval_raw = raw.split(":", 1) if ":" in raw else (raw, "1")
    try:
        interval = int(interval_raw or "1")
    except ValueError:
        interval = 1
    safe_interval = interval if interval > 0 else 1
    if frequency_raw == "DAILY":
        return "Serie quotidienne" if safe_interval == 1 else f"Serie tous les {safe_interval} jours"
    if frequency_raw == "WEEKLY":
        return "Serie hebdo" if safe_interval == 1 else f"Serie toutes les {safe_interval} semaines"
    if frequency_raw == "MONTHLY":
        return "Serie mensuelle" if safe_interval == 1 else f"Serie tous les {safe_interval} mois"
    return raw


def _session_occurrence_label(local_start: datetime, end_at_utc: datetime, timezone_name: str | None) -> tuple[str, str]:
    zone = _safe_zoneinfo(timezone_name)
    local_end = end_at_utc.astimezone(zone)
    date_label = f"{DAY_LABELS[local_start.weekday()]} {local_start.strftime('%d/%m/%Y')}"
    time_range_label = f"{local_start.strftime('%H:%M')}-{local_end.strftime('%H:%M')}"
    return f"{date_label} · {time_range_label}", time_range_label


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _lower(value: object | None) -> str:
    return _text(value).lower()


def _normalize_token(value: object | None) -> str:
    return (
        _lower(value)
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("ç", "c")
    )


def _document_target_tokens(segment: object | None) -> set[str]:
    normalized = _normalize_token(segment)
    if not normalized:
        return set()
    return DOCUMENT_TARGET_ALIASES.get(normalized, {normalized})


def _template_matches_segment_target(template: QuoteTemplate | TermsTemplate, *, segment: object | None) -> bool:
    target_tokens = _document_target_tokens(segment)
    if not target_tokens:
        return False
    template_target = _normalize_token(getattr(template, "target", None))
    if template_target and template_target in target_tokens:
        return True
    haystack = _normalize_token(" ".join(str(getattr(template, field, "") or "") for field in ("code", "name", "description")))
    return any(token and token in haystack for token in target_tokens)


def _configured_document_codes(config: TypeformFormConfig, key: str) -> list[str]:
    configuration_json = getattr(config, "configuration_json", None)
    if not isinstance(configuration_json, dict):
        return []
    raw_value = configuration_json.get(key)
    if isinstance(raw_value, str):
        raw_items = [raw_value]
    elif isinstance(raw_value, list):
        raw_items = raw_value
    else:
        return []
    return [_text(item).upper() for item in raw_items if _text(item)]


def _is_bar_le_duc_value(*values: object | None) -> bool:
    haystack = " ".join(_normalize_token(value) for value in values if value)
    compact = re.sub(r"[^a-z0-9]+", "", haystack)
    words = set(re.split(r"[^a-z0-9]+", haystack))
    return "barleduc" in compact or "bld" in words


def _is_bar_le_duc_config(config: TypeformFormConfig) -> bool:
    configuration_json = getattr(config, "configuration_json", None)
    label = configuration_json.get("label") if isinstance(configuration_json, dict) else None
    return _is_bar_le_duc_value(
        getattr(config, "location_code", None),
        getattr(config, "source_code", None),
        getattr(config, "typeform_form_id", None),
        label,
    )


def _bar_le_duc_document_codes(*, segment: str, document_kind: str) -> list[str]:
    if document_kind == "quote" and segment == "child":
        return [
            "TEMPLATE_DEVIS_COLLECTIF_ENFANTS_BAR_LE_DUC",
            "TEMPLATE_DEVIS_COLLECTIF_ENFANTS_BAR_LE_DUC_EN",
            "TEMPLATE_BAR_LE_DUC_ENFANT",
            "TEMPLATE_BAR_LE_DUC_ENFANTS",
            "TEMPLATE_BLD_ENFANT",
            "TEMPLATE_BLD_ENFANTS",
            "TEMPLATE_COURS_COLLECTIF_ENFANT_BAR_LE_DUC",
            "TEMPLATE_COURS_COLLECTIF_ENFANT_BLD",
        ]
    if document_kind == "quote" and segment == "adult":
        return [
            "TEMPLATE_ADULTE_BAR_LE_DUC",
            "TEMPLATE_ADULTE_BAR_LE_DUC_EN",
            "TEMPLATE_BAR_LE_DUC_ADULTE",
            "TEMPLATE_BAR_LE_DUC_ADULTES",
            "TEMPLATE_BLD_ADULTE",
            "TEMPLATE_BLD_ADULTES",
            "TEMPLATE_COURS_ADULTE_BAR_LE_DUC",
            "TEMPLATE_COURS_ADULTES_BLD",
        ]
    if document_kind == "terms" and segment == "child":
        return [
            "COLLECTIF_ENFANTS_2025_2026_BAR_LE_DUC",
            "COLLECTIF_ENFANTS_2025_2026_BAR_LE_DUC_EN",
            "CGV_BAR_LE_DUC_ENFANTS_2026_2027",
            "CGV_BLD_ENFANTS_2026_2027",
            "CGV_ENFANTS_BAR_LE_DUC_2026_2027",
            "CGV_ENFANTS_BLD_2026_2027",
        ]
    if document_kind == "terms" and segment == "adult":
        return [
            "CONDITIONS_D_ENGAGEMENT_COURS_ADULTES_A_BAR_LE_DUC",
            "CONDITIONS_D_ENGAGEMENT_COURS_ADULTES_A_BAR_LE_DUC_EN",
            "CGV_ADULTES_10_COURS_BAR_LE_DUC",
            "CGV_ADULTES_10_COURS_BAR_LE_DUC_EN",
            "CGV_BAR_LE_DUC_ADULTES_2026_2027",
            "CGV_BLD_ADULTES_2026_2027",
            "CGV_ADULTES_BAR_LE_DUC_2026_2027",
            "CGV_ADULTES_BLD_2026_2027",
        ]
    return []


def _template_matches_bar_le_duc(template: QuoteTemplate | TermsTemplate) -> bool:
    return _is_bar_le_duc_value(
        *(getattr(template, field, None) for field in ("code", "name", "description", "target"))
    )


def _requires_strict_typeform_location_matching(
    *,
    config: TypeformFormConfig | None,
    normalized: dict[str, object],
    runtime_context: dict[str, object],
    resolved_location_id: UUID | None,
) -> bool:
    if resolved_location_id is None:
        return False
    return (
        (config is not None and _is_bar_le_duc_config(config))
        or _is_bar_le_duc_value(normalized.get("requested_location"))
        or _is_bar_le_duc_value(runtime_context.get("location_code"), runtime_context.get("location_name"))
    )


def _preferred_location_document_template(
    candidates: list[QuoteTemplate] | list[TermsTemplate],
    *,
    config: TypeformFormConfig,
    segment: str,
    language: str,
) -> QuoteTemplate | TermsTemplate | None:
    if not _is_bar_le_duc_config(config):
        return None
    language_candidates = [
        item
        for item in candidates
        if not getattr(item, "language", None) or _normalize_token(item.language) == language
    ]
    return next(
        (
            item
            for item in language_candidates
            if _template_matches_bar_le_duc(item) and _template_matches_segment_target(item, segment=segment)
        ),
        None,
    )


def _quote_template_by_code(db: Session, *, codes: list[str], language: str) -> QuoteTemplate | None:
    normalized_codes = {code.strip().upper() for code in codes if code.strip()}
    if not normalized_codes:
        return None
    candidates = db.scalars(
        select(QuoteTemplate)
        .where(
            QuoteTemplate.is_active.is_(True),
            QuoteTemplate.current_version_id.isnot(None),
            func.upper(QuoteTemplate.code).in_(normalized_codes),
        )
    ).all()
    by_code = {candidate.code.upper(): candidate for candidate in candidates}
    for code in codes:
        candidate = by_code.get(code.strip().upper())
        if candidate is None:
            continue
        if getattr(candidate, "language", None) and _normalize_token(candidate.language) != language:
            continue
        return candidate
    return None


def _terms_template_by_code(db: Session, *, codes: list[str], language: str) -> TermsTemplate | None:
    normalized_codes = {code.strip().upper() for code in codes if code.strip()}
    if not normalized_codes:
        return None
    candidates = db.scalars(
        select(TermsTemplate)
        .where(
            TermsTemplate.is_active.is_(True),
            TermsTemplate.current_version_id.isnot(None),
            func.upper(TermsTemplate.code).in_(normalized_codes),
        )
    ).all()
    by_code = {candidate.code.upper(): candidate for candidate in candidates}
    for code in codes:
        candidate = by_code.get(code.strip().upper())
        if candidate is None:
            continue
        if getattr(candidate, "language", None) and _normalize_token(candidate.language) != language:
            continue
        return candidate
    return None


def _preview_lines_include_initiation(preview_lines: list[TypeformQuotePreviewLineOut] | None) -> bool:
    return any("initiation" in _normalize_token(_preview_line_haystack(line)) for line in preview_lines or [])


def _primary_course_modality_for_documents(
    db: Session,
    *,
    preview_lines: list[TypeformQuotePreviewLineOut] | None,
) -> str | None:
    if not preview_lines:
        return None
    activity_ids = [line.activity_id for line in preview_lines if line.activity_id is not None]
    activities = {}
    if activity_ids:
        rows = db.scalars(select(CourseType).where(CourseType.id.in_(activity_ids))).all()
        activities = {row.id: row for row in rows}
    for line in preview_lines:
        if line.activity_id is None:
            continue
        haystack = _normalize_token(_preview_line_haystack(line))
        if "solfege" in haystack:
            continue
        activity = activities.get(line.activity_id)
        modality = _modality_from_delivery_mode(activity.mode if activity is not None else None)
        if modality in {"onsite", "online"}:
            return modality
        if "presentiel" in haystack or "sur place" in haystack:
            return "onsite"
        if "en ligne" in haystack or "online" in haystack or "video" in haystack:
            return "online"
    return None


def _typeform_default_quote_template(
    db: Session,
    *,
    config: TypeformFormConfig,
    preview_lines: list[TypeformQuotePreviewLineOut] | None = None,
) -> QuoteTemplate | None:
    language = _normalize_token(config.default_language) or "fr"
    segment = _normalize_token(config.audience_segment)
    primary_modality = _primary_course_modality_for_documents(db, preview_lines=preview_lines)
    if _preview_lines_include_initiation(preview_lines):
        template = _quote_template_by_code(db, codes=["INITIATION"], language=language)
        if template is not None:
            return template
    configured_codes = _configured_document_codes(config, "default_quote_template_codes")
    location_codes = (
        _bar_le_duc_document_codes(segment=segment, document_kind="quote") if _is_bar_le_duc_config(config) else []
    )
    template = _quote_template_by_code(db, codes=[*configured_codes, *location_codes], language=language)
    if template is not None:
        return template
    candidates = db.scalars(
        select(QuoteTemplate)
        .where(QuoteTemplate.is_active.is_(True), QuoteTemplate.current_version_id.isnot(None))
        .order_by(QuoteTemplate.is_default.desc(), QuoteTemplate.updated_at.desc())
    ).all()
    location_template = _preferred_location_document_template(
        candidates,
        config=config,
        segment=segment,
        language=language,
    )
    if location_template is not None:
        return location_template
    if segment == "child" and primary_modality == "onsite":
        template = _quote_template_by_code(db, codes=["TEMPLATE_COURS_COLLECTIF_ENFANT"], language=language)
        if template is not None:
            return template
    if segment == "child" and primary_modality == "online":
        template = _quote_template_by_code(
            db,
            codes=["TEMPLATE_COURS_COLLECTIF_ENFANT_EN_LIGNE_CONCERT_OPTION"],
            language=language,
        )
        if template is not None:
            return template
    language_candidates = [
        item
        for item in candidates
        if not getattr(item, "language", None) or _normalize_token(item.language) == language
    ]
    return next(
        (item for item in language_candidates if _template_matches_segment_target(item, segment=config.audience_segment)),
        None,
    )


def _typeform_default_terms_template(
    db: Session,
    *,
    config: TypeformFormConfig,
    preview_lines: list[TypeformQuotePreviewLineOut] | None = None,
) -> TermsTemplate | None:
    language = _normalize_token(config.default_language) or "fr"
    segment = _normalize_token(config.audience_segment)
    primary_modality = _primary_course_modality_for_documents(db, preview_lines=preview_lines)
    if _preview_lines_include_initiation(preview_lines):
        template = _terms_template_by_code(db, codes=["CGV_INITIATION_2025"], language=language)
        if template is not None:
            return template
    configured_codes = _configured_document_codes(config, "default_terms_template_codes")
    location_codes = (
        _bar_le_duc_document_codes(segment=segment, document_kind="terms") if _is_bar_le_duc_config(config) else []
    )
    template = _terms_template_by_code(db, codes=[*configured_codes, *location_codes], language=language)
    if template is not None:
        return template
    candidates = db.scalars(
        select(TermsTemplate)
        .where(TermsTemplate.is_active.is_(True), TermsTemplate.current_version_id.isnot(None))
        .order_by(TermsTemplate.updated_at.desc())
    ).all()
    location_template = _preferred_location_document_template(
        candidates,
        config=config,
        segment=segment,
        language=language,
    )
    if location_template is not None:
        return location_template
    if segment == "child" and primary_modality == "onsite":
        template = _terms_template_by_code(
            db,
            codes=["CGV_ENFANTS_GROUPE_2026_2027", "CGV_ENFANTS_COLLECTIFS_2025"],
            language=language,
        )
        if template is not None:
            return template
    if segment == "child" and primary_modality == "online":
        template = _terms_template_by_code(db, codes=["CGV_COURS_EN_LIGNE_ENFANTS_2026_2027"], language=language)
        if template is not None:
            return template
    language_candidates = [
        item
        for item in candidates
        if not getattr(item, "language", None) or _normalize_token(item.language) == language
    ]
    return next(
        (item for item in language_candidates if _template_matches_segment_target(item, segment=config.audience_segment)),
        None,
    )


def _typeform_document_templates_from_binding(
    db: Session,
    *,
    prospect_id: UUID | None,
    client_id: UUID | None,
    context_type: str,
    quote_type_id: UUID | None,
    language: str | None,
    currency: str,
    preview_lines: list[TypeformQuotePreviewLineOut] | None,
) -> tuple[QuoteTemplate | None, TermsTemplate | None]:
    activity_ids = [line.activity_id for line in preview_lines or [] if line.activity_id is not None]
    activity_id, activity_family = _quote_activity_context(db, activity_ids=activity_ids)
    if activity_id is None and activity_family is None:
        return None, None
    prospect_type: str | None = None
    if prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == prospect_id))
        if prospect is not None:
            prospect_type = _normalized_prospect_type(prospect.meta or {})
    if prospect_type is None and client_id is not None:
        client = db.scalar(select(User).where(User.id == client_id))
        if client is not None:
            prospect_type = "child" if (client.client_kind or "").strip().upper() == "CHILD" else "adult"
    quote_template, _, terms_template, _, binding = _resolve_document_templates(
        db,
        prospect_type=prospect_type,
        context_type=context_type,
        activity_family=activity_family,
        activity_id=activity_id,
        quote_type_id=quote_type_id,
        language=language,
        currency=currency,
        quote_template=None,
        quote_template_version=None,
        terms_template=None,
        terms_template_version=None,
    )
    if binding is None or getattr(binding, "activity_id", None) != activity_id:
        return None, None
    return quote_template, terms_template


def _digits(value: object | None) -> str:
    return "".join(ch for ch in _text(value) if ch.isdigit())


def _json_object(value: object | None) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _json_list(value: object | None) -> list[object]:
    if isinstance(value, list):
        return list(value)
    return []


def _coerce_typeform_answers(value: object | None) -> list[TypeformAnswerOut]:
    answers: list[TypeformAnswerOut] = []
    for index, item in enumerate(_json_list(value), start=1):
        row = _json_object(item)
        key = (
            _text(row.get("key"))
            or _text(row.get("field_ref"))
            or _text(row.get("field_id"))
            or f"answer_{index}"
        )
        label = (
            _text(row.get("label"))
            or _text(row.get("field_label"))
            or _text(row.get("question"))
            or key
        )
        raw_value = row.get("value")
        if isinstance(raw_value, list):
            rendered_value = ", ".join(_text(child) for child in raw_value if _text(child))
        elif isinstance(raw_value, bool):
            rendered_value = "Oui" if raw_value else "Non"
        else:
            rendered_value = _text(raw_value)
        answers.append(
            TypeformAnswerOut(
                key=key,
                label=label,
                value=rendered_value,
            )
        )
    return answers


def _template_condition_tokens(value: object | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        tokens: list[str] = []
        for nested in value.values():
            tokens.extend(_template_condition_tokens(nested))
        return list(dict.fromkeys(token for token in tokens if token))
    if isinstance(value, list):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_template_condition_tokens(item))
        return list(dict.fromkeys(token for token in tokens if token))
    token = _normalize_token(value)
    return [token] if token else []


def _template_matches_when(
    template: dict[str, object],
    normalized: dict[str, object],
) -> bool:
    when = _json_object(template.get("when"))
    if not when:
        return True
    for field_name, expected in when.items():
        actual_tokens = _template_condition_tokens(normalized.get(field_name))
        expected_tokens = _template_condition_tokens(expected)
        if not expected_tokens:
            if actual_tokens:
                return False
            continue
        if not actual_tokens:
            return False
        if not any(token in actual_tokens for token in expected_tokens):
            return False
    return True


_ONLINE_ACTIVITY_SUBSTITUTIONS = {
    "PIANO_GROUP_ONSITE_1H": "PIANO_GROUP_ONLINE_1H",
}


def _template_for_runtime_context(
    template: dict[str, object],
    *,
    runtime_context: dict[str, object],
) -> dict[str, object]:
    if not _is_online_runtime_context(runtime_context):
        return template
    activity_code = _text(template.get("activity_code")).strip().upper()
    online_code = _ONLINE_ACTIVITY_SUBSTITUTIONS.get(activity_code)
    if not online_code:
        return template
    adjusted = dict(template)
    adjusted["activity_code"] = online_code
    return adjusted


def _merge_normalized_payload_patch(
    current: dict[str, object],
    patch: dict[str, object | None],
) -> dict[str, object]:
    merged = dict(current)
    for raw_key, raw_value in patch.items():
        key = _text(raw_key)
        if not key:
            continue
        if raw_value is None:
            merged.pop(key, None)
            continue
        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if cleaned:
                merged[key] = cleaned
            else:
                merged.pop(key, None)
            continue
        if isinstance(raw_value, list):
            cleaned_list = [_text(item) for item in raw_value if _text(item)]
            if cleaned_list:
                merged[key] = cleaned_list
            else:
                merged.pop(key, None)
            continue
        merged[key] = raw_value
    return merged


def _parse_dt(value: object | None) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        candidate = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_uuid(value: object | None) -> UUID | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return UUID(raw)
    except Exception:
        return None


def _birth_date_from_normalized_payload(normalized: dict[str, object]) -> date | None:
    raw = _text(normalized.get("child_birth_date"))
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _apply_intake_child_birth_date_to_existing_client(
    db: Session,
    *,
    client_id: UUID | None,
    normalized: dict[str, object],
) -> bool:
    birth_date = _birth_date_from_normalized_payload(normalized)
    if client_id is None or birth_date is None:
        return False
    client = db.scalar(select(User).where(User.id == client_id).with_for_update())
    if client is None or client.role != UserRole.CLIENT or client.client_kind != ClientKind.CHILD or client.birth_date is not None:
        return False
    client.birth_date = birth_date
    client.updated_at = _utcnow()
    db.add(client)
    return True


def _parse_decimal(value: object | None, default: Decimal = Decimal("0.00")) -> Decimal:
    raw = _text(value).replace(",", ".")
    if not raw:
        return default
    try:
        parsed = Decimal(raw)
    except Exception:
        return default
    if not parsed.is_finite():
        return default
    return parsed


def _bool_or_default(value: object | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text_value = _lower(value)
    if text_value in {"1", "true", "yes", "on", "oui"}:
        return True
    if text_value in {"0", "false", "no", "off", "non"}:
        return False
    return default


def _form_label(config: TypeformFormConfig | None) -> str:
    if config is None:
        return "Formulaire inconnu"
    config_json = _json_object(config.configuration_json)
    label = _text(config_json.get("label"))
    if label:
        return label
    return config.source_code


def _display_name(first_name: object | None, last_name: object | None, fallback: str = "-") -> str:
    label = " ".join(part for part in [_text(first_name), _text(last_name)] if part).strip()
    return label or fallback


def _empty_runtime_context(
    *,
    config: TypeformFormConfig | None,
    requested_location: str | None,
) -> dict[str, object]:
    default_quote_type = None
    if config is not None:
        default_quote_type = _text(config.default_quote_type) or None
    return {
        "requested_location": requested_location,
        "location_id": config.default_location_id if config is not None else None,
        "location_code": config.location_code if config is not None else None,
        "location_name": None,
        "quote_type_id": config.default_quote_type_id if config is not None else None,
        "quote_type": default_quote_type,
        "pricing_catalog_id": config.default_pricing_catalog_id if config is not None else None,
        "pricing_catalog_name": None,
        "payment_plan_id": config.default_payment_plan_id if config is not None else None,
        "payment_plan_name": None,
        "legal_entity_id": config.default_legal_entity_id if config is not None else None,
        "legal_entity_name": None,
        "warnings": [],
        "blockages": [],
    }


def _confidence_label(score: int) -> str:
    if score >= 90:
        return "fort"
    if score >= 70:
        return "moyen"
    return "faible"


def _weekday_from_label(value: object | None) -> int | None:
    normalized = _normalize_token(value)
    if not normalized:
        return None
    return DAY_ALIASES.get(normalized)


_DAY_TOKEN_RE = re.compile(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b", re.IGNORECASE)
_TIME_TOKEN_RE = re.compile(r"(?<!\d)(\d{1,2})(?:[:h](\d{1,2}))?(?!\d)")
_EXPLICIT_TIME_HINT_RE = re.compile(r"\d{1,2}\s*(?:h|:)\s*\d{0,2}", re.IGNORECASE)


def _extract_weekday_label(value: object | None) -> str | None:
    weekday = _weekday_from_label(value)
    if weekday is not None:
        return DAY_LABELS[weekday].lower()
    raw = _text(value)
    if not raw:
        return None
    match = _DAY_TOKEN_RE.search(raw)
    if match is None:
        return None
    weekday = _weekday_from_label(match.group(1))
    if weekday is None:
        return None
    return DAY_LABELS[weekday].lower()


def _normalize_day_values(values: list[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, list):
            nested = _normalize_day_values(item)
            for child in nested:
                if child not in seen:
                    seen.add(child)
                    out.append(child)
            continue
        if isinstance(item, str):
            chunks = [chunk.strip() for chunk in item.replace("/", ",").replace(";", ",").split(",")]
        else:
            chunks = [_text(item)]
        for chunk in chunks:
            labels = [
                DAY_LABELS[weekday].lower()
                for match in _DAY_TOKEN_RE.finditer(chunk)
                for weekday in [_weekday_from_label(match.group(1))]
                if weekday is not None
            ]
            if not labels:
                label = _extract_weekday_label(chunk)
                labels = [label] if label is not None else []
            for label in labels:
                if label not in seen:
                    seen.add(label)
                    out.append(label)
    return out


def _extract_time_tokens(value: object | None) -> list[str]:
    raw = _text(value).lower()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    compact = raw.replace(" ", "")
    for hour_s, minute_s in _TIME_TOKEN_RE.findall(compact):
        hour = int(hour_s)
        minute = int(minute_s or "0")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            continue
        token = f"{hour:02d}:{minute:02d}"
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _extract_explicit_time_tokens(value: object | None) -> list[str]:
    raw = _text(value)
    if not raw or _EXPLICIT_TIME_HINT_RE.search(raw) is None:
        return []
    return _extract_time_tokens(value)


def _normalize_time_token(value: object | None) -> str | None:
    raw = _text(value).lower().replace("h", ":")
    if not raw:
        return None
    if raw.count(":") == 0 and raw.isdigit() and len(raw) in {3, 4}:
        raw = f"{raw[:-2]}:{raw[-2:]}"
    if raw.count(":") == 1:
        hour_s, minute_s = raw.split(":", 1)
        if hour_s.isdigit() and minute_s.isdigit():
            hour = int(hour_s)
            minute = int(minute_s)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"
    extracted = _extract_time_tokens(value)
    if extracted:
        return extracted[0]
    return None


def _normalize_time_values(values: list[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, list):
            nested = _normalize_time_values(item)
            for child in nested:
                if child not in seen:
                    seen.add(child)
                    out.append(child)
            continue
        chunks = [chunk.strip() for chunk in _text(item).replace("/", ",").replace(";", ",").split(",")]
        for chunk in chunks:
            normalized = _normalize_time_token(chunk)
            if normalized:
                if normalized not in seen:
                    seen.add(normalized)
                    out.append(normalized)
                continue
            for token in _extract_time_tokens(chunk):
                if token not in seen:
                    seen.add(token)
                    out.append(token)
    return out


def _minutes_from_hhmm(value: str) -> int | None:
    normalized = _normalize_time_token(value)
    if not normalized:
        return None
    hour_s, minute_s = normalized.split(":", 1)
    return int(hour_s) * 60 + int(minute_s)


def _normalize_slot_preferences(
    values: list[object],
    *,
    requested_location: str | None,
    segment: str | None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in values:
        if isinstance(item, list):
            nested = _normalize_slot_preferences(item, requested_location=requested_location, segment=segment)
            for child in nested:
                key = (_text(child.get("day")) or None, _text(child.get("time")) or None)
                if key not in seen:
                    seen.add(key)
                    out.append(child)
            continue
        if isinstance(item, str):
            chunks = [chunk.strip() for chunk in item.replace("/", ",").replace(";", ",").split(",") if chunk.strip()]
            if len(chunks) > 1:
                nested = _normalize_slot_preferences(chunks, requested_location=requested_location, segment=segment)
                for child in nested:
                    key = (_text(child.get("day")) or None, _text(child.get("time")) or None)
                    if key not in seen:
                        seen.add(key)
                        out.append(child)
                continue
        day = _extract_weekday_label(item)
        times = _extract_time_tokens(item)
        if not day and not times:
            continue
        if not times:
            key = (day, None)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "day": day,
                    "time": None,
                    "location": requested_location,
                    "segment": segment,
                }
            )
            continue
        for time_value in times:
            key = (day, time_value)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "day": day,
                    "time": time_value,
                    "location": requested_location,
                    "segment": segment,
                }
            )
    return out


def _is_multisite_location_placeholder(value: object | None) -> bool:
    token = _normalize_token(value)
    compact = re.sub(r"[^a-z0-9]+", "", token)
    return compact in {"multisite", "parismultisite", "parismultisites"}


def _location_hint_from_text(*values: object | None) -> str | None:
    token = " ".join(_normalize_token(value) for value in values if _text(value))
    compact = re.sub(r"[^a-z0-9]+", "", token)
    if not compact:
        return None
    if "barleduc" in compact or compact == "bld":
        return "Bar-le-Duc"
    if "pompe" in compact:
        return "Rue de la Pompe"
    if "scheffer" in compact:
        return "Rue Scheffer"
    if "richelieu" in compact:
        return "Rue de Richelieu"
    if "assas" in compact:
        return "Rue d'Assas"
    return None


def _typeform_site_key(*values: object | None) -> str | None:
    token = " ".join(_normalize_token(value) for value in values if _text(value))
    compact = re.sub(r"[^a-z0-9]+", "", token)
    if not compact:
        return None
    if "barleduc" in compact or "bld" in re.split(r"[^a-z0-9]+", token):
        return "bar_le_duc"
    if "pompe" in compact:
        return "pompe"
    if "scheffer" in compact:
        return "scheffer"
    if "richelieu" in compact:
        return "richelieu"
    if "assas" in compact:
        return "assas"
    if "paris" in compact:
        return "paris"
    if "online" in compact or "enligne" in compact:
        return "online"
    return None


def _typeform_location_allowed_for_alternative(
    *,
    requested_location: object | None,
    runtime_context: dict[str, object],
    candidate_location: Location,
) -> bool:
    requested_key = _typeform_site_key(requested_location)
    if requested_key is None or requested_key == "paris":
        requested_key = _typeform_site_key(
            requested_location,
            runtime_context.get("location_code"),
            runtime_context.get("location_name"),
            runtime_context.get("requested_location"),
        )
    candidate_key = _typeform_site_key(
        getattr(candidate_location, "code", None),
        getattr(candidate_location, "name", None),
    )
    if requested_key is None or candidate_key is None:
        return True
    if requested_key == "online":
        return candidate_key == "online"
    if requested_key == "bar_le_duc":
        return candidate_key == "bar_le_duc"
    if candidate_key == "bar_le_duc":
        return False
    if requested_key == "paris":
        return candidate_key != "bar_le_duc"
    if requested_key in {"pompe", "scheffer"}:
        return candidate_key in {"pompe", "scheffer"}
    if requested_key in {"richelieu", "assas"}:
        return candidate_key == requested_key
    return True


def _location_for_slot_preference(
    requested_location: str | None,
    *hints: object | None,
) -> str | None:
    hinted_location = _location_hint_from_text(*hints)
    if hinted_location and (not requested_location or _is_multisite_location_placeholder(requested_location)):
        return hinted_location
    return requested_location


def _resolve_requested_location_from_slot_preferences(
    requested_location: str | None,
    slot_preferences: list[dict[str, object]],
) -> tuple[str | None, list[dict[str, object]]]:
    if not _is_multisite_location_placeholder(requested_location):
        return requested_location, slot_preferences
    concrete_locations = [
        _text(item.get("location"))
        for item in slot_preferences
        if _text(item.get("location")) and not _is_multisite_location_placeholder(item.get("location"))
    ]
    unique_locations = list(dict.fromkeys(concrete_locations))
    if len(unique_locations) != 1:
        return requested_location, slot_preferences
    resolved_location = unique_locations[0]
    resolved_preferences = [
        {
            **item,
            "location": resolved_location if _is_multisite_location_placeholder(item.get("location")) else item.get("location"),
        }
        for item in slot_preferences
    ]
    return resolved_location, resolved_preferences


def _slot_preference_like_label(value: object | None) -> bool:
    token = _normalize_token(value)
    return "creneau" in token or "slot" in token


def _fallback_requested_slot_preferences_from_simplified_answers(
    simplified_answers: list[dict[str, object]],
    *,
    requested_location: str | None,
    segment: str | None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label"))
        field_title = _text(item.get("field_title"))
        value = _text(item.get("value"))
        nested: list[dict[str, object]] = []
        slot_location = _location_for_slot_preference(requested_location, label, field_title, value)
        label_for_slots = field_title or label
        if _slot_preference_like_label(label) or _slot_preference_like_label(field_title):
            nested = _normalize_slot_preferences(
                [value],
                requested_location=slot_location,
                segment=segment,
            )
        else:
            label_day = _extract_weekday_label(label_for_slots)
            value_day = _extract_weekday_label(value)
            label_times = _extract_explicit_time_tokens(label_for_slots)
            value_times = _extract_time_tokens(value)

            # Keep only cross-signals between label and value so age ranges like
            # "Débutants (5 - 6 ans)" do not get misread as a requested slot.
            if label_day and value_times:
                nested = [
                    {
                        "day": label_day,
                        "time": time_value,
                        "location": slot_location,
                        "segment": segment,
                    }
                    for time_value in value_times
                ]
            elif value_day and label_times:
                nested = [
                    {
                        "day": value_day,
                        "time": label_times[0],
                        "location": slot_location,
                        "segment": segment,
                    }
                ]
        for child in nested:
            key = (_text(child.get("day")) or None, _text(child.get("time")) or None)
            if key in seen:
                continue
            seen.add(key)
            out.append(child)
    return out


def _slot_preferences_have_complete_day_time(preferences: list[dict[str, object]]) -> bool:
    return any(_text(item.get("day")) and _text(item.get("time")) for item in preferences)


def _prefer_more_complete_slot_preferences(
    current: list[dict[str, object]],
    fallback: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not fallback:
        return current
    if not current:
        return fallback
    if _slot_preferences_have_complete_day_time(current):
        return current
    if _slot_preferences_have_complete_day_time(fallback):
        return fallback
    return current


def _is_second_course_label(value: object | None) -> bool:
    token = _normalize_token(value)
    if not token:
        return False
    return (
        "2e cours" in token
        or "2eme cours" in token
        or "deuxieme cours" in token
        or "second cours" in token
    )


def _is_solfege_label(value: object | None) -> bool:
    token = _normalize_token(value)
    return "solfege" in token or re.search(r"\bniveau\s*[1-5]\b", token) is not None


def _main_course_slot_preferences_from_simplified_answers(
    simplified_answers: list[dict[str, object]],
    *,
    requested_location: str | None,
    segment: str | None,
) -> list[dict[str, object]]:
    requested_days: list[str] = []
    requested_times: list[str] = []
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label"))
        value = _text(item.get("value"))
        label_token = _normalize_token(label)
        if not label_token or _is_second_course_label(label) or _is_solfege_label(label):
            continue
        if "jour" in label_token and "cours" in label_token:
            day = _extract_weekday_label(value)
            if day and day not in requested_days:
                requested_days.append(day)
        if "horaire" in label_token and "cours" in label_token:
            for time_value in _extract_time_tokens(value):
                if time_value not in requested_times:
                    requested_times.append(time_value)

    if not requested_days and not requested_times:
        return []
    out: list[dict[str, object]] = []
    seen: set[tuple[str | None, str | None]] = set()
    days = requested_days or [None]
    times = requested_times or [None]
    for day in days:
        for time_value in times:
            key = (day, time_value)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "day": day,
                    "time": time_value,
                    "location": requested_location,
                    "segment": segment,
                }
            )
    return out


def _first_start_time_from_choice(value: object | None) -> str | None:
    for chunk in _text(value).replace("/", ",").replace(";", ",").split(","):
        tokens = _extract_time_tokens(chunk)
        if tokens:
            return tokens[0]
    return None


def _second_course_request_from_simplified_answers(
    simplified_answers: list[dict[str, object]],
    *,
    requested_location: str | None,
    segment: str | None,
) -> dict[str, object]:
    request_label: str | None = None
    request_value: str | None = None
    requested_days: list[str] = []
    requested_times: list[str] = []
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label"))
        value = _text(item.get("value"))
        label_token = _normalize_token(label)
        if not _is_second_course_label(label):
            continue
        if "selection" not in label_token and "jour" not in label_token and "creneau" not in label_token:
            request_label = label
            request_value = value
            continue
        if "jour" in label_token:
            day = _extract_weekday_label(value)
            if day and day not in requested_days:
                requested_days.append(day)
            continue
        if "creneau" in label_token or "horaire" in label_token:
            for day in _normalize_day_values([value]):
                if day and day not in requested_days:
                    requested_days.append(day)
            for time_value in _normalize_time_values([value]):
                if time_value and time_value not in requested_times:
                    requested_times.append(time_value)

    request_token = _normalize_token(request_value)
    requested = bool(request_token and "oui" in request_token and "non" not in request_token)
    if not requested:
        return {"requested": False}

    modality = "online" if "ligne" in request_token or "online" in request_token else "onsite"
    unit_price_match = re.search(r"(\d+(?:[,.]\d+)?)\s*(?:eur|€)", request_value or "", flags=re.IGNORECASE)
    unit_price_ttc = unit_price_match.group(1).replace(",", ".") if unit_price_match else None
    location = "En ligne" if modality == "online" else requested_location
    days = requested_days or [None]
    times = requested_times or [None]
    slot_preferences: list[dict[str, object]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for day in days:
        for time_value in times:
            key = (day, time_value)
            if key in seen:
                continue
            seen.add(key)
            slot_preferences.append(
                {
                    "day": day,
                    "time": time_value,
                    "location": location,
                    "segment": segment,
                }
            )
    return {
        "requested": True,
        "label": request_label,
        "value": request_value,
        "modality": modality,
        "unit_price_ttc": unit_price_ttc,
        "slot_preferences": slot_preferences,
    }


def _fallback_solfege_slot_preferences_from_simplified_answers(
    simplified_answers: list[dict[str, object]],
    *,
    requested_location: str | None,
    segment: str | None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label"))
        field_title = _text(item.get("field_title"))
        value = _text(item.get("value"))
        label_token = _normalize_token(label)
        field_title_token = _normalize_token(field_title)
        label_for_slots = field_title or label
        value_times = _extract_time_tokens(value)
        value_day = _extract_weekday_label(value)
        label_times = _extract_explicit_time_tokens(label_for_slots)
        label_day = _extract_weekday_label(label_for_slots)
        if not ((value_times and value_day) or (value_day and label_times) or (label_day and value_times)):
            continue
        is_solfege_slot_label = (
            "solfege" in label_token
            or "solfege" in field_title_token
            or re.search(r"\bniveau\s*[1-5]\b", label_token) is not None
            or re.search(r"\bniveau\s*[1-5]\b", field_title_token) is not None
            or "debutant" in label_token
            or "debutant" in field_title_token
            or "notion" in label_token
            or "notion" in field_title_token
            or "dechiffrage" in label_token
            or "dechiffrage" in field_title_token
        )
        if not is_solfege_slot_label:
            continue
        children = _normalize_slot_preferences(
            [value],
            requested_location=requested_location,
            segment=segment,
        )
        if not _slot_preferences_have_complete_day_time(children):
            children = []
            if value_day and label_times:
                children.append(
                    {
                        "day": value_day,
                        "time": label_times[0],
                        "location": requested_location,
                        "segment": segment,
                    }
                )
            elif label_day and value_times:
                children.extend(
                    {
                        "day": label_day,
                        "time": time_value,
                        "location": requested_location,
                        "segment": segment,
                    }
                    for time_value in value_times
                )
        for child in children:
            key = (_text(child.get("day")) or None, _text(child.get("time")) or None)
            if key in seen:
                continue
            seen.add(key)
            out.append(child)
    return out


def _truthy_answer_value(value: object | None) -> bool:
    raw = _normalize_token(value)
    return raw in {"1", "true", "yes", "oui", "on", "vrai"}


def _simplified_bool_answer(
    simplified_answers: list[dict[str, object]],
    *,
    label_tokens: tuple[str, ...],
) -> bool:
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label = _normalize_token(item.get("label"))
        if not label or not all(token in label for token in label_tokens):
            continue
        if _truthy_answer_value(item.get("value")):
            return True
    return False


def _fallback_solfege_level_from_simplified_answers(
    simplified_answers: list[dict[str, object]],
) -> str | None:
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label_token = _normalize_token(item.get("label"))
        value_token = _normalize_token(item.get("value"))
        haystack = " ".join(part for part in (label_token, value_token) if part)
        if not haystack or "ne sais pas" in haystack:
            continue
        if not any(token in haystack for token in ("solfege", "niveau", "debutant", "notion", "dechiffrage")):
            continue
        match = re.search(r"niveau\s*([1-5])", haystack)
        if match:
            return match.group(1)
    return None


def _with_solfege_modality_location(
    preferences: list[dict[str, object]],
    *,
    modality: str | None,
) -> list[dict[str, object]]:
    if modality != "online":
        return preferences
    return [
        {
            **preference,
            "location": "En ligne",
        }
        for preference in preferences
    ]


def _answer_is_negative(value: object | None) -> bool:
    raw = _normalize_token(value)
    return raw in {"0", "false", "no", "non", "off", "faux", "ne sais pas"}


def _fallback_requested_solfege_modality_from_simplified_answers(
    simplified_answers: list[dict[str, object]],
) -> str | None:
    fallback_requested = False
    for item in simplified_answers:
        if not isinstance(item, dict):
            continue
        label = _normalize_token(item.get("label"))
        value = _normalize_token(item.get("value"))
        if "solfege" not in label:
            continue
        if _answer_is_negative(item.get("value")):
            continue
        haystack = " ".join(part for part in (label, value) if part)
        if "en ligne" in haystack or "online" in haystack or "video" in haystack:
            return "online"
        if "presentiel" in haystack and _truthy_answer_value(item.get("value")):
            return "onsite"
        if "presentiel" in haystack and any(token in value for token in DAY_ALIASES):
            return "onsite"
        if any(token in value for token in DAY_ALIASES) and _extract_time_tokens(_text(item.get("value"))):
            fallback_requested = True
    return "online" if fallback_requested else None


def _answer_value(answer: dict[str, object]) -> object:
    if "text" in answer:
        return answer.get("text")
    if "email" in answer:
        return answer.get("email")
    if "phone_number" in answer:
        return answer.get("phone_number")
    if "date" in answer:
        return answer.get("date")
    if "number" in answer:
        return answer.get("number")
    if "boolean" in answer:
        return answer.get("boolean")
    if "url" in answer:
        return answer.get("url")
    if "choice" in answer and isinstance(answer.get("choice"), dict):
        return _json_object(answer.get("choice")).get("label")
    if "choices" in answer and isinstance(answer.get("choices"), dict):
        return _json_list(_json_object(answer.get("choices")).get("labels"))
    return answer.get("value")


def _answer_display_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value if _text(item))
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    return _text(value)


def _extract_answers(payload: dict[str, object]) -> list[dict[str, object]]:
    form_response = _json_object(payload.get("form_response"))
    answers = _json_list(form_response.get("answers"))
    if answers:
        return [item for item in answers if isinstance(item, dict)]
    top_level_answers = _json_list(payload.get("answers"))
    return [item for item in top_level_answers if isinstance(item, dict)]


def _extract_field_labels_from_payload(payload: dict[str, object]) -> dict[str, str]:
    form_response = _json_object(payload.get("form_response"))
    definition = _json_object(form_response.get("definition"))
    raw_fields = _json_list(definition.get("fields"))
    labels: dict[str, str] = {}

    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        field = _json_object(item)
        title = _text(field.get("title"))
        if not title:
            continue
        for candidate in (_text(field.get("ref")), _text(field.get("id"))):
            if candidate and candidate not in labels:
                labels[candidate] = title
    return labels


def _answer_keys(answer: dict[str, object], *, index: int) -> list[str]:
    field = _json_object(answer.get("field"))
    out: list[str] = []
    seen: set[str] = set()
    for candidate in (
        _text(field.get("ref")),
        _text(field.get("id")),
        _text(field.get("title")),
    ):
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    if not out:
        out.append(f"answer_{index}")
    return out


def _answer_key(answer: dict[str, object], *, index: int) -> str:
    return _answer_keys(answer, index=index)[0]


def _answer_label(
    answer: dict[str, object],
    *,
    index: int,
    configured_labels: dict[str, object],
    payload_labels: dict[str, str],
) -> str:
    field = _json_object(answer.get("field"))
    for candidate in _answer_keys(answer, index=index):
        configured = _text(configured_labels.get(candidate))
        if configured:
            return configured
        payload_label = _text(payload_labels.get(candidate))
        if payload_label:
            return payload_label
    return _text(field.get("title")) or _answer_key(answer, index=index)


def _extract_answer_map(answers: list[dict[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for index, answer in enumerate(answers):
        value = _answer_value(answer)
        for key in _answer_keys(answer, index=index):
            if key in out:
                existing = out[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    out[key] = [existing, value]
            else:
                out[key] = value
    return out


def _mapping_candidates(field_mapping: dict[str, object], field_name: str) -> list[str]:
    raw = field_mapping.get(field_name)
    if isinstance(raw, str):
        return [_text(raw)] if _text(raw) else []
    if isinstance(raw, list):
        return [_text(item) for item in raw if _text(item)]
    return []


def _mapped_scalar(answer_map: dict[str, object], field_mapping: dict[str, object], field_name: str) -> str | None:
    for candidate in _mapping_candidates(field_mapping, field_name):
        value = answer_map.get(candidate)
        if isinstance(value, list):
            for item in value:
                text = _text(item)
                if text:
                    return text
        else:
            text = _text(value)
            if text:
                return text
    return None


def _scalar_from_answer_map(answer_map: dict[str, object], candidates: list[str]) -> str | None:
    for candidate in candidates:
        value = answer_map.get(candidate)
        if isinstance(value, list):
            for item in value:
                text = _text(item)
                if text:
                    return text
        else:
            text = _text(value)
            if text:
                return text
    return None


def _mapped_scalar_with_fallbacks(
    answer_map: dict[str, object],
    field_mapping: dict[str, object],
    field_name: str,
    *,
    fallbacks: list[str] | None = None,
) -> str | None:
    return _mapped_scalar(answer_map, field_mapping, field_name) or _scalar_from_answer_map(answer_map, fallbacks or [])


def _mapped_list(answer_map: dict[str, object], field_mapping: dict[str, object], field_name: str) -> list[object]:
    out: list[object] = []
    for candidate in _mapping_candidates(field_mapping, field_name):
        value = answer_map.get(candidate)
        if isinstance(value, list):
            out.extend(value)
        elif value is not None:
            out.append(value)
    return out


def _mapped_token_list(answer_map: dict[str, object], field_mapping: dict[str, object], field_name: str) -> list[str]:
    out: list[str] = []
    for candidate in _mapping_candidates(field_mapping, field_name):
        value = answer_map.get(candidate)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, bool):
                if item:
                    out.append(candidate)
                continue
            text = _text(item)
            if text:
                out.append(text)
    return out


def _sanitize_requested_products(
    requested_products: list[str],
    *,
    requested_location: str | None,
    requested_payment_method: str | None,
    address_line_1: str | None,
    address_line_2: str | None,
    city: str | None,
    postal_code: str | None,
    country: str | None,
    address: str | None,
) -> list[str]:
    excluded_tokens = {
        _normalize_token(value)
        for value in [
            requested_location,
            requested_payment_method,
            address_line_1,
            address_line_2,
            city,
            postal_code,
            country,
            address,
        ]
        if _text(value)
    }
    cleaned: list[str] = []
    seen_tokens: set[str] = set()
    for item in requested_products:
        text = _text(item)
        token = _normalize_token(text)
        if not text or not token or token in excluded_tokens or token in seen_tokens:
            continue
        seen_tokens.add(token)
        cleaned.append(text)
    return cleaned


def _requested_payment_method_code(value: object | None) -> str | None:
    token = _normalize_token(value)
    if not token:
        return None
    if "virement" in token or "bank transfer" in token:
        return "BANK_TRANSFER"
    if ("mensuel" in token or "monthly" in token) and ("carte" in token or "cb" in token):
        return "CARD_MONTHLY"
    if "carte" in token or "cb" in token or token in {"visa", "mastercard"}:
        return "CARD"
    if "cheque" in token:
        return "CHECK"
    if "espece" in token:
        return "CASH"
    return None


def _requested_payment_installment_count(value: object | None) -> int | None:
    token = _normalize_token(value)
    if not token:
        return None
    match = re.search(r"\b(\d{1,2})\s*(?:x|fois)\b", token)
    if match:
        count = int(match.group(1))
        if 1 <= count <= 24:
            return count
    return None


def _payment_plan_installment_count(plan: PaymentPlan) -> int | None:
    rules = plan.schedule_rules if isinstance(plan.schedule_rules, dict) else {}
    raw_count = rules.get("installment_count")
    try:
        count = int(raw_count) if raw_count is not None else 0
    except (TypeError, ValueError):
        count = 0
    if count > 0:
        return count
    return _requested_payment_installment_count(f"{plan.name} {plan.code} {plan.schedule_type}")


def _payment_plan_is_monthly(plan: PaymentPlan) -> bool:
    token = _normalize_token(f"{plan.name} {plan.code} {plan.schedule_type}")
    return "monthly" in token or "mensuel" in token


def _payment_method_label_from_code(method_code: str | None) -> str | None:
    normalized = _text(method_code).strip().upper()
    if not normalized:
        return None
    if normalized == "BANK_TRANSFER":
        return "Virement bancaire"
    if normalized == "CARD":
        return "Carte bancaire"
    if normalized == "CARD_MONTHLY":
        return "Carte bancaire mensuelle"
    if normalized in {"CARD_MONTHLY_FIXED", "CB_MONTHLY_FIXED"}:
        return "CB mensuel fixe"
    if normalized == "CHECK":
        return "Chèque"
    if normalized == "CASH":
        return "Espèces"
    return normalized


def _fallback_requested_payment_method(*, requested_products: list[str]) -> str | None:
    for item in requested_products:
        method_code = _requested_payment_method_code(item)
        if method_code is not None:
            return _text(item) or _payment_method_label_from_code(method_code)
    return None


def _specific_requested_payment_method_from_products(
    requested_payment_method: str | None,
    requested_products: list[object],
) -> str | None:
    current_code = _requested_payment_method_code(requested_payment_method)
    current_token = _normalize_token(requested_payment_method)
    current_has_schedule = (
        _requested_payment_installment_count(requested_payment_method) is not None
        or "mensuel" in current_token
        or "monthly" in current_token
    )
    if current_code is not None and current_has_schedule:
        return requested_payment_method

    for item in requested_products:
        text = _text(item)
        item_code = _requested_payment_method_code(text)
        item_token = _normalize_token(text)
        item_has_schedule = (
            _requested_payment_installment_count(text) is not None
            or "mensuel" in item_token
            or "monthly" in item_token
        )
        if item_code is None or not item_has_schedule:
            continue
        if current_code is None or item_code == current_code:
            return text
    return requested_payment_method


def _fallback_referral_referrer_name(simplified_answers: list[dict[str, object]]) -> str | None:
    positive_tokens = ("parrain", "recommand", "conseille", "prescrit", "invite")
    negative_tokens = ("address", "adresse", "city", "ville", "postal")
    for answer in simplified_answers:
        label_token = normalize_referral_text(answer.get("label"))
        if not label_token:
            continue
        if any(token in label_token for token in negative_tokens) and not any(token in label_token for token in ("parrain", "recommand")):
            continue
        if not any(token in label_token for token in positive_tokens):
            continue
        value = _text(answer.get("value"))
        if value:
            return value
    return None


def _extract_typeform_form_id(payload: dict[str, object]) -> str:
    form_response = _json_object(payload.get("form_response"))
    return _text(form_response.get("form_id")) or _text(payload.get("form_id"))


def _extract_typeform_response_id(payload: dict[str, object]) -> str:
    form_response = _json_object(payload.get("form_response"))
    return (
        _text(form_response.get("response_id"))
        or _text(form_response.get("token"))
        or _text(payload.get("response_id"))
        or _text(payload.get("token"))
    )


def _extract_typeform_received_at(payload: dict[str, object]) -> datetime:
    form_response = _json_object(payload.get("form_response"))
    parsed = (
        _parse_dt(form_response.get("submitted_at"))
        or _parse_dt(payload.get("submitted_at"))
        or _parse_dt(payload.get("received_at"))
    )
    return parsed or _utcnow()


def _normalize_payload(
    *,
    payload: dict[str, object],
    config: TypeformFormConfig | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    config_json = _json_object(config.configuration_json if config is not None else {})
    field_mapping = _json_object(config_json.get("field_mapping"))
    field_labels = _json_object(config_json.get("field_labels"))

    answers = _extract_answers(payload)
    payload_field_labels = _extract_field_labels_from_payload(payload)
    answer_map = _extract_answer_map(answers)
    simplified_answers: list[dict[str, object]] = []
    for index, answer in enumerate(answers):
        key = _answer_key(answer, index=index)
        field = _json_object(answer.get("field"))
        simplified_answers.append(
            {
                "key": key,
                "label": _answer_label(
                    answer,
                    index=index,
                    configured_labels=field_labels,
                    payload_labels=payload_field_labels,
                ),
                "field_title": _text(field.get("title")) or _text(payload_field_labels.get(key)),
                "value": _answer_display_value(_answer_value(answer)),
            }
        )

    parent_first_name = _mapped_scalar(answer_map, field_mapping, "parent_first_name") or _mapped_scalar(answer_map, field_mapping, "adult_first_name")
    parent_last_name = _mapped_scalar(answer_map, field_mapping, "parent_last_name") or _mapped_scalar(answer_map, field_mapping, "adult_last_name")
    parent_email = _mapped_scalar(answer_map, field_mapping, "parent_email") or _mapped_scalar(answer_map, field_mapping, "adult_email")
    parent_phone = _mapped_scalar(answer_map, field_mapping, "parent_phone") or _mapped_scalar(answer_map, field_mapping, "adult_phone")
    child_first_name = _mapped_scalar(answer_map, field_mapping, "child_first_name")
    child_last_name = _mapped_scalar(answer_map, field_mapping, "child_last_name")
    child_birth_date = _mapped_scalar(answer_map, field_mapping, "child_birth_date")
    requested_course_mode = _mapped_scalar(answer_map, field_mapping, "requested_course_mode") or _text(config_json.get("default_course_mode")) or None
    requested_location = _mapped_scalar(answer_map, field_mapping, "requested_location") or (config.location_code if config is not None else None)
    requested_formula_type = _mapped_scalar(answer_map, field_mapping, "requested_formula_type") or _text(config_json.get("default_formula_type")) or None
    requested_products = [
        _text(item)
        for item in _mapped_token_list(answer_map, field_mapping, "requested_products")
        if _text(item)
    ]
    notes_parts = [
        _mapped_scalar(answer_map, field_mapping, "notes"),
        _mapped_scalar(answer_map, field_mapping, "notes_secondary"),
    ]
    notes = "\n".join(part for part in notes_parts if part).strip() or None
    requested_days = _normalize_day_values(_mapped_token_list(answer_map, field_mapping, "requested_days"))
    requested_times = _normalize_time_values(_mapped_token_list(answer_map, field_mapping, "requested_times"))

    config_segment = _lower(config.audience_segment if config is not None else None)
    customer_type = "child" if child_first_name or child_last_name or config_segment in {"child", "teen", "eveil"} else "adult"
    if customer_type == "child" and not child_last_name:
        child_last_name = parent_last_name

    if customer_type == "adult":
        child_first_name = None
        child_last_name = None
        child_birth_date = None
        if not parent_email:
            parent_email = _mapped_scalar(answer_map, field_mapping, "email")
        if not parent_phone:
            parent_phone = _mapped_scalar(answer_map, field_mapping, "phone")

    requested_slot_preferences = _normalize_slot_preferences(
        _mapped_token_list(answer_map, field_mapping, "requested_slot_preferences"),
        requested_location=requested_location,
        segment=config_segment or None,
    )
    fallback_main_slot_preferences = _fallback_requested_slot_preferences_from_simplified_answers(
        simplified_answers,
        requested_location=requested_location,
        segment=config_segment or None,
    )
    explicit_main_slot_preferences = _main_course_slot_preferences_from_simplified_answers(
        simplified_answers,
        requested_location=requested_location,
        segment=config_segment or None,
    )
    if explicit_main_slot_preferences:
        requested_slot_preferences = _prefer_more_complete_slot_preferences(
            explicit_main_slot_preferences,
            fallback_main_slot_preferences,
        )
    else:
        requested_slot_preferences = _prefer_more_complete_slot_preferences(
            requested_slot_preferences,
            fallback_main_slot_preferences,
        )
    requested_location, requested_slot_preferences = _resolve_requested_location_from_slot_preferences(
        requested_location,
        requested_slot_preferences,
    )
    requested_second_course = _second_course_request_from_simplified_answers(
        simplified_answers,
        requested_location=requested_location,
        segment=config_segment or None,
    )
    requested_solfege_slot_preferences = _normalize_slot_preferences(
        _mapped_token_list(answer_map, field_mapping, "requested_solfege_slot_preferences"),
        requested_location=requested_location,
        segment=config_segment or None,
    )
    requested_solfege_slot_preferences = _prefer_more_complete_slot_preferences(
        requested_solfege_slot_preferences,
        _fallback_solfege_slot_preferences_from_simplified_answers(
            simplified_answers,
            requested_location=requested_location,
            segment=config_segment or None,
        ),
    )
    if requested_slot_preferences:
        requested_days = list(
            dict.fromkeys(
                _text(item.get("day"))
                for item in requested_slot_preferences
                if _text(item.get("day"))
            )
        )
        requested_times = list(
            dict.fromkeys(
                _text(item.get("time"))
                for item in requested_slot_preferences
                if _text(item.get("time"))
            )
        )
    elif requested_days or requested_times:
        if requested_days and requested_times:
            for day in requested_days:
                for requested_time in requested_times:
                    requested_slot_preferences.append(
                        {
                            "day": day,
                            "time": requested_time,
                            "location": requested_location,
                            "segment": config_segment or None,
                        }
                    )
        elif requested_days:
            for day in requested_days:
                requested_slot_preferences.append(
                    {
                        "day": day,
                        "time": None,
                        "location": requested_location,
                        "segment": config_segment or None,
                    }
                )
        else:
            for requested_time in requested_times:
                requested_slot_preferences.append(
                    {
                        "day": None,
                        "time": requested_time,
                        "location": requested_location,
                        "segment": config_segment or None,
                    }
                )

    address_line_1 = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "parent_address_line_1",
        fallbacks=["Address", "address", "Adresse", "adresse"],
    )
    address_line_2 = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "parent_address_line_2",
        fallbacks=[
            "Address line 2",
            "address line 2",
            "Adresse ligne 2",
            "Complement d'adresse",
            "Complément d'adresse",
        ],
    )
    city = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "parent_city",
        fallbacks=["City/Town", "city/town", "Ville", "ville"],
    )
    postal_code = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "parent_postal_code",
        fallbacks=["Zip/Post Code", "zip/post code", "Code postal", "code postal"],
    )
    country = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "parent_country",
        fallbacks=["Country", "country", "Pays", "pays"],
    )
    requested_payment_method = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "requested_payment_method",
        fallbacks=[
            "Mode de règlement souhaité pour l'année à venir",
            "Mode de reglement souhaite pour l'annee a venir",
            "Mode de règlement souhaité",
            "Mode de reglement souhaite",
        ],
    )
    requested_payment_method = requested_payment_method or _fallback_requested_payment_method(
        requested_products=requested_products,
    )
    estimated_solfege_level = _fallback_solfege_level_from_simplified_answers(simplified_answers)
    requested_solfege_modality = _fallback_requested_solfege_modality_from_simplified_answers(simplified_answers)
    if requested_solfege_modality is None and requested_solfege_slot_preferences:
        requested_solfege_modality = "online"
    requested_solfege_slot_preferences = _with_solfege_modality_location(
        requested_solfege_slot_preferences,
        modality=requested_solfege_modality,
    )
    requested_onsite_solfege = requested_solfege_modality == "onsite"
    requested_online_solfege = requested_solfege_modality == "online"
    referral_referrer_name = _mapped_scalar_with_fallbacks(
        answer_map,
        field_mapping,
        "referral_referrer_name",
        fallbacks=[
            "Famille qui vous a recommandé",
            "Famille qui vous a recommande",
            "Famille qui a recommandé",
            "Famille qui a recommande",
            "Parrainage",
            "Parrain",
            "Recommandation",
        ],
    ) or _fallback_referral_referrer_name(simplified_answers)
    referral_category = referral_category_for_location(requested_location)
    requested_pass_recup = _simplified_bool_answer(simplified_answers, label_tokens=("pass", "recup"))
    is_reenrollment = _simplified_bool_answer(simplified_answers, label_tokens=("reinscription",))
    if (requested_onsite_solfege or requested_online_solfege) and not any("solfege" in _normalize_token(item) for item in requested_products):
        requested_products.append("Cours de solfege en ligne" if requested_online_solfege else "Cours de solfege en presentiel")
    if requested_pass_recup and not any("pass" in _normalize_token(item) and "recup" in _normalize_token(item) for item in requested_products):
        requested_products.append("Pass Recup")
    if _bool_or_default(requested_second_course.get("requested"), False):
        second_course_label = _text(requested_second_course.get("value")) or "2e cours de piano"
        if not any(_is_second_course_label(item) for item in requested_products):
            requested_products.append(second_course_label)
    address_parts = [
        part
        for part in [
            address_line_1,
            address_line_2,
            " ".join(part for part in [postal_code, city] if part).strip() or None,
            country,
        ]
        if part
    ]
    address = ", ".join(address_parts) if address_parts else None
    requested_products = _sanitize_requested_products(
        requested_products,
        requested_location=requested_location,
        requested_payment_method=requested_payment_method,
        address_line_1=address_line_1,
        address_line_2=address_line_2,
        city=city,
        postal_code=postal_code,
        country=country,
        address=address,
    )

    normalized = {
        "parent_first_name": parent_first_name,
        "parent_last_name": parent_last_name,
        "parent_email": parent_email.lower() if parent_email else None,
        "parent_phone": parent_phone,
        "parent_address_line_1": address_line_1,
        "parent_address_line_2": address_line_2,
        "parent_city": city,
        "parent_postal_code": postal_code,
        "parent_country": country,
        "parent_address": address,
        "child_first_name": child_first_name,
        "child_last_name": child_last_name,
        "child_birth_date": child_birth_date,
        "customer_type": customer_type,
        "requested_course_mode": requested_course_mode,
        "requested_location": requested_location,
        "requested_days": requested_days,
        "requested_times": requested_times,
        "requested_slot_preferences": requested_slot_preferences,
        "requested_second_course": requested_second_course,
        "requested_solfege_slot_preferences": requested_solfege_slot_preferences,
        "requested_formula_type": requested_formula_type,
        "requested_payment_method": requested_payment_method,
        "requested_products": requested_products,
        "estimated_solfege_level": estimated_solfege_level,
        "requested_solfege_modality": requested_solfege_modality,
        "requested_onsite_solfege": requested_onsite_solfege,
        "requested_online_solfege": requested_online_solfege,
        "requested_pass_recup": requested_pass_recup,
        "is_reenrollment": is_reenrollment,
        "referral_referrer_name": referral_referrer_name,
        "referral_category": referral_category,
        "notes": notes,
    }
    return normalized, simplified_answers


def _client_out_label(client: User) -> tuple[str, str]:
    display = _display_name(client.first_name, client.last_name, client.email or "-")
    phones = [client.mobile_phone_1, client.phone, client.mobile_phone_2, client.home_phone]
    phone = next((value for value in phones if _text(value)), "")
    subtitle = " · ".join(part for part in [client.email or "", phone, _text(client.family_name if hasattr(client, "family_name") else None)] if part)
    return display, subtitle or None


def _find_existing_adult_parent_client(db: Session, normalized: dict[str, object]) -> User | None:
    parent_email = _lower(normalized.get("parent_email"))
    parent_phone = _digits(normalized.get("parent_phone"))

    base_filters = [
        User.role == UserRole.CLIENT,
        User.client_kind == ClientKind.ADULT,
        User.client_status != ClientStatus.ARCHIVED,
    ]
    if parent_email:
        row = db.scalar(
            select(User)
            .where(
                *base_filters,
                func.lower(User.email) == parent_email,
            )
            .order_by(User.created_at.desc())
            .limit(1)
        )
        if row is not None:
            return row

    if not parent_phone:
        return None

    adults = db.scalars(select(User).where(*base_filters).order_by(User.created_at.desc())).all()
    for adult in adults:
        phones = {
            _digits(adult.phone),
            _digits(adult.mobile_phone_1),
            _digits(adult.mobile_phone_2),
            _digits(adult.home_phone),
        }
        if parent_phone in {phone for phone in phones if phone}:
            return adult
    return None


def _collect_client_candidates(db: Session, normalized: dict[str, object]) -> list[dict[str, object]]:
    parent_email = _lower(normalized.get("parent_email"))
    parent_phone = _digits(normalized.get("parent_phone"))
    parent_first_name = _lower(normalized.get("parent_first_name"))
    parent_last_name = _lower(normalized.get("parent_last_name"))
    child_first_name = _lower(normalized.get("child_first_name"))
    child_last_name = _lower(normalized.get("child_last_name"))
    child_birth_date = _text(normalized.get("child_birth_date"))
    customer_type = _lower(normalized.get("customer_type")) or "adult"

    clients = db.scalars(
        select(User)
        .where(
            User.role == UserRole.CLIENT,
            User.client_status != ClientStatus.ARCHIVED,
        )
        .order_by(User.created_at.desc())
    ).all()

    out: list[dict[str, object]] = []
    for client in clients:
        score = 0
        reasons: list[str] = []
        if parent_email and _lower(client.email) == parent_email:
            score += 85
            reasons.append("email exact")

        candidate_phones = [_digits(client.phone), _digits(client.mobile_phone_1), _digits(client.mobile_phone_2), _digits(client.home_phone)]
        if parent_phone and parent_phone in {phone for phone in candidate_phones if phone}:
            score += 65
            reasons.append("telephone exact")

        if parent_last_name and _lower(client.last_name) == parent_last_name:
            score += 12
            reasons.append("nom de famille proche")
        if parent_first_name and _lower(client.first_name) == parent_first_name:
            score += 10
            reasons.append("prenom proche")

        if customer_type == "adult" and _lower(client.client_kind.value if isinstance(client.client_kind, ClientKind) else client.client_kind) == "adult":
            if parent_first_name and parent_last_name and _lower(client.first_name) == parent_first_name and _lower(client.last_name) == parent_last_name:
                score += 25
                reasons.append("identite adulte exacte")

        if customer_type == "child" and _lower(client.client_kind.value if isinstance(client.client_kind, ClientKind) else client.client_kind) == "child":
            if child_first_name and _lower(client.first_name) == child_first_name:
                score += 25
                reasons.append("prenom eleve exact")
            if child_last_name and _lower(client.last_name) == child_last_name:
                score += 20
                reasons.append("nom eleve exact")
            if child_birth_date and client.birth_date and client.birth_date.isoformat() == child_birth_date:
                score += 30
                reasons.append("date de naissance exacte")

        if score <= 0:
            continue

        display, subtitle = _client_out_label(client)
        out.append(
            {
                "kind": "client",
                "client_id": client.id,
                "client_kind": client.client_kind.value if isinstance(client.client_kind, ClientKind) else client.client_kind,
                "display_name": display,
                "subtitle": subtitle,
                "confidence": score,
                "confidence_label": _confidence_label(score),
                "reasons": reasons,
            }
        )

    out.sort(key=lambda item: (int(item["confidence"]), _text(item["display_name"])), reverse=True)
    return out[:12]


def _is_child_client_candidate(candidate: dict[str, object] | None) -> bool:
    return _lower(_json_object(candidate).get("client_kind")) == "child"


def _collect_family_candidates(db: Session, normalized: dict[str, object]) -> list[dict[str, object]]:
    customer_type = _lower(normalized.get("customer_type")) or "adult"
    if customer_type != "child":
        return []

    adult_user = aliased(User, name="adult_user")
    child_user = aliased(User, name="child_user")
    rows = db.execute(
        select(ClientFamilyLink, adult_user, child_user)
        .join(adult_user, adult_user.id == ClientFamilyLink.adult_user_id)
        .join(child_user, child_user.id == ClientFamilyLink.child_user_id)
        .where(
            adult_user.role == UserRole.CLIENT,
            child_user.role == UserRole.CLIENT,
            adult_user.client_status != ClientStatus.ARCHIVED,
            child_user.client_status != ClientStatus.ARCHIVED,
        )
    ).all()

    parent_email = _lower(normalized.get("parent_email"))
    parent_phone = _digits(normalized.get("parent_phone"))
    parent_first_name = _lower(normalized.get("parent_first_name"))
    parent_last_name = _lower(normalized.get("parent_last_name"))
    child_first_name = _lower(normalized.get("child_first_name"))
    child_last_name = _lower(normalized.get("child_last_name"))
    child_birth_date = _text(normalized.get("child_birth_date"))

    out: list[dict[str, object]] = []
    for link, adult, child in rows:
        score = 0
        reasons: list[str] = []
        if parent_email and _lower(adult.email) == parent_email:
            score += 70
            reasons.append("email parent exact")
        adult_phones = {_digits(adult.phone), _digits(adult.mobile_phone_1), _digits(adult.mobile_phone_2), _digits(adult.home_phone)}
        if parent_phone and parent_phone in {phone for phone in adult_phones if phone}:
            score += 55
            reasons.append("telephone parent exact")
        if parent_first_name and _lower(adult.first_name) == parent_first_name:
            score += 10
            reasons.append("prenom parent proche")
        if parent_last_name and _lower(adult.last_name) == parent_last_name:
            score += 12
            reasons.append("nom parent proche")
        if child_first_name and _lower(child.first_name) == child_first_name:
            score += 28
            reasons.append("prenom eleve exact")
        if child_last_name and _lower(child.last_name) == child_last_name:
            score += 24
            reasons.append("nom eleve exact")
        if child_birth_date and child.birth_date and child.birth_date.isoformat() == child_birth_date:
            score += 28
            reasons.append("date de naissance eleve exacte")

        if score <= 0:
            continue

        child_identity_score = 0
        if child_first_name and _lower(child.first_name) == child_first_name:
            child_identity_score += 28
        if child_last_name and _lower(child.last_name) == child_last_name:
            child_identity_score += 24
        if child_birth_date and child.birth_date and child.birth_date.isoformat() == child_birth_date:
            child_identity_score += 28

        adult_label = _display_name(adult.first_name, adult.last_name, adult.email)
        child_label = _display_name(child.first_name, child.last_name, child.email)
        out.append(
            {
                "kind": "family",
                "adult_client_id": adult.id,
                "child_client_id": child.id,
                "billing_client_id": adult.id if link.is_billing_recipient else adult.id,
                "display_name": f"{adult_label} → {child_label}",
                "subtitle": adult.email,
                "confidence": score,
                "confidence_label": _confidence_label(score),
                "child_identity_score": child_identity_score,
                "reasons": reasons,
            }
        )

    out.sort(key=lambda item: (int(item["confidence"]), _text(item["display_name"])), reverse=True)
    return out[:8]


def _family_candidate_matches_requested_child(candidate: dict[str, object] | None) -> bool:
    if not candidate:
        return False
    return int(candidate.get("child_identity_score") or 0) >= 28


def _default_resolution(
    *,
    normalized: dict[str, object],
    stored_resolution: dict[str, object],
    client_candidates: list[dict[str, object]],
    family_candidates: list[dict[str, object]],
) -> dict[str, object]:
    client_resolution = _json_object(stored_resolution.get("client_resolution"))
    slot_resolution = _json_object(stored_resolution.get("slot_resolution"))
    notes = _text(stored_resolution.get("notes")) or None

    customer_type = _lower(normalized.get("customer_type")) or "adult"
    mode = _text(client_resolution.get("mode"))
    if not mode:
        best_family = family_candidates[0] if family_candidates else None
        best_client = client_candidates[0] if client_candidates else None
        if (
            customer_type == "child"
            and best_family
            and int(best_family.get("confidence") or 0) >= 95
            and _family_candidate_matches_requested_child(best_family)
        ):
            mode = CLIENT_MODE_EXISTING_FAMILY
        elif best_client and int(best_client.get("confidence") or 0) >= 95 and (
            customer_type != "child" or _is_child_client_candidate(best_client)
        ):
            mode = CLIENT_MODE_EXISTING
        elif customer_type == "child":
            mode = CLIENT_MODE_NEW_PARENT_CHILD
        else:
            mode = CLIENT_MODE_NEW_ADULT

    selected_client_id = _text(client_resolution.get("selected_client_id"))
    if not selected_client_id and mode == CLIENT_MODE_EXISTING and client_candidates:
        selected_client_id = str(client_candidates[0]["client_id"])

    selected_family_adult_client_id = _text(client_resolution.get("selected_family_adult_client_id"))
    selected_family_child_client_id = _text(client_resolution.get("selected_family_child_client_id"))
    selected_family_billing_client_id = _text(client_resolution.get("selected_family_billing_client_id"))
    if mode == CLIENT_MODE_EXISTING_FAMILY and family_candidates and not selected_family_adult_client_id:
        selected_family_adult_client_id = str(family_candidates[0]["adult_client_id"])
        selected_family_child_client_id = str(family_candidates[0]["child_client_id"])
        selected_family_billing_client_id = str(family_candidates[0]["billing_client_id"])

    selected_session_ids = _json_object(slot_resolution.get("selected_session_ids"))
    admin_state = _text(stored_resolution.get("admin_state")) or None
    admin_state_meta = _json_object(stored_resolution.get("admin_state_meta"))

    return {
        "client_resolution": {
            "mode": mode,
            "selected_client_id": selected_client_id or None,
            "selected_family_adult_client_id": selected_family_adult_client_id or None,
            "selected_family_child_client_id": selected_family_child_client_id or None,
            "selected_family_billing_client_id": selected_family_billing_client_id or None,
        },
        "slot_resolution": {
            "selected_session_ids": {
                _text(key): _text(value)
                for key, value in selected_session_ids.items()
                if _text(key) and _text(value)
            },
        },
        "notes": notes,
        "created_entities": _json_object(stored_resolution.get("created_entities")),
        "admin_state": admin_state,
        "admin_state_meta": admin_state_meta,
    }


def _resolve_template_item(
    db: Session,
    template: dict[str, object],
) -> tuple[str | None, UUID | None, UUID | None, UUID | None, list[str]]:
    kind = _lower(template.get("kind"))
    issues: list[str] = []
    if kind == "activity":
        item_id = _parse_uuid(template.get("activity_id"))
        activity: CourseType | None = None
        if item_id is not None:
            activity = db.scalar(select(CourseType).where(CourseType.id == item_id))
        if activity is None:
            code = _text(template.get("activity_code"))
            if code:
                activity = db.scalar(select(CourseType).where(CourseType.code == code))
        if activity is None:
            issues.append("activite introuvable dans la configuration Typeform")
            return kind, None, None, None, issues
        return kind, activity.id, None, None, issues

    if kind == "product":
        issues.append("lignes produit non implementees pour cette demo")
        return kind, None, None, None, issues

    if kind == "kit":
        issues.append("lignes kit non implementees pour cette demo")
        return kind, None, None, None, issues

    issues.append("type de ligne Typeform inconnu")
    return kind or None, None, None, None, issues


def _location_override_match_values(entry: dict[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("match_value", "location_label"):
        text = _text(entry.get(key))
        if text:
            values.append(text)
    for key in ("match_values", "aliases", "labels"):
        for item in _json_list(entry.get(key)):
            text = _text(item)
            if text:
                values.append(text)
    location_code = _text(entry.get("location_code"))
    if location_code:
        values.append(location_code)
    location_name = _text(entry.get("location_name"))
    if location_name:
        values.append(location_name)
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _normalize_token(value)
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _find_location_by_request_value(
    db: Session,
    requested_location: str | None,
) -> tuple[Location | None, str | None]:
    token = _normalize_token(requested_location).replace("_", " ")
    if not token:
        return None, None

    rows = db.scalars(select(Location).where(Location.active.is_(True)).order_by(Location.name.asc())).all()
    exact_matches: list[Location] = []
    fuzzy_matches: list[Location] = []

    for row in rows:
        candidates = {
            _normalize_token(row.code).replace("_", " "),
            _normalize_token(row.name),
        }
        if token in candidates:
            exact_matches.append(row)
            continue
        for candidate in candidates:
            if candidate and len(candidate) >= 4 and candidate in token:
                fuzzy_matches.append(row)
                break

    if len(exact_matches) == 1:
        return exact_matches[0], None
    if len(exact_matches) > 1:
        return None, f"Le lieu '{_text(requested_location)}' correspond a plusieurs sites actifs."
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0], None
    if len(fuzzy_matches) > 1:
        return None, f"Le lieu '{_text(requested_location)}' est ambigu entre plusieurs sites."
    return None, None


def _resolve_location_from_override(
    db: Session,
    entry: dict[str, object],
) -> Location | None:
    location_id = _parse_uuid(entry.get("location_id"))
    if location_id is not None:
        row = db.scalar(select(Location).where(Location.id == location_id, Location.active.is_(True)).limit(1))
        if row is not None:
            return row

    location_code = _text(entry.get("location_code"))
    if location_code:
        row = db.scalar(select(Location).where(Location.code == location_code, Location.active.is_(True)).limit(1))
        if row is not None:
            return row

    location_name = _text(entry.get("location_name"))
    if location_name:
        row = db.scalar(select(Location).where(Location.name == location_name, Location.active.is_(True)).limit(1))
        if row is not None:
            return row

    return None


def _apply_runtime_override(runtime_context: dict[str, object], entry: dict[str, object]) -> None:
    quote_type_id = _parse_uuid(entry.get("quote_type_id"))
    if quote_type_id is not None:
        runtime_context["quote_type_id"] = quote_type_id
    quote_type = _text(entry.get("quote_type"))
    if quote_type:
        runtime_context["quote_type"] = quote_type

    pricing_catalog_id = _parse_uuid(entry.get("pricing_catalog_id"))
    if pricing_catalog_id is not None:
        runtime_context["pricing_catalog_id"] = pricing_catalog_id

    payment_plan_id = _parse_uuid(entry.get("payment_plan_id"))
    if payment_plan_id is not None:
        runtime_context["payment_plan_id"] = payment_plan_id

    legal_entity_id = _parse_uuid(entry.get("legal_entity_id"))
    if legal_entity_id is not None:
        runtime_context["legal_entity_id"] = legal_entity_id


def _find_override_for_location(
    location_overrides: list[dict[str, object]],
    location: Location | None,
) -> dict[str, object] | None:
    if location is None:
        return None
    location_tokens = {
        _normalize_token(location.code),
        _normalize_token(location.name),
    }
    for entry in location_overrides:
        match_values = set(_location_override_match_values(entry))
        if match_values & location_tokens:
            return entry
    return None


def _resolve_form_runtime_context(
    db: Session,
    *,
    config: TypeformFormConfig | None,
    normalized: dict[str, object],
) -> dict[str, object]:
    requested_location = _text(normalized.get("requested_location")) or None
    if config is None:
        return {
            "requested_location": requested_location,
            "location_id": None,
            "location_code": None,
            "location_name": None,
            "school_year_label": None,
            "quote_type_id": None,
            "quote_type": None,
            "pricing_catalog_id": None,
            "pricing_catalog_name": None,
            "payment_plan_id": None,
            "payment_plan_name": None,
            "legal_entity_id": None,
            "legal_entity_name": None,
            "warnings": [],
            "blockages": [],
        }

    config_json = _json_object(config.configuration_json)
    location_overrides = [item for item in _json_list(config_json.get("location_overrides")) if isinstance(item, dict)]
    warnings: list[str] = []
    blockages: list[str] = []
    location = db.scalar(select(Location).where(Location.id == config.default_location_id).limit(1)) if config.default_location_id else None

    runtime_context: dict[str, object] = {
        "requested_location": requested_location,
        "location_id": config.default_location_id,
        "location_code": config.location_code,
        "location_name": location.name if location is not None else None,
        "school_year_label": _text(config.school_year_label) or None,
        "quote_type_id": config.default_quote_type_id,
        "quote_type": _text(config.default_quote_type) or None,
        "pricing_catalog_id": config.default_pricing_catalog_id,
        "payment_plan_id": config.default_payment_plan_id,
        "legal_entity_id": config.default_legal_entity_id,
    }

    matched_override: dict[str, object] | None = None
    if requested_location:
        requested_token = _normalize_token(requested_location)
        for entry in location_overrides:
            if requested_token in set(_location_override_match_values(entry)):
                matched_override = entry
                break

        if matched_override is not None:
            override_location = _resolve_location_from_override(db, matched_override)
            if any(_text(matched_override.get(key)) for key in ("location_id", "location_code", "location_name")) and override_location is None:
                blockages.append(
                    f"Le lieu '{requested_location}' est mappe mais le site cible n existe pas dans l application."
                )
            elif override_location is not None:
                location = override_location
        else:
            inferred_location, warning_message = _find_location_by_request_value(db, requested_location)
            if warning_message:
                warnings.append(warning_message)
            if inferred_location is not None:
                location = inferred_location
                matched_override = _find_override_for_location(location_overrides, inferred_location)

        if requested_location and location is None and location_overrides:
            blockages.append(f"Aucun site configure pour le lieu '{requested_location}'.")

    if matched_override is not None:
        _apply_runtime_override(runtime_context, matched_override)

    if location is not None:
        runtime_context["location_id"] = location.id
        runtime_context["location_code"] = location.code
        runtime_context["location_name"] = location.name

    quote_type = db.scalar(select(QuoteType).where(QuoteType.id == runtime_context["quote_type_id"]).limit(1)) if runtime_context.get("quote_type_id") else None
    pricing_catalog = (
        db.scalar(select(PricingCatalog).where(PricingCatalog.id == runtime_context["pricing_catalog_id"]).limit(1))
        if runtime_context.get("pricing_catalog_id")
        else None
    )
    payment_plan = (
        db.scalar(select(PaymentPlan).where(PaymentPlan.id == runtime_context["payment_plan_id"]).limit(1))
        if runtime_context.get("payment_plan_id")
        else None
    )
    legal_entity = (
        db.scalar(select(LegalEntity).where(LegalEntity.id == runtime_context["legal_entity_id"]).limit(1))
        if runtime_context.get("legal_entity_id")
        else None
    )

    runtime_context["quote_type"] = quote_type.name if quote_type is not None else runtime_context.get("quote_type")
    runtime_context["pricing_catalog_name"] = pricing_catalog.name if pricing_catalog is not None else None
    runtime_context["school_year_label"] = (
        _text(quote_type.school_year_label if quote_type is not None else None)
        or _text(pricing_catalog.school_year_label if pricing_catalog is not None else None)
        or _text(config.school_year_label)
        or None
    )

    requested_payment_method = _text(normalized.get("requested_payment_method")) or None
    requested_payment_method = _specific_requested_payment_method_from_products(
        requested_payment_method,
        _json_list(normalized.get("requested_products")),
    )
    requested_payment_method_code = _requested_payment_method_code(requested_payment_method)
    if requested_payment_method_code:
        requested_installments = _requested_payment_installment_count(requested_payment_method)
        requested_monthly = requested_payment_method_code == "CARD_MONTHLY" or (
            "mensuel" in _normalize_token(requested_payment_method)
            or "monthly" in _normalize_token(requested_payment_method)
        )
        candidate_plans = db.scalars(
            select(PaymentPlan)
            .where(
                PaymentPlan.is_active.is_(True),
                PaymentPlan.payment_method == requested_payment_method_code,
            )
            .order_by(PaymentPlan.created_at.asc())
        ).all()
        if candidate_plans:
            matching_plans = candidate_plans
            if requested_installments is not None:
                matching_plans = [
                    item for item in candidate_plans if _payment_plan_installment_count(item) == requested_installments
                ]
            elif requested_monthly:
                matching_plans = [item for item in candidate_plans if _payment_plan_is_monthly(item)]
            if not matching_plans:
                matching_plans = candidate_plans

            if (
                payment_plan is not None
                and _text(payment_plan.payment_method).strip().upper() == requested_payment_method_code
                and payment_plan in matching_plans
            ):
                chosen_payment_plan = payment_plan
            else:
                chosen_payment_plan = next(
                    (item for item in matching_plans if payment_plan is not None and item.schedule_type == payment_plan.schedule_type),
                    matching_plans[0],
                )
            runtime_context["payment_plan_id"] = chosen_payment_plan.id
            payment_plan = chosen_payment_plan

    runtime_context["payment_plan_name"] = payment_plan.name if payment_plan is not None else None
    runtime_context["legal_entity_name"] = legal_entity.name if legal_entity is not None else None
    runtime_context["warnings"] = list(dict.fromkeys(warnings))
    runtime_context["blockages"] = list(dict.fromkeys(blockages))
    return runtime_context


def _catalog_product_haystack(product: CatalogProduct) -> str:
    return _normalize_token(
        " ".join(
            part
            for part in (
                product.title,
                product.barcode,
                product.short_description,
                product.long_description,
            )
            if _text(part)
        )
    )


def _find_pass_recup_product(db: Session) -> CatalogProduct | None:
    rows = db.scalars(
        select(CatalogProduct)
        .where(CatalogProduct.active.is_(True))
        .order_by(CatalogProduct.title.asc())
    ).all()
    candidates: list[tuple[int, str, CatalogProduct]] = []
    for row in rows:
        haystack = _catalog_product_haystack(row)
        if "passrecup" in haystack.replace(" ", "") or ("pass" in haystack and "recup" in haystack):
            price = _q2(Decimal(getattr(row, "price_incl_vat", None) or Decimal("0.00")))
            excluded_automatic_label = any(token in haystack for token in ("offert", "gratuit", "famille"))
            if excluded_automatic_label or price <= Decimal("0.00"):
                continue
            priority = 0 if price == Decimal("50.00") else 1
            candidates.append((priority, _text(getattr(row, "title", "")), row))
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2] if candidates else None


def _find_solfege_book_product(db: Session, level_code: str | None) -> CatalogProduct | None:
    level = _text(level_code)
    if level not in {"1", "2", "3", "4", "5"}:
        return None
    rows = db.scalars(
        select(CatalogProduct)
        .where(CatalogProduct.active.is_(True))
        .order_by(CatalogProduct.title.asc())
    ).all()
    candidates: list[CatalogProduct] = []
    for row in rows:
        haystack = _catalog_product_haystack(row)
        if "cahier" not in haystack or "solfege" not in haystack:
            continue
        if re.search(rf"\b{re.escape(level)}\b", haystack) or f"niveau {level}" in haystack:
            candidates.append(row)
    return candidates[0] if candidates else None


def _quote_lines_contain_product(
    quote_lines: list[QuoteLineIn],
    *,
    product: CatalogProduct | None = None,
    tokens: tuple[str, ...] = (),
) -> bool:
    product_id = product.id if product is not None else None
    for line in quote_lines:
        if product_id is not None and line.product_id == product_id:
            return True
        haystack = _normalize_token(" ".join(part for part in (line.code, line.title, line.description) if _text(part)))
        if tokens and all(token in haystack for token in tokens):
            return True
    return False


def _course_type_haystack(activity: CourseType) -> str:
    return _normalize_token(
        " ".join(
            part
            for part in (
                activity.code,
                activity.name,
                activity.description,
                activity.service_code,
            )
            if _text(part)
        )
    )


def _find_solfege_activity(db: Session, *, modality: str = "onsite", level_code: str | None = None) -> CourseType | None:
    onsite = modality != "online"
    level = _text(level_code)
    rows = db.scalars(
        select(CourseType)
        .where(CourseType.active.is_(True))
        .order_by(CourseType.name.asc())
    ).all()
    candidates: list[tuple[int, CourseType]] = []
    for row in rows:
        haystack = _course_type_haystack(row)
        if "solfege" not in haystack:
            continue
        score = 0
        row_level_match = False
        row_has_other_level = False
        if level in {"1", "2", "3", "4", "5"}:
            row_level_match = bool(
                re.search(rf"\bniveau\s*{re.escape(level)}\b", haystack)
                or re.search(rf"\bn\s*{re.escape(level)}\b", haystack)
                or re.search(rf"\bn{re.escape(level)}\b", haystack)
            )
            row_has_other_level = bool(
                re.search(r"\bniveau\s*[1-5]\b", haystack)
                or re.search(r"\bn\s*[1-5]\b", haystack)
                or re.search(r"\bn[1-5]\b", haystack)
            ) and not row_level_match
            if row_level_match:
                score += 100
            elif row_has_other_level:
                score -= 80
        if row.mode == DeliveryMode.ONSITE:
            score += 20 if onsite else -5
        elif row.mode == DeliveryMode.ONLINE:
            score += -8 if onsite else 20
        elif row.mode == DeliveryMode.ANY:
            score += 8
        if onsite and "presentiel" in haystack:
            score += 10
        if not onsite and ("online" in haystack or "ligne" in haystack):
            score += 10
        if "collectif" in haystack:
            score += 2
        candidates.append((score, row))
    candidates.sort(key=lambda item: (-item[0], item[1].name))
    return candidates[0][1] if candidates else None


def _find_second_piano_activity(
    db: Session,
    *,
    modality: str,
    preview_lines: list[TypeformQuotePreviewLineOut],
) -> CourseType | None:
    if modality != "online":
        for line in preview_lines:
            if line.activity_id is None:
                continue
            haystack = _normalize_token(_preview_line_haystack(line))
            if "piano" in haystack and "solfege" not in haystack:
                return db.scalar(select(CourseType).where(CourseType.id == line.activity_id, CourseType.active.is_(True)))

    rows = db.scalars(
        select(CourseType)
        .where(CourseType.active.is_(True))
        .order_by(CourseType.name.asc())
    ).all()
    candidates: list[tuple[int, CourseType]] = []
    for row in rows:
        haystack = _course_type_haystack(row)
        if "piano" not in haystack or "solfege" in haystack:
            continue
        score = 0
        if "collectif" in haystack or "group" in haystack:
            score += 20
        if modality == "online":
            if row.mode == DeliveryMode.ONLINE:
                score += 40
            if "ligne" in haystack or "online" in haystack:
                score += 20
        elif row.mode == DeliveryMode.ONSITE:
            score += 30
        candidates.append((score, row))
    candidates.sort(key=lambda item: (-item[0], item[1].name))
    return candidates[0][1] if candidates else None


def _quote_lines_contain_solfege_activity(
    quote_lines: list[QuoteLineIn],
    preview_lines: list[TypeformQuotePreviewLineOut],
) -> bool:
    for line in quote_lines:
        if line.activity_id is not None and "solfege" in _normalize_token(" ".join(part for part in (line.code, line.title, line.description) if _text(part))):
            return True
    for line in preview_lines:
        if line.activity_id is not None and "solfege" in _normalize_token(_preview_line_haystack(line)):
            return True
    return False


def _preview_line_from_quote_line(
    line_in: QuoteLineIn,
    *,
    code: str | None,
    title: str,
    description: str | None,
    quantity: Decimal,
    unit_price: Decimal,
    vat_rate: Decimal,
    meta: dict[str, object],
) -> TypeformQuotePreviewLineOut:
    signed_unit_price = _q2(unit_price)
    if line_in.line_type == "discount":
        signed_unit_price = _q2(-abs(signed_unit_price))
    elif line_in.line_type == "surcharge":
        signed_unit_price = _q2(abs(signed_unit_price))
    unit_price_ht, unit_vat_amount = _split_ttc(signed_unit_price, vat_rate)
    amount_ht = _q2(unit_price_ht * quantity)
    amount_vat = _q2(unit_vat_amount * quantity)
    amount_ttc = _q2(amount_ht + amount_vat)
    return TypeformQuotePreviewLineOut(
        line_category=line_in.line_category,
        line_type=line_in.line_type,
        master_item_type=line_in.master_item_type,
        master_item_id=line_in.master_item_id,
        activity_id=line_in.activity_id,
        product_id=line_in.product_id,
        kit_id=line_in.kit_id,
        code=code,
        title=title,
        description=description,
        pricing_unit=line_in.pricing_unit,
        quantity=_q2(quantity),
        vat_rate=vat_rate,
        unit_price_ht=unit_price_ht,
        unit_vat_amount=unit_vat_amount,
        unit_price_ttc=signed_unit_price,
        amount_ht=amount_ht,
        amount_vat=amount_vat,
        amount_ttc=amount_ttc,
        meta=meta,
    )


def _append_catalog_product_quote_line(
    db: Session,
    *,
    product: CatalogProduct,
    quote_lines: list[QuoteLineIn],
    preview_lines: list[TypeformQuotePreviewLineOut],
    pricing_catalog_id: UUID | None,
    resolved_location_id: UUID | None,
    default_vat_rate: Decimal,
    source: str,
) -> None:
    line_in = QuoteLineIn(
        line_category="product",
        line_type="item",
        master_item_type="product",
        master_item_id=product.id,
        product_id=product.id,
        title=product.title,
        quantity=Decimal("1.00"),
        vat_rate=default_vat_rate,
        unit_price_ttc=Decimal("0.00"),
        pricing_unit="item",
        sort_order=len(quote_lines),
        meta={"typeform_automatic_line": source},
    )
    code, title, description, _duration, unit_price, meta = _effective_item_price(
        db,
        line=line_in,
        pricing_catalog_id=pricing_catalog_id,
        location_id=resolved_location_id,
    )
    meta = {**dict(meta), "typeform_automatic_line": source}
    vat_rate = _q3(line_in.vat_rate if line_in.vat_rate is not None else product.vat_rate or default_vat_rate)
    preview_lines.append(
        _preview_line_from_quote_line(
            line_in,
            code=code,
            title=title,
            description=description,
            quantity=Decimal("1.00"),
            unit_price=_q2(unit_price),
            vat_rate=vat_rate,
            meta=meta,
        )
    )
    quote_lines.append(
        QuoteLineIn(
            line_category="product",
            line_type="item",
            master_item_type="product",
            master_item_id=product.id,
            product_id=product.id,
            code=code,
            title=title,
            description=description,
            pricing_unit="item",
            quantity=Decimal("1.00"),
            vat_rate=vat_rate,
            unit_price_ttc=_q2(unit_price),
            sort_order=len(quote_lines),
            meta=meta,
        )
    )


def _append_activity_quote_line(
    db: Session,
    *,
    activity: CourseType,
    quote_lines: list[QuoteLineIn],
    preview_lines: list[TypeformQuotePreviewLineOut],
    pricing_catalog_id: UUID | None,
    resolved_location_id: UUID | None,
    default_vat_rate: Decimal,
    warnings: list[str],
    source: str,
    unit_price_override_ttc: Decimal | None = None,
    extra_meta: dict[str, object] | None = None,
) -> None:
    meta: dict[str, object] = {"typeform_automatic_line": source, **(extra_meta or {})}
    if unit_price_override_ttc is not None and unit_price_override_ttc > Decimal("0.00"):
        meta["manual_unit_price_override"] = True
        meta["typeform_unit_price_ttc"] = str(_q2(unit_price_override_ttc))
    line_in = QuoteLineIn(
        line_category="service",
        line_type="item",
        master_item_type="activity",
        master_item_id=activity.id,
        activity_id=activity.id,
        title=activity.name,
        quantity=Decimal("1.00"),
        vat_rate=default_vat_rate,
        unit_price_ttc=_q2(unit_price_override_ttc) if unit_price_override_ttc is not None else Decimal("0.00"),
        pricing_unit="session",
        sort_order=len(quote_lines),
        meta=meta,
    )
    code, title, description, duration, unit_price, meta = _effective_item_price(
        db,
        line=line_in,
        pricing_catalog_id=pricing_catalog_id,
        location_id=resolved_location_id,
    )
    meta = {**dict(meta), "typeform_automatic_line": source, **(extra_meta or {})}
    pricing_source = _text(meta.get("pricing_source"))
    if pricing_source == "activity_default_course_rate":
        warnings.append(f"Tarif catalogue absent pour {title}, tarif par defaut activite utilise.")
    if pricing_source == "activity_default_hourly_rate":
        warnings.append(f"Tarif catalogue absent pour {title}, tarif horaire par defaut activite utilise.")
    if pricing_source == "catalog_activity" and pricing_catalog_id is not None and resolved_location_id is not None:
        location_specific_price = db.scalar(
            select(PricingActivityPrice.id)
            .where(
                PricingActivityPrice.catalog_id == pricing_catalog_id,
                PricingActivityPrice.activity_id == activity.id,
                PricingActivityPrice.location_id == resolved_location_id,
                PricingActivityPrice.is_active.is_(True),
            )
            .limit(1)
        )
        if location_specific_price is None:
            warnings.append(f"Tarif specifique au site absent pour {title}, tarif catalogue general utilise.")
    vat_rate = _q3(line_in.vat_rate if line_in.vat_rate is not None else default_vat_rate)
    preview_lines.append(
        _preview_line_from_quote_line(
            line_in,
            code=code,
            title=title,
            description=description,
            quantity=Decimal("1.00"),
            unit_price=_q2(unit_price),
            vat_rate=vat_rate,
            meta=meta,
        )
    )
    quote_lines.append(
        QuoteLineIn(
            line_category="service",
            line_type="item",
            master_item_type="activity",
            master_item_id=activity.id,
            activity_id=activity.id,
            code=code,
            title=title,
            description=description,
            duration_minutes=duration,
            pricing_unit="session",
            quantity=Decimal("1.00"),
            vat_rate=vat_rate,
            unit_price_ttc=_q2(unit_price),
            sort_order=len(quote_lines),
            meta=meta,
        )
    )


def _append_loyalty_discount_line(
    *,
    quote_lines: list[QuoteLineIn],
    preview_lines: list[TypeformQuotePreviewLineOut],
    default_vat_rate: Decimal,
) -> None:
    if _quote_lines_contain_product(quote_lines, tokens=("remise", "fidelite")):
        return
    amount = Decimal("2.00")
    line_in = QuoteLineIn(
        line_category="service",
        line_type="discount",
        master_item_type="discount_rule",
        title="Remise fidélité",
        quantity=Decimal("1.00"),
        vat_rate=default_vat_rate,
        unit_price_ttc=amount,
        pricing_unit="fixed",
        sort_order=len(quote_lines),
        meta={"typeform_automatic_line": "loyalty_discount", "discount_kind": "loyalty"},
    )
    meta = dict(line_in.meta)
    preview_lines.append(
        _preview_line_from_quote_line(
            line_in,
            code=None,
            title=line_in.title,
            description=None,
            quantity=Decimal("1.00"),
            unit_price=amount,
            vat_rate=_q3(default_vat_rate),
            meta=meta,
        )
    )
    quote_lines.append(line_in)


def _append_automatic_typeform_lines(
    db: Session,
    *,
    normalized: dict[str, object],
    runtime_context: dict[str, object],
    preview_lines: list[TypeformQuotePreviewLineOut],
    quote_lines: list[QuoteLineIn],
    warnings: list[str],
    default_vat_rate: Decimal,
) -> None:
    pricing_catalog_id = _parse_uuid(runtime_context.get("pricing_catalog_id"))
    runtime_location_id = _parse_uuid(runtime_context.get("location_id"))

    requested_solfege_modality = _text(normalized.get("requested_solfege_modality"))
    if not requested_solfege_modality:
        requested_solfege_modality = "online" if _bool_or_default(normalized.get("requested_online_solfege"), False) else ""
        requested_solfege_modality = requested_solfege_modality or ("onsite" if _bool_or_default(normalized.get("requested_onsite_solfege"), False) else "")

    second_course = _json_object(normalized.get("requested_second_course"))
    if _bool_or_default(second_course.get("requested"), False):
        second_course_modality = _text(second_course.get("modality")) or "onsite"
        activity = _find_second_piano_activity(
            db,
            modality=second_course_modality,
            preview_lines=preview_lines,
        )
        if activity is None:
            warnings.append("Activite automatique introuvable pour le 2e cours de piano.")
        elif not any(_text(_json_object(line.meta).get("typeform_automatic_line")) == "second_piano_course" for line in quote_lines):
            unit_price_override = _parse_decimal(second_course.get("unit_price_ttc"))
            resolved_location_id = runtime_location_id if second_course_modality != "online" else None
            display_name = "2e cours de piano en ligne" if second_course_modality == "online" else "2e cours de piano en presentiel"
            _append_activity_quote_line(
                db,
                activity=activity,
                quote_lines=quote_lines,
                preview_lines=preview_lines,
                pricing_catalog_id=pricing_catalog_id,
                resolved_location_id=resolved_location_id,
                default_vat_rate=default_vat_rate,
                warnings=warnings,
                source="second_piano_course",
                unit_price_override_ttc=unit_price_override if unit_price_override > Decimal("0.00") else None,
                extra_meta={
                    "typeform_display_name": display_name,
                    "typeform_second_course": True,
                    "typeform_second_course_modality": second_course_modality,
                },
            )

    if requested_solfege_modality in {"online", "onsite"}:
        resolved_location_id = runtime_location_id if requested_solfege_modality == "onsite" else None
        activity = _find_solfege_activity(
            db,
            modality=requested_solfege_modality,
            level_code=_text(normalized.get("estimated_solfege_level")),
        )
        if activity is None:
            modality_label = "en ligne" if requested_solfege_modality == "online" else "en presentiel"
            warnings.append(f"Activite automatique introuvable pour Cours de solfege {modality_label}.")
        elif not _quote_lines_contain_solfege_activity(quote_lines, preview_lines):
            _append_activity_quote_line(
                db,
                activity=activity,
                quote_lines=quote_lines,
                preview_lines=preview_lines,
                pricing_catalog_id=pricing_catalog_id,
                resolved_location_id=resolved_location_id,
                default_vat_rate=default_vat_rate,
                warnings=warnings,
                source=f"{requested_solfege_modality}_solfege",
            )

    if _bool_or_default(normalized.get("requested_pass_recup"), False):
        resolved_location_id = runtime_location_id
        product = _find_pass_recup_product(db)
        if product is None:
            warnings.append("Produit automatique introuvable pour Pass Recup.")
        elif not _quote_lines_contain_product(quote_lines, product=product, tokens=("pass", "recup")):
            _append_catalog_product_quote_line(
                db,
                product=product,
                quote_lines=quote_lines,
                preview_lines=preview_lines,
                pricing_catalog_id=pricing_catalog_id,
                resolved_location_id=resolved_location_id,
                default_vat_rate=default_vat_rate,
                source="pass_recup",
            )

    level_code = _text(normalized.get("estimated_solfege_level"))
    if level_code in {"1", "2", "3", "4", "5"}:
        resolved_location_id = runtime_location_id
        product = _find_solfege_book_product(db, level_code)
        if product is None:
            warnings.append(f"Produit automatique introuvable pour Cahier de solfege niveau {level_code}.")
        elif not _quote_lines_contain_product(quote_lines, product=product, tokens=("cahier", "solfege")):
            _append_catalog_product_quote_line(
                db,
                product=product,
                quote_lines=quote_lines,
                preview_lines=preview_lines,
                pricing_catalog_id=pricing_catalog_id,
                resolved_location_id=resolved_location_id,
                default_vat_rate=default_vat_rate,
                source=f"solfege_book_level_{level_code}",
            )

    if _bool_or_default(normalized.get("is_reenrollment"), False):
        _append_loyalty_discount_line(
            quote_lines=quote_lines,
            preview_lines=preview_lines,
            default_vat_rate=default_vat_rate,
        )


def _build_preview_lines(
    db: Session,
    *,
    config: TypeformFormConfig | None,
    normalized: dict[str, object],
    runtime_context: dict[str, object],
) -> tuple[list[TypeformQuotePreviewLineOut], list[QuoteLineIn], list[str], list[str]]:
    config_json = _json_object(config.configuration_json if config is not None else {})
    line_templates = [item for item in _json_list(config_json.get("line_templates")) if isinstance(item, dict)]
    warnings: list[str] = []
    blockages: list[str] = []
    preview_lines: list[TypeformQuotePreviewLineOut] = []
    quote_lines: list[QuoteLineIn] = []

    default_vat_rate = _parse_decimal(config_json.get("default_vat_rate"), Decimal("20.00"))
    pricing_catalog_id = _parse_uuid(runtime_context.get("pricing_catalog_id"))
    resolved_location_id = _parse_uuid(runtime_context.get("location_id"))

    if not line_templates:
        blockages.append("Aucune ligne de pre-devis n est configuree pour ce formulaire.")
        return preview_lines, quote_lines, warnings, blockages

    applicable_templates = [
        dict(item)
        for item in line_templates
        if _template_matches_when(dict(item), normalized)
    ]
    if not applicable_templates:
        blockages.append("Aucune ligne de pre-devis ne correspond aux choix du formulaire.")
        return preview_lines, quote_lines, warnings, blockages

    for index, raw_template in enumerate(applicable_templates):
        template = _template_for_runtime_context(dict(raw_template), runtime_context=runtime_context)
        kind, activity_id, product_id, kit_id, issues = _resolve_template_item(db, template)
        if issues:
            blockages.extend(issues)
            continue

        quantity = _parse_decimal(template.get("quantity"), Decimal("1.00"))
        if quantity <= Decimal("0"):
            quantity = Decimal("1.00")
        template_unit_price = _q2(_parse_decimal(template.get("unit_price_ttc")))
        typeform_price_mode = ""
        if template_unit_price > Decimal("0"):
            if _bool_or_default(template.get("allow_price_override"), False) or _lower(template.get("price_mode")) in {"override", "forced"}:
                typeform_price_mode = "override"
            else:
                typeform_price_mode = "fallback"

        line_category = "service" if kind == "activity" else "product"
        meta_payload: dict[str, object] = {
            "typeform_template": template,
            "typeform_price_mode": typeform_price_mode or None,
            "typeform_unit_price_ttc": str(template_unit_price) if template_unit_price > Decimal("0") else None,
        }
        planning_session_limit = _planning_session_limit_from_meta(meta_payload)
        if planning_session_limit is not None:
            meta_payload["planning_session_limit"] = planning_session_limit
        commitment_kind = _text(template.get("commitment_kind"))
        if commitment_kind:
            meta_payload["commitment_kind"] = commitment_kind

        line_in = QuoteLineIn(
            line_category=line_category,
            line_type="item",
            master_item_type=kind if kind in {"activity", "product", "kit"} else None,
            master_item_id=activity_id or product_id or kit_id,
            activity_id=activity_id,
            product_id=product_id,
            kit_id=kit_id,
            title=_text(template.get("title")) or "Typeform item",
            quantity=quantity,
            vat_rate=default_vat_rate,
            unit_price_ttc=template_unit_price if typeform_price_mode == "override" else Decimal("0.00"),
            pricing_unit="session" if kind == "activity" else "item",
            sort_order=index,
            meta=meta_payload,
        )
        code, title, description, _duration, unit_price, meta = _effective_item_price(
            db,
            line=line_in,
            pricing_catalog_id=pricing_catalog_id,
            location_id=resolved_location_id,
        )
        meta = dict(meta)
        pricing_source = _text(meta.get("pricing_source"))
        if pricing_source == "activity_default_course_rate":
            warnings.append(f"Tarif catalogue absent pour {title}, tarif par defaut activite utilise.")
        if pricing_source == "activity_default_hourly_rate":
            warnings.append(f"Tarif catalogue absent pour {title}, tarif horaire par defaut activite utilise.")
        if pricing_source == "typeform_template_fallback":
            warnings.append(f"Tarif catalogue/activite absent pour {title}, tarif Typeform de secours utilise.")
        if pricing_source == "catalog_activity" and activity_id is not None and resolved_location_id is not None:
            location_specific_price = db.scalar(
                select(PricingActivityPrice.id)
                .where(
                    PricingActivityPrice.catalog_id == pricing_catalog_id,
                    PricingActivityPrice.activity_id == activity_id,
                    PricingActivityPrice.location_id == resolved_location_id,
                    PricingActivityPrice.is_active.is_(True),
                )
                .limit(1)
            )
            if location_specific_price is None:
                warnings.append(f"Tarif specifique au site absent pour {title}, tarif catalogue general utilise.")

        vat_rate = line_in.vat_rate if line_in.vat_rate is not None else _extract_vat_rate({"tva_rate": str(default_vat_rate)}) or Decimal("0.00")
        vat_rate = _q3(vat_rate)
        unit_price_ht, unit_vat_amount = _split_ttc(_q2(unit_price), vat_rate)
        amount_ht = _q2(unit_price_ht * quantity)
        amount_vat = _q2(unit_vat_amount * quantity)
        amount_ttc = _q2(amount_ht + amount_vat)

        preview_lines.append(
            TypeformQuotePreviewLineOut(
                line_category=line_category,
                line_type="item",
                master_item_type=line_in.master_item_type,
                master_item_id=line_in.master_item_id,
                activity_id=activity_id,
                product_id=product_id,
                kit_id=kit_id,
                code=code,
                title=title,
                description=description,
                pricing_unit=line_in.pricing_unit,
                quantity=_q2(quantity),
                vat_rate=vat_rate,
                unit_price_ht=unit_price_ht,
                unit_vat_amount=unit_vat_amount,
                unit_price_ttc=_q2(unit_price),
                amount_ht=amount_ht,
                amount_vat=amount_vat,
                amount_ttc=amount_ttc,
                meta=meta,
            )
        )
        quote_lines.append(
            QuoteLineIn(
                line_category=line_category,
                line_type="item",
                master_item_type=line_in.master_item_type,
                master_item_id=line_in.master_item_id,
                activity_id=activity_id,
                product_id=product_id,
                kit_id=kit_id,
                code=code,
                title=title,
                description=description,
                pricing_unit=line_in.pricing_unit,
                quantity=_q2(quantity),
                vat_rate=vat_rate,
                unit_price_ttc=_q2(unit_price),
                sort_order=index,
                meta=meta,
            )
        )

    _append_automatic_typeform_lines(
        db,
        normalized=normalized,
        runtime_context=runtime_context,
        preview_lines=preview_lines,
        quote_lines=quote_lines,
        warnings=warnings,
        default_vat_rate=default_vat_rate,
    )

    if not preview_lines:
        blockages.append("Le pre-devis est vide car aucune ligne exploitable n a ete resolue.")
    return preview_lines, quote_lines, warnings, blockages


_EMPTY_PREQUOTE_BLOCKAGES = {
    "Aucune ligne de pre-devis n est configuree pour ce formulaire.",
    "Aucune ligne de pre-devis ne correspond aux choix du formulaire.",
    "Le pre-devis est vide car aucune ligne exploitable n a ete resolue.",
}


def _can_force_empty_draft_quote(*, blockages: list[object], preview_lines_in: list[QuoteLineIn]) -> bool:
    if preview_lines_in:
        return False
    normalized_blockages = [_text(item) for item in blockages if _text(item)]
    if not normalized_blockages:
        return False
    return all(message in _EMPTY_PREQUOTE_BLOCKAGES for message in normalized_blockages)


def _safe_zoneinfo(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(_text(value) or "Europe/Paris")
    except Exception:
        return ZoneInfo("UTC")


def _session_is_typeform_candidate(session_obj: CourseSession) -> bool:
    # Intake matching is an administrative quote workflow. A private session must
    # stay hidden from public booking without being excluded from admin proposals.
    return session_obj.status == SessionStatus.SCHEDULED


def _requested_summary(normalized: dict[str, object]) -> str | None:
    return _requested_slot_summary(_json_list(normalized.get("requested_slot_preferences"))) or _requested_day_time_summary(normalized)


def _requested_slot_summary(preferences: list[object]) -> str | None:
    slot_labels: list[str] = []
    for item in preferences:
        if not isinstance(item, dict):
            continue
        day = _text(item.get("day"))
        time = _text(item.get("time"))
        if day and time:
            slot_labels.append(f"{day.capitalize()} {time}")
        elif day:
            slot_labels.append(day.capitalize())
        elif time:
            slot_labels.append(time)
    if slot_labels:
        return ", ".join(slot_labels)
    return None


def _requested_day_time_summary(normalized: dict[str, object]) -> str | None:
    days = [DAY_LABELS[_weekday_from_label(day)] for day in _json_list(normalized.get("requested_days")) if _weekday_from_label(day) is not None]
    times = [_text(item) for item in _json_list(normalized.get("requested_times")) if _text(item)]
    parts: list[str] = []
    if days:
        parts.append(", ".join(days))
    if times:
        parts.append(", ".join(times))
    return " · ".join(parts) if parts else None


def _school_year_bounds_from_label(label: object | None) -> tuple[date, date] | None:
    normalized = _text(label)
    match = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{4})", normalized)
    if match is None:
        return None
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year < start_year:
        return None
    return date(start_year, 9, 1), date(end_year, 8, 31)


def _school_year_start_year(label: object | None) -> int | None:
    bounds = _school_year_bounds_from_label(label)
    if bounds is None:
        return None
    return bounds[0].year


def _session_local_slot_key(
    session_obj: CourseSession,
    *,
    fallback_timezone: object | None = None,
) -> tuple[date, str, str, str, str]:
    zone = _safe_zoneinfo(getattr(session_obj, "timezone", None) or fallback_timezone)
    local_start = session_obj.start_at_utc.astimezone(zone)
    local_end = session_obj.end_at_utc.astimezone(zone)
    return (
        local_start.date(),
        local_start.strftime("%H:%M"),
        local_end.strftime("%H:%M"),
        str(session_obj.course_type_id),
        str(session_obj.location_id),
    )


def _dedupe_sessions_by_local_slot(
    session_rows: list[CourseSession],
    *,
    fallback_timezone: object | None = None,
) -> list[CourseSession]:
    deduped: list[CourseSession] = []
    seen: set[tuple[date, str, str, str, str]] = set()
    for row in sorted(session_rows, key=lambda item: item.start_at_utc):
        slot_key = _session_local_slot_key(row, fallback_timezone=fallback_timezone)
        if slot_key in seen:
            continue
        seen.add(slot_key)
        deduped.append(row)
    return deduped


def _local_school_year_bounds_utc(
    label: object | None,
    *,
    zone: ZoneInfo,
) -> tuple[datetime, datetime] | None:
    bounds = _school_year_bounds_from_label(label)
    if bounds is None:
        return None
    school_year_start, school_year_end = bounds
    start_local = datetime.combine(school_year_start, time.min, tzinfo=zone)
    end_local = datetime.combine(school_year_end + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _load_selected_session_school_year_series(
    db: Session,
    *,
    selected_session: CourseSession,
    location: Location,
    school_year_label: object | None,
) -> list[CourseSession]:
    if selected_session.recurrence_group_id is None:
        return [selected_session]

    zone = _safe_zoneinfo(selected_session.timezone or location.timezone)
    selected_local_start = selected_session.start_at_utc.astimezone(zone)
    selected_local_end = selected_session.end_at_utc.astimezone(zone)
    selected_start_label = selected_local_start.strftime("%H:%M")
    selected_end_label = selected_local_end.strftime("%H:%M")

    stmt = select(CourseSession).where(
        CourseSession.status == SessionStatus.SCHEDULED,
        CourseSession.course_type_id == selected_session.course_type_id,
        CourseSession.location_id == selected_session.location_id,
    )
    school_year_bounds_utc = _local_school_year_bounds_utc(school_year_label, zone=zone)
    if school_year_bounds_utc is not None:
        school_year_start_utc, school_year_end_utc = school_year_bounds_utc
        stmt = stmt.where(
            CourseSession.start_at_utc >= school_year_start_utc,
            CourseSession.start_at_utc < school_year_end_utc,
        )

    rows = db.scalars(stmt.order_by(CourseSession.start_at_utc.asc())).all()
    matching_rows = []
    for row in rows:
        row_zone = _safe_zoneinfo(row.timezone or location.timezone)
        local_start = row.start_at_utc.astimezone(row_zone)
        local_end = row.end_at_utc.astimezone(row_zone)
        if local_start.weekday() != selected_local_start.weekday():
            continue
        if local_start.strftime("%H:%M") != selected_start_label:
            continue
        if local_end.strftime("%H:%M") != selected_end_label:
            continue
        matching_rows.append(row)

    series_rows = _dedupe_sessions_by_local_slot(matching_rows, fallback_timezone=location.timezone)
    return series_rows or [selected_session]


def _source_code_school_year_family(source_code: object | None) -> str:
    normalized = _text(source_code).strip().lower()
    return re.sub(r"20\d{2}_20\d{2}", "{school_year}", normalized)


def _session_recommendations_have_options(
    recommendations: list[TypeformSessionRecommendationOut] | list[dict[str, object]] | None,
) -> bool:
    for recommendation in recommendations or []:
        if isinstance(recommendation, dict):
            options = _json_list(recommendation.get("options"))
            manual_options = _json_list(recommendation.get("manual_options"))
        else:
            options = list(getattr(recommendation, "options", []) or [])
            manual_options = list(getattr(recommendation, "manual_options", []) or [])
        if options or manual_options:
            return True
    return False


def _should_try_future_school_year_config(
    *,
    config: TypeformFormConfig | None,
    normalized: dict[str, object],
    session_recommendations: list[TypeformSessionRecommendationOut],
) -> bool:
    if config is None:
        return False
    has_requested_slots = bool(
        _json_list(normalized.get("requested_slot_preferences"))
        or _json_list(normalized.get("requested_days"))
        or _json_list(normalized.get("requested_times"))
    )
    if not has_requested_slots:
        return False
    return not _session_recommendations_have_options(session_recommendations)


def _future_school_year_candidate_configs(
    db: Session,
    *,
    current_config: TypeformFormConfig,
) -> list[TypeformFormConfig]:
    current_start_year = _school_year_start_year(current_config.school_year_label)
    if current_start_year is None:
        return []

    family = _source_code_school_year_family(current_config.source_code)
    rows = db.scalars(
        select(TypeformFormConfig).where(
            TypeformFormConfig.is_active.is_(True),
            TypeformFormConfig.id != current_config.id,
            TypeformFormConfig.location_code == current_config.location_code,
            TypeformFormConfig.audience_segment == current_config.audience_segment,
        )
    ).all()

    candidates: list[tuple[int, str, TypeformFormConfig]] = []
    for row in rows:
        if row.location_code != current_config.location_code:
            continue
        if row.audience_segment != current_config.audience_segment:
            continue
        candidate_start_year = _school_year_start_year(row.school_year_label)
        if candidate_start_year is None or candidate_start_year <= current_start_year:
            continue
        if _source_code_school_year_family(row.source_code) != family:
            continue
        candidates.append((candidate_start_year, row.source_code, row))

    candidates.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in candidates]


def _grouped_occurrence_label(option: TypeformSessionMatchOptionOut) -> str:
    return f"Chaque {option.weekday_label.lower()} · {option.start_time_label}-{option.end_time_label}"


def _collapse_session_option_groups(
    option_rows: list[tuple[CourseSession, TypeformSessionMatchOptionOut]],
    *,
    selected_session_id: UUID | None,
) -> list[TypeformSessionMatchOptionOut]:
    grouped_rows: dict[str, list[tuple[CourseSession, TypeformSessionMatchOptionOut]]] = {}
    for session_obj, option in option_rows:
        group_key = str(session_obj.recurrence_group_id or session_obj.id)
        grouped_rows.setdefault(group_key, []).append((session_obj, option))

    collapsed: list[TypeformSessionMatchOptionOut] = []
    for rows in grouped_rows.values():
        rows.sort(
            key=lambda row: (
                row[1].is_full,
                -row[1].score,
                row[0].start_at_utc.timestamp(),
            )
        )
        selected_row = next(
            (
                row
                for row in rows
                if selected_session_id is not None and row[1].session_id == selected_session_id
            ),
            None,
        )
        chosen_session, chosen_option = selected_row or rows[0]
        if len(rows) == 1 or chosen_session.recurrence_group_id is None:
            collapsed.append(chosen_option)
            continue

        aggregate_is_full = all(option.is_full for _, option in rows)
        aggregate_seats = max((option.seats_remaining for _, option in rows), default=chosen_option.seats_remaining)
        aggregate_score = max((option.score for _, option in rows), default=chosen_option.score)
        occurrence_label = _grouped_occurrence_label(chosen_option)
        selection_label = " · ".join(
            part
            for part in [
                occurrence_label,
                chosen_option.activity_name if chosen_option.activity_name else None,
                chosen_option.location_name,
                chosen_option.recurrence_label or "Seance ponctuelle",
                f"places {aggregate_seats}",
            ]
            if part
        )
        collapsed.append(
            TypeformSessionMatchOptionOut(
                session_id=chosen_option.session_id,
                activity_id=chosen_option.activity_id,
                activity_name=chosen_option.activity_name,
                location_id=chosen_option.location_id,
                location_name=chosen_option.location_name,
                title=chosen_option.title,
                start_at=chosen_option.start_at,
                start_time_label=chosen_option.start_time_label,
                end_time_label=chosen_option.end_time_label,
                weekday_label=chosen_option.weekday_label,
                occurrence_label=occurrence_label,
                selection_label=selection_label,
                recurrence_group_id=chosen_option.recurrence_group_id,
                recurrence_label=chosen_option.recurrence_label,
                seats_remaining=aggregate_seats,
                is_full=aggregate_is_full,
                score=aggregate_score,
                reasons=list(dict.fromkeys(chosen_option.reasons)),
            )
        )

    collapsed.sort(
        key=lambda item: (
            item.is_full,
            -item.score,
            item.start_at.timestamp(),
        )
    )
    return collapsed


def _typeform_session_option_from_row(
    *,
    session_obj: CourseSession,
    activity: CourseType,
    location: Location,
    booked_count: int,
    config: TypeformFormConfig | None,
    requested_location: str,
    resolved_location_id: UUID | None,
    requested_slot_preferences: list[dict[str, int | None]],
    requested_days: set[int],
    requested_times: list[int],
    include_activity_in_label: bool = False,
    extra_reasons: list[str] | None = None,
    allow_low_score: bool = False,
) -> TypeformSessionMatchOptionOut | None:
    zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
    local_start = session_obj.start_at_utc.astimezone(zone)
    weekday = local_start.weekday()
    start_minutes = local_start.hour * 60 + local_start.minute
    recurrence_label = _recurrence_label(session_obj.recurrence_rule)
    occurrence_label, time_range_label = _session_occurrence_label(
        local_start,
        session_obj.end_at_utc,
        session_obj.timezone or location.timezone,
    )
    score = 30
    reasons: list[str] = []
    if resolved_location_id is not None and resolved_location_id == location.id:
        score += 20
        reasons.append("site choisi")
    elif config is not None and config.default_location_id == location.id:
        score += 10
        reasons.append("site par defaut")
    requested_location_token = _normalize_token(requested_location).replace("_", " ")
    location_tokens = {
        _normalize_token(location.code).replace("_", " "),
        _normalize_token(location.name),
    }
    if (
        requested_location_token
        and resolved_location_id is None
        and any(token and token in requested_location_token for token in location_tokens)
    ):
        score += 20
        reasons.append("lieu prefere")
    if requested_slot_preferences:
        slot_match_found = False
        best_bonus = -20
        best_reason = "hors creneaux souhaites"
        for preference in requested_slot_preferences:
            pref_day = preference["day"]
            pref_time = preference["time"]
            if pref_day is not None and pref_day != weekday:
                continue
            slot_match_found = True
            if pref_time is None:
                if best_bonus < 25:
                    best_bonus = 25
                    best_reason = "jour souhaite"
                continue
            delta = abs(start_minutes - pref_time)
            if delta == 0 and best_bonus < 40:
                best_bonus = 40
                best_reason = "creneau exact"
            elif delta <= 30 and best_bonus < 32:
                best_bonus = 32
                best_reason = "creneau proche"
            elif delta <= 60 and best_bonus < 22:
                best_bonus = 22
                best_reason = "horaire acceptable"
        if not slot_match_found:
            return None
        else:
            score += best_bonus
            reasons.append(best_reason)
    else:
        if requested_days:
            if weekday in requested_days:
                score += 30
                reasons.append("jour souhaite")
            else:
                score -= 20
        if requested_times:
            best_delta = min(abs(start_minutes - item) for item in requested_times)
            if best_delta <= 30:
                score += 30
                reasons.append("horaire ideal")
            elif best_delta <= 60:
                score += 20
                reasons.append("horaire proche")
            elif best_delta <= 120:
                score += 10
                reasons.append("horaire acceptable")
            else:
                score -= 15
    seats_remaining = max(int(session_obj.capacity_max or 0) - int(booked_count), 0)
    is_full = seats_remaining <= 0
    if is_full:
        score -= 30
        reasons.append("complet")
    else:
        score += 15
        reasons.append("places disponibles")
    if extra_reasons:
        reasons.extend([_text(item) for item in extra_reasons if _text(item)])
    if score <= 0 and not allow_low_score:
        return None
    if score <= 0:
        reasons.append("choix manuel administrateur")
        score = max(score, 0)
    selection_label_parts = [occurrence_label]
    if include_activity_in_label:
        selection_label_parts.append(activity.name)
    selection_label_parts.extend(
        [
            location.name,
            recurrence_label or "Seance ponctuelle",
            f"places {seats_remaining}",
        ]
    )
    return TypeformSessionMatchOptionOut(
        session_id=session_obj.id,
        activity_id=activity.id,
        activity_name=activity.name,
        location_id=location.id,
        location_name=location.name,
        title=session_obj.title,
        start_at=session_obj.start_at_utc,
        start_time_label=local_start.strftime("%H:%M"),
        end_time_label=time_range_label.split("-", 1)[1],
        weekday_label=DAY_LABELS[weekday],
        occurrence_label=occurrence_label,
        selection_label=" · ".join(part for part in selection_label_parts if part),
        recurrence_group_id=session_obj.recurrence_group_id,
        recurrence_label=recurrence_label,
        seats_remaining=seats_remaining,
        is_full=is_full,
        score=score,
        reasons=reasons,
    )


def _preview_line_haystack(line: TypeformQuotePreviewLineOut) -> str:
    meta = _json_object(line.meta)
    template = _json_object(meta.get("typeform_template"))
    parts = [
        line.code,
        line.title,
        line.description,
        meta.get("activity_code"),
        meta.get("activity_name"),
        meta.get("service_code"),
        meta.get("location_code"),
        meta.get("location_name"),
        template.get("activity_code"),
        template.get("title"),
        template.get("description"),
        template.get("location_code"),
        template.get("location_name"),
    ]
    return " ".join(_text(part) for part in parts if _text(part)).lower()


def _matching_words(value: object | None) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", _normalize_token(value))
        if len(word) >= 3
    }


def _activity_matches_line_for_slot_fallback(activity: CourseType, line: TypeformQuotePreviewLineOut) -> bool:
    line_words = _matching_words(_preview_line_haystack(line))
    activity_words = _matching_words(" ".join([_text(activity.code), _text(activity.name)]))
    if not line_words or not activity_words:
        return False
    shared_words = line_words & activity_words
    collective_words = {"collectif", "collectifs"}
    teen_adult_words = {"ado", "ados", "adult", "adulte", "adultes"}
    child_words = {"child", "children", "enfant", "enfants"}
    onsite_words = {"onsite", "presentiel"}
    both_collective = bool((line_words & collective_words) and (activity_words & collective_words))
    if both_collective and (line_words & teen_adult_words) and (activity_words & teen_adult_words):
        return True
    if both_collective and (line_words & teen_adult_words) and (activity_words & child_words):
        return True
    if both_collective and (line_words & teen_adult_words) and (activity_words & onsite_words):
        return True
    if (
        both_collective
        and (line_words & onsite_words)
        and (activity_words & child_words)
        and not (activity_words & teen_adult_words)
    ):
        return True
    return len(shared_words) >= 3


def _line_expected_modality_for_slot_fallback(line: TypeformQuotePreviewLineOut) -> str | None:
    haystack = _normalize_token(_preview_line_haystack(line)).replace("_", " ")
    if "online" in haystack or "en ligne" in haystack or "ligne" in haystack:
        return "online"
    if "onsite" in haystack or "presentiel" in haystack:
        return "onsite"
    return None


def _line_allows_session_modality(
    line: TypeformQuotePreviewLineOut,
    *,
    activity: CourseType,
    location: Location,
) -> bool:
    expected_modality = _line_expected_modality_for_slot_fallback(line)
    if expected_modality is None:
        return True
    return _modality_from_activity_location(activity, location) == expected_modality


def _is_online_runtime_context(runtime_context: dict[str, object]) -> bool:
    tokens = {
        _normalize_token(runtime_context.get("location_code")),
        _normalize_token(runtime_context.get("location_name")),
        _normalize_token(runtime_context.get("requested_location")),
    }
    tokens.discard("")
    if "online" in tokens:
        return True
    return any(token in {"videocall", "video call", "visioconference", "video"} for token in tokens)


def _is_non_blocking_solfege_line(
    line: TypeformQuotePreviewLineOut,
    *,
    runtime_context: dict[str, object],
) -> bool:
    _ = runtime_context
    haystack = _normalize_token(_preview_line_haystack(line))
    if "solfege" not in haystack:
        return False
    return True


def _should_search_onsite_solfege_without_main_slot_filters(
    *,
    line_is_solfege: bool,
    line_solfege_modality: str,
    solfege_requested_slot_preferences: list[object],
) -> bool:
    return bool(
        line_is_solfege
        and line_solfege_modality == "onsite"
        and not solfege_requested_slot_preferences
    )


def _is_solfege_recommendation(
    recommendation: TypeformSessionRecommendationOut,
    *,
    runtime_context: dict[str, object],
) -> bool:
    haystack = _normalize_token(recommendation.activity_name)
    return "solfege" in haystack


def _extract_estimated_solfege_level(
    *,
    normalized: dict[str, object],
    session_recommendations: list[TypeformSessionRecommendationOut],
) -> str | None:
    has_solfege_context = any("solfege" in _normalize_token(item.activity_name) for item in session_recommendations)
    has_solfege_context = has_solfege_context or bool(_json_list(normalized.get("requested_solfege_slot_preferences")))
    has_solfege_context = has_solfege_context or _bool_or_default(normalized.get("requested_online_solfege"), False)
    has_solfege_context = has_solfege_context or _bool_or_default(normalized.get("requested_onsite_solfege"), False)
    has_solfege_context = has_solfege_context or any(
        "solfege" in _normalize_token(item)
        for item in _json_list(normalized.get("requested_products"))
    )
    if not has_solfege_context:
        return None

    normalized_level = _text(normalized.get("estimated_solfege_level"))
    if normalized_level in {"1", "2", "3", "4", "5"}:
        return normalized_level

    candidates = [
        _text(item)
        for item in _json_list(normalized.get("requested_products"))
        if _text(item)
    ]
    requested_formula = _text(normalized.get("requested_formula_type"))
    if requested_formula:
        candidates.append(requested_formula)

    for candidate in candidates:
        normalized_candidate = _normalize_token(candidate)
        if not normalized_candidate or "ne sais pas" in normalized_candidate:
            continue
        match = re.search(r"niveau\s*([1-5])", normalized_candidate)
        if match:
            return match.group(1)
    return None


def _effective_selected_session_ids(
    *,
    resolution: dict[str, object],
    session_recommendations: list[TypeformSessionRecommendationOut],
) -> dict[str, str]:
    stored_session_ids = _json_object(_json_object(resolution.get("slot_resolution")).get("selected_session_ids"))
    effective: dict[str, str] = {
        _text(key): _text(value)
        for key, value in stored_session_ids.items()
        if _text(key) and _text(value)
    }
    for recommendation in session_recommendations:
        activity_key = _session_recommendation_key(recommendation)
        if activity_key in effective or recommendation.selected_session_id is None:
            continue
        effective[activity_key] = str(recommendation.selected_session_id)
    return effective


def _line_recommendation_key(line: TypeformQuotePreviewLineOut) -> str:
    meta = _json_object(line.meta)
    source = _text(meta.get("typeform_automatic_line"))
    if source:
        return f"{line.activity_id}:{source}"
    return str(line.activity_id)


def _quote_line_recommendation_key(line: QuoteLineIn) -> str | None:
    if line.activity_id is None:
        return None
    meta = _json_object(line.meta)
    source = _text(meta.get("typeform_automatic_line"))
    if source:
        return f"{line.activity_id}:{source}"
    return str(line.activity_id)


def _planned_quantities_from_calendar_snapshot(calendar_snapshot: dict[str, object]) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = {}
    for raw_session in _json_list(_json_object(calendar_snapshot).get("sessions")):
        if not isinstance(raw_session, dict):
            continue
        activity_id = _text(raw_session.get("activity_id"))
        recommendation_key = _text(raw_session.get("recommendation_key"))
        keys = list(dict.fromkeys(key for key in (recommendation_key, activity_id) if key))
        for key in keys:
            quantities[key] = quantities.get(key, Decimal("0.00")) + Decimal("1.00")
    return quantities


def _planned_quantities_by_recommendation_key(calendar_snapshot: dict[str, object]) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = {}
    for raw_session in _json_list(_json_object(calendar_snapshot).get("sessions")):
        if not isinstance(raw_session, dict):
            continue
        recommendation_key = _text(raw_session.get("recommendation_key"))
        if not recommendation_key:
            continue
        quantities[recommendation_key] = quantities.get(recommendation_key, Decimal("0.00")) + Decimal("1.00")
    return quantities


def _planned_recommendation_key_order_by_activity(calendar_snapshot: dict[str, object]) -> dict[str, list[str]]:
    snapshot = _json_object(calendar_snapshot)
    keys_by_activity: dict[str, list[str]] = {}
    seen_by_activity: dict[str, set[str]] = {}

    def add_key(activity_id: str, recommendation_key: str) -> None:
        if not activity_id or not recommendation_key:
            return
        seen = seen_by_activity.setdefault(activity_id, set())
        if recommendation_key in seen:
            return
        seen.add(recommendation_key)
        keys_by_activity.setdefault(activity_id, []).append(recommendation_key)

    for raw_block in _json_list(snapshot.get("blocks")):
        if not isinstance(raw_block, dict):
            continue
        activity_id = _text(raw_block.get("activity_id"))
        recommendation_key = _text(raw_block.get("recommendation_key"))
        add_key(activity_id, recommendation_key)

    for raw_session in _json_list(snapshot.get("sessions")):
        if not isinstance(raw_session, dict):
            continue
        activity_id = _text(raw_session.get("activity_id"))
        recommendation_key = _text(raw_session.get("recommendation_key"))
        add_key(activity_id, recommendation_key)

    return keys_by_activity


def _preview_line_with_quantity(line: TypeformQuotePreviewLineOut, quantity: Decimal, meta: dict[str, object]) -> TypeformQuotePreviewLineOut:
    amount_ht = _q2(line.unit_price_ht * quantity)
    amount_vat = _q2(line.unit_vat_amount * quantity)
    return line.model_copy(
        update={
            "quantity": _q2(quantity),
            "amount_ht": amount_ht,
            "amount_vat": amount_vat,
            "amount_ttc": _q2(amount_ht + amount_vat),
            "meta": meta,
        }
    )


def _quote_line_with_quantity(line: QuoteLineIn, quantity: Decimal, meta: dict[str, object]) -> QuoteLineIn:
    return line.model_copy(update={"quantity": _q2(quantity), "meta": meta})


def _apply_planned_quantities_to_activity_lines(
    *,
    preview_lines: list[TypeformQuotePreviewLineOut],
    quote_lines: list[QuoteLineIn],
    calendar_snapshot: dict[str, object],
) -> tuple[list[TypeformQuotePreviewLineOut], list[QuoteLineIn]]:
    planned_quantities = _planned_quantities_from_calendar_snapshot(calendar_snapshot)
    if not planned_quantities:
        return preview_lines, quote_lines
    recommendation_quantities = _planned_quantities_by_recommendation_key(calendar_snapshot)
    recommendation_keys_by_activity = _planned_recommendation_key_order_by_activity(calendar_snapshot)
    activity_line_counts: dict[str, int] = {}
    for line in quote_lines:
        if line.activity_id is None:
            continue
        activity_id = str(line.activity_id)
        activity_line_counts[activity_id] = activity_line_counts.get(activity_id, 0) + 1
    used_recommendation_keys: set[str] = set()

    adjusted_preview_lines: list[TypeformQuotePreviewLineOut] = []
    adjusted_quote_lines: list[QuoteLineIn] = []
    for index, quote_line in enumerate(quote_lines):
        preview_line = preview_lines[index] if index < len(preview_lines) else None
        planned_quantity: Decimal | None = None
        matched_recommendation_key: str | None = None
        recommendation_key = _quote_line_recommendation_key(quote_line)
        if recommendation_key and recommendation_key in recommendation_quantities:
            planned_quantity = recommendation_quantities.get(recommendation_key)
            matched_recommendation_key = recommendation_key
        if planned_quantity is None and quote_line.activity_id is not None:
            activity_id = str(quote_line.activity_id)
            if activity_line_counts.get(activity_id, 0) > 1:
                for candidate_key in recommendation_keys_by_activity.get(activity_id, []):
                    if candidate_key in used_recommendation_keys:
                        continue
                    candidate_quantity = recommendation_quantities.get(candidate_key)
                    if candidate_quantity is None:
                        continue
                    planned_quantity = candidate_quantity
                    matched_recommendation_key = candidate_key
                    break
            else:
                planned_quantity = planned_quantities.get(activity_id)

        if quote_line.activity_id is None or planned_quantity is None or planned_quantity <= Decimal("0.00"):
            adjusted_quote_lines.append(quote_line)
            if preview_line is not None:
                adjusted_preview_lines.append(preview_line)
            continue
        if matched_recommendation_key:
            used_recommendation_keys.add(matched_recommendation_key)

        meta = dict(quote_line.meta or {})
        if _q2(quote_line.quantity) != _q2(planned_quantity):
            meta.setdefault("typeform_original_billing_quantity", str(_q2(quote_line.quantity)))
            meta["typeform_planned_quantity_applied"] = True
            meta["typeform_planned_quantity"] = str(_q2(planned_quantity))
        adjusted_quote_lines.append(_quote_line_with_quantity(quote_line, planned_quantity, meta))
        if preview_line is not None:
            adjusted_preview_lines.append(_preview_line_with_quantity(preview_line, planned_quantity, meta))

    if len(preview_lines) > len(adjusted_preview_lines):
        adjusted_preview_lines.extend(preview_lines[len(adjusted_preview_lines):])
    return adjusted_preview_lines, adjusted_quote_lines


def _planning_session_limit_from_meta(meta: object | None) -> int | None:
    meta_obj = _json_object(meta)
    template = _json_object(meta_obj.get("typeform_template"))
    raw_limit = meta_obj.get("planning_session_limit")
    if raw_limit is None:
        raw_limit = template.get("planning_session_limit")
    try:
        limit = int(str(raw_limit).strip())
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _session_recommendation_key(recommendation: TypeformSessionRecommendationOut) -> str:
    return _text(getattr(recommendation, "recommendation_key", None)) or str(recommendation.activity_id)


def _recurrence_frequency_from_rule(value: object | None) -> str:
    raw = _text(value).strip().upper()
    if not raw:
        return "weekly"
    if "@" in raw:
        raw, _ = raw.split("@", 1)
    frequency_raw, interval_raw = raw.split(":", 1) if ":" in raw else (raw, "1")
    try:
        interval = int(interval_raw or "1")
    except ValueError:
        interval = 1
    if frequency_raw == "MONTHLY":
        return "monthly"
    if frequency_raw == "WEEKLY" and interval == 2:
        return "biweekly"
    return "weekly"


def _slot_filters_from_preferences(
    preferences: list[object],
) -> tuple[set[int], list[int], list[dict[str, int | None]]]:
    requested_days = {_weekday_from_label(_json_object(item).get("day")) for item in preferences if isinstance(item, dict)}
    requested_days.discard(None)
    requested_times = [
        _minutes_from_hhmm(_text(_json_object(item).get("time")))
        for item in preferences
        if isinstance(item, dict)
    ]
    requested_times = [value for value in requested_times if value is not None]
    requested_slot_preferences = [
        {
            "day": _weekday_from_label(_json_object(item).get("day")),
            "time": _minutes_from_hhmm(_text(_json_object(item).get("time"))),
        }
        for item in preferences
        if isinstance(item, dict)
    ]
    requested_slot_preferences = [
        item
        for item in requested_slot_preferences
        if item["day"] is not None or item["time"] is not None
    ]
    return requested_days, requested_times, requested_slot_preferences


def _modality_from_delivery_mode(value: DeliveryMode | str | None) -> str | None:
    if value == DeliveryMode.ONLINE or _text(value).strip().upper() == DeliveryMode.ONLINE.value:
        return "online"
    if value == DeliveryMode.ONSITE or _text(value).strip().upper() == DeliveryMode.ONSITE.value:
        return "onsite"
    return None


def _modality_from_activity_location(activity: CourseType, location: Location | None) -> str | None:
    modality = _modality_from_delivery_mode(activity.mode)
    if modality:
        return modality
    if location is None:
        return None
    tokens = {
        _normalize_token(location.code),
        _normalize_token(location.name),
    }
    tokens.discard("")
    if "online" in tokens or any(token in {"videocall", "video call", "visioconference", "video"} for token in tokens):
        return "online"
    return None


def _matching_solfege_rule_for_intake(
    db: Session,
    *,
    level_code: str | None,
    location_id: object | None,
    modality: str | None,
) -> SolfegeLevelRule | None:
    level = _text(level_code)
    if not level:
        return None
    rows = db.scalars(
        select(SolfegeLevelRule)
        .where(
            SolfegeLevelRule.level_code == level,
            SolfegeLevelRule.is_active.is_(True),
        )
    ).all()
    if not rows:
        return None
    expected_location_id = _text(location_id) or None
    expected_modality = _text(modality).upper() or None

    def _score(rule: SolfegeLevelRule) -> tuple[int, int, float]:
        rule_location_id = _text(rule.location_id) if rule.location_id is not None else None
        rule_modality = _text(rule.modality).upper() or None
        location_score = 0 if expected_location_id and rule_location_id == expected_location_id else (1 if rule_location_id is None else 3)
        modality_score = 0 if expected_modality and rule_modality == expected_modality else (1 if rule_modality is None else 3)
        created_rank = -(rule.created_at.timestamp() if getattr(rule, "created_at", None) else 0.0)
        return location_score, modality_score, created_rank

    return min(rows, key=_score)


def _solfege_slot_proposal_from_normalized(
    db: Session,
    *,
    normalized: dict[str, object],
    runtime_context: dict[str, object],
    session_recommendations: list[TypeformSessionRecommendationOut],
) -> dict[str, object]:
    preferences = [
        _json_object(item)
        for item in _json_list(normalized.get("requested_solfege_slot_preferences"))
        if isinstance(item, dict)
    ]
    if not preferences:
        return {}
    level_code = _extract_estimated_solfege_level(
        normalized=normalized,
        session_recommendations=session_recommendations,
    )
    modality = _text(normalized.get("requested_solfege_modality")) or "online"
    location_id = None if modality == "online" else _parse_uuid(runtime_context.get("location_id"))
    rule = _matching_solfege_rule_for_intake(
        db,
        level_code=level_code,
        location_id=location_id,
        modality=modality,
    )
    duration_minutes = int(rule.duration_minutes) if rule is not None else 45
    location_label = "En ligne" if modality == "online" else (
        _text(runtime_context.get("location_name")) or _text(preferences[0].get("location"))
    )
    for preference in preferences:
        weekday = _weekday_from_label(preference.get("day"))
        start_time = _text(preference.get("time"))
        start_minutes = _minutes_from_hhmm(start_time)
        if weekday is None or start_minutes is None:
            continue
        end_minutes = start_minutes + duration_minutes
        end_time = f"{(end_minutes // 60) % 24:02d}:{end_minutes % 60:02d}"
        weekday_label = DAY_LABELS[weekday]
        label_parts = [
            f"{weekday_label} {start_time}-{end_time}",
            location_label,
            "Présentiel" if modality == "onsite" else "",
        ]
        return {
            "level_code": level_code,
            "weekday": weekday,
            "weekday_label": weekday_label,
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": duration_minutes,
            "location_id": str(location_id) if location_id is not None else None,
            "location_label": location_label or None,
            "modality": modality,
            "label": " · ".join(part for part in label_parts if part),
            "source": "typeform_solfege_slot_preference",
        }
    return {}


def _build_session_recommendations(
    db: Session,
    *,
    config: TypeformFormConfig | None,
    normalized: dict[str, object],
    preview_lines: list[TypeformQuotePreviewLineOut],
    resolution: dict[str, object],
    runtime_context: dict[str, object],
) -> tuple[list[TypeformSessionRecommendationOut], list[str], list[str]]:
    activity_ids = [line.activity_id for line in preview_lines if line.activity_id is not None]
    if not activity_ids:
        return [], [], []

    school_year_bounds = _school_year_bounds_from_label(
        _text(runtime_context.get("school_year_label"))
        or _text(runtime_context.get("quote_type"))
        or _text(runtime_context.get("pricing_catalog_name"))
        or _text(config.school_year_label if config is not None else None)
    )
    school_year_start_utc: datetime | None = None
    school_year_end_utc: datetime | None = None
    if school_year_bounds is not None:
        school_year_start, school_year_end = school_year_bounds
        school_year_start_utc = datetime.combine(school_year_start, time.min, tzinfo=timezone.utc)
        school_year_end_utc = datetime.combine(school_year_end + timedelta(days=1), time.min, tzinfo=timezone.utc)

    booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("booked_count"),
        )
        .where(Booking.status == BookingStatus.BOOKED)
        .group_by(Booking.session_id)
        .subquery()
    )

    rows_stmt = (
        select(CourseSession, CourseType, Location, func.coalesce(booked_counts.c.booked_count, 0))
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .where(
            CourseSession.course_type_id.in_(activity_ids),
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= _utcnow() - timedelta(hours=1),
        )
    )
    if school_year_start_utc is not None and school_year_end_utc is not None:
        rows_stmt = rows_stmt.where(
            CourseSession.start_at_utc >= school_year_start_utc,
            CourseSession.start_at_utc < school_year_end_utc,
        )
    rows = db.execute(
        rows_stmt.order_by(CourseSession.start_at_utc.asc())
    ).all()

    manual_rows_stmt = (
        select(CourseSession, CourseType, Location, func.coalesce(booked_counts.c.booked_count, 0))
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= _utcnow() - timedelta(hours=1),
        )
    )
    if school_year_start_utc is not None and school_year_end_utc is not None:
        manual_rows_stmt = manual_rows_stmt.where(
            CourseSession.start_at_utc >= school_year_start_utc,
            CourseSession.start_at_utc < school_year_end_utc,
        )

    by_activity: dict[UUID, list[tuple[CourseSession, CourseType, Location, int]]] = {}
    for session_obj, activity, location, booked_count in rows:
        by_activity.setdefault(activity.id, []).append((session_obj, activity, location, int(booked_count or 0)))

    requested_location = _lower(normalized.get("requested_location"))
    resolved_location_id = _parse_uuid(runtime_context.get("location_id"))
    manual_location_id = resolved_location_id
    if manual_location_id is None and requested_location:
        inferred_location, _ = _find_location_by_request_value(db, requested_location)
        if inferred_location is not None:
            manual_location_id = inferred_location.id
    elif not requested_location and config is not None and config.default_location_id is not None:
        manual_location_id = config.default_location_id
    requested_days = {_weekday_from_label(day) for day in _json_list(normalized.get("requested_days"))}
    requested_days.discard(None)
    requested_times = [_minutes_from_hhmm(_text(value)) for value in _json_list(normalized.get("requested_times"))]
    requested_times = [value for value in requested_times if value is not None]
    _, _, requested_slot_preferences = _slot_filters_from_preferences(
        _json_list(normalized.get("requested_slot_preferences"))
    )
    (
        solfege_requested_days,
        solfege_requested_times,
        solfege_requested_slot_preferences,
    ) = _slot_filters_from_preferences(_json_list(normalized.get("requested_solfege_slot_preferences")))
    manual_rows_all = db.execute(
        manual_rows_stmt.order_by(CourseSession.start_at_utc.asc())
    ).all()
    manual_rows_all = [
        (session_obj, activity, location, booked_count)
        for session_obj, activity, location, booked_count in manual_rows_all
        if _session_is_typeform_candidate(session_obj)
    ]
    manual_rows = [
        row
        for row in manual_rows_all
        if manual_location_id is None or row[2].id == manual_location_id
    ]
    selected_session_ids = _json_object(_json_object(resolution.get("slot_resolution")).get("selected_session_ids"))

    recommendations: list[TypeformSessionRecommendationOut] = []
    warnings: list[str] = []
    blockages: list[str] = []

    for line in preview_lines:
        if line.activity_id is None:
            continue
        recommendation_key = _line_recommendation_key(line)
        allow_deferred_selection = _is_non_blocking_solfege_line(
            line,
            runtime_context=runtime_context,
        )
        line_is_solfege = "solfege" in _normalize_token(_preview_line_haystack(line))
        line_is_second_course = _bool_or_default(_json_object(line.meta).get("typeform_second_course"), False)
        line_uses_solfege_slot_request = bool(line_is_solfege and solfege_requested_slot_preferences)
        second_course_preferences = []
        if line_is_second_course:
            second_course_preferences = _json_list(_json_object(normalized.get("requested_second_course")).get("slot_preferences"))
        (
            second_course_requested_days,
            second_course_requested_times,
            second_course_requested_slot_preferences,
        ) = _slot_filters_from_preferences(second_course_preferences)
        line_solfege_modality = _text(normalized.get("requested_solfege_modality")) if line_is_solfege else ""
        line_searches_onsite_solfege_without_main_slot_filters = (
            _should_search_onsite_solfege_without_main_slot_filters(
                line_is_solfege=line_is_solfege,
                line_solfege_modality=line_solfege_modality,
                solfege_requested_slot_preferences=solfege_requested_slot_preferences,
            )
        )
        line_second_course_modality = _text(_json_object(normalized.get("requested_second_course")).get("modality")) if line_is_second_course else ""
        line_resolved_location_id = (
            None
            if line_uses_solfege_slot_request and line_solfege_modality == "online"
            else None
            if line_is_second_course and line_second_course_modality == "online"
            else resolved_location_id
        )
        line_requested_location = (
            "online"
            if line_uses_solfege_slot_request and line_solfege_modality == "online"
            else "online"
            if line_is_second_course and line_second_course_modality == "online"
            else requested_location
        )
        effective_requested_days = (
            solfege_requested_days
            if line_uses_solfege_slot_request
            else set()
            if line_searches_onsite_solfege_without_main_slot_filters
            else second_course_requested_days
            if line_is_second_course and second_course_preferences
            else requested_days
        )
        effective_requested_times = (
            solfege_requested_times
            if line_uses_solfege_slot_request
            else []
            if line_searches_onsite_solfege_without_main_slot_filters
            else second_course_requested_times
            if line_is_second_course and second_course_preferences
            else requested_times
        )
        effective_requested_slot_preferences = (
            solfege_requested_slot_preferences
            if line_uses_solfege_slot_request
            else []
            if line_searches_onsite_solfege_without_main_slot_filters
            else second_course_requested_slot_preferences
            if line_is_second_course and second_course_preferences
            else requested_slot_preferences
        )
        strict_location_matching = _requires_strict_typeform_location_matching(
            config=config,
            normalized=normalized,
            runtime_context=runtime_context,
            resolved_location_id=line_resolved_location_id,
        )
        has_explicit_slot_request = bool(
            effective_requested_slot_preferences
            or effective_requested_days
            or effective_requested_times
        )
        activity_rows = by_activity.get(line.activity_id, [])
        option_rows: list[tuple[CourseSession, TypeformSessionMatchOptionOut]] = []
        for session_obj, activity, location, booked_count in activity_rows:
            if not _typeform_location_allowed_for_alternative(
                requested_location=line_requested_location,
                runtime_context=runtime_context,
                candidate_location=location,
            ):
                continue
            if (
                not _session_is_typeform_candidate(session_obj)
                and not line_uses_solfege_slot_request
                and not line_searches_onsite_solfege_without_main_slot_filters
            ):
                continue
            if line_resolved_location_id is not None and location.id != line_resolved_location_id:
                continue
            option = _typeform_session_option_from_row(
                session_obj=session_obj,
                activity=activity,
                location=location,
                booked_count=int(booked_count or 0),
                config=config,
                requested_location=line_requested_location,
                resolved_location_id=line_resolved_location_id,
                requested_slot_preferences=effective_requested_slot_preferences,
                requested_days=effective_requested_days,
                requested_times=effective_requested_times,
            )
            if option is not None:
                option_rows.append((session_obj, option))

        selected_session_id = _parse_uuid(selected_session_ids.get(recommendation_key) or selected_session_ids.get(str(line.activity_id)))
        options = _collapse_session_option_groups(
            option_rows,
            selected_session_id=selected_session_id,
        )
        if (
            not options
            and has_explicit_slot_request
            and line_resolved_location_id is not None
            and not strict_location_matching
        ):
            relaxed_option_rows: list[tuple[CourseSession, TypeformSessionMatchOptionOut]] = []
            for session_obj, activity, location, booked_count in activity_rows:
                if not _typeform_location_allowed_for_alternative(
                    requested_location=line_requested_location,
                    runtime_context=runtime_context,
                    candidate_location=location,
                ):
                    continue
                if (
                    not _session_is_typeform_candidate(session_obj)
                    and not line_uses_solfege_slot_request
                    and not line_searches_onsite_solfege_without_main_slot_filters
                ):
                    continue
                option = _typeform_session_option_from_row(
                    session_obj=session_obj,
                    activity=activity,
                    location=location,
                    booked_count=int(booked_count or 0),
                    config=config,
                    requested_location=line_requested_location,
                    resolved_location_id=None,
                    requested_slot_preferences=effective_requested_slot_preferences,
                    requested_days=effective_requested_days,
                    requested_times=effective_requested_times,
                )
                if option is not None:
                    relaxed_option_rows.append((session_obj, option))
            options = _collapse_session_option_groups(
                relaxed_option_rows,
                selected_session_id=selected_session_id,
            )
        if has_explicit_slot_request:
            compatible_option_rows: list[tuple[CourseSession, TypeformSessionMatchOptionOut]] = []
            existing_option_ids = {item.session_id for item in options}
            seen_compatible_session_ids: set[UUID] = set()
            compatible_row_groups = [manual_rows]
            if not strict_location_matching and manual_rows_all is not manual_rows:
                compatible_row_groups.append(manual_rows_all)
            for compatible_rows in compatible_row_groups:
                for session_obj, activity, location, booked_count in compatible_rows:
                    if not _typeform_location_allowed_for_alternative(
                        requested_location=line_requested_location,
                        runtime_context=runtime_context,
                        candidate_location=location,
                    ):
                        continue
                    if session_obj.id in existing_option_ids or session_obj.id in seen_compatible_session_ids:
                        continue
                    if activity.id == line.activity_id or not _activity_matches_line_for_slot_fallback(activity, line):
                        continue
                    if not _line_allows_session_modality(line, activity=activity, location=location):
                        continue
                    option = _typeform_session_option_from_row(
                        session_obj=session_obj,
                        activity=activity,
                        location=location,
                        booked_count=int(booked_count or 0),
                        config=config,
                        requested_location=line_requested_location,
                        resolved_location_id=line_resolved_location_id if location.id == line_resolved_location_id else None,
                        requested_slot_preferences=effective_requested_slot_preferences,
                        requested_days=effective_requested_days,
                        requested_times=effective_requested_times,
                        include_activity_in_label=True,
                        extra_reasons=[f"activite compatible: {activity.name}"],
                        allow_low_score=True,
                    )
                    if option is not None:
                        seen_compatible_session_ids.add(session_obj.id)
                        compatible_option_rows.append((session_obj, option))
                if compatible_option_rows and options:
                    break
            if compatible_option_rows:
                compatible_options = _collapse_session_option_groups(
                    compatible_option_rows,
                    selected_session_id=selected_session_id,
                )
                merged_options: list[TypeformSessionMatchOptionOut] = []
                seen_option_ids: set[UUID] = set()
                for item in [*options, *compatible_options]:
                    if item.session_id in seen_option_ids:
                        continue
                    seen_option_ids.add(item.session_id)
                    merged_options.append(item)
                merged_options.sort(
                    key=lambda item: (
                        item.is_full,
                        -item.score,
                        item.start_at.timestamp(),
                    )
                )
                options = merged_options
        available_options = [item for item in options if not item.is_full]
        option_session_ids = {item.session_id for item in options}
        manual_options: list[TypeformSessionMatchOptionOut] = []
        slot_proposals: list[dict[str, object]] = []
        if line_uses_solfege_slot_request:
            solfege_slot_proposal = _solfege_slot_proposal_from_normalized(
                db,
                normalized=normalized,
                runtime_context=runtime_context,
                session_recommendations=[],
            )
            if solfege_slot_proposal:
                slot_proposals.append(solfege_slot_proposal)
        if not options or (selected_session_id is not None and selected_session_id not in option_session_ids):
            manual_series_rows: dict[str, tuple[CourseSession, CourseType, Location, int]] = {}
            for session_obj, activity, location, booked_count in manual_rows:
                series_key = str(session_obj.recurrence_group_id or session_obj.id)
                existing = manual_series_rows.get(series_key)
                if existing is None or session_obj.start_at_utc < existing[0].start_at_utc:
                    manual_series_rows[series_key] = (session_obj, activity, location, int(booked_count or 0))

            for session_obj, activity, location, booked_count in manual_series_rows.values():
                if not _typeform_location_allowed_for_alternative(
                    requested_location=line_requested_location,
                    runtime_context=runtime_context,
                    candidate_location=location,
                ):
                    continue
                if activity.id != line.activity_id and not _activity_matches_line_for_slot_fallback(activity, line):
                    continue
                if not _line_allows_session_modality(line, activity=activity, location=location):
                    continue
                option = _typeform_session_option_from_row(
                    session_obj=session_obj,
                    activity=activity,
                    location=location,
                    booked_count=int(booked_count or 0),
                    config=config,
                    requested_location=line_requested_location,
                    resolved_location_id=line_resolved_location_id,
                    requested_slot_preferences=effective_requested_slot_preferences,
                    requested_days=effective_requested_days,
                    requested_times=effective_requested_times,
                    include_activity_in_label=True,
                    extra_reasons=(
                        [f"activite differente: {activity.name}"]
                        if activity.id != line.activity_id
                        else None
                    ),
                    allow_low_score=True,
                )
                if option is not None:
                    zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
                    local_start = session_obj.start_at_utc.astimezone(zone)
                    local_end = session_obj.end_at_utc.astimezone(zone)
                    slot_label = f"{DAY_LABELS[local_start.weekday()]} · {local_start.strftime('%H:%M')}-{local_end.strftime('%H:%M')}"
                    start_label = f"demarrage {local_start.strftime('%d/%m/%Y')}"
                    selection_parts = [
                        slot_label,
                        activity.name,
                        location.name,
                        option.recurrence_label or "Seance ponctuelle",
                        start_label,
                        f"places {option.seats_remaining}",
                    ]
                    option = option.model_copy(
                        update={
                            "occurrence_label": slot_label,
                            "selection_label": " · ".join(part for part in selection_parts if part),
                            "reasons": [*option.reasons, start_label],
                        }
                    )
                    manual_options.append(option)
            manual_options.sort(key=lambda item: (item.score, item.seats_remaining, -item.start_at.timestamp()), reverse=True)
            manual_options = manual_options[:12]

        manual_session_ids = {item.session_id for item in manual_options}
        exact_selected = selected_session_id is not None and selected_session_id in option_session_ids
        manual_selected = selected_session_id is not None and selected_session_id in manual_session_ids

        summary_status = "ideal_available"
        summary_label = "Creneau ideal disponible"
        local_warnings: list[str] = []
        local_blockages: list[str] = []
        if selected_session_id is not None and not exact_selected and not manual_selected:
            selected_session_id = None
            local_warnings.append(f"Le creneau selectionne precedemment n'est plus disponible pour {line.title}.")
        if manual_selected:
            summary_status = "manual_selected"
            summary_label = "Creneau manuel retenu"
        elif not options:
            if slot_proposals:
                summary_status = "proposed_match"
                summary_label = "Creneau Typeform propose"
            elif manual_options:
                if allow_deferred_selection:
                    summary_status = "selection_deferred"
                    summary_label = "Creneau a confirmer ulterieurement"
                    local_warnings.append(
                        f"Aucun creneau exact trouve pour {line.title}. Le choix pourra etre finalise plus tard."
                    )
                else:
                    summary_status = "manual_selection_required"
                    summary_label = "Choix manuel de creneau requis"
                    local_blockages.append(
                        f"Aucun creneau exact trouve pour {line.title}. Selectionnez manuellement un creneau compatible."
                    )
            elif allow_deferred_selection:
                summary_status = "selection_deferred"
                summary_label = "Creneau a confirmer ulterieurement"
                local_warnings.append(
                    f"Aucun creneau pertinent trouve pour {line.title}. Le choix pourra etre finalise plus tard."
                )
            else:
                summary_status = "no_relevant_slot"
                summary_label = "Aucun creneau pertinent"
                local_blockages.append(f"Aucun creneau pertinent trouve pour {line.title}.")
        elif not available_options:
            if allow_deferred_selection:
                summary_status = "selection_deferred"
                summary_label = "Creneau a confirmer ulterieurement"
                local_warnings.append(
                    f"Aucun creneau disponible immediatement pour {line.title}. Le choix pourra etre finalise plus tard."
                )
            else:
                summary_status = "full"
                summary_label = "Creneaux trouves mais complets"
                local_blockages.append(f"Les creneaux trouves pour {line.title} sont complets.")
        elif len(available_options) > 1:
            if allow_deferred_selection:
                summary_status = "selection_deferred"
                summary_label = "Creneau a confirmer ulterieurement"
                local_warnings.append(
                    f"Plusieurs creneaux sont compatibles pour {line.title}. Le choix pourra etre finalise plus tard."
                )
            else:
                summary_status = "multiple_options"
                summary_label = "Plusieurs creneaux possibles"
                local_warnings.append(f"Plusieurs creneaux sont compatibles pour {line.title}.")
        elif options and options[0].is_full and available_options:
            summary_status = "full_with_alternative"
            summary_label = "Demande complete mais alternative disponible"
            local_warnings.append(f"Le creneau le plus proche est complet pour {line.title}, une alternative est proposee.")

        if selected_session_id is None and available_options and summary_status in {"ideal_available", "full_with_alternative"}:
            selected_session_id = available_options[0].session_id
        if (
            selected_session_id is None
            and available_options
            and line_is_solfege
            and line_uses_solfege_slot_request
            and summary_status == "selection_deferred"
        ):
            selected_session_id = available_options[0].session_id
            summary_status = "proposed_match"
            summary_label = "Creneau solfege propose"

        line_meta = _json_object(line.meta)
        display_activity_name = _text(line_meta.get("typeform_display_name")) or _text(line_meta.get("activity_name")) or line.title
        recommendations.append(
            TypeformSessionRecommendationOut(
                activity_id=line.activity_id,
                recommendation_key=recommendation_key,
                activity_name=display_activity_name,
                requested_location=_text(line_requested_location) or None,
                requested_summary=(
                    _requested_slot_summary(_json_list(normalized.get("requested_solfege_slot_preferences")))
                    if line_uses_solfege_slot_request
                    else "Solfege en presentiel"
                    if line_searches_onsite_solfege_without_main_slot_filters
                    else _requested_slot_summary(second_course_preferences)
                    if line_is_second_course and second_course_preferences
                    else _requested_summary(normalized)
                ),
                summary_status=summary_status,
                summary_label=summary_label,
                selected_session_id=selected_session_id,
                options=options[:6],
                manual_options=manual_options,
                slot_proposals=slot_proposals,
                warnings=local_warnings,
                blockages=local_blockages,
            )
        )
        warnings.extend(local_warnings)
        blockages.extend(local_blockages)

    return recommendations, warnings, blockages


def _build_preview(
    db: Session,
    *,
    config: TypeformFormConfig | None,
    normalized: dict[str, object],
    resolution: dict[str, object],
    preview_lines: list[TypeformQuotePreviewLineOut],
    session_recommendations: list[TypeformSessionRecommendationOut],
    runtime_context: dict[str, object],
) -> TypeformQuotePreviewOut | None:
    if config is None or not preview_lines:
        return None

    client_resolution = _json_object(resolution.get("client_resolution"))
    mode = _text(client_resolution.get("mode")) or CLIENT_MODE_NEW_ADULT
    customer_type = _lower(normalized.get("customer_type")) or "adult"
    context_type = "active_client" if mode in {CLIENT_MODE_EXISTING, CLIENT_MODE_EXISTING_FAMILY} else "acquisition"
    context_label = "Client existant" if context_type == "active_client" else "Prospect / acquisition"

    if customer_type == "child":
        customer_label = _display_name(normalized.get("child_first_name"), normalized.get("child_last_name"), "Eleve")
        parent_label = _display_name(normalized.get("parent_first_name"), normalized.get("parent_last_name"), "Parent")
        if parent_label != "Parent":
            customer_label = f"{customer_label} (parent: {parent_label})"
    else:
        customer_label = _display_name(normalized.get("parent_first_name"), normalized.get("parent_last_name"), _text(normalized.get("parent_email")) or "Adulte")

    selected_options = []
    requested_formula = _text(normalized.get("requested_formula_type"))
    if requested_formula:
        selected_options.append(f"Formule: {requested_formula}")
    for item in _json_list(normalized.get("requested_products")):
        text = _text(item)
        if text:
            selected_options.append(text)

    total_ht = _q2(sum((line.amount_ht for line in preview_lines), Decimal("0.00")))
    total_vat = _q2(sum((line.amount_vat for line in preview_lines), Decimal("0.00")))
    total_ttc = _q2(sum((line.amount_ttc for line in preview_lines), Decimal("0.00")))

    return TypeformQuotePreviewOut(
        context_type=context_type,
        context_label=context_label,
        customer_label=customer_label,
        location_id=_parse_uuid(runtime_context.get("location_id")),
        location_name=_text(runtime_context.get("location_name")) or None,
        payment_plan_id=_parse_uuid(runtime_context.get("payment_plan_id")),
        payment_plan_name=_text(runtime_context.get("payment_plan_name")) or None,
        quote_type_id=_parse_uuid(runtime_context.get("quote_type_id")),
        quote_type_name=_text(runtime_context.get("quote_type")) or config.default_quote_type,
        pricing_catalog_id=_parse_uuid(runtime_context.get("pricing_catalog_id")),
        pricing_catalog_name=_text(runtime_context.get("pricing_catalog_name")) or None,
        legal_entity_id=_parse_uuid(runtime_context.get("legal_entity_id")),
        legal_entity_name=_text(runtime_context.get("legal_entity_name")) or None,
        school_year_label=config.school_year_label,
        language=config.default_language,
        currency="EUR",
        selected_options=selected_options,
        lines=preview_lines,
        total_ht=total_ht,
        total_vat=total_vat,
        total_ttc=total_ttc,
        meta={
            "segment": config.audience_segment,
            "location_code": _text(runtime_context.get("location_code")) or config.location_code,
            "form_location_code": config.location_code,
            "session_recommendations": [
                {
                    "activity_id": str(item.activity_id),
                    "recommendation_key": _session_recommendation_key(item),
                    "summary_status": item.summary_status,
                    "selected_session_id": str(item.selected_session_id) if item.selected_session_id else None,
                }
                for item in session_recommendations
            ],
        },
    )


def _needs_client_arbitrage(client_candidates: list[dict[str, object]], family_candidates: list[dict[str, object]], resolution: dict[str, object]) -> bool:
    mode = _text(_json_object(resolution.get("client_resolution")).get("mode"))
    if mode in {CLIENT_MODE_NEW_ADULT, CLIENT_MODE_NEW_PARENT_CHILD, CLIENT_MODE_EXISTING, CLIENT_MODE_EXISTING_FAMILY}:
        if mode in {CLIENT_MODE_EXISTING, CLIENT_MODE_EXISTING_FAMILY}:
            return False
    high_clients = [item for item in client_candidates if int(item.get("confidence") or 0) >= 70]
    high_families = [item for item in family_candidates if int(item.get("confidence") or 0) >= 75]
    if len(high_clients) >= 2 and abs(int(high_clients[0]["confidence"]) - int(high_clients[1]["confidence"])) <= 10:
        return True
    if len(high_families) >= 2 and abs(int(high_families[0]["confidence"]) - int(high_families[1]["confidence"])) <= 10:
        return True
    return False


def _needs_session_arbitrage(session_recommendations: list[TypeformSessionRecommendationOut]) -> bool:
    return any(item.summary_status == "multiple_options" and item.selected_session_id is None for item in session_recommendations)


def _draft_quote_warning_for_pending_arbitrage(
    *,
    client_arbitrage_required: bool,
    session_arbitrage_required: bool,
) -> str | None:
    if client_arbitrage_required and session_arbitrage_required:
        return "Devis brouillon cree avec avertissement : des arbitrages client et creneau restent a finaliser."
    if client_arbitrage_required:
        return "Devis brouillon cree avec avertissement : la correspondance client reste a finaliser."
    if session_arbitrage_required:
        return (
            "Devis brouillon cree avec avertissement : plusieurs creneaux restent a arbitrer. "
            "Le planning devra etre finalise dans le devis avant envoi."
        )
    return None


def _analysis_for_intake(
    db: Session,
    intake: TypeformIntake,
) -> dict[str, object]:
    config = db.scalar(select(TypeformFormConfig).where(TypeformFormConfig.id == intake.form_config_id)) if intake.form_config_id else None
    normalized = _json_object(intake.normalized_payload_json)
    raw_payload = _json_object(intake.raw_payload_json)
    simplified_answers = _json_list(intake.simplified_response_json)
    if not normalized and config is not None:
        normalized, simplified_answers = _normalize_payload(payload=raw_payload, config=config)
        intake.normalized_payload_json = normalized
        intake.simplified_response_json = simplified_answers
    elif raw_payload:
        refreshed_normalized, refreshed_simplified_answers = _normalize_payload(payload=raw_payload, config=config)
        if refreshed_normalized != normalized:
            normalized = refreshed_normalized
            intake.normalized_payload_json = refreshed_normalized
        if refreshed_simplified_answers != simplified_answers:
            simplified_answers = refreshed_simplified_answers
            intake.simplified_response_json = refreshed_simplified_answers

    def _run_analysis(active_config: TypeformFormConfig | None, active_normalized: dict[str, object]) -> dict[str, object]:
        client_candidates = _collect_client_candidates(db, active_normalized)
        family_candidates = _collect_family_candidates(db, active_normalized)
        effective_resolution = _default_resolution(
            normalized=active_normalized,
            stored_resolution=_json_object(intake.resolution_json),
            client_candidates=client_candidates,
            family_candidates=family_candidates,
        )

        runtime_context = _resolve_form_runtime_context(db, config=active_config, normalized=active_normalized)
        preview_lines, quote_lines, line_warnings, line_blockages = _build_preview_lines(
            db,
            config=active_config,
            normalized=active_normalized,
            runtime_context=runtime_context,
        )
        session_recommendations, session_warnings, session_blockages = _build_session_recommendations(
            db,
            config=active_config,
            normalized=active_normalized,
            preview_lines=preview_lines,
            resolution=effective_resolution,
            runtime_context=runtime_context,
        )
        preview_quote = _build_preview(
            db,
            config=active_config,
            normalized=active_normalized,
            resolution=effective_resolution,
            preview_lines=preview_lines,
            session_recommendations=session_recommendations,
            runtime_context=runtime_context,
        )

        warnings = list(dict.fromkeys(_json_list(runtime_context.get("warnings")) + line_warnings + session_warnings))
        blockages = list(dict.fromkeys(_json_list(runtime_context.get("blockages")) + line_blockages + session_blockages))

        if active_config is None:
            blockages.insert(0, "Aucune configuration active ne correspond au formulaire Typeform.")

        if _needs_client_arbitrage(client_candidates, family_candidates, effective_resolution):
            warnings.append("Plusieurs correspondances client ou famille doivent etre arbitrees.")
        if _needs_session_arbitrage(session_recommendations):
            warnings.append("Plusieurs creneaux compatibles demandent un arbitrage.")
        solfege_slot_proposal = _solfege_slot_proposal_from_normalized(
            db,
            normalized=active_normalized,
            runtime_context=runtime_context,
            session_recommendations=session_recommendations,
        )

        admin_state = _lower(effective_resolution.get("admin_state"))
        if intake.related_quote_id is not None:
            intake_status = INTAKE_STATUS_PROCESSED
        elif admin_state == "ignored":
            intake_status = INTAKE_STATUS_IGNORED
        elif blockages:
            intake_status = INTAKE_STATUS_BLOCKED
        elif _needs_client_arbitrage(client_candidates, family_candidates, effective_resolution) or _needs_session_arbitrage(session_recommendations):
            intake_status = INTAKE_STATUS_MATCHING_REQUIRED
        elif active_normalized:
            intake_status = INTAKE_STATUS_READY
        else:
            intake_status = INTAKE_STATUS_NORMALIZED

        return {
            "config": active_config,
            "normalized": active_normalized,
            "answers": _coerce_typeform_answers(intake.simplified_response_json),
            "client_candidates": client_candidates,
            "family_candidates": family_candidates,
            "effective_resolution": effective_resolution,
            "preview_quote": preview_quote,
            "preview_quote_lines_in": quote_lines,
            "session_recommendations": session_recommendations,
            "runtime_context": runtime_context,
            "warnings": list(dict.fromkeys(warnings)),
            "blockages": list(dict.fromkeys(blockages)),
            "solfege_slot_proposal": solfege_slot_proposal,
            "referral": referral_summary(
                db.scalar(select(ReferralReward).where(ReferralReward.typeform_intake_id == intake.id)),
                db,
            ),
            "intake_status": intake_status,
        }

    analysis = _run_analysis(config, normalized)
    if config is not None and raw_payload and _should_try_future_school_year_config(
        config=config,
        normalized=normalized,
        session_recommendations=_json_list(analysis.get("session_recommendations")),
    ):
        current_school_year_label = config.school_year_label
        for candidate_config in _future_school_year_candidate_configs(db, current_config=config):
            candidate_normalized, candidate_simplified_answers = _normalize_payload(payload=raw_payload, config=candidate_config)
            candidate_analysis = _run_analysis(candidate_config, candidate_normalized)
            if not _session_recommendations_have_options(_json_list(candidate_analysis.get("session_recommendations"))):
                continue
            config = candidate_config
            normalized = candidate_normalized
            simplified_answers = candidate_simplified_answers
            intake.form_config_id = candidate_config.id
            intake.normalized_payload_json = candidate_normalized
            intake.simplified_response_json = candidate_simplified_answers
            candidate_warnings = _json_list(candidate_analysis.get("warnings"))
            candidate_warnings.insert(
                0,
                (
                    "Le formulaire initial a ete reroute vers l annee scolaire "
                    f"{candidate_config.school_year_label} car aucun creneau pertinent n etait disponible "
                    f"sur {current_school_year_label}."
                ),
            )
            candidate_analysis["warnings"] = list(dict.fromkeys(candidate_warnings))
            candidate_analysis["answers"] = _coerce_typeform_answers(candidate_simplified_answers)
            analysis = candidate_analysis
            break

    return analysis


def _safe_analysis_for_intake(
    db: Session,
    intake: TypeformIntake,
) -> dict[str, object]:
    try:
        return _analysis_for_intake(db, intake)
    except Exception:
        logger.exception(
            "Typeform intake analysis failed for intake_id=%s response_id=%s",
            intake.id,
            intake.source_response_id,
        )
        config = db.scalar(select(TypeformFormConfig).where(TypeformFormConfig.id == intake.form_config_id)) if intake.form_config_id else None
        normalized = _json_object(intake.normalized_payload_json)
        requested_location = _text(normalized.get("requested_location")) or None
        try:
            runtime_context = _resolve_form_runtime_context(db, config=config, normalized=normalized)
        except Exception:
            logger.exception(
                "Unable to resolve runtime context for failed intake_id=%s",
                intake.id,
            )
            runtime_context = _empty_runtime_context(
                config=config,
                requested_location=requested_location,
            )

        effective_resolution = _default_resolution(
            normalized=normalized,
            stored_resolution=_json_object(intake.resolution_json),
            client_candidates=[],
            family_candidates=[],
        )
        warnings = [
            _text(_json_object(item).get("message"))
            for item in _json_list(intake.warnings_json)
            if _text(_json_object(item).get("message"))
        ]
        blockages = [
            "Cette intake contient des donnees legacy ou incoherentes qui ont empeche l analyse automatique."
        ]
        blockages.extend(
            _text(_json_object(item).get("message"))
            for item in _json_list(intake.blocking_reasons_json)
            if _text(_json_object(item).get("message"))
        )
        return {
            "config": config,
            "normalized": normalized,
            "answers": _coerce_typeform_answers(intake.simplified_response_json),
            "client_candidates": [],
            "family_candidates": [],
            "effective_resolution": effective_resolution,
            "preview_quote": None,
            "preview_quote_lines_in": [],
            "session_recommendations": [],
            "runtime_context": runtime_context,
            "warnings": list(dict.fromkeys(warnings)),
            "blockages": list(dict.fromkeys(blockages)),
            "referral": referral_summary(
                db.scalar(select(ReferralReward).where(ReferralReward.typeform_intake_id == intake.id)),
                db,
            ),
            "intake_status": INTAKE_STATUS_BLOCKED,
        }


def _refresh_intake_analysis(db: Session, intake: TypeformIntake) -> dict[str, object]:
    analysis = _safe_analysis_for_intake(db, intake)
    intake.intake_status = str(analysis["intake_status"])
    runtime_context = _json_object(analysis.get("runtime_context"))
    resolved_school_year = (
        _text(runtime_context.get("school_year_label"))
        or _text(_json_object(analysis["normalized"]).get("requested_formula_type"))
        or (analysis["config"].school_year_label if analysis["config"] is not None else None)
    )
    intake.detected_location = (
        _text(runtime_context.get("location_name"))
        or _text(runtime_context.get("location_code"))
        or _text(_json_object(analysis["normalized"]).get("requested_location"))
        or (analysis["config"].location_code if analysis["config"] is not None else None)
    )
    intake.detected_segment = analysis["config"].audience_segment if analysis["config"] is not None else None
    intake.detected_school_year = resolved_school_year
    intake.warnings_json = [{"message": message} for message in analysis["warnings"]]
    intake.blocking_reasons_json = [{"message": message} for message in analysis["blockages"]]
    intake.updated_at = _utcnow()
    db.add(intake)
    return analysis


def _intake_list_out(intake: TypeformIntake, analysis: dict[str, object]) -> TypeformIntakeListOut:
    normalized = _json_object(analysis["normalized"])
    runtime_context = _json_object(analysis.get("runtime_context"))
    resolved_school_year = (
        _text(runtime_context.get("school_year_label"))
        or (
            analysis["config"].school_year_label
            if analysis["config"] is not None
            else intake.detected_school_year
        )
    )
    if _lower(normalized.get("customer_type")) == "child":
        prospect_label = _display_name(normalized.get("parent_first_name"), normalized.get("parent_last_name"), _text(normalized.get("parent_email")) or "-")
        child_label = _display_name(normalized.get("child_first_name"), normalized.get("child_last_name"), "-")
    else:
        prospect_label = _display_name(normalized.get("parent_first_name"), normalized.get("parent_last_name"), _text(normalized.get("parent_email")) or "-")
        child_label = None

    return TypeformIntakeListOut(
        id=intake.id,
        source_form_id=intake.source_form_id,
        source_form_label=_form_label(analysis["config"]),
        source_response_id=intake.source_response_id,
        received_at=intake.received_at,
        intake_status=_text(analysis.get("intake_status")) or intake.intake_status,
        detected_location=(
            _text(runtime_context.get("location_name"))
            or _text(runtime_context.get("location_code"))
            or intake.detected_location
        ),
        detected_segment=(
            analysis["config"].audience_segment
            if analysis["config"] is not None
            else intake.detected_segment
        ),
        detected_school_year=(
            resolved_school_year
        ),
        prospect_label=prospect_label,
        child_label=child_label,
        warnings=[_text(item) for item in _json_list(analysis.get("warnings")) if _text(item)],
        blockages=[_text(item) for item in _json_list(analysis.get("blockages")) if _text(item)],
        admin_comment=_text(intake.admin_comment) or None,
        related_quote_id=intake.related_quote_id,
        referral=analysis.get("referral") if isinstance(analysis.get("referral"), dict) else None,
        local_confirmation_status=getattr(intake, "local_confirmation_status", None) or "NOT_REQUIRED",
        local_confirmation_assignee_name=getattr(intake, "local_confirmation_assignee_name", None),
        local_confirmation_schedule_snapshot=getattr(intake, "local_confirmation_schedule_snapshot", None),
        local_confirmation_partition_snapshot=getattr(intake, "local_confirmation_partition_snapshot", None),
        local_confirmation_confirmed_at=getattr(intake, "local_confirmation_confirmed_at", None),
    )


def _stored_messages(value: object | None) -> list[str]:
    messages: list[str] = []
    for item in _json_list(value):
        row = _json_object(item)
        message = _text(row.get("message")) if row else _text(item)
        if message:
            messages.append(message)
    return list(dict.fromkeys(messages))


def _intake_list_out_fast(
    intake: TypeformIntake,
    *,
    config: TypeformFormConfig | None,
) -> TypeformIntakeListOut:
    normalized = _json_object(intake.normalized_payload_json)
    customer_type = _lower(normalized.get("customer_type"))
    has_child = customer_type == "child" or bool(
        _text(normalized.get("child_first_name")) or _text(normalized.get("child_last_name"))
    )
    prospect_label = _display_name(
        normalized.get("parent_first_name"),
        normalized.get("parent_last_name"),
        _text(normalized.get("parent_email")) or "-",
    )
    child_label = (
        _display_name(normalized.get("child_first_name"), normalized.get("child_last_name"), "-")
        if has_child
        else None
    )
    return TypeformIntakeListOut(
        id=intake.id,
        source_form_id=intake.source_form_id,
        source_form_label=_form_label(config) if config is not None else intake.source_form_id,
        source_response_id=intake.source_response_id,
        received_at=intake.received_at,
        intake_status=intake.intake_status,
        detected_location=intake.detected_location or _text(normalized.get("requested_location")) or None,
        detected_segment=(
            config.audience_segment
            if config is not None
            else intake.detected_segment
        ),
        detected_school_year=intake.detected_school_year
        or (config.school_year_label if config is not None else None),
        prospect_label=prospect_label,
        child_label=child_label,
        warnings=_stored_messages(intake.warnings_json),
        blockages=_stored_messages(intake.blocking_reasons_json),
        admin_comment=_text(intake.admin_comment) or None,
        related_quote_id=intake.related_quote_id,
        referral=None,
        local_confirmation_status=getattr(intake, "local_confirmation_status", None) or "NOT_REQUIRED",
        local_confirmation_assignee_name=getattr(intake, "local_confirmation_assignee_name", None),
        local_confirmation_schedule_snapshot=getattr(intake, "local_confirmation_schedule_snapshot", None),
        local_confirmation_partition_snapshot=getattr(intake, "local_confirmation_partition_snapshot", None),
        local_confirmation_confirmed_at=getattr(intake, "local_confirmation_confirmed_at", None),
    )


def _intake_detail_out(intake: TypeformIntake, analysis: dict[str, object]) -> TypeformIntakeDetailOut:
    runtime_context = _json_object(analysis.get("runtime_context"))
    resolved_school_year = (
        _text(runtime_context.get("school_year_label"))
        or (
            analysis["config"].school_year_label
            if analysis["config"] is not None
            else intake.detected_school_year
        )
    )
    candidates = [
        TypeformMatchCandidateOut(
            kind=item["kind"],
            client_id=item.get("client_id"),
            adult_client_id=item.get("adult_client_id"),
            child_client_id=item.get("child_client_id"),
            billing_client_id=item.get("billing_client_id"),
            display_name=_text(item.get("display_name")),
            subtitle=_text(item.get("subtitle")) or None,
            confidence=int(item.get("confidence") or 0),
            confidence_label=_text(item.get("confidence_label")) or "faible",
            reasons=[_text(reason) for reason in item.get("reasons") or [] if _text(reason)],
        )
        for item in [*analysis["family_candidates"], *analysis["client_candidates"]]
    ]

    config_out = _form_config_out(analysis["config"]) if analysis["config"] is not None else None
    return TypeformIntakeDetailOut(
        id=intake.id,
        source_form_id=intake.source_form_id,
        source_form_label=_form_label(analysis["config"]),
        source_response_id=intake.source_response_id,
        received_at=intake.received_at,
        intake_status=_text(analysis.get("intake_status")) or intake.intake_status,
        detected_location=(
            _text(runtime_context.get("location_name"))
            or _text(runtime_context.get("location_code"))
            or intake.detected_location
        ),
        detected_segment=(
            analysis["config"].audience_segment
            if analysis["config"] is not None
            else intake.detected_segment
        ),
        detected_school_year=(
            resolved_school_year
        ),
        raw_payload_json=_json_object(intake.raw_payload_json),
        normalized_payload_json=_json_object(analysis["normalized"]),
        answers=analysis["answers"],
        warnings=[_text(item) for item in _json_list(analysis.get("warnings")) if _text(item)],
        blockages=[_text(item) for item in _json_list(analysis.get("blockages")) if _text(item)],
        admin_comment=_text(intake.admin_comment) or None,
        resolution=analysis["effective_resolution"],
        client_candidates=candidates,
        session_recommendations=analysis["session_recommendations"],
        solfege_slot_proposal=_json_object(analysis.get("solfege_slot_proposal")),
        preview_quote=analysis["preview_quote"],
        related_quote_id=intake.related_quote_id,
        form_config=config_out,
        referral=analysis.get("referral") if isinstance(analysis.get("referral"), dict) else None,
        local_confirmation_status=intake.local_confirmation_status or "NOT_REQUIRED",
        local_confirmation_assignee_professor_id=intake.local_confirmation_assignee_professor_id,
        local_confirmation_assignee_name=intake.local_confirmation_assignee_name,
        local_confirmation_session_id=intake.local_confirmation_session_id,
        local_confirmation_product_id=intake.local_confirmation_product_id,
        local_confirmation_schedule_snapshot=intake.local_confirmation_schedule_snapshot,
        local_confirmation_partition_snapshot=intake.local_confirmation_partition_snapshot,
        local_confirmation_partition_not_required=intake.local_confirmation_partition_not_required,
        local_confirmation_comment=intake.local_confirmation_comment,
        local_confirmation_requested_at=intake.local_confirmation_requested_at,
        local_confirmation_notified_at=intake.local_confirmation_notified_at,
        local_confirmation_confirmed_at=intake.local_confirmation_confirmed_at,
        local_confirmation_confirmed_by_name=intake.local_confirmation_confirmed_by_name,
    )


def _form_config_out(config: TypeformFormConfig) -> TypeformFormConfigOut:
    return TypeformFormConfigOut(
        id=config.id,
        typeform_form_id=config.typeform_form_id,
        source_code=config.source_code,
        location_code=config.location_code,
        school_year_label=config.school_year_label,
        audience_segment=config.audience_segment,
        default_quote_type=config.default_quote_type,
        default_quote_type_id=config.default_quote_type_id,
        default_pricing_catalog_id=config.default_pricing_catalog_id,
        default_payment_plan_id=config.default_payment_plan_id,
        default_legal_entity_id=config.default_legal_entity_id,
        default_location_id=config.default_location_id,
        default_language=config.default_language,
        configuration_json=_json_object(config.configuration_json),
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _ingest_typeform_payload(db: Session, payload: dict[str, object]) -> TypeformIntake:
    source_form_id = _extract_typeform_form_id(payload)
    source_response_id = _extract_typeform_response_id(payload)
    if not source_form_id or not source_response_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Typeform payload must include form_id and response_id/token")

    config = db.scalar(
        select(TypeformFormConfig)
        .where(
            TypeformFormConfig.typeform_form_id == source_form_id,
            TypeformFormConfig.is_active.is_(True),
        )
        .limit(1)
    )

    normalized, simplified_answers = _normalize_payload(payload=payload, config=config)
    intake = db.scalar(
        select(TypeformIntake)
        .where(
            TypeformIntake.source_form_id == source_form_id,
            TypeformIntake.source_response_id == source_response_id,
        )
        .with_for_update(of=TypeformIntake)
    )
    if intake is None:
        intake = TypeformIntake(
            form_config_id=config.id if config is not None else None,
            source_form_id=source_form_id,
            source_response_id=source_response_id,
            received_at=_extract_typeform_received_at(payload),
            raw_payload_json=payload,
            normalized_payload_json=normalized,
            simplified_response_json=simplified_answers,
            intake_status=INTAKE_STATUS_NEW,
            detected_location=_text(normalized.get("requested_location")) or (config.location_code if config is not None else None),
            detected_segment=config.audience_segment if config is not None else None,
            detected_school_year=config.school_year_label if config is not None else None,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    else:
        intake.form_config_id = config.id if config is not None else None
        intake.received_at = _extract_typeform_received_at(payload)
        intake.raw_payload_json = payload
        intake.normalized_payload_json = normalized
        intake.simplified_response_json = simplified_answers
        intake.updated_at = _utcnow()

    db.add(intake)
    db.flush()
    _refresh_intake_analysis(db, intake)
    ensure_referral_for_intake(db, intake=intake, normalized=_json_object(intake.normalized_payload_json))
    local_assignee = ensure_local_confirmation_assignment(db, intake=intake, config=config)
    db.commit()
    db.refresh(intake)
    if local_assignee is not None and intake.local_confirmation_notified_at is None:
        try:
            if notify_local_confirmation_assignee(db, intake=intake, professor=local_assignee):
                db.commit()
                db.refresh(intake)
        except Exception:
            db.rollback()
            logger.exception("Unable to notify Bar-le-Duc local confirmation assignee for intake %s", intake.id)
    return intake


def _ensure_demo_activity(
    db: Session,
    *,
    code: str,
    name: str,
    default_price_ttc: Decimal,
    legal_entity: LegalEntity,
    duration_minutes: int,
    active_records: list[str],
) -> CourseType:
    row = db.scalar(select(CourseType).where(CourseType.code == code))
    if row is None:
        row = CourseType(
            code=code,
            name=name,
            description="Activite de demonstration pour le pipeline Typeform.",
            service_code="TYPEFORM_DEMO",
            billing_entity_code=normalize_billing_entity("PIANO_ACADEMIE"),
            seller_legal_entity_id=legal_entity.id,
            payor_legal_entity_id=legal_entity.id,
            credit_type_id=None,
            duration_minutes=duration_minutes,
            color_hex="#3266D0",
            mode=DeliveryMode.ONSITE,
            requires_professor=False,
            default_capacity=6,
            default_hourly_rate=None,
            default_course_rate_ttc=_q2(default_price_ttc),
            active=True,
            created_at=_utcnow(),
        )
        db.add(row)
        db.flush()
        active_records.append(f"activite {code}")
    return row


def _ensure_demo_pricing(
    db: Session,
    *,
    catalog: PricingCatalog,
    activity: CourseType,
    location: Location,
    unit_price_ttc: Decimal,
    active_records: list[str],
) -> None:
    row = db.scalar(
        select(PricingActivityPrice)
        .where(
            PricingActivityPrice.catalog_id == catalog.id,
            PricingActivityPrice.activity_id == activity.id,
            PricingActivityPrice.location_id == location.id,
        )
        .limit(1)
    )
    if row is None:
        db.add(
            PricingActivityPrice(
                catalog_id=catalog.id,
                activity_id=activity.id,
                location_id=location.id,
                student_category=None,
                pricing_unit="per_session",
                unit_price_ttc=_q2(unit_price_ttc),
                currency="EUR",
                is_active=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        active_records.append(f"tarif {activity.code}/{location.code}")


def _ensure_demo_client(
    db: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    client_kind: ClientKind,
    phone: str | None,
    birth_date_iso: str | None,
    active_records: list[str],
) -> User:
    row = db.scalar(select(User).where(User.email == email.lower()).limit(1))
    if row is None:
        row = User(
            email=email.lower(),
            hashed_password=hash_password(generate_temporary_password()),
            role=UserRole.CLIENT,
            client_kind=client_kind,
            client_status=ClientStatus.ACTIVE,
            first_name=first_name,
            last_name=last_name,
            address_country="FR",
            residence_country="FR",
            preferred_currency="EUR",
            timezone="Europe/Paris",
            phone=phone,
            mobile_phone_1=phone,
            birth_date=datetime.fromisoformat(f"{birth_date_iso}T00:00:00").date() if birth_date_iso else None,
            is_active=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(row)
        db.flush()
        active_records.append(f"client {email.lower()}")
    return row


def _ensure_demo_family_link(
    db: Session,
    *,
    adult: User,
    child: User,
    active_records: list[str],
) -> None:
    row = db.scalar(
        select(ClientFamilyLink)
        .where(
            ClientFamilyLink.adult_user_id == adult.id,
            ClientFamilyLink.child_user_id == child.id,
        )
        .limit(1)
    )
    if row is None:
        db.add(
            ClientFamilyLink(
                adult_user_id=adult.id,
                child_user_id=child.id,
                relationship_label="Parent",
                is_billing_recipient=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        active_records.append(f"famille {adult.email}->{child.email}")


def _local_to_utc(*, weekday: int, hour: int, minute: int, timezone_name: str = "Europe/Paris") -> datetime:
    zone = _safe_zoneinfo(timezone_name)
    now_local = _utcnow().astimezone(zone)
    days_ahead = (weekday - now_local.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = (now_local + timedelta(days=days_ahead)).date()
    local_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=zone)
    return local_dt.astimezone(timezone.utc)


def _ensure_demo_session(
    db: Session,
    *,
    marker: str,
    activity: CourseType,
    location: Location,
    weekday: int,
    hour: int,
    minute: int,
    capacity_max: int,
    active_records: list[str],
) -> None:
    row = db.scalar(select(CourseSession).where(CourseSession.private_description == marker).limit(1))
    start_at_utc = _local_to_utc(weekday=weekday, hour=hour, minute=minute, timezone_name=location.timezone)
    end_at_utc = start_at_utc + timedelta(minutes=int(activity.duration_minutes))
    if row is None:
        db.add(
            CourseSession(
                course_type_id=activity.id,
                billing_entity_snapshot=normalize_billing_entity(activity.billing_entity_code),
                snapshot_seller_legal_entity_id=activity.seller_legal_entity_id,
                snapshot_payor_legal_entity_id=activity.payor_legal_entity_id,
                location_id=location.id,
                professor_id=None,
                title=activity.name,
                description="Session de demonstration Typeform.",
                private_description=marker,
                start_at_utc=start_at_utc,
                end_at_utc=end_at_utc,
                is_all_day=False,
                capacity_max=capacity_max,
                status=SessionStatus.SCHEDULED,
                auto_cancel_deadline_utc=start_at_utc - timedelta(hours=12),
                cancel_reason=None,
                zoom_link=None,
                is_private=False,
                allow_online_booking=True,
                timezone=location.timezone,
                recurrence_group_id=None,
                recurrence_rule=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        active_records.append(f"session {marker}")


def _line_templates_for_activity(code: str) -> list[dict[str, object]]:
    return [
        {
            "kind": "activity",
            "activity_code": code,
            "quantity": "1",
        }
    ]


def _ensure_form_config(
    db: Session,
    *,
    typeform_form_id: str,
    source_code: str,
    location_code: str,
    school_year_label: str,
    audience_segment: str,
    quote_type: QuoteType,
    catalog: PricingCatalog,
    payment_plan: PaymentPlan,
    legal_entity: LegalEntity,
    location: Location,
    line_templates: list[dict[str, object]],
    field_mapping: dict[str, object],
    field_labels: dict[str, object],
    label: str,
    active_records: list[str],
) -> TypeformFormConfig:
    row = db.scalar(select(TypeformFormConfig).where(TypeformFormConfig.typeform_form_id == typeform_form_id).limit(1))
    if row is None:
        row = TypeformFormConfig(
            typeform_form_id=typeform_form_id,
            source_code=source_code,
            location_code=location_code,
            school_year_label=school_year_label,
            audience_segment=audience_segment,
            default_quote_type=quote_type.name,
            default_quote_type_id=quote_type.id,
            default_pricing_catalog_id=catalog.id,
            default_payment_plan_id=payment_plan.id,
            default_legal_entity_id=legal_entity.id,
            default_location_id=location.id,
            default_language="fr",
            configuration_json={
                "label": label,
                "field_mapping": field_mapping,
                "field_labels": field_labels,
                "line_templates": line_templates,
                "default_vat_rate": "20.00",
                "default_course_mode": "onsite",
                "default_pre_registration_deposit_enabled": True,
                "default_pre_registration_deposit_amount_ttc": "200.00",
            },
            is_active=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(row)
        db.flush()
        active_records.append(f"formulaire {typeform_form_id}")
    return row


def _demo_payload(*, form_id: str, response_id: str, answers: list[dict[str, object]]) -> dict[str, object]:
    return {
        "event_id": f"evt-{response_id}",
        "event_type": "form_response",
        "form_response": {
            "form_id": form_id,
            "token": response_id,
            "submitted_at": _utcnow().isoformat(),
            "answers": answers,
        },
    }


def _answer(ref: str, value: object) -> dict[str, object]:
    field = {"ref": ref}
    if isinstance(value, list):
        return {"field": field, "type": "choices", "choices": {"labels": [_text(item) for item in value if _text(item)]}}
    if isinstance(value, bool):
        return {"field": field, "type": "boolean", "boolean": value}
    text_value = _text(value)
    if "@" in text_value:
        return {"field": field, "type": "email", "email": text_value}
    if text_value.startswith("+") or _digits(text_value):
        if len(_digits(text_value)) >= 9 and any(ch in text_value for ch in "+0123456789"):
            return {"field": field, "type": "phone_number", "phone_number": text_value}
    if len(text_value) == 10 and text_value[4] == "-" and text_value[7] == "-":
        return {"field": field, "type": "date", "date": text_value}
    return {"field": field, "type": "text", "text": text_value}


def _create_or_reuse_adult_prospect(
    db: Session,
    *,
    normalized: dict[str, object],
    intake: TypeformIntake,
    config: TypeformFormConfig,
) -> Prospect:
    email = _lower(normalized.get("parent_email"))
    if not email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email parent/adulte manquant pour creer le prospect")
    existing_parent_client = _find_existing_adult_parent_client(db, normalized)
    existing = db.scalar(
        select(Prospect)
        .where(
            Prospect.email == email,
            func.coalesce(Prospect.meta["prospect_type"].astext, "adult") != "child",
        )
        .limit(1)
    )
    if existing is not None:
        if existing_parent_client is not None:
            existing.linked_client_id = existing.linked_client_id or existing_parent_client.id
            existing.first_name = existing_parent_client.first_name or existing.first_name
            existing.last_name = existing_parent_client.last_name or existing.last_name
            existing.phone = existing_parent_client.mobile_phone_1 or existing_parent_client.phone or existing.phone
            meta = _json_object(existing.meta)
            meta["linked_parent_client_id"] = str(existing_parent_client.id)
            existing.meta = meta
            existing.updated_at = _utcnow()
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return existing

    parent_first_name = _text(normalized.get("parent_first_name")) or None
    parent_last_name = _text(normalized.get("parent_last_name")) or None
    parent_phone = _text(normalized.get("parent_phone")) or None
    if existing_parent_client is not None:
        parent_first_name = existing_parent_client.first_name or parent_first_name
        parent_last_name = existing_parent_client.last_name or parent_last_name
        parent_phone = existing_parent_client.mobile_phone_1 or existing_parent_client.phone or parent_phone

    row = Prospect(
        linked_client_id=existing_parent_client.id if existing_parent_client is not None else None,
        parent_prospect_id=None,
        status="active",
        first_name=parent_first_name,
        last_name=parent_last_name,
        email=email,
        phone=parent_phone,
        source=f"typeform:{config.source_code}",
        notes=_text(normalized.get("notes")) or None,
        meta={
            "prospect_type": "adult",
            "typeform_intake_id": str(intake.id),
            "requested_location": normalized.get("requested_location"),
            "requested_formula_type": normalized.get("requested_formula_type"),
            "linked_parent_client_id": str(existing_parent_client.id) if existing_parent_client is not None else None,
        },
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _create_or_reuse_child_prospect(
    db: Session,
    *,
    normalized: dict[str, object],
    intake: TypeformIntake,
    config: TypeformFormConfig,
    parent: Prospect,
) -> Prospect:
    email = _lower(normalized.get("parent_email"))
    child_first_name = _text(normalized.get("child_first_name"))
    child_last_name = _text(normalized.get("child_last_name"))
    child_birth_date = _text(normalized.get("child_birth_date"))
    existing_children = db.scalars(
        select(Prospect)
        .where(
            Prospect.parent_prospect_id == parent.id,
            func.coalesce(Prospect.meta["prospect_type"].astext, "adult") == "child",
        )
    ).all()
    for child in existing_children:
        child_meta = _json_object(child.meta).get("child")
        child_meta = _json_object(child_meta)
        if (
            _lower(child_meta.get("first_name")) == _lower(child_first_name)
            and _lower(child_meta.get("last_name")) == _lower(child_last_name)
            and _text(child_meta.get("birth_date")) == child_birth_date
        ):
            return child

    row = Prospect(
        linked_client_id=None,
        parent_prospect_id=parent.id,
        status="active",
        first_name=child_first_name or None,
        last_name=child_last_name or None,
        email=email,
        phone=_text(normalized.get("parent_phone")) or None,
        source=f"typeform:{config.source_code}",
        notes=_text(normalized.get("notes")) or None,
        meta={
            "prospect_type": "child",
            "parent_referent_mode": "existing_parent" if parent.linked_client_id is not None else "new_parent",
            "child": {
                "first_name": child_first_name,
                "last_name": child_last_name,
                "birth_date": child_birth_date or None,
            },
            "parent_referent": {
                "first_name": parent.first_name,
                "last_name": parent.last_name,
                "email": parent.email,
                "phone": parent.phone,
            },
            "typeform_intake_id": str(intake.id),
        },
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _quote_meta_from_analysis(
    *,
    intake: TypeformIntake,
    config: TypeformFormConfig,
    normalized: dict[str, object],
    resolution: dict[str, object],
    session_recommendations: list[TypeformSessionRecommendationOut],
    runtime_context: dict[str, object],
) -> dict[str, object]:
    selected_session_ids = _effective_selected_session_ids(
        resolution=resolution,
        session_recommendations=session_recommendations,
    )
    return {
        "source": "typeform_intake",
        "language": config.default_language,
        "typeform_intake": {
            "intake_id": str(intake.id),
            "source_form_id": intake.source_form_id,
            "source_response_id": intake.source_response_id,
            "source_code": config.source_code,
            "location_code": _text(runtime_context.get("location_code")) or config.location_code,
            "form_location_code": config.location_code,
            "location_id": str(_parse_uuid(runtime_context.get("location_id"))) if _parse_uuid(runtime_context.get("location_id")) else None,
            "audience_segment": config.audience_segment,
            "school_year_label": config.school_year_label,
            "normalized_payload": normalized,
            "resolution": resolution,
            "selected_session_ids": selected_session_ids,
            "session_recommendations": [
                {
                    "activity_id": str(item.activity_id),
                    "summary_status": item.summary_status,
                    "selected_session_id": str(item.selected_session_id) if item.selected_session_id else None,
                }
                for item in session_recommendations
            ],
        },
    }


def _default_pre_registration_deposit_from_config(config: TypeformFormConfig) -> dict[str, object] | None:
    config_json = _json_object(config.configuration_json)
    enabled = _bool_or_default(config_json.get("default_pre_registration_deposit_enabled"), True)
    if not enabled:
        return None
    amount = _q2(_parse_decimal(config_json.get("default_pre_registration_deposit_amount_ttc"), Decimal("200.00")))
    if amount <= Decimal("0.00"):
        amount = Decimal("200.00")
    return {
        "enabled": True,
        "amount_ttc": str(amount),
    }


def _calendar_snapshot_from_analysis(
    db: Session,
    *,
    normalized: dict[str, object],
    resolution: dict[str, object],
    session_recommendations: list[TypeformSessionRecommendationOut],
    runtime_context: dict[str, object],
    quote_lines: list[QuoteLineIn] | None = None,
) -> dict[str, object]:
    selected_session_ids = _effective_selected_session_ids(
        resolution=resolution,
        session_recommendations=session_recommendations,
    )
    snapshot = {
        "typeform_preferences": {
            "requested_days": _json_list(normalized.get("requested_days")),
            "requested_times": _json_list(normalized.get("requested_times")),
            "requested_location": normalized.get("requested_location"),
            "requested_slot_preferences": _json_list(normalized.get("requested_slot_preferences")),
        },
        "typeform_recommendations": [
            {
                "activity_id": str(item.activity_id),
                "recommendation_key": _session_recommendation_key(item),
                "activity_name": item.activity_name,
                "summary_status": item.summary_status,
                "summary_label": item.summary_label,
                "selected_session_id": selected_session_ids.get(_session_recommendation_key(item)) or selected_session_ids.get(str(item.activity_id)),
                "options": [
                    {
                        "session_id": str(option.session_id),
                        "location_name": option.location_name,
                        "weekday_label": option.weekday_label,
                        "start_time_label": option.start_time_label,
                        "seats_remaining": option.seats_remaining,
                    }
                    for option in item.options
                ],
            }
            for item in session_recommendations
        ],
    }
    blocks: list[dict[str, object]] = []
    sessions: list[dict[str, object]] = []
    estimated_solfege_level = _extract_estimated_solfege_level(
        normalized=normalized,
        session_recommendations=session_recommendations,
    )
    solfege_selected_slot: dict[str, object] = {}
    session_limit_by_key: dict[str, int] = {}
    for line in quote_lines or []:
        limit = _planning_session_limit_from_meta(line.meta)
        if limit is None:
            continue
        recommendation_key = _quote_line_recommendation_key(line)
        if recommendation_key:
            session_limit_by_key[recommendation_key] = limit
        if line.activity_id is not None:
            session_limit_by_key.setdefault(str(line.activity_id), limit)

    selected_uuid_map: dict[str, UUID] = {}
    for activity_id, session_id in selected_session_ids.items():
        parsed = _parse_uuid(session_id)
        if parsed is not None:
            selected_uuid_map[activity_id] = parsed

    if selected_uuid_map:
        selected_rows = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(CourseSession.id.in_(list(selected_uuid_map.values())))
        ).all()
        selected_rows_by_id: dict[UUID, tuple[CourseSession, CourseType, Location]] = {
            session_obj.id: (session_obj, activity, location)
            for session_obj, activity, location in selected_rows
        }

        for recommendation in session_recommendations:
            selected_session_id = selected_uuid_map.get(_session_recommendation_key(recommendation)) or selected_uuid_map.get(str(recommendation.activity_id))
            if selected_session_id is None:
                continue
            selected_row = selected_rows_by_id.get(selected_session_id)
            if selected_row is None:
                continue

            session_obj, activity, location = selected_row
            series_sessions = _load_selected_session_school_year_series(
                db,
                selected_session=session_obj,
                location=location,
                school_year_label=runtime_context.get("school_year_label"),
            )
            if not series_sessions:
                series_sessions = [session_obj]
            session_limit = session_limit_by_key.get(_session_recommendation_key(recommendation)) or session_limit_by_key.get(
                str(recommendation.activity_id)
            )

            zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
            first_local_start = series_sessions[0].start_at_utc.astimezone(zone)
            first_local_end = series_sessions[0].end_at_utc.astimezone(zone)
            last_local_start = series_sessions[-1].start_at_utc.astimezone(zone)
            modality = _modality_from_activity_location(activity, location)
            series_key = str(session_obj.recurrence_group_id or session_obj.id)
            blocks.append(
                {
                    "activity_id": str(activity.id),
                    "recommendation_key": _session_recommendation_key(recommendation),
                    "activity_label": activity.name,
                    "location_id": str(location.id),
                    "location_label": location.name,
                    "weekday": first_local_start.weekday(),
                    "weekday_label": DAY_LABELS[first_local_start.weekday()],
                    "recurrence_frequency": _recurrence_frequency_from_rule(session_obj.recurrence_rule),
                    "start_date": first_local_start.date().isoformat(),
                    "end_date": last_local_start.date().isoformat(),
                    "start_time": first_local_start.strftime("%H:%M"),
                    "end_time": first_local_end.strftime("%H:%M"),
                    "modality": modality,
                    "series_key": series_key,
                    "planning_session_limit": session_limit,
                    "school_year_label": runtime_context.get("school_year_label"),
                    "selection_pending": False,
                }
            )

            for occurrence in series_sessions:
                occurrence_zone = _safe_zoneinfo(occurrence.timezone or location.timezone)
                local_start = occurrence.start_at_utc.astimezone(occurrence_zone)
                local_end = occurrence.end_at_utc.astimezone(occurrence_zone)
                sessions.append(
                    {
                        "date": local_start.date().isoformat(),
                        "start_time": local_start.strftime("%H:%M"),
                        "end_time": local_end.strftime("%H:%M"),
                        "duration_minutes": int((local_end - local_start).total_seconds() // 60),
                        "activity_id": str(activity.id),
                        "recommendation_key": _session_recommendation_key(recommendation),
                        "activity_label": activity.name,
                        "location_id": str(location.id),
                        "location_label": location.name,
                        "series_key": series_key,
                        "weekday": local_start.weekday(),
                        "weekday_label": DAY_LABELS[local_start.weekday()],
                        "modality": modality,
                    }
                )

            if _is_solfege_recommendation(recommendation, runtime_context=runtime_context) and not solfege_selected_slot:
                solfege_selected_slot = {
                    "level_code": estimated_solfege_level,
                    "weekday": first_local_start.weekday(),
                    "weekday_label": DAY_LABELS[first_local_start.weekday()],
                    "start_time": first_local_start.strftime("%H:%M"),
                    "end_time": first_local_end.strftime("%H:%M"),
                    "duration_minutes": int((first_local_end - first_local_start).total_seconds() // 60),
                    "location_id": str(location.id),
                    "location_label": location.name,
                    "modality": modality,
                    "label": f"{DAY_LABELS[first_local_start.weekday()]} {first_local_start.strftime('%H:%M')}-{first_local_end.strftime('%H:%M')} · {location.name}",
                }

    if not solfege_selected_slot:
        solfege_selected_slot = _solfege_slot_proposal_from_normalized(
            db,
            normalized=normalized,
            runtime_context=runtime_context,
            session_recommendations=session_recommendations,
        )

    if estimated_solfege_level:
        pending_recommendation = next(
            (
                item
                for item in session_recommendations
                if _is_solfege_recommendation(item, runtime_context=runtime_context)
                and _session_recommendation_key(item) not in selected_session_ids
                and str(item.activity_id) not in selected_session_ids
            ),
            None,
        )
        if pending_recommendation is not None:
            resolved_location_id = _parse_uuid(runtime_context.get("location_id"))
            resolved_location_name = _text(runtime_context.get("location_name")) or pending_recommendation.requested_location or None
            pending_slot_options = [
                {
                    "weekday": DAY_ALIASES.get(_normalize_token(option.weekday_label)),
                    "weekday_label": option.weekday_label,
                    "start_time": option.start_time_label,
                    "end_time": option.end_time_label,
                    "duration_minutes": None,
                    "location_id": str(option.location_id),
                    "location_label": option.location_name,
                    "modality": "ONLINE" if _is_online_runtime_context(runtime_context) else "ONSITE",
                    "label": " · ".join(
                        part
                        for part in (
                            " ".join(part for part in (option.weekday_label, option.start_time_label) if part),
                            option.location_name,
                        )
                        if part
                    ),
                }
                for option in pending_recommendation.options
            ]
            selected_slot = _json_object(solfege_selected_slot)
            selected_weekday = selected_slot.get("weekday")
            selected_weekday_label = _text(selected_slot.get("weekday_label")) or (
                DAY_LABELS[int(selected_weekday)]
                if isinstance(selected_weekday, int) and 0 <= selected_weekday <= 6
                else "Selection a faire"
            )
            selected_start = _text(selected_slot.get("start_time"))
            selected_end = _text(selected_slot.get("end_time"))
            school_year_bounds = _school_year_bounds_from_label(_text(runtime_context.get("school_year_label")))
            start_date = school_year_bounds[0].isoformat() if school_year_bounds is not None else ""
            end_date = school_year_bounds[1].isoformat() if school_year_bounds is not None else ""
            blocks.append(
                {
                    "activity_id": str(pending_recommendation.activity_id),
                    "activity_label": pending_recommendation.activity_name,
                    "location_id": selected_slot.get("location_id") if selected_slot else (str(resolved_location_id) if resolved_location_id is not None else None),
                    "location_label": _text(selected_slot.get("location_label")) if selected_slot else resolved_location_name,
                    "weekday": selected_weekday if selected_slot else -1,
                    "weekday_label": selected_weekday_label,
                    "recurrence_frequency": "weekly",
                    "start_date": start_date if selected_slot else "",
                    "end_date": end_date if selected_slot else "",
                    "start_time": selected_start if selected_slot else "",
                    "end_time": selected_end if selected_slot else "",
                    "duration_minutes": selected_slot.get("duration_minutes") if selected_slot else None,
                    "modality": selected_slot.get("modality") if selected_slot else ("online" if _is_online_runtime_context(runtime_context) else None),
                    "selection_pending": False if selected_slot else True,
                    "pending_solfege_level": estimated_solfege_level,
                    "pending_slot_options": [] if selected_slot else pending_slot_options,
                }
            )

    sessions.sort(
        key=lambda item: (
            _text(item.get("date")),
            _text(item.get("start_time")),
            _text(item.get("activity_label")),
        )
    )
    snapshot["blocks"] = blocks
    snapshot["sessions"] = sessions
    snapshot["sessions_count"] = len(sessions)
    snapshot["generated_at"] = _utcnow().isoformat()
    if estimated_solfege_level or solfege_selected_slot:
        snapshot["solfege"] = {
            "level_code": estimated_solfege_level,
            "selected_slot": solfege_selected_slot,
        }
    return _calendar_snapshot_with_planning_sessions(db, snapshot)


@router.get("/form-configs", response_model=list[TypeformFormConfigOut])
def list_typeform_form_configs(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[TypeformFormConfigOut]:
    stmt = select(TypeformFormConfig).order_by(TypeformFormConfig.source_code.asc())
    if active_only:
        stmt = stmt.where(TypeformFormConfig.is_active.is_(True))
    rows = db.scalars(stmt).all()
    return [_form_config_out(row) for row in rows]


@router.patch("/form-configs/{config_id}/quote-defaults", response_model=TypeformFormConfigOut)
def update_typeform_form_config_quote_defaults(
    config_id: UUID,
    payload: TypeformFormConfigQuoteDefaultsRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformFormConfigOut:
    row = db.scalar(select(TypeformFormConfig).where(TypeformFormConfig.id == config_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuration Typeform introuvable")
    config_json = _json_object(row.configuration_json)
    amount = _q2(payload.default_pre_registration_deposit_amount_ttc)
    config_json["default_pre_registration_deposit_enabled"] = bool(payload.default_pre_registration_deposit_enabled)
    config_json["default_pre_registration_deposit_amount_ttc"] = str(amount)
    row.configuration_json = config_json
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _form_config_out(row)


@router.get("/intakes", response_model=TypeformIntakeListPageOut)
def list_typeform_intakes(
    status_filter: str | None = Query(default=None, alias="status"),
    include_ignored: bool = Query(default=False),
    exclude_processed: bool = Query(default=True),
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_intakes")),
) -> TypeformIntakeListPageOut:
    stmt = select(TypeformIntake)
    if status_filter:
        stmt = stmt.where(TypeformIntake.intake_status == _text(status_filter).upper())
    else:
        if not include_ignored:
            stmt = stmt.where(TypeformIntake.intake_status != INTAKE_STATUS_IGNORED)
        if exclude_processed:
            stmt = stmt.where(TypeformIntake.intake_status != INTAKE_STATUS_PROCESSED)
    for search_token in [token for token in _text(q).split() if token]:
        like = f"%{search_token}%"
        stmt = stmt.where(
            or_(
                TypeformIntake.source_form_id.ilike(like),
                TypeformIntake.source_response_id.ilike(like),
                TypeformIntake.detected_location.ilike(like),
                TypeformIntake.detected_segment.ilike(like),
                TypeformIntake.detected_school_year.ilike(like),
                TypeformIntake.admin_comment.ilike(like),
                cast(TypeformIntake.normalized_payload_json, Text).ilike(like),
                cast(TypeformIntake.simplified_response_json, Text).ilike(like),
            )
        )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max((total + page_size - 1) // page_size, 1)
    current_page = min(page, total_pages)
    rows = db.scalars(
        stmt.order_by(TypeformIntake.received_at.desc(), TypeformIntake.id.desc())
        .offset((current_page - 1) * page_size)
        .limit(page_size)
    ).all()
    config_ids = {row.form_config_id for row in rows if row.form_config_id is not None}
    configs_by_id = (
        {
            config.id: config
            for config in db.scalars(
                select(TypeformFormConfig).where(TypeformFormConfig.id.in_(list(config_ids)))
            ).all()
        }
        if config_ids
        else {}
    )
    return TypeformIntakeListPageOut(
        items=[_intake_list_out_fast(row, config=configs_by_id.get(row.form_config_id)) for row in rows],
        total=total,
        page=current_page,
        page_size=page_size,
    )


@router.get("/intakes/{intake_id}", response_model=TypeformIntakeDetailOut)
def get_typeform_intake(
    intake_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_intakes")),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.post("/intakes/{intake_id}/reanalyze", response_model=TypeformIntakeDetailOut)
def reanalyze_typeform_intake(
    intake_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.patch("/intakes/{intake_id}/resolution", response_model=TypeformIntakeDetailOut)
def update_typeform_intake_resolution(
    intake_id: UUID,
    payload: TypeformIntakeResolutionRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    current_resolution = _json_object(intake.resolution_json)
    next_resolution = _json_object(payload.resolution)
    for preserved_key in ("created_entities", "admin_state", "admin_state_meta"):
        if preserved_key not in next_resolution and preserved_key in current_resolution:
            next_resolution[preserved_key] = current_resolution[preserved_key]
    intake.resolution_json = next_resolution
    intake.updated_at = _utcnow()
    db.add(intake)
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.patch("/intakes/{intake_id}/admin-state", response_model=TypeformIntakeDetailOut)
def update_typeform_intake_admin_state(
    intake_id: UUID,
    payload: TypeformIntakeAdminStateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    if payload.ignored and intake.related_quote_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Impossible d'ignorer une intake deja liee a un devis",
        )
    resolution = _json_object(intake.resolution_json)
    if payload.ignored:
        resolution["admin_state"] = "ignored"
        resolution["admin_state_meta"] = {
            "updated_at": _utcnow().isoformat(),
        }
    else:
        resolution.pop("admin_state", None)
        resolution.pop("admin_state_meta", None)
    intake.resolution_json = resolution
    intake.updated_at = _utcnow()
    db.add(intake)
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.patch("/intakes/{intake_id}/admin-comment", response_model=TypeformIntakeDetailOut)
def update_typeform_intake_admin_comment(
    intake_id: UUID,
    payload: TypeformIntakeAdminCommentRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    intake.admin_comment = _text(payload.admin_comment) or None
    intake.updated_at = _utcnow()
    db.add(intake)
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.patch("/intakes/{intake_id}/normalized", response_model=TypeformIntakeDetailOut)
def update_typeform_intake_normalized_payload(
    intake_id: UUID,
    payload: TypeformIntakeNormalizedPatchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    intake.normalized_payload_json = _merge_normalized_payload_patch(
        _json_object(intake.normalized_payload_json),
        _json_object(payload.normalized_payload_json),
    )
    intake.updated_at = _utcnow()
    db.add(intake)
    ensure_referral_for_intake(db, intake=intake, normalized=_json_object(intake.normalized_payload_json))
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.patch("/intakes/{intake_id}/referral", response_model=TypeformIntakeDetailOut)
def update_typeform_intake_referral(
    intake_id: UUID,
    payload: TypeformIntakeReferralRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformIntakeDetailOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    reward = db.scalar(select(ReferralReward).where(ReferralReward.typeform_intake_id == intake.id).with_for_update())
    if reward is None:
        reward = ensure_referral_for_intake(db, intake=intake, normalized=_json_object(intake.normalized_payload_json))
    if reward is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun parrainage declare sur cette intake")
    try:
        manually_validate_referral(
            db,
            reward_id=reward.id,
            referrer_user_id=payload.referrer_user_id,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    analysis = _refresh_intake_analysis(db, intake)
    db.commit()
    db.refresh(intake)
    return _intake_detail_out(intake, analysis)


@router.post("/intakes/{intake_id}/draft-quote", response_model=TypeformDraftQuoteResultOut, status_code=status.HTTP_201_CREATED)
def create_draft_quote_from_typeform_intake(
    intake_id: UUID,
    allow_empty_quote: bool = Query(default=False),
    family_only_quote: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformDraftQuoteResultOut:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    if intake.related_quote_id is not None:
        return TypeformDraftQuoteResultOut(
            intake_id=intake.id,
            quote_id=intake.related_quote_id,
            intake_status=INTAKE_STATUS_PROCESSED,
        )

    analysis = _refresh_intake_analysis(db, intake)
    client_arbitrage_required = _needs_client_arbitrage(
        analysis["client_candidates"],
        analysis["family_candidates"],
        analysis["effective_resolution"],
    )
    session_arbitrage_required = _needs_session_arbitrage(analysis["session_recommendations"])
    pending_arbitrage_warning = _draft_quote_warning_for_pending_arbitrage(
        client_arbitrage_required=client_arbitrage_required,
        session_arbitrage_required=session_arbitrage_required,
    )
    if intake.intake_status == INTAKE_STATUS_IGNORED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cette intake est ignoree. Reactivez-la avant de generer un devis.",
        )
    if intake.intake_status == INTAKE_STATUS_BLOCKED and not family_only_quote:
        blocking_messages = [message for message in analysis["blockages"] if _text(message)]
        preview_lines_in = analysis["preview_quote_lines_in"]
        if not (
            allow_empty_quote
            and _can_force_empty_draft_quote(
                blockages=blocking_messages,
                preview_lines_in=preview_lines_in,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=" ; ".join(blocking_messages) or "Cette intake comporte encore des blocages.",
            )
    config = analysis["config"]
    if config is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Configuration formulaire introuvable")
    normalized = _json_object(analysis["normalized"])
    resolution = _json_object(analysis["effective_resolution"])
    client_resolution = _json_object(resolution.get("client_resolution"))
    preview_lines_in = [] if family_only_quote else analysis["preview_quote_lines_in"]
    if not preview_lines_in and not allow_empty_quote:
        if not family_only_quote:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pre-devis vide")

    created_entities = _json_object(resolution.get("created_entities"))
    context_type = "acquisition"
    client_id: UUID | None = None
    prospect_id: UUID | None = None
    mode = _text(client_resolution.get("mode")) or CLIENT_MODE_NEW_ADULT
    if mode == CLIENT_MODE_EXISTING:
        client_id = _parse_uuid(client_resolution.get("selected_client_id"))
        if client_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Client selectionne manquant")
        context_type = "active_client"
        _apply_intake_child_birth_date_to_existing_client(db, client_id=client_id, normalized=normalized)
    elif mode == CLIENT_MODE_EXISTING_FAMILY:
        client_id = _parse_uuid(client_resolution.get("selected_family_child_client_id"))
        if client_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Eleve selectionne manquant")
        context_type = "active_client"
        _apply_intake_child_birth_date_to_existing_client(db, client_id=client_id, normalized=normalized)
    elif mode == CLIENT_MODE_NEW_PARENT_CHILD:
        parent_prospect_id = _parse_uuid(created_entities.get("parent_prospect_id"))
        child_prospect_id = _parse_uuid(created_entities.get("child_prospect_id"))
        parent = db.scalar(select(Prospect).where(Prospect.id == parent_prospect_id)) if parent_prospect_id else None
        child = db.scalar(select(Prospect).where(Prospect.id == child_prospect_id)) if child_prospect_id else None
        if parent is None:
            parent = _create_or_reuse_adult_prospect(db, normalized=normalized, intake=intake, config=config)
        if child is None:
            child = _create_or_reuse_child_prospect(db, normalized=normalized, intake=intake, config=config, parent=parent)
        prospect_id = child.id
        created_entities["parent_prospect_id"] = str(parent.id)
        created_entities["child_prospect_id"] = str(child.id)
    else:
        adult_prospect_id = _parse_uuid(created_entities.get("adult_prospect_id"))
        adult_prospect = db.scalar(select(Prospect).where(Prospect.id == adult_prospect_id)) if adult_prospect_id else None
        if adult_prospect is None:
            adult_prospect = _create_or_reuse_adult_prospect(db, normalized=normalized, intake=intake, config=config)
        prospect_id = adult_prospect.id
        created_entities["adult_prospect_id"] = str(adult_prospect.id)

    quote_meta = _quote_meta_from_analysis(
        intake=intake,
        config=config,
        normalized=normalized,
        resolution={**resolution, "created_entities": created_entities},
        session_recommendations=[] if family_only_quote else analysis["session_recommendations"],
        runtime_context=_json_object(analysis.get("runtime_context")),
    )
    default_deposit = _default_pre_registration_deposit_from_config(config)
    if default_deposit is not None:
        quote_meta["pre_registration_deposit"] = default_deposit
    if _bool_or_default(normalized.get("requested_pass_recup"), False):
        quote_meta["pass_recup_mode"] = "enabled"
        quote_meta["pass_recup_enabled"] = True
    if pending_arbitrage_warning:
        quote_meta["typeform_pending_arbitrage_at_creation"] = True
        quote_meta["typeform_creation_warning"] = pending_arbitrage_warning
        quote_meta["typeform_client_arbitrage_required"] = client_arbitrage_required
        quote_meta["typeform_session_arbitrage_required"] = session_arbitrage_required
        quote_meta["typeform_unselected_session_recommendations"] = [
            {
                "activity_id": str(item.activity_id),
                "activity_name": item.activity_name,
                "summary_status": item.summary_status,
                "summary_label": item.summary_label,
                "option_count": len(item.options),
            }
            for item in analysis["session_recommendations"]
            if item.selected_session_id is None
        ]
    if mode == CLIENT_MODE_EXISTING_FAMILY:
        quote_meta["typeform_selected_family_adult_client_id"] = client_resolution.get("selected_family_adult_client_id")
        quote_meta["typeform_selected_family_child_client_id"] = client_resolution.get("selected_family_child_client_id")
        quote_meta["typeform_selected_family_billing_client_id"] = (
            client_resolution.get("selected_family_billing_client_id")
            or client_resolution.get("selected_family_adult_client_id")
        )
    if allow_empty_quote and not preview_lines_in:
        quote_meta["typeform_empty_quote_created"] = True
        quote_meta["typeform_empty_quote_reason"] = [
            _text(message)
            for message in _json_list(analysis.get("blockages"))
            if _text(message)
        ]
    if family_only_quote:
        quote_meta["typeform_family_only_quote_created"] = True
        quote_meta["typeform_family_only_quote_reason"] = [
            _text(message)
            for message in _json_list(analysis.get("blockages"))
            if _text(message)
        ]

    if family_only_quote:
        calendar_snapshot = {
            "typeform_preferences": {
                "requested_days": _json_list(normalized.get("requested_days")),
                "requested_times": _json_list(normalized.get("requested_times")),
                "requested_location": normalized.get("requested_location"),
                "requested_slot_preferences": _json_list(normalized.get("requested_slot_preferences")),
            },
            "typeform_recommendations": [],
            "blocks": [],
            "sessions": [],
            "sessions_count": 0,
            "generated_at": _utcnow().isoformat(),
            "family_only_quote": True,
        }
    else:
        preview_quote = analysis["preview_quote"]
        preview_template_lines = list(preview_quote.lines) if preview_quote is not None else []
        calendar_snapshot = _calendar_snapshot_from_analysis(
            db,
            normalized=normalized,
            resolution=resolution,
            session_recommendations=analysis["session_recommendations"],
            runtime_context=_json_object(analysis.get("runtime_context")),
            quote_lines=preview_lines_in,
        )
        preview_template_lines, preview_lines_in = _apply_planned_quantities_to_activity_lines(
            preview_lines=preview_template_lines,
            quote_lines=preview_lines_in,
            calendar_snapshot=calendar_snapshot,
        )
    estimated_solfege_level = _extract_estimated_solfege_level(
        normalized=normalized,
        session_recommendations=[] if family_only_quote else analysis["session_recommendations"],
    )
    selected_solfege_slot = {} if family_only_quote else _json_object(_json_object(calendar_snapshot.get("solfege")).get("selected_slot"))
    if family_only_quote:
        preview_quote = analysis["preview_quote"]
        preview_template_lines = list(preview_quote.lines) if preview_quote is not None else []
    quote_type_id = _parse_uuid(_json_object(analysis.get("runtime_context")).get("quote_type_id")) or config.default_quote_type_id
    default_quote_template = None
    default_terms_template = None
    if _is_bar_le_duc_config(config):
        default_quote_template = _typeform_default_quote_template(
            db,
            config=config,
            preview_lines=preview_template_lines,
        )
        default_terms_template = _typeform_default_terms_template(
            db,
            config=config,
            preview_lines=preview_template_lines,
        )
    binding_quote_template, binding_terms_template = _typeform_document_templates_from_binding(
        db,
        prospect_id=prospect_id,
        client_id=client_id,
        context_type=context_type,
        quote_type_id=quote_type_id,
        language=config.default_language,
        currency="EUR",
        preview_lines=preview_template_lines,
    )
    default_quote_template = default_quote_template or binding_quote_template
    default_terms_template = default_terms_template or binding_terms_template
    default_quote_template = default_quote_template or _typeform_default_quote_template(
        db,
        config=config,
        preview_lines=preview_template_lines,
    )
    default_terms_template = default_terms_template or _typeform_default_terms_template(
        db,
        config=config,
        preview_lines=preview_template_lines,
    )

    quote_payload = QuoteCreateRequest(
        context_type=context_type,
        quote_type=_text(_json_object(analysis.get("runtime_context")).get("quote_type")) or _text(config.default_quote_type) or "forfait",
        quote_type_id=quote_type_id,
        pricing_catalog_id=_parse_uuid(_json_object(analysis.get("runtime_context")).get("pricing_catalog_id")) or config.default_pricing_catalog_id,
        prospect_id=prospect_id,
        client_id=client_id,
        location_id=_parse_uuid(_json_object(analysis.get("runtime_context")).get("location_id")) or config.default_location_id,
        legal_entity_id=_parse_uuid(_json_object(analysis.get("runtime_context")).get("legal_entity_id")) or config.default_legal_entity_id,
        payment_plan_id=_parse_uuid(_json_object(analysis.get("runtime_context")).get("payment_plan_id")) or config.default_payment_plan_id,
        school_year_label=config.school_year_label,
        currency="EUR",
        language=config.default_language,
        vat_rate=_extract_vat_rate({"tva_rate": _text(_json_object(config.configuration_json).get("default_vat_rate"))}) or Decimal("20.00"),
        estimated_solfege_level=estimated_solfege_level,
        selected_solfege_slot=selected_solfege_slot,
        calendar_snapshot=calendar_snapshot,
        quote_template_uuid=default_quote_template.id if default_quote_template is not None else None,
        quote_template_version_id=default_quote_template.current_version_id if default_quote_template is not None else None,
        terms_template_id=default_terms_template.id if default_terms_template is not None else None,
        terms_template_version_id=default_terms_template.current_version_id if default_terms_template is not None else None,
        meta=quote_meta,
        lines=preview_lines_in,
    )
    quote_detail = create_quote_from_payload(db, payload=quote_payload, current_user=current_user)
    link_referral_to_quote(db, intake_id=intake.id, quote_id=quote_detail.quote.id)

    intake.related_quote_id = quote_detail.quote.id
    intake.resolution_json = {
        **resolution,
        "created_entities": created_entities,
    }
    intake.intake_status = INTAKE_STATUS_PROCESSED
    intake.updated_at = _utcnow()
    db.add(intake)
    db.commit()
    return TypeformDraftQuoteResultOut(
        intake_id=intake.id,
        quote_id=quote_detail.quote.id,
        intake_status=INTAKE_STATUS_PROCESSED,
        warning_message=pending_arbitrage_warning,
    )


@router.delete("/intakes/{intake_id}", status_code=status.HTTP_200_OK)
def delete_typeform_intake(
    intake_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, bool]:
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_id).with_for_update())
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Typeform intake not found")
    if intake.related_quote_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Impossible de supprimer une intake liee a un devis",
        )
    db.delete(intake)
    db.commit()
    return {"ok": True}


@router.post("/demo/seed", response_model=TypeformDemoSeedOut, status_code=status.HTTP_201_CREATED)
def seed_typeform_demo(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TypeformDemoSeedOut:
    before_form_configs = db.scalar(select(func.count(TypeformFormConfig.id))) or 0
    before_intakes = db.scalar(select(func.count(TypeformIntake.id))) or 0

    legal_entity = db.scalar(
        select(LegalEntity)
        .where(LegalEntity.is_active.is_(True))
        .order_by(LegalEntity.name.asc())
        .limit(1)
    )
    quote_type = db.scalar(select(QuoteType).where(QuoteType.is_active.is_(True)).order_by(QuoteType.created_at.asc()).limit(1))
    catalog = db.scalar(select(PricingCatalog).where(PricingCatalog.is_active.is_(True)).order_by(PricingCatalog.created_at.asc()).limit(1))
    payment_plan = db.scalar(select(PaymentPlan).where(PaymentPlan.is_active.is_(True)).order_by(PaymentPlan.created_at.asc()).limit(1))
    if legal_entity is None or quote_type is None or catalog is None or payment_plan is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Core quote configuration incomplete: legal entity, quote type, catalog and payment plan are required",
        )

    location_by_code = {
        row.code: row
        for row in db.scalars(select(Location).where(Location.code.in_(["RICHELIEU", "POMPE", "BAR_LE_DUC"]))).all()
    }
    if {"RICHELIEU", "POMPE", "BAR_LE_DUC"} - set(location_by_code):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Locations RICHELIEU, POMPE and BAR_LE_DUC are required")

    active_records: list[str] = []
    child_activity = _ensure_demo_activity(
        db,
        code="TF_DEMO_CHILD",
        name="Typeform Demo Piano Enfant",
        default_price_ttc=Decimal("48.00"),
        legal_entity=legal_entity,
        duration_minutes=60,
        active_records=active_records,
    )
    eveil_activity = _ensure_demo_activity(
        db,
        code="TF_DEMO_EVEIL",
        name="Typeform Demo Eveil Musical",
        default_price_ttc=Decimal("36.00"),
        legal_entity=legal_entity,
        duration_minutes=45,
        active_records=active_records,
    )
    teen_activity = _ensure_demo_activity(
        db,
        code="TF_DEMO_TEEN",
        name="Typeform Demo Piano Ado",
        default_price_ttc=Decimal("52.00"),
        legal_entity=legal_entity,
        duration_minutes=60,
        active_records=active_records,
    )
    adult_activity = _ensure_demo_activity(
        db,
        code="TF_DEMO_ADULT",
        name="Typeform Demo Piano Adulte",
        default_price_ttc=Decimal("60.00"),
        legal_entity=legal_entity,
        duration_minutes=60,
        active_records=active_records,
    )

    _ensure_demo_pricing(db, catalog=catalog, activity=child_activity, location=location_by_code["RICHELIEU"], unit_price_ttc=Decimal("48.00"), active_records=active_records)
    _ensure_demo_pricing(db, catalog=catalog, activity=eveil_activity, location=location_by_code["POMPE"], unit_price_ttc=Decimal("36.00"), active_records=active_records)
    _ensure_demo_pricing(db, catalog=catalog, activity=teen_activity, location=location_by_code["RICHELIEU"], unit_price_ttc=Decimal("52.00"), active_records=active_records)
    _ensure_demo_pricing(db, catalog=catalog, activity=adult_activity, location=location_by_code["BAR_LE_DUC"], unit_price_ttc=Decimal("44.00"), active_records=active_records)
    _ensure_demo_pricing(db, catalog=catalog, activity=child_activity, location=location_by_code["BAR_LE_DUC"], unit_price_ttc=Decimal("40.00"), active_records=active_records)
    _ensure_demo_pricing(db, catalog=catalog, activity=eveil_activity, location=location_by_code["BAR_LE_DUC"], unit_price_ttc=Decimal("32.00"), active_records=active_records)
    db.commit()

    _ensure_demo_session(db, marker="TYPEFORM_DEMO|PARIS_CHILD_SINGLE", activity=child_activity, location=location_by_code["RICHELIEU"], weekday=1, hour=17, minute=30, capacity_max=6, active_records=active_records)
    _ensure_demo_session(db, marker="TYPEFORM_DEMO|PARIS_EVEIL_WED", activity=eveil_activity, location=location_by_code["POMPE"], weekday=2, hour=10, minute=0, capacity_max=6, active_records=active_records)
    _ensure_demo_session(db, marker="TYPEFORM_DEMO|PARIS_EVEIL_SAT", activity=eveil_activity, location=location_by_code["POMPE"], weekday=5, hour=10, minute=0, capacity_max=6, active_records=active_records)
    _ensure_demo_session(db, marker="TYPEFORM_DEMO|BLD_ADULT", activity=adult_activity, location=location_by_code["BAR_LE_DUC"], weekday=3, hour=19, minute=0, capacity_max=4, active_records=active_records)
    db.commit()

    adult_family = _ensure_demo_client(
        db,
        email="claire.martin.demo@piano-academie.test",
        first_name="Claire",
        last_name="Martin",
        client_kind=ClientKind.ADULT,
        phone="+33600000011",
        birth_date_iso=None,
        active_records=active_records,
    )
    child_family = _ensure_demo_client(
        db,
        email="louis.martin.demo@piano-academie.test",
        first_name="Louis",
        last_name="Martin",
        client_kind=ClientKind.CHILD,
        phone=None,
        birth_date_iso="2014-05-12",
        active_records=active_records,
    )
    _ensure_demo_family_link(db, adult=adult_family, child=child_family, active_records=active_records)
    _ensure_demo_client(
        db,
        email="julien.bernard.demo@piano-academie.test",
        first_name="Julien",
        last_name="Bernard",
        client_kind=ClientKind.ADULT,
        phone="+33600000022",
        birth_date_iso=None,
        active_records=active_records,
    )
    db.commit()

    common_child_mapping = {
        "parent_first_name": ["parent_first_name", "prenom_parent"],
        "parent_last_name": ["parent_last_name", "nom_parent"],
        "parent_email": ["parent_email", "email_parent"],
        "parent_phone": ["parent_phone", "telephone_parent"],
        "child_first_name": ["child_first_name", "prenom_enfant"],
        "child_last_name": ["child_last_name", "nom_enfant"],
        "child_birth_date": ["child_birth_date", "date_naissance_enfant"],
        "requested_days": ["requested_days", "jours_souhaites"],
        "requested_times": ["requested_times", "horaires_souhaites"],
        "requested_formula_type": ["requested_formula_type", "formule_souhaitee"],
        "notes": ["notes", "commentaires"],
    }
    common_child_labels = {
        "parent_first_name": "Prenom parent",
        "parent_last_name": "Nom parent",
        "parent_email": "Email parent",
        "parent_phone": "Telephone parent",
        "child_first_name": "Prenom enfant",
        "child_last_name": "Nom enfant",
        "child_birth_date": "Date de naissance enfant",
        "requested_days": "Jours souhaites",
        "requested_times": "Horaires souhaites",
        "requested_formula_type": "Formule souhaitee",
        "notes": "Commentaires",
        "prenom_parent": "Prenom parent",
        "nom_parent": "Nom parent",
        "email_parent": "Email parent",
        "telephone_parent": "Telephone parent",
        "prenom_enfant": "Prenom enfant",
        "nom_enfant": "Nom enfant",
        "date_naissance_enfant": "Date de naissance enfant",
        "jours_souhaites": "Jours souhaites",
        "horaires_souhaites": "Horaires souhaites",
        "formule_souhaitee": "Formule souhaitee",
        "commentaires": "Commentaires",
    }
    adult_mapping = {
        "adult_first_name": ["adult_first_name"],
        "adult_last_name": ["adult_last_name"],
        "adult_email": ["adult_email"],
        "adult_phone": ["adult_phone"],
        "requested_days": ["requested_days"],
        "requested_times": ["requested_times"],
        "requested_formula_type": ["requested_formula_type"],
        "notes": ["notes"],
    }
    adult_labels = {
        "adult_first_name": "Prenom",
        "adult_last_name": "Nom",
        "adult_email": "Email",
        "adult_phone": "Telephone",
        "requested_days": "Jours souhaites",
        "requested_times": "Horaires souhaites",
        "requested_formula_type": "Formule souhaitee",
        "notes": "Commentaires",
    }

    _ensure_form_config(
        db,
        typeform_form_id="tf_paris_child_2025_richelieu",
        source_code="TYPEFORM_PARIS_CHILD_2025_RICHELIEU",
        location_code="paris_richelieu",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="child",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["RICHELIEU"],
        line_templates=_line_templates_for_activity(child_activity.code),
        field_mapping=common_child_mapping,
        field_labels=common_child_labels,
        label="Paris Richelieu · Enfants · 2025-2026",
        active_records=active_records,
    )
    _ensure_form_config(
        db,
        typeform_form_id="tf_paris_eveil_2025_pompe",
        source_code="TYPEFORM_PARIS_EVEIL_2025_POMPE",
        location_code="paris_pompe",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="eveil",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["POMPE"],
        line_templates=_line_templates_for_activity(eveil_activity.code),
        field_mapping=common_child_mapping,
        field_labels=common_child_labels,
        label="Paris Pompe · Eveil musical · 2025-2026",
        active_records=active_records,
    )
    _ensure_form_config(
        db,
        typeform_form_id="tf_paris_teen_2025_richelieu",
        source_code="TYPEFORM_PARIS_TEEN_2025_RICHELIEU",
        location_code="paris_richelieu",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="teen",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["RICHELIEU"],
        line_templates=_line_templates_for_activity(teen_activity.code),
        field_mapping=common_child_mapping,
        field_labels=common_child_labels,
        label="Paris Richelieu · Ados · 2025-2026",
        active_records=active_records,
    )
    _ensure_form_config(
        db,
        typeform_form_id="tf_paris_adult_2025_pompe",
        source_code="TYPEFORM_PARIS_ADULT_2025_POMPE",
        location_code="paris_pompe",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="adult",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["POMPE"],
        line_templates=_line_templates_for_activity(adult_activity.code),
        field_mapping=adult_mapping,
        field_labels=adult_labels,
        label="Paris Pompe · Adultes · 2025-2026",
        active_records=active_records,
    )
    _ensure_form_config(
        db,
        typeform_form_id="tf_bld_eveil_2025",
        source_code="TYPEFORM_BLD_EVEIL_2025",
        location_code="bar_le_duc",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="eveil",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["BAR_LE_DUC"],
        line_templates=_line_templates_for_activity(eveil_activity.code),
        field_mapping=common_child_mapping,
        field_labels=common_child_labels,
        label="Bar-le-Duc · Eveil musical · 2025-2026",
        active_records=active_records,
    )
    _ensure_form_config(
        db,
        typeform_form_id="tf_bld_child_2025",
        source_code="TYPEFORM_BLD_CHILD_2025",
        location_code="bar_le_duc",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="child",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["BAR_LE_DUC"],
        line_templates=_line_templates_for_activity(child_activity.code),
        field_mapping=common_child_mapping,
        field_labels=common_child_labels,
        label="Bar-le-Duc · Enfants · 2025-2026",
        active_records=active_records,
    )
    _ensure_form_config(
        db,
        typeform_form_id="tf_bld_adult_2025",
        source_code="TYPEFORM_BLD_ADULT_2025",
        location_code="bar_le_duc",
        school_year_label=quote_type.school_year_label or "Année 2025-2026",
        audience_segment="adult",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["BAR_LE_DUC"],
        line_templates=_line_templates_for_activity(adult_activity.code),
        field_mapping=adult_mapping,
        field_labels=adult_labels,
        label="Bar-le-Duc · Adultes · 2025-2026",
        active_records=active_records,
    )
    db.commit()

    demo_payloads = [
        _demo_payload(
            form_id="tf_paris_child_2025_richelieu",
            response_id="demo_paris_child_simple",
            answers=[
                _answer("parent_first_name", "Camille"),
                _answer("parent_last_name", "Durand"),
                _answer("parent_email", "camille.durand.demo@piano-academie.test"),
                _answer("parent_phone", "+33600000001"),
                _answer("child_first_name", "Emma"),
                _answer("child_last_name", "Durand"),
                _answer("child_birth_date", "2016-03-15"),
                _answer("requested_days", ["Mardi"]),
                _answer("requested_times", ["17:30"]),
                _answer("requested_formula_type", "Cours collectif enfant"),
                _answer("notes", "Recherche un cours d essai a Richelieu."),
            ],
        ),
        _demo_payload(
            form_id="tf_paris_eveil_2025_pompe",
            response_id="demo_paris_eveil_multi_slot",
            answers=[
                _answer("prenom_parent", "Sarah"),
                _answer("nom_parent", "Petit"),
                _answer("email_parent", "sarah.petit.demo@piano-academie.test"),
                _answer("telephone_parent", "+33600000002"),
                _answer("prenom_enfant", "Noa"),
                _answer("nom_enfant", "Petit"),
                _answer("date_naissance_enfant", "2020-09-03"),
                _answer("jours_souhaites", ["Mercredi", "Samedi"]),
                _answer("horaires_souhaites", ["10:00"]),
                _answer("formule_souhaitee", "Eveil musical"),
                _answer("commentaires", "Souhaite comparer deux horaires possibles."),
            ],
        ),
        _demo_payload(
            form_id="tf_bld_adult_2025",
            response_id="demo_bld_adult_existing_client",
            answers=[
                _answer("adult_first_name", "Julien"),
                _answer("adult_last_name", "Bernard"),
                _answer("adult_email", "julien.bernard.demo@piano-academie.test"),
                _answer("adult_phone", "+33600000022"),
                _answer("requested_days", ["Jeudi"]),
                _answer("requested_times", ["19:00"]),
                _answer("requested_formula_type", "Cours adulte individuel"),
                _answer("notes", "Ancien client, souhaite reprendre cette annee."),
            ],
        ),
        _demo_payload(
            form_id="tf_paris_teen_2025_richelieu",
            response_id="demo_blocked_no_slot",
            answers=[
                _answer("parent_first_name", "Marc"),
                _answer("parent_last_name", "Robert"),
                _answer("parent_email", "marc.robert.demo@piano-academie.test"),
                _answer("parent_phone", "+33600000004"),
                _answer("child_first_name", "Leo"),
                _answer("child_last_name", "Robert"),
                _answer("child_birth_date", "2011-01-19"),
                _answer("requested_days", ["Lundi"]),
                _answer("requested_times", ["21:00"]),
                _answer("requested_formula_type", "Cours ado"),
                _answer("notes", "Aucun autre jour possible."),
            ],
        ),
    ]

    intake_ids: list[UUID] = []
    for payload in demo_payloads:
        intake = _ingest_typeform_payload(db, payload)
        intake_ids.append(intake.id)

    after_form_configs = db.scalar(select(func.count(TypeformFormConfig.id))) or 0
    after_intakes = db.scalar(select(func.count(TypeformIntake.id))) or 0
    created_form_configs = max(int(after_form_configs - before_form_configs), 0)
    created_intakes = max(int(after_intakes - before_intakes), 0)
    return TypeformDemoSeedOut(
        created_form_configs=created_form_configs,
        created_intakes=created_intakes,
        created_core_records=active_records,
        intake_ids=intake_ids,
    )


@router.post("/webhook", response_model=TypeformWebhookOut, status_code=status.HTTP_201_CREATED)
def ingest_typeform_webhook(
    payload: dict[str, object],
    db: Session = Depends(get_db),
) -> TypeformWebhookOut:
    intake = _ingest_typeform_payload(db, payload)
    return TypeformWebhookOut(
        intake_id=intake.id,
        intake_status=intake.intake_status,
        source_response_id=intake.source_response_id,
    )
