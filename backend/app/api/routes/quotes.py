from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
import re
import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.core.config import settings
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus
from app.models.ops import AppSetting
from app.models.product_catalog import CatalogKit, CatalogProduct
from app.models.quote import (
    PaymentPlan,
    PricingActivityPrice,
    PricingCatalog,
    PricingKitPrice,
    PricingProductPrice,
    Prospect,
    Quote,
    QuoteAcceptanceFollowup,
    QuoteDocumentBinding,
    QuoteDocumentSnapshot,
    QuoteEmailOutbox,
    QuoteEvent,
    QuoteLine,
    QuoteTemplate,
    QuoteTemplateVersion,
    QuoteType,
    SolfegeLevelRule,
    TermsTemplate,
    TermsTemplateVersion,
)
from app.models.user import ClientStatus, User, UserRole
from app.schemas.quote import (
    PaymentPlanOut,
    PaymentPlanUpsertRequest,
    PricingActivityPriceOut,
    PricingActivityPriceUpsertRequest,
    PricingCatalogOut,
    PricingCatalogUpsertRequest,
    PricingKitPriceOut,
    PricingKitPriceUpsertRequest,
    PricingProductPriceOut,
    PricingProductPriceUpsertRequest,
    ProspectCreateRequest,
    ProspectOut,
    ProspectUpdateRequest,
    QuoteCalendarPreviewRequest,
    QuoteChangeRequestIn,
    QuoteCreateRequest,
    QuoteDetailOut,
    QuoteFollowupOut,
    QuoteFollowupPaymentMethodRequest,
    QuoteFollowupSlotRequest,
    QuoteFollowupUpdateRequest,
    QuoteLineIn,
    QuoteLineOut,
    QuoteOut,
    QuotePaymentSchedulePreviewRequest,
    QuotePublicOut,
    QuoteSchoolCalendarOut,
    QuoteSchoolCalendarDeploymentActionOut,
    QuoteSchoolCalendarDeploymentPreviewOut,
    QuoteSchoolCalendarDeploymentSummaryOut,
    QuoteSchoolCalendarGeneratedSlotOut,
    QuoteSchoolCalendarPeriod,
    QuoteSchoolCalendarResolveOut,
    QuoteSchoolCalendarUpsertRequest,
    QuoteSendRequest,
    QuoteTypeOut,
    QuoteTypeUpsertRequest,
    QuoteTemplateV2Out,
    QuoteTemplateV2UpsertRequest,
    QuoteTemplateVersionOut,
    QuoteTemplateVersionPublishRequest,
    QuoteTemplateVariableOut,
    QuoteUpdateRequest,
    QuoteDocumentBindingOut,
    QuoteDocumentBindingUpsertRequest,
    SolfegeLevelRuleOut,
    SolfegeLevelRuleUpsertRequest,
    TermsTemplateOut,
    TermsTemplateUpsertRequest,
    TermsTemplateVersionOut,
    TermsTemplateVersionPublishRequest,
)
from app.services.email_delivery import send_email
from app.services.invoice_documents import normalize_billing_entity
from app.services.quotes.calendar_engine import CalendarGenerationInput, generate_calendar_snapshot
from app.services.quotes.lifecycle_jobs import run_quote_daily_lifecycle_job
from app.services.quotes.payment_plan_engine import PaymentPlanScheduleInput, build_payment_schedule
from app.services.quotes.quote_documents import (
    AUDIENCE_ADMIN_PREVIEW,
    AUDIENCE_CLIENT_PDF,
    AUDIENCE_PUBLIC_PAGE,
    render_quote_document_bundle,
    render_quote_pdf_from_combined_html,
    render_quote_parts_html,
)
from app.services.quotes.template_registry import (
    list_quote_template_variables,
)
from app.services.security import hash_password

router = APIRouter()

QUOTE_FINANCIAL_ADJUSTMENT_META_KEY = "financial_adjustment"
QUOTE_FINANCIAL_ADJUSTMENT_NONE = "none"
QUOTE_FINANCIAL_ADJUSTMENT_CREDIT = "credit"
QUOTE_FINANCIAL_ADJUSTMENT_DEBT = "debt"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _q2(value: Decimal) -> Decimal:
    return Decimal(value or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q3(value: Decimal) -> Decimal:
    return Decimal(value or Decimal("0")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _decimal_or_none(value: object | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _normalize_quote_meta(value: object | None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _normalize_quote_adjustment(meta: dict[str, object] | None) -> dict[str, object]:
    payload = meta.get(QUOTE_FINANCIAL_ADJUSTMENT_META_KEY) if isinstance(meta, dict) else None
    source = payload if isinstance(payload, dict) else {}

    kind = str(source.get("type") or "").strip().lower()
    if kind not in {QUOTE_FINANCIAL_ADJUSTMENT_CREDIT, QUOTE_FINANCIAL_ADJUSTMENT_DEBT}:
        kind = QUOTE_FINANCIAL_ADJUSTMENT_NONE

    raw_amount = source.get("amount_ttc")
    amount = _decimal_or_none(raw_amount)
    if amount is None:
        amount = Decimal("0")
    amount = _q2(abs(amount))
    if amount <= Decimal("0"):
        kind = QUOTE_FINANCIAL_ADJUSTMENT_NONE

    effective_date = str(source.get("effective_date") or "").strip()
    if effective_date:
        try:
            parsed = date.fromisoformat(effective_date)
            effective_date = parsed.isoformat()
        except ValueError:
            effective_date = ""
    label = str(source.get("label") or "").strip()[:200]

    return {
        "type": kind,
        "amount_ttc": str(amount),
        "effective_date": effective_date or None,
        "label": label or None,
    }


def _quote_adjustment_signature(meta: dict[str, object] | None) -> tuple[str, str, str, str]:
    normalized = _normalize_quote_adjustment(meta)
    return (
        str(normalized.get("type") or QUOTE_FINANCIAL_ADJUSTMENT_NONE),
        str(normalized.get("amount_ttc") or "0.00"),
        str(normalized.get("effective_date") or ""),
        str(normalized.get("label") or ""),
    )


def _quote_adjustment_signed_amount(meta: dict[str, object] | None) -> Decimal:
    normalized = _normalize_quote_adjustment(meta)
    amount = _decimal_or_none(normalized.get("amount_ttc")) or Decimal("0")
    if amount <= Decimal("0"):
        return Decimal("0")
    kind = str(normalized.get("type") or QUOTE_FINANCIAL_ADJUSTMENT_NONE).strip().lower()
    if kind == QUOTE_FINANCIAL_ADJUSTMENT_CREDIT:
        return _q2(-abs(amount))
    if kind == QUOTE_FINANCIAL_ADJUSTMENT_DEBT:
        return _q2(abs(amount))
    return Decimal("0")


def _quote_total_with_adjustment(*, lines_total_ttc: Decimal, meta: dict[str, object] | None) -> Decimal:
    adjusted = _q2(lines_total_ttc + _quote_adjustment_signed_amount(meta))
    if adjusted < Decimal("0"):
        return Decimal("0.00")
    return adjusted


def _split_ttc(unit_price_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    normalized_vat = _q3(vat_rate if vat_rate > Decimal("0") else Decimal("0"))
    if normalized_vat <= Decimal("0"):
        return _q2(unit_price_ttc), Decimal("0.00")
    divisor = Decimal("1.00") + (normalized_vat / Decimal("100"))
    unit_ht = _q2(unit_price_ttc / divisor)
    unit_vat = _q2(unit_price_ttc - unit_ht)
    return unit_ht, unit_vat


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _new_quote_number() -> str:
    return f"DV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"


def _quote_type_code_from_name(name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", (name or "").strip().upper()).strip("_")
    if not normalized:
        normalized = "QUOTE_TYPE"
    return normalized[:60]


def _next_available_quote_type_code(db: Session, *, base_code: str, exclude_id: UUID | None = None) -> str:
    root = (base_code or "QUOTE_TYPE").strip().upper() or "QUOTE_TYPE"
    root = root[:60]
    candidate = root
    index = 2
    while True:
        stmt = select(QuoteType.id).where(func.upper(QuoteType.code) == candidate.upper())
        if exclude_id is not None:
            stmt = stmt.where(QuoteType.id != exclude_id)
        existing = db.scalar(stmt.limit(1))
        if existing is None:
            return candidate
        suffix = f"_{index}"
        candidate = f"{root[: max(1, 60 - len(suffix))]}{suffix}"
        index += 1


def _payment_plan_code_from_name(name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", (name or "").strip().upper()).strip("_")
    if not normalized:
        normalized = "PAYMENT_PLAN"
    return normalized[:60]


def _next_available_payment_plan_code(db: Session, *, base_code: str, exclude_id: UUID | None = None) -> str:
    root = (base_code or "PAYMENT_PLAN").strip().upper() or "PAYMENT_PLAN"
    root = root[:60]
    candidate = root
    index = 2
    while True:
        stmt = select(PaymentPlan.id).where(func.upper(PaymentPlan.code) == candidate.upper())
        if exclude_id is not None:
            stmt = stmt.where(PaymentPlan.id != exclude_id)
        existing = db.scalar(stmt.limit(1))
        if existing is None:
            return candidate
        suffix = f"_{index}"
        candidate = f"{root[: max(1, 60 - len(suffix))]}{suffix}"
        index += 1


def _payment_method_label_from_code(method_code: str) -> str:
    normalized = (method_code or "").strip().upper()
    if normalized == "CARD":
        return "Carte bancaire"
    if normalized == "CARD_MONTHLY":
        return "Carte bancaire mensuelle"
    if normalized == "CHECK":
        return "Cheque"
    if normalized in {"CHECK_2", "CHEQUE_2", "CHEQUE_X2"}:
        return "Cheque en 2 fois"
    if normalized in {"CHECK_3", "CHEQUE_3", "CHEQUE_X3"}:
        return "Cheque en 3 fois"
    if normalized in {"CHECK_4", "CHEQUE_4", "CHEQUE_X4"}:
        return "Cheque en 4 fois"
    if normalized == "BANK_TRANSFER":
        return "Virement bancaire"
    if normalized == "CASH":
        return "Especes"
    if normalized == "CARD_4X_FEES":
        return "4 fois avec frais"
    return normalized or "Paiement"


def _bool_or_default(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text_value = str(value).strip().lower()
    if text_value in {"1", "true", "yes", "on", "oui"}:
        return True
    if text_value in {"0", "false", "no", "off", "non"}:
        return False
    return default


def _build_payment_terms_snapshot_from_plan(
    *,
    quote: Quote,
    plan: PaymentPlan,
    total_ttc: Decimal,
    registration_date: date,
) -> dict[str, object]:
    rules = dict(plan.schedule_rules or {})
    normalized_adjustment = _normalize_quote_adjustment(quote.meta or {})
    adjustment_signed = _quote_adjustment_signed_amount(quote.meta or {})
    lines_total_ttc = _q2(total_ttc - adjustment_signed)
    payment_method_label = _payment_method_label_from_code(plan.payment_method)
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code=plan.payment_method,
            schedule_type=plan.schedule_type or "single",
            schedule_rules=rules,
            payment_method_label=payment_method_label,
            total_ttc=total_ttc,
            registration_date=registration_date,
            currency=(quote.currency or "EUR").upper(),
        )
    )
    installment_count = len(schedule)
    visibility_raw = rules.get("schedule_visibility") if isinstance(rules.get("schedule_visibility"), dict) else {}
    show_schedule_to_client_default = installment_count > 1
    schedule_visibility = {
        AUDIENCE_ADMIN_PREVIEW: _bool_or_default((visibility_raw or {}).get(AUDIENCE_ADMIN_PREVIEW), True),
        AUDIENCE_PUBLIC_PAGE: _bool_or_default(
            (visibility_raw or {}).get(AUDIENCE_PUBLIC_PAGE),
            show_schedule_to_client_default,
        ),
        AUDIENCE_CLIENT_PDF: _bool_or_default(
            (visibility_raw or {}).get(AUDIENCE_CLIENT_PDF),
            show_schedule_to_client_default,
        ),
    }
    check_submission_address = str(rules.get("check_submission_address") or "").strip()
    check_submission_instruction = str(rules.get("check_submission_instruction") or "").strip()
    normalized_payment_method = plan.payment_method.strip().upper()
    is_check_family = normalized_payment_method in {
        "CHECK",
        "CHECK_2",
        "CHECK_3",
        "CHECK_4",
        "CHEQUE_2",
        "CHEQUE_3",
        "CHEQUE_4",
        "CHEQUE_X2",
        "CHEQUE_X3",
        "CHEQUE_X4",
    }
    collect_all_checks = _bool_or_default(rules.get("collect_all_checks_upfront"), is_check_family)
    if not check_submission_instruction and collect_all_checks and is_check_family and installment_count > 1:
        check_submission_instruction = "Tous les cheques doivent etre envoyes en meme temps."
    if check_submission_address:
        if check_submission_instruction:
            check_submission_instruction = f"{check_submission_instruction} Adresse d envoi: {check_submission_address}"
        else:
            check_submission_instruction = f"Adresse d envoi des cheques: {check_submission_address}"
    payment_schedule_summary = f"Paiement en {installment_count} fois" if installment_count > 1 else "Paiement en 1 fois"
    return {
        "schedule": schedule,
        "currency": (quote.currency or "EUR").upper(),
        "payment_plan_code": plan.code,
        "payment_plan_name": plan.name,
        "plan_name": plan.name,
        "payment_method": plan.payment_method,
        "payment_method_label": payment_method_label,
        "schedule_type": plan.schedule_type,
        "schedule_rules": rules,
        "payment_schedule_summary": payment_schedule_summary,
        "schedule_visibility": schedule_visibility,
        "check_submission_address": check_submission_address,
        "payment_instruction": check_submission_instruction,
        "lines_total_ttc": str(lines_total_ttc),
        "adjustment": normalized_adjustment,
        "adjustment_signed_amount_ttc": str(_q2(adjustment_signed)),
        "total_ttc_after_adjustment": str(_q2(total_ttc)),
    }


QUOTE_SCHOOL_CALENDARS_SETTING_KEY = "quote_school_calendars_v1"
CALENDAR_DEPLOYMENT_BLOCK_PREFIX = "GEN:QUOTE_CAL_DEPLOY"
CALENDAR_DEPLOYMENT_LEGACY_BLOCK_MARKER = "GEN:QUOTE_SCHOOL_CALENDAR_BLOCK"
CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED = "not_deployed"
CALENDAR_DEPLOYMENT_STATUS_DEPLOYED = "deployed"
CALENDAR_DEPLOYMENT_STATUS_STALE = "stale"
CALENDAR_DEPLOYMENT_STATUS_REMOVED = "removed"
CALENDAR_DEPLOYMENT_REASON_HOLIDAY = "holiday"
CALENDAR_DEPLOYMENT_REASON_VACATION = "vacation"
CALENDAR_DEPLOYMENT_REASON_CLOSURE = "closure"


def _parse_iso_date(raw: str) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _deployment_private_description(
    *,
    calendar_id: UUID,
    day: date,
    reason_types: set[str],
    source_hash: str,
) -> str:
    normalized_types = ",".join(sorted(reason_types))
    return (
        f"{CALENDAR_DEPLOYMENT_BLOCK_PREFIX}"
        f"|calendar={calendar_id}"
        f"|day={day.isoformat()}"
        f"|types={normalized_types}"
        f"|hash={source_hash}"
    )


def _parse_calendar_deployment_private_description(value: str | None) -> tuple[UUID | None, date | None, set[str]]:
    raw = str(value or "").strip()
    if not raw.startswith(CALENDAR_DEPLOYMENT_BLOCK_PREFIX):
        return (None, None, set())
    segments = raw.split("|")
    calendar_value = ""
    day_value = ""
    type_value = ""
    for segment in segments[1:]:
        if "=" not in segment:
            continue
        key, val = segment.split("=", 1)
        key = key.strip().lower()
        val = val.strip()
        if key == "calendar":
            calendar_value = val
        elif key == "day":
            day_value = val
        elif key == "types":
            type_value = val
    calendar_id: UUID | None = None
    day: date | None = None
    try:
        calendar_id = UUID(calendar_value) if calendar_value else None
    except Exception:
        calendar_id = None
    try:
        day = date.fromisoformat(day_value) if day_value else None
    except Exception:
        day = None
    reason_types = {
        token.strip().lower()
        for token in type_value.split(",")
        if token.strip().lower() in {
            CALENDAR_DEPLOYMENT_REASON_HOLIDAY,
            CALENDAR_DEPLOYMENT_REASON_VACATION,
            CALENDAR_DEPLOYMENT_REASON_CLOSURE,
        }
    }
    return (calendar_id, day, reason_types)


def _calendar_day_reason_map(
    *,
    periods: list[QuoteSchoolCalendarPeriod],
    holiday_days: list[date],
    closure_days: list[date],
) -> dict[date, set[str]]:
    day_reasons: dict[date, set[str]] = {}
    for day in holiday_days:
        day_reasons.setdefault(day, set()).add(CALENDAR_DEPLOYMENT_REASON_HOLIDAY)
    for day in closure_days:
        day_reasons.setdefault(day, set()).add(CALENDAR_DEPLOYMENT_REASON_CLOSURE)
    for day in _expand_vacation_periods(periods):
        day_reasons.setdefault(day, set()).add(CALENDAR_DEPLOYMENT_REASON_VACATION)
    return day_reasons


def _calendar_source_hash(
    *,
    name: str,
    school_year_label: str,
    location_id: UUID,
    periods: list[QuoteSchoolCalendarPeriod],
    holiday_days: list[date],
    closure_days: list[date],
    is_active: bool,
) -> str:
    payload = {
        "name": (name or "").strip(),
        "school_year_label": (school_year_label or "").strip(),
        "location_id": str(location_id),
        "is_active": bool(is_active),
        "vacation_periods": [
            {
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "label": (period.label or "").strip() or None,
            }
            for period in periods
        ],
        "holiday_dates": sorted({item.isoformat() for item in holiday_days}),
        "closure_dates": sorted({item.isoformat() for item in closure_days}),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _calendar_generated_slot_like_pattern(calendar_id: UUID) -> str:
    return f"{CALENDAR_DEPLOYMENT_BLOCK_PREFIX}|calendar={calendar_id}|%"


def _school_year_bounds_from_label(label: str) -> tuple[date, date] | None:
    normalized = (label or "").strip()
    match = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{4})", normalized)
    if match is None:
        return None
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year < start_year:
        return None
    return (date(start_year, 9, 1), date(end_year, 8, 31))


def _calendar_block_title_from_reason_types(reason_types: set[str]) -> str:
    normalized = {item.strip().lower() for item in reason_types}
    if normalized == {CALENDAR_DEPLOYMENT_REASON_HOLIDAY}:
        return "Jour férié"
    if normalized == {CALENDAR_DEPLOYMENT_REASON_VACATION}:
        return "Vacances scolaires"
    if normalized == {CALENDAR_DEPLOYMENT_REASON_CLOSURE}:
        return "Fermeture exceptionnelle"
    labels: list[str] = []
    if CALENDAR_DEPLOYMENT_REASON_VACATION in normalized:
        labels.append("Vacances scolaires")
    if CALENDAR_DEPLOYMENT_REASON_HOLIDAY in normalized:
        labels.append("Jour férié")
    if CALENDAR_DEPLOYMENT_REASON_CLOSURE in normalized:
        labels.append("Fermeture exceptionnelle")
    if not labels:
        return "Fermeture calendrier"
    return " / ".join(labels)


def _calendar_periods_out(periods: object) -> list[QuoteSchoolCalendarPeriod]:
    if not isinstance(periods, list):
        return []
    out: list[QuoteSchoolCalendarPeriod] = []
    for item in periods:
        if not isinstance(item, dict):
            continue
        start = _parse_iso_date(str(item.get("start_date") or ""))
        end = _parse_iso_date(str(item.get("end_date") or ""))
        if start is None or end is None or end < start:
            continue
        label_raw = str(item.get("label") or "").strip()
        out.append(
            QuoteSchoolCalendarPeriod(
                start_date=start,
                end_date=end,
                label=label_raw[:120] if label_raw else None,
            )
        )
    return out


def _calendar_dates_out(raw: object) -> list[date]:
    if not isinstance(raw, list):
        return []
    out: set[date] = set()
    for entry in raw:
        parsed = _parse_iso_date(str(entry or ""))
        if parsed is not None:
            out.add(parsed)
    return sorted(out)


def _expand_vacation_periods(periods: list[QuoteSchoolCalendarPeriod]) -> list[date]:
    out: set[date] = set()
    for period in periods:
        current = period.start_date
        while current <= period.end_date:
            out.add(current)
            current += timedelta(days=1)
    return sorted(out)


def _load_quote_school_calendars(db: Session) -> list[dict[str, object]]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
    if setting is None:
        return []
    try:
        parsed = json.loads(setting.value or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _save_quote_school_calendars(db: Session, items: list[dict[str, object]]) -> None:
    now = _utcnow()
    serialized = json.dumps(items, ensure_ascii=False)
    setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY).with_for_update())
    if setting is None:
        setting = AppSetting(key=QUOTE_SCHOOL_CALENDARS_SETTING_KEY, value=serialized, updated_at=now)
    else:
        setting.value = serialized
        setting.updated_at = now
    db.add(setting)


def _calendar_out(row: dict[str, object]) -> QuoteSchoolCalendarOut:
    location_id = UUID(str(row.get("location_id")))
    periods = _calendar_periods_out(row.get("vacation_periods"))
    holiday_dates = _calendar_dates_out(row.get("holiday_dates"))
    closure_dates = _calendar_dates_out(row.get("closure_dates"))
    source_hash = _calendar_source_hash(
        name=str(row.get("name") or ""),
        school_year_label=str(row.get("school_year_label") or ""),
        location_id=location_id,
        periods=periods,
        holiday_days=holiday_dates,
        closure_days=closure_dates,
        is_active=bool(row.get("is_active", True)),
    )
    stored_status = str(row.get("deployment_status") or CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED).strip().lower()
    if stored_status not in {
        CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED,
        CALENDAR_DEPLOYMENT_STATUS_DEPLOYED,
        CALENDAR_DEPLOYMENT_STATUS_STALE,
        CALENDAR_DEPLOYMENT_STATUS_REMOVED,
    }:
        stored_status = CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED
    deployment_source_hash = str(row.get("deployment_source_hash") or "").strip() or None
    if stored_status == CALENDAR_DEPLOYMENT_STATUS_DEPLOYED and deployment_source_hash and deployment_source_hash != source_hash:
        deployment_status = CALENDAR_DEPLOYMENT_STATUS_STALE
    else:
        deployment_status = stored_status
    return QuoteSchoolCalendarOut(
        id=UUID(str(row.get("id"))),
        name=str(row.get("name") or "").strip() or "Calendrier",
        school_year_label=str(row.get("school_year_label") or "").strip() or "N/A",
        location_id=location_id,
        vacation_periods=periods,
        holiday_dates=holiday_dates,
        closure_dates=closure_dates,
        is_active=bool(row.get("is_active", True)),
        deployment_status=deployment_status,
        deployment_last_at=_parse_iso_datetime(str(row.get("deployment_last_at") or "").strip()) if row.get("deployment_last_at") else None,
        deployment_last_sync_at=_parse_iso_datetime(str(row.get("deployment_last_sync_at") or "").strip()) if row.get("deployment_last_sync_at") else None,
        deployment_source_hash=deployment_source_hash,
        deployment_generated_count=max(0, int(row.get("deployment_generated_count") or 0)),
        deployment_generated_active_count=max(0, int(row.get("deployment_generated_active_count") or 0)),
        created_at=_parse_iso_datetime(str(row.get("created_at") or _utcnow().isoformat())),
        updated_at=_parse_iso_datetime(str(row.get("updated_at") or _utcnow().isoformat())),
    )


def _calendar_record_from_payload(
    payload: QuoteSchoolCalendarUpsertRequest,
    *,
    row_id: UUID,
    created_at: datetime | None,
    location_id: UUID,
) -> dict[str, object]:
    now = _utcnow()
    periods = [
        QuoteSchoolCalendarPeriod(
            start_date=period.start_date,
            end_date=period.end_date,
            label=period.label or None,
        )
        for period in payload.vacation_periods
        if period.end_date >= period.start_date
    ]
    holidays = sorted({item for item in payload.holiday_dates})
    closures = sorted({item for item in payload.closure_dates})
    source_hash = _calendar_source_hash(
        name=payload.name.strip(),
        school_year_label=payload.school_year_label.strip(),
        location_id=location_id,
        periods=periods,
        holiday_days=holidays,
        closure_days=closures,
        is_active=bool(payload.is_active),
    )
    return {
        "id": str(row_id),
        "name": payload.name.strip(),
        "school_year_label": payload.school_year_label.strip(),
        "location_id": str(location_id),
        "vacation_periods": [
            {
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "label": period.label or None,
            }
            for period in periods
        ],
        "holiday_dates": sorted({item.isoformat() for item in holidays}),
        "closure_dates": sorted({item.isoformat() for item in closures}),
        "is_active": bool(payload.is_active),
        "source_hash": source_hash,
        "deployment_status": CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED,
        "deployment_last_at": None,
        "deployment_last_sync_at": None,
        "deployment_source_hash": None,
        "deployment_generated_count": 0,
        "deployment_generated_active_count": 0,
        "created_at": (created_at or now).isoformat(),
        "updated_at": now.isoformat(),
    }


def _calendar_location_ids_from_payload(payload: QuoteSchoolCalendarUpsertRequest) -> list[UUID]:
    out: list[UUID] = []
    seen: set[UUID] = set()
    if payload.location_id is not None and payload.location_id not in seen:
        seen.add(payload.location_id)
        out.append(payload.location_id)
    for location_id in payload.location_ids:
        if location_id in seen:
            continue
        seen.add(location_id)
        out.append(location_id)
    return out


def _validate_calendar_locations_exist(db: Session, location_ids: list[UUID]) -> None:
    if not location_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Location not found")
    existing_ids = {
        row_id
        for row_id in db.scalars(
            select(Location.id).where(Location.id.in_(location_ids))
        ).all()
    }
    missing = [location_id for location_id in location_ids if location_id not in existing_ids]
    if missing:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Location not found")


def _calendar_source_hash_for_row(row: dict[str, object]) -> str:
    location_id = UUID(str(row.get("location_id")))
    periods = _calendar_periods_out(row.get("vacation_periods"))
    holidays = _calendar_dates_out(row.get("holiday_dates"))
    closures = _calendar_dates_out(row.get("closure_dates"))
    return _calendar_source_hash(
        name=str(row.get("name") or ""),
        school_year_label=str(row.get("school_year_label") or ""),
        location_id=location_id,
        periods=periods,
        holiday_days=holidays,
        closure_days=closures,
        is_active=bool(row.get("is_active", True)),
    )


def _calendar_preview_for_row(db: Session, *, row: dict[str, object]) -> QuoteSchoolCalendarDeploymentPreviewOut:
    calendar = _calendar_out(row)
    day_reasons = _calendar_day_reason_map(
        periods=calendar.vacation_periods,
        holiday_days=calendar.holiday_dates,
        closure_days=calendar.closure_dates,
    )
    target_days = sorted(day_reasons.keys())
    source_hash = _calendar_source_hash_for_row(row)
    existing = db.scalars(
        select(CourseSession)
        .where(
            CourseSession.location_id == calendar.location_id,
            CourseSession.private_description.like(_calendar_generated_slot_like_pattern(calendar.id)),
        )
    ).all()
    existing_by_day: dict[date, list[CourseSession]] = {}
    active_existing = 0
    for session in existing:
        parsed_calendar_id, parsed_day, _ = _parse_calendar_deployment_private_description(session.private_description)
        if parsed_calendar_id != calendar.id or parsed_day is None:
            continue
        existing_by_day.setdefault(parsed_day, []).append(session)
        if session.status != SessionStatus.CANCELLED:
            active_existing += 1

    would_create = 0
    would_keep = 0
    would_reactivate = 0
    for day in target_days:
        day_sessions = existing_by_day.get(day, [])
        if not day_sessions:
            would_create += 1
            continue
        has_active = any(session.status != SessionStatus.CANCELLED for session in day_sessions)
        if has_active:
            would_keep += 1
        else:
            would_reactivate += 1
    would_cancel = sum(
        1
        for day, sessions in existing_by_day.items()
        if day not in day_reasons and any(session.status != SessionStatus.CANCELLED for session in sessions)
    )

    vacation_days = {
        day
        for day, types in day_reasons.items()
        if CALENDAR_DEPLOYMENT_REASON_VACATION in types
    }
    holiday_days = {
        day
        for day, types in day_reasons.items()
        if CALENDAR_DEPLOYMENT_REASON_HOLIDAY in types
    }
    closure_days = {
        day
        for day, types in day_reasons.items()
        if CALENDAR_DEPLOYMENT_REASON_CLOSURE in types
    }

    return QuoteSchoolCalendarDeploymentPreviewOut(
        calendar_id=calendar.id,
        location_id=calendar.location_id,
        deployment_status=calendar.deployment_status,
        source_hash=source_hash,
        existing_generated_active_count=active_existing,
        summary=QuoteSchoolCalendarDeploymentSummaryOut(
            total_target_days=len(target_days),
            vacation_days=len(vacation_days),
            holiday_days=len(holiday_days),
            closure_days=len(closure_days),
        ),
        would_create=would_create,
        would_keep=would_keep,
        would_reactivate=would_reactivate,
        would_cancel=would_cancel,
        sample_dates=target_days[:12],
    )


def _sync_deployed_status_after_payload_change(
    *,
    old_row: dict[str, object],
    new_row: dict[str, object],
) -> None:
    new_source_hash = str(new_row.get("source_hash") or "").strip() or _calendar_source_hash_for_row(new_row)
    old_deployment_source_hash = str(old_row.get("deployment_source_hash") or "").strip()
    old_status = str(old_row.get("deployment_status") or CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED).strip().lower()
    if old_status not in {
        CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED,
        CALENDAR_DEPLOYMENT_STATUS_DEPLOYED,
        CALENDAR_DEPLOYMENT_STATUS_STALE,
        CALENDAR_DEPLOYMENT_STATUS_REMOVED,
    }:
        old_status = CALENDAR_DEPLOYMENT_STATUS_NOT_DEPLOYED
    if old_status == CALENDAR_DEPLOYMENT_STATUS_DEPLOYED and old_deployment_source_hash and old_deployment_source_hash != new_source_hash:
        new_status = CALENDAR_DEPLOYMENT_STATUS_STALE
    else:
        new_status = old_status
    new_row["deployment_status"] = new_status
    new_row["deployment_last_at"] = old_row.get("deployment_last_at")
    new_row["deployment_last_sync_at"] = old_row.get("deployment_last_sync_at")
    new_row["deployment_source_hash"] = old_row.get("deployment_source_hash")
    new_row["deployment_generated_count"] = int(old_row.get("deployment_generated_count") or 0)
    new_row["deployment_generated_active_count"] = int(old_row.get("deployment_generated_active_count") or 0)
    new_row["source_hash"] = new_source_hash


def _deploy_calendar_row(
    db: Session,
    *,
    row: dict[str, object],
    actor: User | None,
) -> QuoteSchoolCalendarDeploymentActionOut:
    calendar = _calendar_out(row)
    day_reasons = _calendar_day_reason_map(
        periods=calendar.vacation_periods,
        holiday_days=calendar.holiday_dates,
        closure_days=calendar.closure_dates,
    )
    source_hash = _calendar_source_hash_for_row(row)

    vacation_type = db.scalar(select(CourseType).where(CourseType.code == "VACATION_DAY"))
    if vacation_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Activite VACATION_DAY introuvable pour deployer le calendrier",
        )
    location = db.scalar(select(Location).where(Location.id == calendar.location_id))
    if location is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Location not found")

    existing_rows = db.scalars(
        select(CourseSession)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.location_id == calendar.location_id,
            CourseType.code == "VACATION_DAY",
            or_(
                CourseSession.private_description.like(_calendar_generated_slot_like_pattern(calendar.id)),
                CourseSession.private_description == CALENDAR_DEPLOYMENT_LEGACY_BLOCK_MARKER,
            ),
        )
        .with_for_update()
    ).all()
    existing_by_day: dict[date, list[CourseSession]] = {}
    for session in existing_rows:
        parsed_calendar_id, parsed_day, _ = _parse_calendar_deployment_private_description(session.private_description)
        is_legacy = (session.private_description or "").strip() == CALENDAR_DEPLOYMENT_LEGACY_BLOCK_MARKER
        if parsed_day is None and is_legacy:
            parsed_day = session.start_at_utc.date()
        if parsed_day is None:
            continue
        if not is_legacy and parsed_calendar_id != calendar.id:
            continue
        existing_by_day.setdefault(parsed_day, []).append(session)

    now = _utcnow()
    created_count = 0
    updated_count = 0
    reactivated_count = 0
    removed_count = 0

    for day, reason_types in sorted(day_reasons.items(), key=lambda item: item[0]):
        start_at_utc = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end_at_utc = start_at_utc + timedelta(days=1)
        block_title = _calendar_block_title_from_reason_types(reason_types)
        marker = _deployment_private_description(
            calendar_id=calendar.id,
            day=day,
            reason_types=reason_types,
            source_hash=source_hash,
        )
        display_reasons = ", ".join(
            {
                CALENDAR_DEPLOYMENT_REASON_HOLIDAY: "jour ferie",
                CALENDAR_DEPLOYMENT_REASON_VACATION: "vacances",
                CALENDAR_DEPLOYMENT_REASON_CLOSURE: "fermeture",
            }[item]
            for item in sorted(reason_types)
        )
        description = f"Blocage automatique calendrier scolaire ({display_reasons})"
        day_sessions = existing_by_day.get(day, [])
        target = next((session for session in day_sessions if session.status != SessionStatus.CANCELLED), None)
        if target is None and day_sessions:
            target = day_sessions[0]
        if target is None:
            db.add(
                CourseSession(
                    course_type_id=vacation_type.id,
                    billing_entity_snapshot=normalize_billing_entity(vacation_type.billing_entity_code),
                    snapshot_seller_legal_entity_id=vacation_type.seller_legal_entity_id,
                    snapshot_payor_legal_entity_id=vacation_type.payor_legal_entity_id,
                    location_id=calendar.location_id,
                    professor_id=None,
                    title=block_title,
                    description=description,
                    private_description=marker,
                    start_at_utc=start_at_utc,
                    end_at_utc=end_at_utc,
                    is_all_day=True,
                    capacity_max=0,
                    status=SessionStatus.SCHEDULED,
                    auto_cancel_deadline_utc=start_at_utc,
                    cancel_reason=None,
                    zoom_link=None,
                    is_private=True,
                    allow_online_booking=False,
                    timezone=location.timezone,
                    recurrence_group_id=None,
                    recurrence_rule=None,
                    updated_at=now,
                )
            )
            created_count += 1
            continue
        was_cancelled = target.status == SessionStatus.CANCELLED
        target.start_at_utc = start_at_utc
        target.end_at_utc = end_at_utc
        target.title = block_title
        target.description = description
        target.private_description = marker
        target.is_all_day = True
        target.capacity_max = 0
        target.auto_cancel_deadline_utc = start_at_utc
        target.status = SessionStatus.SCHEDULED
        target.cancel_reason = None
        target.is_private = True
        target.allow_online_booking = False
        target.timezone = location.timezone
        target.updated_at = now
        if was_cancelled:
            reactivated_count += 1
        else:
            updated_count += 1
        for extra in day_sessions:
            if extra.id == target.id:
                continue
            db.delete(extra)
            removed_count += 1

    for day, sessions in existing_by_day.items():
        if day in day_reasons:
            continue
        for session in sessions:
            db.delete(session)
            removed_count += 1

    active_generated_count = db.scalar(
        select(func.count(CourseSession.id))
        .where(
            CourseSession.location_id == calendar.location_id,
            CourseSession.private_description.like(_calendar_generated_slot_like_pattern(calendar.id)),
            CourseSession.status != SessionStatus.CANCELLED,
        )
    ) or 0
    row["deployment_status"] = CALENDAR_DEPLOYMENT_STATUS_DEPLOYED
    row["deployment_last_at"] = now.isoformat()
    row["deployment_last_sync_at"] = now.isoformat()
    row["deployment_source_hash"] = source_hash
    row["deployment_generated_count"] = len(day_reasons)
    row["deployment_generated_active_count"] = int(active_generated_count)
    row["source_hash"] = source_hash
    row["deployment_last_by"] = str(actor.id) if actor is not None else None

    return QuoteSchoolCalendarDeploymentActionOut(
        calendar_id=calendar.id,
        deployment_status=CALENDAR_DEPLOYMENT_STATUS_DEPLOYED,
        source_hash=source_hash,
        created_count=created_count,
        updated_count=updated_count,
        reactivated_count=reactivated_count,
        cancelled_count=removed_count,
        deleted_count=removed_count,
        active_generated_count=int(active_generated_count),
        message=(
            f"Deploiement termine ({int(active_generated_count)} creneaux actifs, "
            f"{created_count} crees, {reactivated_count} reactives, {removed_count} supprimes)"
        ),
    )


def _remove_calendar_deployment(
    db: Session,
    *,
    row: dict[str, object],
) -> QuoteSchoolCalendarDeploymentActionOut:
    calendar = _calendar_out(row)
    now = _utcnow()
    deployment_any_pattern = f"{CALENDAR_DEPLOYMENT_BLOCK_PREFIX}|calendar=%"
    query = (
        select(CourseSession)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.location_id == calendar.location_id,
            CourseType.code == "VACATION_DAY",
            or_(
                CourseSession.private_description.like(_calendar_generated_slot_like_pattern(calendar.id)),
                CourseSession.private_description == CALENDAR_DEPLOYMENT_LEGACY_BLOCK_MARKER,
                CourseSession.private_description.like(deployment_any_pattern),
            ),
        )
        .with_for_update()
    )
    bounds = _school_year_bounds_from_label(calendar.school_year_label)
    if bounds is not None:
        school_year_start, school_year_end = bounds
        start_dt = datetime.combine(school_year_start, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(school_year_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        query = query.where(
            CourseSession.start_at_utc >= start_dt,
            CourseSession.start_at_utc < end_dt,
        )
    to_delete = db.scalars(query).all()
    removed_count = 0
    for session in to_delete:
        db.delete(session)
        removed_count += 1
    row["deployment_status"] = CALENDAR_DEPLOYMENT_STATUS_REMOVED
    row["deployment_last_sync_at"] = now.isoformat()
    row["deployment_generated_count"] = 0
    row["deployment_generated_active_count"] = 0
    return QuoteSchoolCalendarDeploymentActionOut(
        calendar_id=calendar.id,
        deployment_status=CALENDAR_DEPLOYMENT_STATUS_REMOVED,
        source_hash=str(row.get("deployment_source_hash") or "").strip() or None,
        cancelled_count=removed_count,
        deleted_count=removed_count,
        active_generated_count=0,
        message=f"Deploiement retire ({removed_count} creneaux supprimes)",
    )


def _list_calendar_generated_slots(
    db: Session,
    *,
    calendar_id: UUID,
    location_id: UUID,
) -> list[QuoteSchoolCalendarGeneratedSlotOut]:
    rows = db.scalars(
        select(CourseSession)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.location_id == location_id,
            CourseType.code == "VACATION_DAY",
            or_(
                CourseSession.private_description.like(_calendar_generated_slot_like_pattern(calendar_id)),
                CourseSession.private_description == CALENDAR_DEPLOYMENT_LEGACY_BLOCK_MARKER,
            ),
        )
        .order_by(CourseSession.start_at_utc.asc())
    ).all()
    out: list[QuoteSchoolCalendarGeneratedSlotOut] = []
    for row in rows:
        parsed_calendar_id, parsed_day, reason_types = _parse_calendar_deployment_private_description(row.private_description)
        is_legacy = (row.private_description or "").strip() == CALENDAR_DEPLOYMENT_LEGACY_BLOCK_MARKER
        if not is_legacy and parsed_calendar_id != calendar_id:
            continue
        if parsed_day is None:
            parsed_day = row.start_at_utc.date()
        if not reason_types and is_legacy:
            reason_types = {CALENDAR_DEPLOYMENT_REASON_VACATION}
        out.append(
            QuoteSchoolCalendarGeneratedSlotOut(
                session_id=row.id,
                location_id=row.location_id,
                date=parsed_day,
                reason_types=sorted(reason_types),
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
                title=row.title,
                start_at=row.start_at_utc,
                end_at=row.end_at_utc,
            )
        )
    return out


def _apply_school_calendar_to_management_planning(
    db: Session,
    *,
    payload: QuoteSchoolCalendarUpsertRequest,
    location_ids: list[UUID],
) -> tuple[int, int]:
    rows = _load_quote_school_calendars(db)
    created = 0
    touched = 0
    changed = False
    for location_id in location_ids:
        row = next(
            (
                item
                for item in rows
                if str(item.get("location_id") or "") == str(location_id)
                and str(item.get("name") or "").strip().lower() == payload.name.strip().lower()
                and str(item.get("school_year_label") or "").strip().lower() == payload.school_year_label.strip().lower()
            ),
            None,
        )
        if row is None:
            continue
        action = _deploy_calendar_row(db, row=row, actor=None)
        changed = True
        created += action.created_count
        touched += action.created_count + action.updated_count + action.reactivated_count
    if changed:
        _save_quote_school_calendars(db, rows)
    return (created, touched)


def _time_from_hhmm(value: str, *, field: str) -> time:
    raw = (value or "").strip()
    try:
        hour_s, minute_s = raw.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
        return time(hour=hour, minute=minute)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field} must be HH:MM") from exc


def _prospect_out(row: Prospect) -> ProspectOut:
    return ProspectOut(
        id=row.id,
        linked_client_id=row.linked_client_id,
        parent_prospect_id=row.parent_prospect_id,
        status=row.status,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone=row.phone,
        source=row.source,
        notes=row.notes,
        meta=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _line_out(row: QuoteLine) -> QuoteLineOut:
    return QuoteLineOut(
        id=row.id,
        quote_id=row.quote_id,
        line_category=row.line_category,
        line_type=row.line_type,
        master_item_type=row.master_item_type,
        master_item_id=row.master_item_id,
        activity_id=row.activity_id,
        product_id=row.product_id,
        kit_id=row.kit_id,
        code=row.code,
        title=row.title,
        description=row.description,
        duration_minutes=row.duration_minutes,
        pricing_unit=row.pricing_unit,
        quantity=_q2(Decimal(row.quantity or 0)),
        vat_rate=_q3(Decimal(row.vat_rate or 0)),
        unit_price_ht=_q2(Decimal(row.unit_price_ht or 0)),
        unit_vat_amount=_q2(Decimal(row.unit_vat_amount or 0)),
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        amount_ht=_q2(Decimal(row.amount_ht or 0)),
        amount_vat=_q2(Decimal(row.amount_vat or 0)),
        amount_ttc=_q2(Decimal(row.amount_ttc or 0)),
        sort_order=int(row.sort_order or 0),
        meta=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _quote_out(row: Quote) -> QuoteOut:
    meta = row.meta or {}
    fallback_language = str(meta.get("language") or "").strip().lower() or None
    fallback_vat = _extract_vat_rate(meta)
    return QuoteOut(
        id=row.id,
        quote_number=row.quote_number,
        context_type=row.context_type,
        quote_type=row.quote_type,
        quote_type_id=row.quote_type_id,
        pricing_catalog_id=row.pricing_catalog_id,
        prospect_id=row.prospect_id,
        client_id=row.client_id,
        location_id=row.location_id,
        payment_plan_id=row.payment_plan_id,
        quote_template_id=row.quote_template_id,
        quote_template_version_id=row.quote_template_version_id,
        terms_template_id=row.terms_template_id,
        terms_template_version_id=row.terms_template_version_id,
        status=row.status,
        public_token=row.public_token,
        pdf_token=row.pdf_token,
        version_number=int(row.version_number or 1),
        parent_quote_id=row.parent_quote_id,
        currency=row.currency,
        total_ttc=_q2(Decimal(row.total_ttc or 0)),
        expiry_days=int(row.expiry_days or 10),
        expires_at=row.expires_at,
        sent_at=row.sent_at,
        approved_at=row.approved_at,
        rejected_at=row.rejected_at,
        expired_at=row.expired_at,
        cancelled_at=row.cancelled_at,
        school_year_label=row.school_year_label,
        language=row.language or fallback_language,
        vat_rate=_q2(Decimal(row.vat_rate or 0)) if row.vat_rate is not None else fallback_vat,
        estimated_solfege_level=row.estimated_solfege_level,
        solfege_duration_minutes=row.solfege_duration_minutes,
        selected_solfege_slot=row.selected_solfege_slot or {},
        calendar_snapshot=row.calendar_snapshot or {},
        payment_terms_snapshot=row.payment_terms_snapshot or {},
        cgv_snapshot=row.cgv_snapshot or {},
        price_snapshot=row.price_snapshot or {},
        meta=meta,
        document_status=row.document_status,
        document_snapshot_id=row.document_snapshot_id,
        document_hash=row.document_hash,
        document_generated_at=row.document_generated_at,
        reminder_sent_at=row.reminder_sent_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _payment_plan_out(row: PaymentPlan) -> PaymentPlanOut:
    return PaymentPlanOut(
        id=row.id,
        code=row.code,
        name=row.name,
        payment_method=row.payment_method,
        schedule_type=row.schedule_type,
        schedule_rules=row.schedule_rules or {},
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _quote_type_out(row: QuoteType) -> QuoteTypeOut:
    return QuoteTypeOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        default_expiry_days=int(row.default_expiry_days or 10),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_catalog_out(row: PricingCatalog) -> PricingCatalogOut:
    return PricingCatalogOut(
        id=row.id,
        name=row.name,
        school_year_label=row.school_year_label,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        is_default=bool(row.is_default),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_activity_price_out(row: PricingActivityPrice) -> PricingActivityPriceOut:
    return PricingActivityPriceOut(
        id=row.id,
        catalog_id=row.catalog_id,
        activity_id=row.activity_id,
        location_id=row.location_id,
        student_category=row.student_category,
        pricing_unit=row.pricing_unit,
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        currency=row.currency,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_product_price_out(row: PricingProductPrice) -> PricingProductPriceOut:
    return PricingProductPriceOut(
        id=row.id,
        catalog_id=row.catalog_id,
        product_id=row.product_id,
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        currency=row.currency,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_kit_price_out(row: PricingKitPrice) -> PricingKitPriceOut:
    return PricingKitPriceOut(
        id=row.id,
        catalog_id=row.catalog_id,
        kit_id=row.kit_id,
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        currency=row.currency,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _solfege_rule_out(row: SolfegeLevelRule) -> SolfegeLevelRuleOut:
    return SolfegeLevelRuleOut(
        id=row.id,
        level_code=row.level_code,
        duration_minutes=int(row.duration_minutes),
        allowed_weekdays=[int(v) for v in (row.allowed_weekdays or [])],
        allowed_time_slots=list(row.allowed_time_slots or []),
        location_id=row.location_id,
        modality=row.modality,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _followup_out(row: QuoteAcceptanceFollowup) -> QuoteFollowupOut:
    return QuoteFollowupOut(
        id=row.id,
        quote_id=row.quote_id,
        target_client_id=row.target_client_id,
        status=row.status,
        payment_method_status=row.payment_method_status,
        solfege_slot_status=row.solfege_slot_status,
        payload=row.payload or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_iso_datetime(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed = _utcnow()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalized_prospect_type(meta: dict[str, object] | None) -> str:
    value = str((meta or {}).get("prospect_type") or "").strip().lower()
    return "child" if value == "child" else "adult"


def _ensure_parent_prospect(db: Session, parent_prospect_id: UUID, *, current_prospect_id: UUID | None = None) -> Prospect:
    if current_prospect_id is not None and parent_prospect_id == current_prospect_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Parent prospect cannot be self")
    parent = db.scalar(select(Prospect).where(Prospect.id == parent_prospect_id))
    if parent is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Parent prospect not found")
    if _normalized_prospect_type(parent.meta or {}) == "child":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Parent prospect must be adult")
    return parent


def _active_quote_template_version(db: Session, template_id: UUID, *, lock: bool = False) -> QuoteTemplateVersion | None:
    stmt = (
        select(QuoteTemplateVersion)
        .where(QuoteTemplateVersion.quote_template_id == template_id)
        .order_by(QuoteTemplateVersion.is_active_version.desc(), QuoteTemplateVersion.version_number.desc())
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _active_terms_template_version(db: Session, template_id: UUID, *, lock: bool = False) -> TermsTemplateVersion | None:
    stmt = (
        select(TermsTemplateVersion)
        .where(TermsTemplateVersion.terms_template_id == template_id)
        .order_by(TermsTemplateVersion.is_active_version.desc(), TermsTemplateVersion.version_number.desc())
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _quote_template_version_out(row: QuoteTemplateVersion) -> QuoteTemplateVersionOut:
    return QuoteTemplateVersionOut(
        id=row.id,
        quote_template_id=row.quote_template_id,
        version_number=int(row.version_number),
        content_snapshot=row.content_snapshot or {},
        is_active_version=bool(row.is_active_version),
        published_at=row.published_at,
        changelog=row.changelog,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _quote_template_v2_out(db: Session, row: QuoteTemplate) -> QuoteTemplateV2Out:
    active_version = _active_quote_template_version(db, row.id)
    return QuoteTemplateV2Out(
        id=row.id,
        code=row.code,
        name=row.name,
        template_type=row.template_type,
        target=row.target,
        language=row.language,
        description=row.description,
        is_active=bool(row.is_active),
        is_default=bool(row.is_default),
        status=row.status,
        current_version_id=row.current_version_id,
        current_version_number=int(active_version.version_number) if active_version is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
    )


def _terms_template_version_out(row: TermsTemplateVersion) -> TermsTemplateVersionOut:
    return TermsTemplateVersionOut(
        id=row.id,
        terms_template_id=row.terms_template_id,
        version_number=int(row.version_number),
        content_snapshot=row.content_snapshot or {},
        is_active_version=bool(row.is_active_version),
        published_at=row.published_at,
        changelog=row.changelog,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _terms_template_out(db: Session, row: TermsTemplate) -> TermsTemplateOut:
    active_version = _active_terms_template_version(db, row.id)
    return TermsTemplateOut(
        id=row.id,
        code=row.code,
        name=row.name,
        terms_type=row.terms_type,
        target=row.target,
        language=row.language,
        description=row.description,
        is_active=bool(row.is_active),
        status=row.status,
        current_version_id=row.current_version_id,
        current_version_number=int(active_version.version_number) if active_version is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
    )


def _quote_document_binding_out(row: QuoteDocumentBinding) -> QuoteDocumentBindingOut:
    return QuoteDocumentBindingOut(
        id=row.id,
        prospect_type=row.prospect_type,
        context_type=row.context_type,
        activity_family=row.activity_family,
        activity_id=row.activity_id,
        quote_type_id=row.quote_type_id,
        language=row.language,
        currency=row.currency,
        quote_template_id=row.quote_template_id,
        quote_template_version_id=row.quote_template_version_id,
        terms_template_id=row.terms_template_id,
        terms_template_version_id=row.terms_template_version_id,
        priority=int(row.priority or 100),
        is_active=bool(row.is_active),
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalized_match_value(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    return cleaned or None


def _next_quote_template_version_number(db: Session, template_id: UUID) -> int:
    current = db.scalar(
        select(func.max(QuoteTemplateVersion.version_number)).where(QuoteTemplateVersion.quote_template_id == template_id)
    )
    return int(current or 0) + 1


def _next_terms_template_version_number(db: Session, template_id: UUID) -> int:
    current = db.scalar(
        select(func.max(TermsTemplateVersion.version_number)).where(TermsTemplateVersion.terms_template_id == template_id)
    )
    return int(current or 0) + 1


def _clear_quote_template_default_flag(db: Session, *, language: str | None, except_id: UUID | None = None) -> None:
    rows = db.scalars(select(QuoteTemplate).where(QuoteTemplate.is_default.is_(True)).with_for_update()).all()
    normalized_language = _normalized_match_value(language)
    for row in rows:
        row_language = _normalized_match_value(row.language)
        if normalized_language is not None and row_language != normalized_language:
            continue
        if except_id is not None and row.id == except_id:
            continue
        row.is_default = False
        row.updated_at = _utcnow()
        db.add(row)


def _cgv_snapshot_from_terms_version(version: TermsTemplateVersion) -> dict[str, object]:
    content_snapshot = version.content_snapshot or {}
    return {
        "terms_template_id": str(version.terms_template_id),
        "terms_template_version_id": str(version.id),
        "version_label": str(content_snapshot.get("version_label") or f"terms-v{version.version_number}"),
        "content": str(content_snapshot.get("content") or ""),
    }


def _quote_prospect_type_for_context(
    db: Session,
    *,
    prospect_id: UUID | None,
    client_id: UUID | None,
) -> str | None:
    if prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == prospect_id))
        if prospect is not None:
            return _normalized_prospect_type(prospect.meta or {})
    if client_id is not None:
        client = db.scalar(select(User).where(User.id == client_id))
        if client is not None:
            kind = (client.client_kind or "").strip().upper()
            if kind == "CHILD":
                return "child"
            return "adult"
    return None


def _quote_activity_context(
    db: Session,
    *,
    activity_ids: list[UUID],
) -> tuple[UUID | None, str | None]:
    if not activity_ids:
        return None, None
    first_activity_id = activity_ids[0]
    activity = db.scalar(select(CourseType).where(CourseType.id == first_activity_id))
    if activity is None:
        return first_activity_id, None
    service_code = (activity.service_code or "").strip().lower() or None
    return first_activity_id, service_code


def _resolve_document_binding(
    db: Session,
    *,
    prospect_type: str | None,
    context_type: str | None,
    activity_family: str | None,
    activity_id: UUID | None,
    quote_type_id: UUID | None,
    language: str | None,
    currency: str | None,
) -> QuoteDocumentBinding | None:
    normalized_prospect_type = _normalized_match_value(prospect_type)
    normalized_context_type = _normalized_match_value(context_type)
    normalized_activity_family = _normalized_match_value(activity_family)
    normalized_language = _normalized_match_value(language)
    normalized_currency = _normalized_match_value(currency)

    rows = db.scalars(
        select(QuoteDocumentBinding)
        .where(QuoteDocumentBinding.is_active.is_(True))
        .order_by(QuoteDocumentBinding.priority.asc(), QuoteDocumentBinding.created_at.desc())
    ).all()
    for row in rows:
        if row.prospect_type and _normalized_match_value(row.prospect_type) != normalized_prospect_type:
            continue
        if row.context_type and _normalized_match_value(row.context_type) != normalized_context_type:
            continue
        if row.activity_family and _normalized_match_value(row.activity_family) != normalized_activity_family:
            continue
        if row.activity_id is not None and row.activity_id != activity_id:
            continue
        if row.quote_type_id is not None and row.quote_type_id != quote_type_id:
            continue
        if row.language and _normalized_match_value(row.language) != normalized_language:
            continue
        if row.currency and _normalized_match_value(row.currency) != normalized_currency:
            continue
        return row
    return None


def _resolve_document_templates(
    db: Session,
    *,
    prospect_type: str | None,
    context_type: str | None,
    activity_family: str | None,
    activity_id: UUID | None,
    quote_type_id: UUID | None,
    language: str | None,
    currency: str | None,
    quote_template: QuoteTemplate | None,
    quote_template_version: QuoteTemplateVersion | None,
    terms_template: TermsTemplate | None,
    terms_template_version: TermsTemplateVersion | None,
) -> tuple[QuoteTemplate | None, QuoteTemplateVersion | None, TermsTemplate | None, TermsTemplateVersion | None, QuoteDocumentBinding | None]:
    selected_quote_template = quote_template
    selected_quote_template_version = quote_template_version
    selected_terms_template = terms_template
    selected_terms_template_version = terms_template_version

    binding = _resolve_document_binding(
        db,
        prospect_type=prospect_type,
        context_type=context_type,
        activity_family=activity_family,
        activity_id=activity_id,
        quote_type_id=quote_type_id,
        language=language,
        currency=currency,
    )

    if selected_quote_template_version is None and binding and binding.quote_template_version_id is not None:
        selected_quote_template_version = db.scalar(
            select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == binding.quote_template_version_id)
        )
    if selected_quote_template is None:
        if selected_quote_template_version is not None:
            selected_quote_template = db.scalar(
                select(QuoteTemplate).where(QuoteTemplate.id == selected_quote_template_version.quote_template_id)
            )
        elif binding and binding.quote_template_id is not None:
            selected_quote_template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == binding.quote_template_id))
        else:
            normalized_language = _normalized_match_value(language)
            candidates = db.scalars(
                select(QuoteTemplate)
                .where(QuoteTemplate.is_active.is_(True))
                .order_by(QuoteTemplate.is_default.desc(), QuoteTemplate.updated_at.desc())
            ).all()
            selected_quote_template = next(
                (
                    candidate
                    for candidate in candidates
                    if normalized_language is None or _normalized_match_value(candidate.language) == normalized_language
                ),
                candidates[0] if candidates else None,
            )
    if selected_quote_template_version is None and selected_quote_template is not None:
        selected_quote_template_version = _active_quote_template_version(db, selected_quote_template.id)

    if selected_terms_template_version is None and binding and binding.terms_template_version_id is not None:
        selected_terms_template_version = db.scalar(
            select(TermsTemplateVersion).where(TermsTemplateVersion.id == binding.terms_template_version_id)
        )
    if selected_terms_template is None:
        if selected_terms_template_version is not None:
            selected_terms_template = db.scalar(
                select(TermsTemplate).where(TermsTemplate.id == selected_terms_template_version.terms_template_id)
            )
        elif binding and binding.terms_template_id is not None:
            selected_terms_template = db.scalar(select(TermsTemplate).where(TermsTemplate.id == binding.terms_template_id))
        else:
            normalized_language = _normalized_match_value(language)
            candidates = db.scalars(
                select(TermsTemplate).where(TermsTemplate.is_active.is_(True)).order_by(TermsTemplate.updated_at.desc())
            ).all()
            selected_terms_template = next(
                (
                    candidate
                    for candidate in candidates
                    if normalized_language is None or _normalized_match_value(candidate.language) == normalized_language
                ),
                candidates[0] if candidates else None,
            )
    if selected_terms_template_version is None and selected_terms_template is not None:
        selected_terms_template_version = _active_terms_template_version(db, selected_terms_template.id)

    return (
        selected_quote_template,
        selected_quote_template_version,
        selected_terms_template,
        selected_terms_template_version,
        binding,
    )


def _load_quote(db: Session, quote_id: UUID, *, lock: bool = False) -> Quote:
    stmt = select(Quote).where(Quote.id == quote_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return row


def _load_quote_lines(db: Session, quote_id: UUID) -> list[QuoteLine]:
    return db.scalars(
        select(QuoteLine)
        .where(QuoteLine.quote_id == quote_id)
        .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
    ).all()


def _quote_detail_out(db: Session, quote: Quote) -> QuoteDetailOut:
    lines = _load_quote_lines(db, quote.id)
    return QuoteDetailOut(quote=_quote_out(quote), lines=[_line_out(row) for row in lines])


def _resolve_recipient_email(db: Session, quote: Quote, explicit_email: str | None = None) -> str | None:
    if explicit_email and explicit_email.strip():
        return explicit_email.strip().lower()
    from_meta = str((quote.meta or {}).get("recipient_email") or "").strip().lower()
    if from_meta:
        return from_meta
    if quote.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
        if prospect is not None and prospect.email:
            return prospect.email.strip().lower()
    if quote.client_id is not None:
        user = db.scalar(select(User).where(User.id == quote.client_id))
        if user is not None and user.email:
            return user.email.strip().lower()
    return None


def _build_payment_schedule_for_quote(db: Session, quote: Quote, *, total_ttc: Decimal) -> list[dict[str, object]]:
    if quote.payment_plan_id is None:
        return []
    plan = db.scalar(select(PaymentPlan).where(PaymentPlan.id == quote.payment_plan_id))
    if plan is None:
        return []
    snapshot = _build_payment_terms_snapshot_from_plan(
        quote=quote,
        plan=plan,
        total_ttc=total_ttc,
        registration_date=_utcnow().date(),
    )
    return [item for item in _json_list(snapshot.get("schedule")) if isinstance(item, dict)]


def _build_payment_terms_snapshot_for_quote(db: Session, quote: Quote, *, total_ttc: Decimal) -> dict[str, object]:
    if quote.payment_plan_id is None:
        return {
            "schedule": [],
            "currency": (quote.currency or "EUR").upper(),
        }
    plan = db.scalar(select(PaymentPlan).where(PaymentPlan.id == quote.payment_plan_id))
    if plan is None:
        return {
            "schedule": [],
            "currency": (quote.currency or "EUR").upper(),
        }
    return _build_payment_terms_snapshot_from_plan(
        quote=quote,
        plan=plan,
        total_ttc=total_ttc,
        registration_date=_utcnow().date(),
    )


def _extract_vat_rate(meta: dict[str, object] | None) -> Decimal | None:
    if not meta:
        return None
    raw = str(meta.get("tva_rate") or "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except Exception:
        return None
    if value < Decimal("0") or value > Decimal("100"):
        return None
    return value.quantize(Decimal("0.01"))


def _freeze_quote_document_snapshot(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    state: str,
    audience: str = AUDIENCE_CLIENT_PDF,
) -> QuoteDocumentSnapshot:
    body_html, terms_html, combined_html = render_quote_parts_html(
        db=db,
        quote=quote,
        lines=lines,
        audience=audience,
    )
    document_hash = hashlib.sha256(combined_html.encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(QuoteDocumentSnapshot)
        .where(
            QuoteDocumentSnapshot.quote_id == quote.id,
            QuoteDocumentSnapshot.snapshot_kind == "combined",
            QuoteDocumentSnapshot.document_hash == document_hash,
        )
        .order_by(QuoteDocumentSnapshot.created_at.desc())
        .limit(1)
    )
    now = _utcnow()
    if existing is None:
        existing = QuoteDocumentSnapshot(
            quote_id=quote.id,
            snapshot_kind="combined",
            language=quote.language,
            currency=quote.currency,
            vat_rate=quote.vat_rate,
            quote_template_id=quote.quote_template_id,
            quote_template_version_id=quote.quote_template_version_id,
            terms_template_id=quote.terms_template_id,
            terms_template_version_id=quote.terms_template_version_id,
            quote_body_snapshot=body_html,
            terms_body_snapshot=terms_html,
            combined_html_snapshot=combined_html,
            document_hash=document_hash,
            created_at=now,
        )
        db.add(existing)
        db.flush()

    quote.document_snapshot_id = existing.id
    quote.document_hash = existing.document_hash
    quote.document_generated_at = now
    quote.document_status = state
    quote.updated_at = now
    db.add(quote)
    return existing


def _resolve_quote_pdf_bytes(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    freeze_state: str,
    audience: str = AUDIENCE_CLIENT_PDF,
) -> bytes:
    if freeze_state == "generated" and (quote.document_status or "") != "frozen":
        snapshot = _freeze_quote_document_snapshot(
            db,
            quote=quote,
            lines=lines,
            state=freeze_state,
            audience=audience,
        )
        return render_quote_pdf_from_combined_html(
            db=db,
            quote=quote,
            lines=lines,
            combined_html=str(snapshot.combined_html_snapshot),
            audience=audience,
        )

    if quote.document_snapshot_id:
        snapshot = db.scalar(select(QuoteDocumentSnapshot).where(QuoteDocumentSnapshot.id == quote.document_snapshot_id))
        if snapshot is not None and snapshot.combined_html_snapshot:
            return render_quote_pdf_from_combined_html(
                db=db,
                quote=quote,
                lines=lines,
                combined_html=str(snapshot.combined_html_snapshot),
                audience=audience,
            )
    snapshot = _freeze_quote_document_snapshot(
        db,
        quote=quote,
        lines=lines,
        state=freeze_state,
        audience=audience,
    )
    return render_quote_pdf_from_combined_html(
        db=db,
        quote=quote,
        lines=lines,
        combined_html=str(snapshot.combined_html_snapshot),
        audience=audience,
    )


def _effective_item_price(
    db: Session,
    *,
    line: QuoteLineIn,
    pricing_catalog_id: UUID | None,
) -> tuple[str | None, str, str | None, int | None, Decimal, dict[str, object]]:
    title = line.title
    code = line.code
    description = line.description
    duration = line.duration_minutes
    unit_price = _q2(line.unit_price_ttc)
    meta = dict(line.meta)

    if line.activity_id is not None:
        activity = db.scalar(select(CourseType).where(CourseType.id == line.activity_id, CourseType.active.is_(True)))
        if activity is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown activity_id")
        code = activity.code
        title = activity.name
        description = activity.description
        duration = int(activity.duration_minutes)
        if pricing_catalog_id is not None:
            activity_price = db.scalar(
                select(PricingActivityPrice)
                .where(
                    PricingActivityPrice.catalog_id == pricing_catalog_id,
                    PricingActivityPrice.activity_id == line.activity_id,
                    PricingActivityPrice.is_active.is_(True),
                )
                .order_by(PricingActivityPrice.location_id.asc().nullsfirst())
                .limit(1)
            )
            if activity_price is not None:
                unit_price = _q2(Decimal(activity_price.unit_price_ttc))
                meta["pricing_source"] = "catalog_activity"
        if unit_price <= Decimal("0") and activity.default_course_rate_ttc is not None:
            unit_price = _q2(Decimal(activity.default_course_rate_ttc))
            meta["pricing_source"] = "activity_default_course_rate"

    if line.product_id is not None:
        product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == line.product_id, CatalogProduct.active.is_(True)))
        if product is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown product_id")
        code = code or product.barcode
        title = product.title
        description = line.description or product.short_description or product.long_description
        if pricing_catalog_id is not None:
            product_price = db.scalar(
                select(PricingProductPrice)
                .where(
                    PricingProductPrice.catalog_id == pricing_catalog_id,
                    PricingProductPrice.product_id == line.product_id,
                    PricingProductPrice.is_active.is_(True),
                )
                .limit(1)
            )
            if product_price is not None:
                unit_price = _q2(Decimal(product_price.unit_price_ttc))
                meta["pricing_source"] = "catalog_product"
        if unit_price <= Decimal("0"):
            unit_price = _q2(Decimal(product.price_incl_vat or 0))
            meta["pricing_source"] = "product_price_incl_vat"
        meta["default_vat_rate"] = str(_q3(Decimal(product.vat_rate or 0)))

    if line.kit_id is not None:
        kit = db.scalar(select(CatalogKit).where(CatalogKit.id == line.kit_id, CatalogKit.active.is_(True)))
        if kit is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown kit_id")
        code = code or kit.code
        title = kit.title
        description = line.description or kit.short_description or kit.long_description
        if pricing_catalog_id is not None:
            kit_price = db.scalar(
                select(PricingKitPrice)
                .where(
                    PricingKitPrice.catalog_id == pricing_catalog_id,
                    PricingKitPrice.kit_id == line.kit_id,
                    PricingKitPrice.is_active.is_(True),
                )
                .limit(1)
            )
            if kit_price is not None:
                unit_price = _q2(Decimal(kit_price.unit_price_ttc))
                meta["pricing_source"] = "catalog_kit"
        if unit_price <= Decimal("0"):
            if (kit.price_mode or "").strip().lower() == "forced" and kit.forced_price is not None:
                unit_price = _q2(Decimal(kit.forced_price))
            else:
                unit_price = _q2(Decimal(kit.price_incl_vat or 0))
            meta["pricing_source"] = "kit_price"
        meta["default_vat_rate"] = str(_q3(Decimal(kit.vat_rate or 0)))

    return code, title, description, duration, unit_price, meta


def _materialize_quote_lines(
    db: Session,
    *,
    quote: Quote,
    lines_in: list[QuoteLineIn],
) -> Decimal:
    db.query(QuoteLine).filter(QuoteLine.quote_id == quote.id).delete(synchronize_session=False)
    lines_total = Decimal("0.00")

    for item in lines_in:
        if item.line_category == "service" and item.line_type == "item" and item.activity_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service line requires activity_id")
        if item.line_category == "product" and item.line_type == "item" and item.product_id is None and item.kit_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Product line requires product_id or kit_id")

        code, title, description, duration, unit_price, meta = _effective_item_price(
            db,
            line=item,
            pricing_catalog_id=quote.pricing_catalog_id,
        )

        quantity = _q2(item.quantity)
        amount = _q2(quantity * unit_price)
        if item.line_type == "discount":
            amount = _q2(-abs(amount))
            unit_price = _q2(-abs(unit_price))
        elif item.line_type == "surcharge":
            amount = _q2(abs(amount))
            unit_price = _q2(abs(unit_price))

        fallback_vat_rate = _decimal_or_none(meta.get("default_vat_rate"))
        quote_vat_rate = quote.vat_rate if quote.vat_rate is not None else _extract_vat_rate(quote.meta or {})
        vat_rate = item.vat_rate if item.vat_rate is not None else fallback_vat_rate if fallback_vat_rate is not None else quote_vat_rate
        normalized_vat_rate = _q3(vat_rate if vat_rate is not None else Decimal("0"))
        unit_price_ht, unit_vat_amount = _split_ttc(unit_price, normalized_vat_rate)
        amount_ht = _q2(unit_price_ht * quantity)
        amount_vat = _q2(unit_vat_amount * quantity)
        amount = _q2(amount_ht + amount_vat)

        row = QuoteLine(
            quote_id=quote.id,
            line_category=item.line_category,
            line_type=item.line_type,
            master_item_type=item.master_item_type,
            master_item_id=item.master_item_id,
            activity_id=item.activity_id,
            product_id=item.product_id,
            kit_id=item.kit_id,
            code=code,
            title=title,
            description=description,
            duration_minutes=duration,
            pricing_unit=item.pricing_unit,
            quantity=quantity,
            vat_rate=normalized_vat_rate,
            unit_price_ht=unit_price_ht,
            unit_vat_amount=unit_vat_amount,
            unit_price_ttc=unit_price,
            amount_ht=amount_ht,
            amount_vat=amount_vat,
            amount_ttc=amount,
            sort_order=int(item.sort_order),
            meta=meta,
        )
        db.add(row)
        lines_total += amount

    quote.total_ttc = _quote_total_with_adjustment(lines_total_ttc=_q2(lines_total), meta=quote.meta or {})
    quote.updated_at = _utcnow()
    db.add(quote)
    db.flush()
    return _q2(quote.total_ttc)


def _quote_lines_total_ttc(db: Session, *, quote_id: UUID) -> Decimal:
    raw = db.scalar(select(func.coalesce(func.sum(QuoteLine.amount_ttc), Decimal("0"))).where(QuoteLine.quote_id == quote_id))
    return _q2(Decimal(raw or 0))


def _ensure_quote_editable(quote: Quote) -> None:
    if quote.status != "created":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote is immutable once sent")


def _ensure_public_token(quote: Quote) -> None:
    if not quote.public_token:
        quote.public_token = _new_token()
    if not quote.pdf_token:
        quote.pdf_token = _new_token()


@router.get("/prospects", response_model=list[ProspectOut])
def list_prospects(
    q: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    prospect_type_filter: str | None = Query(default=None, alias="prospect_type"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[ProspectOut]:
    stmt = select(Prospect)
    if status_filter:
        stmt = stmt.where(Prospect.status == status_filter.strip())
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Prospect.email.ilike(pattern),
                Prospect.first_name.ilike(pattern),
                Prospect.last_name.ilike(pattern),
                Prospect.phone.ilike(pattern),
            )
        )
    normalized_type = (prospect_type_filter or "").strip().lower()
    if normalized_type == "child":
        stmt = stmt.where(func.coalesce(Prospect.meta["prospect_type"].astext, "adult") == "child")
    elif normalized_type == "adult":
        stmt = stmt.where(func.coalesce(Prospect.meta["prospect_type"].astext, "adult") != "child")
    rows = db.scalars(stmt.order_by(Prospect.created_at.desc()).limit(limit)).all()
    return [_prospect_out(row) for row in rows]


@router.post("/prospects", response_model=ProspectOut, status_code=status.HTTP_201_CREATED)
def create_prospect(
    payload: ProspectCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    email = payload.email.strip().lower()
    prospect_type = _normalized_prospect_type(payload.meta)
    if prospect_type != "child":
        existing = db.scalar(
            select(Prospect).where(
                Prospect.email == email,
                func.coalesce(Prospect.meta["prospect_type"].astext, "adult") != "child",
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prospect already exists")
    if payload.parent_prospect_id is not None:
        if prospect_type != "child":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="parent_prospect_id is only allowed for child prospects")
        _ensure_parent_prospect(db, payload.parent_prospect_id)

    now = _utcnow()
    row = Prospect(
        linked_client_id=payload.linked_client_id,
        parent_prospect_id=payload.parent_prospect_id,
        status="active",
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=email,
        phone=payload.phone,
        source=payload.source,
        notes=payload.notes,
        meta=payload.meta,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _prospect_out(row)


@router.get("/prospects/{prospect_id}", response_model=ProspectOut)
def get_prospect(
    prospect_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    row = db.scalar(select(Prospect).where(Prospect.id == prospect_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return _prospect_out(row)


@router.patch("/prospects/{prospect_id}", response_model=ProspectOut)
def update_prospect(
    prospect_id: UUID,
    payload: ProspectUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    row = db.scalar(select(Prospect).where(Prospect.id == prospect_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")

    if payload.linked_client_id is not None:
        row.linked_client_id = payload.linked_client_id
    if "parent_prospect_id" in payload.model_fields_set:
        next_parent_id = payload.parent_prospect_id
        if next_parent_id is not None:
            _ensure_parent_prospect(db, next_parent_id, current_prospect_id=row.id)
        row.parent_prospect_id = next_parent_id
    if payload.status is not None:
        row.status = payload.status.strip()
    if payload.first_name is not None:
        row.first_name = payload.first_name
    if payload.last_name is not None:
        row.last_name = payload.last_name
    next_meta = payload.meta if payload.meta is not None else (row.meta or {})
    next_type = _normalized_prospect_type(next_meta)
    next_email = (payload.email.strip().lower() if payload.email is not None else (row.email or "").strip().lower())
    if next_type != "child":
        duplicate = db.scalar(
            select(Prospect.id).where(
                Prospect.email == next_email,
                Prospect.id != row.id,
                func.coalesce(Prospect.meta["prospect_type"].astext, "adult") != "child",
            ).limit(1)
        )
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prospect email already used")
    if payload.email is not None:
        row.email = next_email
    if payload.phone is not None:
        row.phone = payload.phone
    if payload.source is not None:
        row.source = payload.source
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.meta is not None:
        row.meta = payload.meta
    if row.parent_prospect_id is not None and _normalized_prospect_type(row.meta or {}) != "child":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only child prospects can keep parent_prospect_id")
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _prospect_out(row)


@router.post("/prospects/from-client/{client_id}", response_model=ProspectOut)
def create_prospect_from_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    user = db.scalar(select(User).where(User.id == client_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    existing = db.scalar(select(Prospect).where(Prospect.linked_client_id == client_id).limit(1))
    if existing is not None:
        return _prospect_out(existing)

    existing_by_email = db.scalar(
        select(Prospect).where(
            Prospect.email == user.email,
            func.coalesce(Prospect.meta["prospect_type"].astext, "adult") != "child",
        ).limit(1)
    )
    if existing_by_email is not None:
        existing_by_email.linked_client_id = client_id
        existing_by_email.updated_at = _utcnow()
        db.add(existing_by_email)
        db.commit()
        db.refresh(existing_by_email)
        return _prospect_out(existing_by_email)

    now = _utcnow()
    row = Prospect(
        linked_client_id=client_id,
        status="active",
        first_name=user.first_name,
        last_name=user.last_name,
        email=(user.email or "").strip().lower(),
        phone=user.mobile_phone_1 or user.phone,
        source="from_client",
        meta={"origin": "client"},
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _prospect_out(row)


@router.get("/quotes", response_model=list[QuoteOut])
def list_quotes(
    status_filter: str | None = Query(default=None, alias="status"),
    context_type: str | None = None,
    prospect_id: UUID | None = None,
    client_id: UUID | None = None,
    activity_id: UUID | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteOut]:
    stmt = select(Quote)
    if status_filter:
        stmt = stmt.where(Quote.status == status_filter.strip())
    if context_type:
        stmt = stmt.where(Quote.context_type == context_type.strip())
    if prospect_id is not None:
        stmt = stmt.where(Quote.prospect_id == prospect_id)
    if client_id is not None:
        stmt = stmt.where(Quote.client_id == client_id)
    if activity_id is not None:
        stmt = stmt.where(
            exists(
                select(QuoteLine.id)
                .where(QuoteLine.quote_id == Quote.id, QuoteLine.activity_id == activity_id)
                .limit(1)
            )
        )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(Quote.quote_number.ilike(pattern))

    rows = db.scalars(stmt.order_by(Quote.created_at.desc()).limit(limit)).all()
    return [_quote_out(row) for row in rows]


@router.post("/quotes/calendar/preview")
def preview_quote_calendar(
    payload: QuoteCalendarPreviewRequest,
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    snapshot = generate_calendar_snapshot(
        CalendarGenerationInput(
            start_date=payload.start_date,
            end_date=payload.end_date,
            weekdays=payload.weekdays,
            start_time=_time_from_hhmm(payload.start_time, field="start_time"),
            end_time=_time_from_hhmm(payload.end_time, field="end_time"),
            activity_id=payload.activity_id,
            location_id=payload.location_id,
            modality=payload.modality,
            holiday_dates=payload.holiday_dates,
            closure_dates=payload.closure_dates,
        )
    )
    return snapshot


@router.post("/quotes/payment-schedule/preview")
def preview_quote_payment_schedule(
    payload: QuotePaymentSchedulePreviewRequest,
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code=payload.payment_method_code,
            schedule_type=payload.schedule_type or "single",
            schedule_rules=payload.schedule_rules or {},
            payment_method_label=payload.payment_method_label,
            total_ttc=payload.total_ttc,
            registration_date=payload.registration_date,
            currency=payload.currency.upper(),
        )
    )
    return {"schedule": schedule}


@router.post("/quotes", response_model=QuoteDetailOut, status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: QuoteCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    if payload.context_type == "acquisition" and payload.prospect_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="prospect_id is required for acquisition quote")
    if payload.context_type == "active_client" and payload.client_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="client_id is required for active_client quote")

    prospect: Prospect | None = None
    if payload.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == payload.prospect_id))
        if prospect is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    client: User | None = None
    if payload.client_id is not None:
        client = db.scalar(select(User).where(User.id == payload.client_id))
        if client is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    selected_quote_template = None
    if payload.quote_template_uuid is not None:
        selected_quote_template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == payload.quote_template_uuid))
        if selected_quote_template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template UUID not found")
    selected_quote_template_version = None
    if payload.quote_template_version_id is not None:
        selected_quote_template_version = db.scalar(
            select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == payload.quote_template_version_id)
        )
        if selected_quote_template_version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template version not found")
        if payload.quote_template_uuid is not None and selected_quote_template_version.quote_template_id != payload.quote_template_uuid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Template version does not match template")
        if selected_quote_template is None:
            selected_quote_template = db.scalar(
                select(QuoteTemplate).where(QuoteTemplate.id == selected_quote_template_version.quote_template_id)
            )

    selected_terms_template = None
    if payload.terms_template_id is not None:
        selected_terms_template = db.scalar(select(TermsTemplate).where(TermsTemplate.id == payload.terms_template_id))
        if selected_terms_template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")
    selected_terms_template_version = None
    if payload.terms_template_version_id is not None:
        selected_terms_template_version = db.scalar(
            select(TermsTemplateVersion).where(TermsTemplateVersion.id == payload.terms_template_version_id)
        )
        if selected_terms_template_version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template version not found")
        if payload.terms_template_id is not None and selected_terms_template_version.terms_template_id != payload.terms_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Terms version does not match template")
        if selected_terms_template is None:
            selected_terms_template = db.scalar(
                select(TermsTemplate).where(TermsTemplate.id == selected_terms_template_version.terms_template_id)
            )

    now = _utcnow()
    quote_dt = datetime.combine(payload.quote_date or now.date(), time(0, 0), tzinfo=timezone.utc)
    expires_at = quote_dt + timedelta(days=int(payload.expiry_days))
    quote_meta = _normalize_quote_meta(payload.meta)
    if payload.language is not None and payload.language.strip():
        quote_meta["language"] = payload.language.strip().lower()
    if payload.vat_rate is not None:
        quote_meta["tva_rate"] = str(payload.vat_rate)
    resolved_language = (
        payload.language.strip().lower()
        if payload.language is not None and payload.language.strip()
        else None
    )
    activity_ids = [line.activity_id for line in payload.lines if line.activity_id is not None]
    activity_id_for_document, activity_family_for_document = _quote_activity_context(db, activity_ids=activity_ids)
    prospect_type_for_document = (
        _normalized_prospect_type((prospect.meta if prospect is not None else {}) or {})
        if prospect is not None
        else ("child" if (client and (client.client_kind or "").strip().upper() == "CHILD") else ("adult" if client is not None else None))
    )
    (
        selected_quote_template,
        selected_quote_template_version,
        selected_terms_template,
        selected_terms_template_version,
        selected_binding,
    ) = _resolve_document_templates(
        db,
        prospect_type=prospect_type_for_document,
        context_type=payload.context_type,
        activity_family=activity_family_for_document,
        activity_id=activity_id_for_document,
        quote_type_id=payload.quote_type_id,
        language=resolved_language,
        currency=payload.currency,
        quote_template=selected_quote_template,
        quote_template_version=selected_quote_template_version,
        terms_template=selected_terms_template,
        terms_template_version=selected_terms_template_version,
    )
    if selected_binding is not None:
        quote_meta["document_binding_id"] = str(selected_binding.id)
    if selected_quote_template is not None:
        quote_meta["quote_template_uuid"] = str(selected_quote_template.id)
    if selected_quote_template_version is not None:
        quote_meta["quote_template_version_id"] = str(selected_quote_template_version.id)
    if selected_terms_template is not None:
        quote_meta["terms_template_id"] = str(selected_terms_template.id)
    if selected_terms_template_version is not None:
        quote_meta["terms_template_version_id"] = str(selected_terms_template_version.id)
    quote_meta[QUOTE_FINANCIAL_ADJUSTMENT_META_KEY] = _normalize_quote_adjustment(quote_meta)

    row = Quote(
        quote_number=_new_quote_number(),
        context_type=payload.context_type,
        quote_type=payload.quote_type,
        quote_type_id=payload.quote_type_id,
        pricing_catalog_id=payload.pricing_catalog_id,
        prospect_id=payload.prospect_id,
        client_id=payload.client_id,
        location_id=payload.location_id,
        payment_plan_id=payload.payment_plan_id,
        quote_template_id=selected_quote_template.id if selected_quote_template is not None else None,
        quote_template_version_id=selected_quote_template_version.id if selected_quote_template_version is not None else None,
        terms_template_id=selected_terms_template.id if selected_terms_template is not None else None,
        terms_template_version_id=selected_terms_template_version.id if selected_terms_template_version is not None else None,
        status="created",
        version_number=1,
        currency=payload.currency.upper(),
        total_ttc=Decimal("0"),
        expiry_days=int(payload.expiry_days),
        expires_at=expires_at,
        school_year_label=payload.school_year_label,
        language=resolved_language or None,
        vat_rate=payload.vat_rate if payload.vat_rate is not None else _extract_vat_rate(quote_meta),
        estimated_solfege_level=payload.estimated_solfege_level,
        selected_solfege_slot=payload.selected_solfege_slot,
        calendar_snapshot=payload.calendar_snapshot,
        payment_terms_snapshot=payload.payment_terms_snapshot,
        cgv_snapshot=payload.cgv_snapshot,
        price_snapshot=payload.price_snapshot,
        meta=quote_meta,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )

    if row.estimated_solfege_level:
        solfege_rule = db.scalar(
            select(SolfegeLevelRule)
            .where(
                SolfegeLevelRule.level_code == row.estimated_solfege_level,
                SolfegeLevelRule.is_active.is_(True),
            )
            .order_by(SolfegeLevelRule.created_at.desc())
            .limit(1)
        )
        if solfege_rule is not None:
            row.solfege_duration_minutes = int(solfege_rule.duration_minutes)

    if selected_terms_template_version is not None:
        row.cgv_snapshot = _cgv_snapshot_from_terms_version(selected_terms_template_version)

    db.add(row)
    db.flush()

    total = _materialize_quote_lines(db, quote=row, lines_in=payload.lines)
    lines_total = _quote_lines_total_ttc(db, quote_id=row.id)
    if not row.payment_terms_snapshot:
        row.payment_terms_snapshot = _build_payment_terms_snapshot_for_quote(db, row, total_ttc=total)
    if not row.price_snapshot:
        row.price_snapshot = {
            "catalog_id": str(row.pricing_catalog_id) if row.pricing_catalog_id else None,
            "currency": row.currency,
            "lines_total_ttc": str(lines_total),
            "total_ttc": str(total),
        }

    db.add(
        QuoteEvent(
            quote_id=row.id,
            event_type="quote_created",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"context_type": row.context_type},
        )
    )
    db.commit()
    db.refresh(row)
    return _quote_detail_out(db, row)


@router.get("/quotes/{quote_id}", response_model=QuoteDetailOut)
def get_quote(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    row = _load_quote(db, quote_id)
    return _quote_detail_out(db, row)


@router.patch("/quotes/{quote_id}", response_model=QuoteDetailOut)
def update_quote(
    quote_id: UUID,
    payload: QuoteUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    row = _load_quote(db, quote_id, lock=True)
    _ensure_quote_editable(row)
    document_dirty = False
    payment_plan_changed = False
    adjustment_changed = False
    computed_total: Decimal | None = None
    previous_adjustment_signature = _quote_adjustment_signature(row.meta or {})

    if payload.quote_type is not None:
        row.quote_type = payload.quote_type
        document_dirty = True
    if payload.quote_type_id is not None:
        row.quote_type_id = payload.quote_type_id
        document_dirty = True
    if payload.pricing_catalog_id is not None:
        row.pricing_catalog_id = payload.pricing_catalog_id
        document_dirty = True
    if payload.location_id is not None:
        row.location_id = payload.location_id
        document_dirty = True
    if payload.payment_plan_id is not None:
        if row.payment_plan_id != payload.payment_plan_id:
            payment_plan_changed = True
        row.payment_plan_id = payload.payment_plan_id
        document_dirty = True
    if payload.quote_template_uuid is not None:
        selected_quote_template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == payload.quote_template_uuid))
        if selected_quote_template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template UUID not found")
        row.quote_template_id = selected_quote_template.id
        selected_quote_template_version_id = selected_quote_template.current_version_id
        if selected_quote_template_version_id is None:
            fallback_quote_version = db.scalar(
                select(QuoteTemplateVersion)
                .where(QuoteTemplateVersion.quote_template_id == selected_quote_template.id)
                .order_by(QuoteTemplateVersion.version_number.desc())
                .limit(1)
            )
            selected_quote_template_version_id = fallback_quote_version.id if fallback_quote_version is not None else None
        row.quote_template_version_id = selected_quote_template_version_id
        document_dirty = True
    if payload.quote_template_version_id is not None:
        selected_quote_template_version = db.scalar(
            select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == payload.quote_template_version_id)
        )
        if selected_quote_template_version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template version not found")
        if row.quote_template_id is not None and selected_quote_template_version.quote_template_id != row.quote_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Template version does not match template")
        row.quote_template_id = selected_quote_template_version.quote_template_id
        row.quote_template_version_id = selected_quote_template_version.id
        document_dirty = True
    if payload.terms_template_id is not None:
        selected_terms_template = db.scalar(select(TermsTemplate).where(TermsTemplate.id == payload.terms_template_id))
        if selected_terms_template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")
        row.terms_template_id = selected_terms_template.id
        selected_terms_template_version = None
        if selected_terms_template.current_version_id is not None:
            selected_terms_template_version = db.scalar(
                select(TermsTemplateVersion).where(TermsTemplateVersion.id == selected_terms_template.current_version_id)
            )
        if selected_terms_template_version is None:
            selected_terms_template_version = db.scalar(
                select(TermsTemplateVersion)
                .where(TermsTemplateVersion.terms_template_id == selected_terms_template.id)
                .order_by(TermsTemplateVersion.version_number.desc())
                .limit(1)
            )
        row.terms_template_version_id = selected_terms_template_version.id if selected_terms_template_version is not None else None
        if selected_terms_template_version is not None:
            row.cgv_snapshot = _cgv_snapshot_from_terms_version(selected_terms_template_version)
        document_dirty = True
    if payload.terms_template_version_id is not None:
        selected_terms_template_version = db.scalar(
            select(TermsTemplateVersion).where(TermsTemplateVersion.id == payload.terms_template_version_id)
        )
        if selected_terms_template_version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template version not found")
        if row.terms_template_id is not None and selected_terms_template_version.terms_template_id != row.terms_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Terms version does not match template")
        row.terms_template_id = selected_terms_template_version.terms_template_id
        row.terms_template_version_id = selected_terms_template_version.id
        row.cgv_snapshot = _cgv_snapshot_from_terms_version(selected_terms_template_version)
        document_dirty = True
    if payload.school_year_label is not None:
        row.school_year_label = payload.school_year_label
        document_dirty = True
    if payload.currency is not None:
        row.currency = payload.currency.upper()
        document_dirty = True
    if payload.language is not None and payload.language.strip():
        normalized_language = payload.language.strip().lower()
        row.meta = {**(row.meta or {}), "language": normalized_language}
        row.language = normalized_language
        document_dirty = True
    if payload.vat_rate is not None:
        row.vat_rate = payload.vat_rate
        row.meta = {**(row.meta or {}), "tva_rate": str(payload.vat_rate)}
        document_dirty = True
    if payload.expiry_days is not None:
        row.expiry_days = int(payload.expiry_days)
        row.expires_at = _utcnow() + timedelta(days=int(payload.expiry_days))
        document_dirty = True
    if payload.estimated_solfege_level is not None:
        row.estimated_solfege_level = payload.estimated_solfege_level
        document_dirty = True
    if payload.selected_solfege_slot is not None:
        row.selected_solfege_slot = payload.selected_solfege_slot
        document_dirty = True
    if payload.calendar_snapshot is not None:
        row.calendar_snapshot = payload.calendar_snapshot
        document_dirty = True
    if payload.payment_terms_snapshot is not None:
        row.payment_terms_snapshot = payload.payment_terms_snapshot
        document_dirty = True
    if payload.cgv_snapshot is not None:
        row.cgv_snapshot = payload.cgv_snapshot
        document_dirty = True
    if payload.price_snapshot is not None:
        row.price_snapshot = payload.price_snapshot
    if payload.meta is not None:
        next_meta = _normalize_quote_meta(payload.meta)
        next_meta[QUOTE_FINANCIAL_ADJUSTMENT_META_KEY] = _normalize_quote_adjustment(next_meta)
        adjustment_changed = _quote_adjustment_signature(next_meta) != previous_adjustment_signature
        row.meta = next_meta
        row.vat_rate = _extract_vat_rate(row.meta or {})
        document_dirty = True

    if payload.lines is not None:
        computed_total = _materialize_quote_lines(db, quote=row, lines_in=payload.lines)
        document_dirty = True
    elif adjustment_changed:
        lines_total = _quote_lines_total_ttc(db, quote_id=row.id)
        computed_total = _quote_total_with_adjustment(lines_total_ttc=lines_total, meta=row.meta or {})
        row.total_ttc = computed_total
        document_dirty = True

    if payload.payment_terms_snapshot is None and (payment_plan_changed or payload.lines is not None or adjustment_changed):
        total_for_schedule = computed_total if computed_total is not None else _q2(Decimal(row.total_ttc or 0))
        row.payment_terms_snapshot = _build_payment_terms_snapshot_for_quote(db, row, total_ttc=total_for_schedule)

    if payload.price_snapshot is None and (payload.lines is not None or adjustment_changed):
        lines_total_ttc = _quote_lines_total_ttc(db, quote_id=row.id)
        row.price_snapshot = {
            "catalog_id": str(row.pricing_catalog_id) if row.pricing_catalog_id else None,
            "currency": row.currency,
            "lines_total_ttc": str(lines_total_ttc),
            "total_ttc": str(_q2(Decimal(row.total_ttc or 0))),
        }

    document_fields = {
        "quote_template_uuid",
        "quote_template_version_id",
        "terms_template_id",
        "terms_template_version_id",
    }
    explicit_document_override = any(field in payload.model_fields_set for field in document_fields)
    if not explicit_document_override and (
        row.quote_template_id is None
        or row.quote_template_version_id is None
        or row.terms_template_id is None
        or row.terms_template_version_id is None
    ):
        existing_quote_template = (
            db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == row.quote_template_id))
            if row.quote_template_id is not None
            else None
        )
        existing_quote_template_version = (
            db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == row.quote_template_version_id))
            if row.quote_template_version_id is not None
            else None
        )
        existing_terms_template = (
            db.scalar(select(TermsTemplate).where(TermsTemplate.id == row.terms_template_id))
            if row.terms_template_id is not None
            else None
        )
        existing_terms_template_version = (
            db.scalar(select(TermsTemplateVersion).where(TermsTemplateVersion.id == row.terms_template_version_id))
            if row.terms_template_version_id is not None
            else None
        )
        quote_lines_for_context = payload.lines if payload.lines is not None else _load_quote_lines(db, row.id)
        activity_ids_for_context = [
            item.activity_id if isinstance(item, QuoteLineIn) else item.activity_id
            for item in quote_lines_for_context
            if getattr(item, "activity_id", None) is not None
        ]
        activity_id_for_document, activity_family_for_document = _quote_activity_context(
            db, activity_ids=[item for item in activity_ids_for_context if item is not None]
        )
        language_for_document = (row.language or str((row.meta or {}).get("language") or "")).strip().lower() or None
        prospect_type_for_document = _quote_prospect_type_for_context(
            db,
            prospect_id=row.prospect_id,
            client_id=row.client_id,
        )
        (
            resolved_quote_template,
            resolved_quote_template_version,
            resolved_terms_template,
            resolved_terms_template_version,
            resolved_binding,
        ) = _resolve_document_templates(
            db,
            prospect_type=prospect_type_for_document,
            context_type=row.context_type,
            activity_family=activity_family_for_document,
            activity_id=activity_id_for_document,
            quote_type_id=row.quote_type_id,
            language=language_for_document,
            currency=row.currency,
            quote_template=existing_quote_template,
            quote_template_version=existing_quote_template_version,
            terms_template=existing_terms_template,
            terms_template_version=existing_terms_template_version,
        )
        if resolved_quote_template is not None and row.quote_template_id is None:
            row.quote_template_id = resolved_quote_template.id
            document_dirty = True
        if resolved_quote_template_version is not None and row.quote_template_version_id is None:
            row.quote_template_version_id = resolved_quote_template_version.id
            document_dirty = True
        if resolved_terms_template is not None and row.terms_template_id is None:
            row.terms_template_id = resolved_terms_template.id
            document_dirty = True
        if resolved_terms_template_version is not None and row.terms_template_version_id is None:
            row.terms_template_version_id = resolved_terms_template_version.id
            row.cgv_snapshot = _cgv_snapshot_from_terms_version(resolved_terms_template_version)
            document_dirty = True
        if resolved_binding is not None:
            row.meta = {**(row.meta or {}), "document_binding_id": str(resolved_binding.id)}
            document_dirty = True

    if document_dirty:
        row.document_status = "stale"
        row.document_hash = None
        row.document_generated_at = None
        row.document_snapshot_id = None

    row.updated_at = _utcnow()
    db.add(row)
    db.add(
        QuoteEvent(
            quote_id=row.id,
            event_type="quote_updated",
            actor_type="admin",
            actor_id=current_user.id,
            payload={},
        )
    )
    db.commit()
    db.refresh(row)
    return _quote_detail_out(db, row)


@router.post("/quotes/{quote_id}/duplicate", response_model=QuoteDetailOut, status_code=status.HTTP_201_CREATED)
def duplicate_quote(
    quote_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    source = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    now = _utcnow()

    clone = Quote(
        quote_number=_new_quote_number(),
        context_type=source.context_type,
        quote_type=source.quote_type,
        quote_type_id=source.quote_type_id,
        pricing_catalog_id=source.pricing_catalog_id,
        prospect_id=source.prospect_id,
        client_id=source.client_id,
        location_id=source.location_id,
        payment_plan_id=source.payment_plan_id,
        status="created",
        version_number=int(source.version_number or 1) + 1,
        parent_quote_id=source.id,
        currency=source.currency,
        total_ttc=source.total_ttc,
        expiry_days=source.expiry_days,
        expires_at=now + timedelta(days=int(source.expiry_days or 10)),
        school_year_label=source.school_year_label,
        estimated_solfege_level=source.estimated_solfege_level,
        solfege_duration_minutes=source.solfege_duration_minutes,
        selected_solfege_slot=source.selected_solfege_slot,
        calendar_snapshot=source.calendar_snapshot,
        payment_terms_snapshot=source.payment_terms_snapshot,
        cgv_snapshot=source.cgv_snapshot,
        price_snapshot=source.price_snapshot,
        meta={**(source.meta or {}), "duplicated_from": str(source.id)},
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(clone)
    db.flush()

    for line in lines:
        db.add(
            QuoteLine(
                quote_id=clone.id,
                line_category=line.line_category,
                line_type=line.line_type,
                master_item_type=line.master_item_type,
                master_item_id=line.master_item_id,
                activity_id=line.activity_id,
                product_id=line.product_id,
                kit_id=line.kit_id,
                code=line.code,
                title=line.title,
                description=line.description,
                duration_minutes=line.duration_minutes,
                pricing_unit=line.pricing_unit,
                quantity=line.quantity,
                unit_price_ttc=line.unit_price_ttc,
                amount_ttc=line.amount_ttc,
                sort_order=line.sort_order,
                meta=line.meta,
                created_at=now,
                updated_at=now,
            )
        )

    db.add(
        QuoteEvent(
            quote_id=clone.id,
            event_type="quote_duplicated",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"source_quote_id": str(source.id)},
        )
    )
    db.commit()
    db.refresh(clone)
    return _quote_detail_out(db, clone)


@router.post("/quotes/{quote_id}/generate-pdf")
def generate_quote_pdf(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> StreamingResponse:
    quote = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    pdf_bytes = _resolve_quote_pdf_bytes(db, quote=quote, lines=lines, freeze_state="generated")
    db.commit()
    filename = f"devis-{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/quotes/{quote_id}/document-preview")
def preview_quote_document(
    quote_id: UUID,
    audience: str = Query(default=AUDIENCE_ADMIN_PREVIEW),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    quote = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    resolved_audience = audience.strip().lower() if audience else AUDIENCE_ADMIN_PREVIEW
    if resolved_audience not in {AUDIENCE_ADMIN_PREVIEW, AUDIENCE_PUBLIC_PAGE, AUDIENCE_CLIENT_PDF}:
        resolved_audience = AUDIENCE_ADMIN_PREVIEW
    bundle = render_quote_document_bundle(db=db, quote=quote, lines=lines, audience=resolved_audience)
    combined_html = str(bundle["combined_html"])
    document_hash = hashlib.sha256(combined_html.encode("utf-8")).hexdigest()
    return {
        "quote_id": str(quote.id),
        "audience": resolved_audience,
        "document_hash": document_hash,
        "document_status": quote.document_status,
        "document_snapshot_id": str(quote.document_snapshot_id) if quote.document_snapshot_id else None,
        "quote_body_html": bundle["body_html"],
        "terms_html": bundle["terms_html"],
        "combined_html": combined_html,
        "display_flags": bundle["display_flags"],
        "visible_blocks": bundle["visible_blocks"],
        "hidden_blocks": bundle["hidden_blocks"],
        "payment_schedule_compact_notice": bundle["payment_schedule_compact_notice"],
    }


@router.post("/quotes/{quote_id}/document/regenerate")
def regenerate_quote_document(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    quote = _load_quote(db, quote_id, lock=True)
    _ensure_quote_editable(quote)
    if quote.quote_template_id is not None:
        template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == quote.quote_template_id))
        if template is not None and template.current_version_id is not None:
            quote.quote_template_version_id = template.current_version_id
    if quote.terms_template_id is not None:
        terms_template = db.scalar(select(TermsTemplate).where(TermsTemplate.id == quote.terms_template_id))
        if terms_template is not None and terms_template.current_version_id is not None:
            quote.terms_template_version_id = terms_template.current_version_id
            terms_version = db.scalar(
                select(TermsTemplateVersion).where(TermsTemplateVersion.id == terms_template.current_version_id)
            )
            if terms_version is not None:
                quote.cgv_snapshot = _cgv_snapshot_from_terms_version(terms_version)
    if quote.payment_plan_id is not None:
        quote.payment_terms_snapshot = _build_payment_terms_snapshot_for_quote(
            db,
            quote,
            total_ttc=_q2(Decimal(quote.total_ttc or 0)),
        )
    lines = _load_quote_lines(db, quote.id)
    snapshot = _freeze_quote_document_snapshot(db, quote=quote, lines=lines, state="generated")
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_document_regenerated",
            actor_type="admin",
            payload={"snapshot_id": str(snapshot.id), "document_hash": snapshot.document_hash},
            created_at=_utcnow(),
        )
    )
    db.commit()
    return {
        "quote_id": str(quote.id),
        "document_status": quote.document_status,
        "document_snapshot_id": str(snapshot.id),
        "document_hash": snapshot.document_hash,
        "generated_at": quote.document_generated_at.isoformat() if quote.document_generated_at else None,
    }


@router.get("/quotes/{quote_id}/pdf")
def download_quote_pdf(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> StreamingResponse:
    quote = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    pdf_bytes = _resolve_quote_pdf_bytes(db, quote=quote, lines=lines, freeze_state="generated")
    db.commit()
    filename = f"devis-{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _send_quote_email(
    db: Session,
    *,
    quote: Quote,
    recipient_email: str,
    kind: str,
    actor_id: UUID | None,
) -> None:
    now = _utcnow()
    message_key = f"{kind}:{quote.id}:{recipient_email}"
    existing = db.scalar(select(QuoteEmailOutbox).where(QuoteEmailOutbox.message_key == message_key).limit(1))
    if existing is not None:
        return

    frontend_base = (settings.frontend_base_url or "http://localhost:3000").rstrip("/")
    public_url = f"{frontend_base}/q/{quote.id}?t={quote.public_token}"
    pdf_url = f"{frontend_base}/api/v1/public/quotes/{quote.id}/pdf?t={quote.pdf_token}"
    subject = f"Devis {quote.quote_number}"
    body = (
        f"Votre devis {quote.quote_number} est disponible.\n\n"
        f"Consulter et agir: {public_url}\n"
        f"Telecharger le PDF: {pdf_url}\n"
        f"Total TTC: {quote.total_ttc} {quote.currency}\n"
    )

    out = QuoteEmailOutbox(
        quote_id=quote.id,
        kind=kind,
        message_key=message_key,
        recipient_email=recipient_email,
        subject=subject,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(out)
    db.flush()

    provider_message_id = send_email(
        to_email=recipient_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="QUOTE_SENT",
    )
    out.provider_message_id = provider_message_id
    out.status = "sent" if provider_message_id else "failed"
    out.sent_at = now if provider_message_id else None
    out.updated_at = now
    db.add(out)

    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_email_sent",
            actor_type="admin",
            actor_id=actor_id,
            payload={"kind": kind, "recipient_email": recipient_email},
            created_at=now,
        )
    )


@router.post("/quotes/{quote_id}/send", response_model=QuoteDetailOut)
def send_quote(
    quote_id: UUID,
    payload: QuoteSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    quote = _load_quote(db, quote_id, lock=True)
    _ensure_quote_editable(quote)
    _ensure_public_token(quote)

    now = _utcnow()
    quote.status = "sent"
    quote.sent_at = now
    if quote.expires_at is None:
        quote.expires_at = now + timedelta(days=int(quote.expiry_days or 10))
    quote.updated_at = now

    recipient = _resolve_recipient_email(db, quote, explicit_email=payload.recipient_email)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No recipient email resolved for quote")

    quote.meta = {**(quote.meta or {}), "recipient_email": recipient}
    lines = _load_quote_lines(db, quote.id)
    snapshot = _freeze_quote_document_snapshot(db, quote=quote, lines=lines, state="frozen")
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_sent",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"recipient_email": recipient, "document_snapshot_id": str(snapshot.id), "document_hash": snapshot.document_hash},
            created_at=now,
        )
    )
    _send_quote_email(db, quote=quote, recipient_email=recipient, kind="quote_sent", actor_id=current_user.id)
    db.commit()
    db.refresh(quote)
    return _quote_detail_out(db, quote)


@router.post("/quotes/{quote_id}/resend", response_model=QuoteDetailOut)
def resend_quote(
    quote_id: UUID,
    payload: QuoteSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.status not in {"sent", "approved", "rejected", "expired"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot be resent in current status")
    _ensure_public_token(quote)

    recipient = _resolve_recipient_email(db, quote, explicit_email=payload.recipient_email)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No recipient email resolved for quote")

    quote.meta = {**(quote.meta or {}), "recipient_email": recipient}
    lines = _load_quote_lines(db, quote.id)
    snapshot = _freeze_quote_document_snapshot(db, quote=quote, lines=lines, state="frozen")
    quote.updated_at = _utcnow()
    db.add(quote)
    _send_quote_email(db, quote=quote, recipient_email=recipient, kind="quote_resend", actor_id=current_user.id)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_resent",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"recipient_email": recipient, "document_snapshot_id": str(snapshot.id), "document_hash": snapshot.document_hash},
            created_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(quote)
    return _quote_detail_out(db, quote)


@router.get("/public/quotes/{quote_id}", response_model=QuotePublicOut)
def public_get_quote(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    lines = _load_quote_lines(db, quote.id)
    preview_bundle = render_quote_document_bundle(db=db, quote=quote, lines=lines, audience=AUDIENCE_PUBLIC_PAGE)
    schedule_flag = bool((preview_bundle.get("display_flags") or {}).get("showPaymentScheduleDetailed"))
    payment_schedule = list((quote.payment_terms_snapshot or {}).get("schedule", [])) if schedule_flag else []
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=payment_schedule,
    )


@router.get("/public/quotes/{quote_id}/document")
def public_get_quote_document(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    audience: str = Query(default=AUDIENCE_PUBLIC_PAGE),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    quote = _load_quote(db, quote_id)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    lines = _load_quote_lines(db, quote.id)
    resolved_audience = audience.strip().lower() if audience else AUDIENCE_PUBLIC_PAGE
    if resolved_audience not in {AUDIENCE_ADMIN_PREVIEW, AUDIENCE_PUBLIC_PAGE, AUDIENCE_CLIENT_PDF}:
        resolved_audience = AUDIENCE_PUBLIC_PAGE
    bundle = render_quote_document_bundle(db=db, quote=quote, lines=lines, audience=resolved_audience)
    combined_html = str(bundle["combined_html"])
    return {
        "quote_id": str(quote.id),
        "quote_status": quote.status,
        "audience": resolved_audience,
        "document_hash": hashlib.sha256(combined_html.encode("utf-8")).hexdigest(),
        "combined_html": combined_html,
        "quote_body_html": bundle["body_html"],
        "terms_html": bundle["terms_html"],
        "display_flags": bundle["display_flags"],
        "visible_blocks": bundle["visible_blocks"],
        "hidden_blocks": bundle["hidden_blocks"],
        "payment_schedule_compact_notice": bundle["payment_schedule_compact_notice"],
    }


def _ensure_followup(db: Session, quote: Quote) -> QuoteAcceptanceFollowup:
    followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id).limit(1))
    if followup is not None:
        return followup
    now = _utcnow()
    followup = QuoteAcceptanceFollowup(
        quote_id=quote.id,
        target_client_id=quote.client_id,
        status="pending",
        payment_method_status="pending",
        solfege_slot_status="pending" if quote.estimated_solfege_level else "not_applicable",
        payload={},
        created_at=now,
        updated_at=now,
    )
    db.add(followup)
    db.flush()
    return followup


def _ensure_pending_client_from_prospect(db: Session, quote: Quote) -> UUID | None:
    if quote.context_type != "acquisition":
        return quote.client_id
    if quote.client_id is not None:
        return quote.client_id
    if quote.prospect_id is None:
        return None

    prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id).with_for_update())
    if prospect is None:
        return None
    if prospect.linked_client_id is not None:
        quote.client_id = prospect.linked_client_id
        db.add(quote)
        return prospect.linked_client_id

    if not prospect.email:
        return None
    existing = db.scalar(select(User).where(User.email == prospect.email.strip().lower()).limit(1))
    if existing is not None:
        prospect.linked_client_id = existing.id
        prospect.status = "converted"
        prospect.updated_at = _utcnow()
        quote.client_id = existing.id
        db.add_all([prospect, quote])
        return existing.id

    now = _utcnow()
    generated_password = hash_password(secrets.token_urlsafe(24))
    client = User(
        email=prospect.email.strip().lower(),
        hashed_password=generated_password,
        role=UserRole.CLIENT,
        first_name=prospect.first_name,
        last_name=prospect.last_name,
        phone=prospect.phone,
        mobile_phone_1=prospect.phone,
        client_status=ClientStatus.PENDING,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(client)
    db.flush()

    prospect.linked_client_id = client.id
    prospect.status = "converted"
    prospect.updated_at = now
    quote.client_id = client.id
    db.add_all([prospect, quote])
    return client.id


@router.post("/public/quotes/{quote_id}/approve", response_model=QuotePublicOut)
def public_approve_quote(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    if quote.status not in {"sent", "change_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot be approved in current status")

    now = _utcnow()
    quote.status = "approved"
    quote.approved_at = now
    quote.updated_at = now

    target_client_id = _ensure_pending_client_from_prospect(db, quote)
    followup = _ensure_followup(db, quote)
    if target_client_id is not None:
        followup.target_client_id = target_client_id
    followup.status = "pending"
    followup.updated_at = now
    db.add(followup)

    lines = _load_quote_lines(db, quote.id)
    snapshot = _freeze_quote_document_snapshot(db, quote=quote, lines=lines, state="frozen")
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_approved",
            actor_type="prospect",
            payload={
                "target_client_id": str(target_client_id) if target_client_id else None,
                "document_snapshot_id": str(snapshot.id),
                "document_hash": snapshot.document_hash,
            },
            created_at=now,
        )
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    public_bundle = render_quote_document_bundle(db=db, quote=quote, lines=lines, audience=AUDIENCE_PUBLIC_PAGE)
    public_schedule = (
        list((quote.payment_terms_snapshot or {}).get("schedule", []))
        if bool((public_bundle.get("display_flags") or {}).get("showPaymentScheduleDetailed"))
        else []
    )
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=public_schedule,
    )


@router.post("/public/quotes/{quote_id}/reject", response_model=QuotePublicOut)
def public_reject_quote(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    if quote.status not in {"sent", "change_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot be rejected in current status")

    now = _utcnow()
    quote.status = "rejected"
    quote.rejected_at = now
    quote.updated_at = now
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_rejected",
            actor_type="prospect",
            payload={},
            created_at=now,
        )
    )
    db.commit()
    db.refresh(quote)
    lines = _load_quote_lines(db, quote.id)
    public_bundle = render_quote_document_bundle(db=db, quote=quote, lines=lines, audience=AUDIENCE_PUBLIC_PAGE)
    public_schedule = (
        list((quote.payment_terms_snapshot or {}).get("schedule", []))
        if bool((public_bundle.get("display_flags") or {}).get("showPaymentScheduleDetailed"))
        else []
    )
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=public_schedule,
    )


@router.post("/public/quotes/{quote_id}/change-request", response_model=QuotePublicOut)
def public_change_request_quote(
    quote_id: UUID,
    payload: QuoteChangeRequestIn,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    if quote.status not in {"sent", "change_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot accept change request in current status")

    now = _utcnow()
    quote.status = "change_requested"
    quote.updated_at = now
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_change_requested",
            actor_type="prospect",
            payload={"message": payload.message.strip()},
            created_at=now,
        )
    )
    db.commit()
    db.refresh(quote)
    lines = _load_quote_lines(db, quote.id)
    public_bundle = render_quote_document_bundle(db=db, quote=quote, lines=lines, audience=AUDIENCE_PUBLIC_PAGE)
    public_schedule = (
        list((quote.payment_terms_snapshot or {}).get("schedule", []))
        if bool((public_bundle.get("display_flags") or {}).get("showPaymentScheduleDetailed"))
        else []
    )
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=public_schedule,
    )


@router.get("/public/quotes/{quote_id}/pdf")
def public_quote_pdf(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    quote = _load_quote(db, quote_id)
    if quote.pdf_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid PDF token")
    lines = _load_quote_lines(db, quote.id)
    pdf_bytes = _resolve_quote_pdf_bytes(db, quote=quote, lines=lines, freeze_state="frozen")
    db.commit()
    filename = f"devis-{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/quote-followups/{followup_id}", response_model=QuoteFollowupOut)
def get_quote_followup(
    followup_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")
    return _followup_out(row)


@router.get("/quote-followups", response_model=list[QuoteFollowupOut])
def list_quote_followups(
    quote_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteFollowupOut]:
    stmt = select(QuoteAcceptanceFollowup)
    if quote_id is not None:
        stmt = stmt.where(QuoteAcceptanceFollowup.quote_id == quote_id)
    if status_filter:
        stmt = stmt.where(QuoteAcceptanceFollowup.status == status_filter.strip())
    rows = db.scalars(stmt.order_by(QuoteAcceptanceFollowup.updated_at.desc(), QuoteAcceptanceFollowup.created_at.desc()).limit(500)).all()
    return [_followup_out(row) for row in rows]


@router.patch("/quote-followups/{followup_id}", response_model=QuoteFollowupOut)
def update_quote_followup(
    followup_id: UUID,
    payload: QuoteFollowupUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    if payload.status is not None:
        row.status = payload.status
    if payload.payment_method_status is not None:
        row.payment_method_status = payload.payment_method_status
    if payload.solfege_slot_status is not None:
        row.solfege_slot_status = payload.solfege_slot_status
    if payload.payload is not None:
        row.payload = payload.payload
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/quote-followups/{followup_id}/select-solfege-slot", response_model=QuoteFollowupOut)
def select_quote_followup_solfege_slot(
    followup_id: UUID,
    payload: QuoteFollowupSlotRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    row.payload = {**(row.payload or {}), "selected_solfege_slot": payload.slot}
    row.solfege_slot_status = "chosen"
    row.status = "partially_configured"
    row.updated_at = _utcnow()

    quote = _load_quote(db, row.quote_id, lock=True)
    quote.selected_solfege_slot = payload.slot
    quote.updated_at = _utcnow()
    db.add_all([row, quote])
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/quote-followups/{followup_id}/change-payment-method", response_model=QuoteFollowupOut)
def change_quote_followup_payment_method(
    followup_id: UUID,
    payload: QuoteFollowupPaymentMethodRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    quote = _load_quote(db, row.quote_id, lock=True)
    row.payload = {
        **(row.payload or {}),
        "payment_method_code": payload.payment_method_code,
        "payment_plan_id": str(payload.payment_plan_id) if payload.payment_plan_id else None,
    }
    row.payment_method_status = "changed"
    row.status = "partially_configured"
    row.updated_at = _utcnow()

    if payload.payment_plan_id is not None:
        plan = db.scalar(select(PaymentPlan).where(PaymentPlan.id == payload.payment_plan_id))
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment plan not found")
        quote.payment_plan_id = plan.id
        quote.payment_terms_snapshot = _build_payment_terms_snapshot_from_plan(
            quote=quote,
            plan=plan,
            total_ttc=_q2(Decimal(quote.total_ttc or 0)),
            registration_date=_utcnow().date(),
        )
    quote.updated_at = _utcnow()

    db.add_all([row, quote])
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/quote-followups/{followup_id}/finalize", response_model=QuoteFollowupOut)
def finalize_quote_followup(
    followup_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    row.status = "completed"
    if row.payment_method_status in {"pending", "changed"}:
        row.payment_method_status = "validated"
    if row.solfege_slot_status == "chosen":
        row.solfege_slot_status = "validated"
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/internal/jobs/run-quotes-daily")
def run_quotes_daily_job(
    limit: int = Query(default=2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    result = run_quote_daily_lifecycle_job(db, now=_utcnow(), limit=limit)
    db.commit()
    return {
        "checked": result.checked,
        "reminders_sent": result.reminders_sent,
        "expired": result.expired,
        "cancelled": result.cancelled,
        "archived_prospects": result.archived_prospects,
        "failed": result.failed,
        "job_run_id": str(result.job_run_id),
    }


@router.get("/quote-template-variables", response_model=list[QuoteTemplateVariableOut])
def get_quote_template_variables(
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteTemplateVariableOut]:
    return [QuoteTemplateVariableOut(**item) for item in list_quote_template_variables()]


@router.get("/quote-templates-v2", response_model=list[QuoteTemplateV2Out])
def list_quote_templates_v2(
    active_only: bool = Query(default=False),
    language: str | None = Query(default=None),
    target: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteTemplateV2Out]:
    stmt = select(QuoteTemplate)
    if active_only:
        stmt = stmt.where(QuoteTemplate.is_active.is_(True))
    if language:
        stmt = stmt.where(func.lower(QuoteTemplate.language) == language.strip().lower())
    if target:
        stmt = stmt.where(func.lower(func.coalesce(QuoteTemplate.target, "")) == target.strip().lower())
    if status_filter:
        stmt = stmt.where(func.lower(QuoteTemplate.status) == status_filter.strip().lower())
    rows = db.scalars(stmt.order_by(QuoteTemplate.updated_at.desc())).all()
    return [_quote_template_v2_out(db, row) for row in rows]


@router.post("/quote-templates-v2", response_model=QuoteTemplateV2Out, status_code=status.HTTP_201_CREATED)
def create_quote_template_v2(
    payload: QuoteTemplateV2UpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTemplateV2Out:
    now = _utcnow()
    normalized_language = payload.language.strip().lower()
    if payload.is_default:
        _clear_quote_template_default_flag(db, language=normalized_language)

    row = QuoteTemplate(
        code=payload.code.strip(),
        name=payload.name.strip(),
        template_type=payload.template_type.strip(),
        target=payload.target.strip().lower() if payload.target else None,
        language=normalized_language,
        description=payload.description,
        is_active=payload.is_active,
        is_default=payload.is_default,
        status="published" if payload.publish_now else payload.status.strip().lower(),
        current_version_id=None,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )
    db.add(row)
    db.flush()

    version = QuoteTemplateVersion(
        quote_template_id=row.id,
        version_number=_next_quote_template_version_number(db, row.id),
        content_snapshot={
            "subject_template": payload.subject_template,
            "body_template": payload.body_template,
        },
        is_active_version=payload.publish_now,
        published_at=now if payload.publish_now else None,
        changelog=payload.changelog,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()

    if payload.publish_now:
        row.current_version_id = version.id
    row.updated_at = now
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote template code already exists") from exc
    db.refresh(row)
    return _quote_template_v2_out(db, row)


@router.patch("/quote-templates-v2/{template_id}", response_model=QuoteTemplateV2Out)
def update_quote_template_v2(
    template_id: UUID,
    payload: QuoteTemplateV2UpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTemplateV2Out:
    row = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")

    now = _utcnow()
    normalized_language = payload.language.strip().lower()
    if payload.is_default:
        _clear_quote_template_default_flag(db, language=normalized_language, except_id=row.id)

    row.code = payload.code.strip()
    row.name = payload.name.strip()
    row.template_type = payload.template_type.strip()
    row.target = payload.target.strip().lower() if payload.target else None
    row.language = normalized_language
    row.description = payload.description
    row.is_active = payload.is_active
    row.is_default = payload.is_default
    row.status = "published" if payload.publish_now else payload.status.strip().lower()
    row.archived_at = None if row.status != "archived" else (row.archived_at or now)

    if payload.publish_now:
        active_versions = db.scalars(
            select(QuoteTemplateVersion)
            .where(
                QuoteTemplateVersion.quote_template_id == row.id,
                QuoteTemplateVersion.is_active_version.is_(True),
            )
            .with_for_update()
        ).all()
        for version_row in active_versions:
            version_row.is_active_version = False
            version_row.updated_at = now
            db.add(version_row)

    version = QuoteTemplateVersion(
        quote_template_id=row.id,
        version_number=_next_quote_template_version_number(db, row.id),
        content_snapshot={
            "subject_template": payload.subject_template,
            "body_template": payload.body_template,
        },
        is_active_version=payload.publish_now,
        published_at=now if payload.publish_now else None,
        changelog=payload.changelog,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    if payload.publish_now:
        row.current_version_id = version.id
    row.updated_at = now
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote template code already exists") from exc
    db.refresh(row)
    return _quote_template_v2_out(db, row)


@router.get("/quote-templates-v2/{template_id}/versions", response_model=list[QuoteTemplateVersionOut])
def list_quote_template_v2_versions(
    template_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteTemplateVersionOut]:
    exists_row = db.scalar(select(QuoteTemplate.id).where(QuoteTemplate.id == template_id))
    if exists_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")
    rows = db.scalars(
        select(QuoteTemplateVersion)
        .where(QuoteTemplateVersion.quote_template_id == template_id)
        .order_by(QuoteTemplateVersion.version_number.desc())
    ).all()
    return [_quote_template_version_out(row) for row in rows]


@router.post("/quote-templates-v2/{template_id}/versions", response_model=QuoteTemplateVersionOut, status_code=status.HTTP_201_CREATED)
def publish_quote_template_v2_version(
    template_id: UUID,
    payload: QuoteTemplateVersionPublishRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTemplateVersionOut:
    template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == template_id).with_for_update())
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")
    now = _utcnow()

    if payload.activate:
        active_versions = db.scalars(
            select(QuoteTemplateVersion)
            .where(
                QuoteTemplateVersion.quote_template_id == template.id,
                QuoteTemplateVersion.is_active_version.is_(True),
            )
            .with_for_update()
        ).all()
        for row in active_versions:
            row.is_active_version = False
            row.updated_at = now
            db.add(row)

    version = QuoteTemplateVersion(
        quote_template_id=template.id,
        version_number=_next_quote_template_version_number(db, template.id),
        content_snapshot={
            "subject_template": payload.subject_template,
            "body_template": payload.body_template,
        },
        is_active_version=payload.activate,
        published_at=now if payload.activate else None,
        changelog=payload.changelog,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    if payload.activate:
        template.current_version_id = version.id
        template.status = "published"
    template.updated_at = now
    db.add(template)
    db.commit()
    db.refresh(version)
    return _quote_template_version_out(version)


@router.delete("/quote-templates-v2/{template_id}", status_code=status.HTTP_200_OK)
def archive_quote_template_v2(
    template_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")
    row.is_active = False
    row.is_default = False
    row.status = "archived"
    row.archived_at = _utcnow()
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()


@router.delete("/quote-templates-v2/{template_id}/permanent", status_code=status.HTTP_200_OK)
def hard_delete_quote_template_v2(
    template_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    row = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")

    version_ids_stmt = select(QuoteTemplateVersion.id).where(QuoteTemplateVersion.quote_template_id == template_id)

    blockers: list[str] = []
    if row.is_default:
        blockers.append("template marque comme modele par defaut")

    binding_refs = int(
        db.scalar(
            select(func.count())
            .select_from(QuoteDocumentBinding)
            .where(
                or_(
                    QuoteDocumentBinding.quote_template_id == template_id,
                    QuoteDocumentBinding.quote_template_version_id.in_(version_ids_stmt),
                )
            )
        )
        or 0
    )
    if binding_refs > 0:
        blockers.append(f"{binding_refs} regle(s) d'association documentaire reference(nt) ce modele")

    quote_refs = int(
        db.scalar(
            select(func.count())
            .select_from(Quote)
            .where(
                or_(
                    Quote.quote_template_id == template_id,
                    Quote.quote_template_version_id.in_(version_ids_stmt),
                )
            )
        )
        or 0
    )
    if quote_refs > 0:
        blockers.append(f"{quote_refs} devis reference(nt) ce modele")

    snapshot_refs = int(
        db.scalar(
            select(func.count())
            .select_from(QuoteDocumentSnapshot)
            .where(
                or_(
                    QuoteDocumentSnapshot.quote_template_id == template_id,
                    QuoteDocumentSnapshot.quote_template_version_id.in_(version_ids_stmt),
                )
            )
        )
        or 0
    )
    if snapshot_refs > 0:
        blockers.append(f"{snapshot_refs} snapshot(s) documentaires reference(nt) ce modele")

    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Suppression definitive impossible: {', '.join(blockers)}. Archivez plutot le modele.",
        )

    db.delete(row)
    db.commit()
    return {"deleted": True, "template_id": str(template_id)}


@router.get("/terms-templates", response_model=list[TermsTemplateOut])
def list_terms_templates(
    active_only: bool = Query(default=False),
    language: str | None = Query(default=None),
    target: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[TermsTemplateOut]:
    stmt = select(TermsTemplate)
    if active_only:
        stmt = stmt.where(TermsTemplate.is_active.is_(True))
    if language:
        stmt = stmt.where(func.lower(TermsTemplate.language) == language.strip().lower())
    if target:
        stmt = stmt.where(func.lower(func.coalesce(TermsTemplate.target, "")) == target.strip().lower())
    if status_filter:
        stmt = stmt.where(func.lower(TermsTemplate.status) == status_filter.strip().lower())
    rows = db.scalars(stmt.order_by(TermsTemplate.updated_at.desc())).all()
    return [_terms_template_out(db, row) for row in rows]


@router.post("/terms-templates", response_model=TermsTemplateOut, status_code=status.HTTP_201_CREATED)
def create_terms_template(
    payload: TermsTemplateUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TermsTemplateOut:
    now = _utcnow()
    row = TermsTemplate(
        code=payload.code.strip(),
        name=payload.name.strip(),
        terms_type=payload.terms_type.strip(),
        target=payload.target.strip().lower() if payload.target else None,
        language=payload.language.strip().lower(),
        description=payload.description,
        is_active=payload.is_active,
        status="published" if payload.publish_now else payload.status.strip().lower(),
        current_version_id=None,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )
    db.add(row)
    db.flush()

    version = TermsTemplateVersion(
        terms_template_id=row.id,
        version_number=_next_terms_template_version_number(db, row.id),
        content_snapshot={
            "version_label": payload.version_label,
            "content": payload.content,
        },
        is_active_version=payload.publish_now,
        published_at=now if payload.publish_now else None,
        changelog=payload.changelog,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    if payload.publish_now:
        row.current_version_id = version.id
    row.updated_at = now
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Terms template code already exists") from exc
    db.refresh(row)
    return _terms_template_out(db, row)


@router.patch("/terms-templates/{template_id}", response_model=TermsTemplateOut)
def update_terms_template(
    template_id: UUID,
    payload: TermsTemplateUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TermsTemplateOut:
    row = db.scalar(select(TermsTemplate).where(TermsTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")

    now = _utcnow()
    row.code = payload.code.strip()
    row.name = payload.name.strip()
    row.terms_type = payload.terms_type.strip()
    row.target = payload.target.strip().lower() if payload.target else None
    row.language = payload.language.strip().lower()
    row.description = payload.description
    row.is_active = payload.is_active
    row.status = "published" if payload.publish_now else payload.status.strip().lower()
    row.archived_at = None if row.status != "archived" else (row.archived_at or now)

    if payload.publish_now:
        active_versions = db.scalars(
            select(TermsTemplateVersion)
            .where(
                TermsTemplateVersion.terms_template_id == row.id,
                TermsTemplateVersion.is_active_version.is_(True),
            )
            .with_for_update()
        ).all()
        for version_row in active_versions:
            version_row.is_active_version = False
            version_row.updated_at = now
            db.add(version_row)

    version = TermsTemplateVersion(
        terms_template_id=row.id,
        version_number=_next_terms_template_version_number(db, row.id),
        content_snapshot={
            "version_label": payload.version_label,
            "content": payload.content,
        },
        is_active_version=payload.publish_now,
        published_at=now if payload.publish_now else None,
        changelog=payload.changelog,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    if payload.publish_now:
        row.current_version_id = version.id
    row.updated_at = now
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Terms template code already exists") from exc
    db.refresh(row)
    return _terms_template_out(db, row)


@router.get("/terms-templates/{template_id}/versions", response_model=list[TermsTemplateVersionOut])
def list_terms_template_versions(
    template_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[TermsTemplateVersionOut]:
    exists_row = db.scalar(select(TermsTemplate.id).where(TermsTemplate.id == template_id))
    if exists_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")
    rows = db.scalars(
        select(TermsTemplateVersion)
        .where(TermsTemplateVersion.terms_template_id == template_id)
        .order_by(TermsTemplateVersion.version_number.desc())
    ).all()
    return [_terms_template_version_out(row) for row in rows]


@router.post("/terms-templates/{template_id}/versions", response_model=TermsTemplateVersionOut, status_code=status.HTTP_201_CREATED)
def publish_terms_template_version(
    template_id: UUID,
    payload: TermsTemplateVersionPublishRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> TermsTemplateVersionOut:
    template = db.scalar(select(TermsTemplate).where(TermsTemplate.id == template_id).with_for_update())
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")
    now = _utcnow()

    if payload.activate:
        active_versions = db.scalars(
            select(TermsTemplateVersion)
            .where(
                TermsTemplateVersion.terms_template_id == template.id,
                TermsTemplateVersion.is_active_version.is_(True),
            )
            .with_for_update()
        ).all()
        for row in active_versions:
            row.is_active_version = False
            row.updated_at = now
            db.add(row)

    version = TermsTemplateVersion(
        terms_template_id=template.id,
        version_number=_next_terms_template_version_number(db, template.id),
        content_snapshot={
            "version_label": payload.version_label,
            "content": payload.content,
        },
        is_active_version=payload.activate,
        published_at=now if payload.activate else None,
        changelog=payload.changelog,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    if payload.activate:
        template.current_version_id = version.id
        template.status = "published"
    template.updated_at = now
    db.add(template)
    db.commit()
    db.refresh(version)
    return _terms_template_version_out(version)


@router.delete("/terms-templates/{template_id}", status_code=status.HTTP_200_OK)
def archive_terms_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(TermsTemplate).where(TermsTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")
    row.is_active = False
    row.status = "archived"
    row.archived_at = _utcnow()
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()


@router.delete("/terms-templates/{template_id}/permanent", status_code=status.HTTP_200_OK)
def hard_delete_terms_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    row = db.scalar(select(TermsTemplate).where(TermsTemplate.id == template_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")

    version_ids_stmt = select(TermsTemplateVersion.id).where(TermsTemplateVersion.terms_template_id == template_id)

    blockers: list[str] = []
    binding_refs = int(
        db.scalar(
            select(func.count())
            .select_from(QuoteDocumentBinding)
            .where(
                or_(
                    QuoteDocumentBinding.terms_template_id == template_id,
                    QuoteDocumentBinding.terms_template_version_id.in_(version_ids_stmt),
                )
            )
        )
        or 0
    )
    if binding_refs > 0:
        blockers.append(f"{binding_refs} regle(s) d'association documentaire reference(nt) ce modele CGV")

    quote_refs = int(
        db.scalar(
            select(func.count())
            .select_from(Quote)
            .where(
                or_(
                    Quote.terms_template_id == template_id,
                    Quote.terms_template_version_id.in_(version_ids_stmt),
                )
            )
        )
        or 0
    )
    if quote_refs > 0:
        blockers.append(f"{quote_refs} devis reference(nt) ce modele CGV")

    snapshot_refs = int(
        db.scalar(
            select(func.count())
            .select_from(QuoteDocumentSnapshot)
            .where(
                or_(
                    QuoteDocumentSnapshot.terms_template_id == template_id,
                    QuoteDocumentSnapshot.terms_template_version_id.in_(version_ids_stmt),
                )
            )
        )
        or 0
    )
    if snapshot_refs > 0:
        blockers.append(f"{snapshot_refs} snapshot(s) documentaires reference(nt) ce modele CGV")

    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Suppression definitive impossible: {', '.join(blockers)}. Archivez plutot le modele.",
        )

    db.delete(row)
    db.commit()
    return {"deleted": True, "template_id": str(template_id)}


@router.get("/quote-document-bindings", response_model=list[QuoteDocumentBindingOut])
def list_quote_document_bindings(
    active_only: bool = Query(default=False),
    language: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteDocumentBindingOut]:
    stmt = select(QuoteDocumentBinding)
    if active_only:
        stmt = stmt.where(QuoteDocumentBinding.is_active.is_(True))
    if language:
        stmt = stmt.where(func.lower(func.coalesce(QuoteDocumentBinding.language, "")) == language.strip().lower())
    rows = db.scalars(
        stmt.order_by(QuoteDocumentBinding.priority.asc(), QuoteDocumentBinding.updated_at.desc())
    ).all()
    return [_quote_document_binding_out(row) for row in rows]


@router.post("/quote-document-bindings", response_model=QuoteDocumentBindingOut, status_code=status.HTTP_201_CREATED)
def create_quote_document_binding(
    payload: QuoteDocumentBindingUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDocumentBindingOut:
    quote_template_id = payload.quote_template_id
    quote_template_version_id = payload.quote_template_version_id
    terms_template_id = payload.terms_template_id
    terms_template_version_id = payload.terms_template_version_id

    if quote_template_version_id is not None:
        version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote_template_version_id))
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template version not found")
        if quote_template_id is not None and version.quote_template_id != quote_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Quote template version does not match quote_template_id")
        quote_template_id = version.quote_template_id
    if quote_template_id is not None:
        template = db.scalar(select(QuoteTemplate.id).where(QuoteTemplate.id == quote_template_id))
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")

    if terms_template_version_id is not None:
        version = db.scalar(select(TermsTemplateVersion).where(TermsTemplateVersion.id == terms_template_version_id))
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template version not found")
        if terms_template_id is not None and version.terms_template_id != terms_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Terms template version does not match terms_template_id")
        terms_template_id = version.terms_template_id
    if terms_template_id is not None:
        template = db.scalar(select(TermsTemplate.id).where(TermsTemplate.id == terms_template_id))
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")

    now = _utcnow()
    row = QuoteDocumentBinding(
        prospect_type=_normalized_match_value(payload.prospect_type),
        context_type=_normalized_match_value(payload.context_type),
        activity_family=_normalized_match_value(payload.activity_family),
        activity_id=payload.activity_id,
        quote_type_id=payload.quote_type_id,
        language=_normalized_match_value(payload.language),
        currency=_normalized_match_value(payload.currency.upper() if payload.currency else None),
        quote_template_id=quote_template_id,
        quote_template_version_id=quote_template_version_id,
        terms_template_id=terms_template_id,
        terms_template_version_id=terms_template_version_id,
        priority=payload.priority,
        is_active=payload.is_active,
        notes=payload.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote document binding already exists for this scope") from exc
    db.refresh(row)
    return _quote_document_binding_out(row)


@router.patch("/quote-document-bindings/{binding_id}", response_model=QuoteDocumentBindingOut)
def update_quote_document_binding(
    binding_id: UUID,
    payload: QuoteDocumentBindingUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDocumentBindingOut:
    row = db.scalar(select(QuoteDocumentBinding).where(QuoteDocumentBinding.id == binding_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote document binding not found")

    quote_template_id = payload.quote_template_id
    quote_template_version_id = payload.quote_template_version_id
    terms_template_id = payload.terms_template_id
    terms_template_version_id = payload.terms_template_version_id

    if quote_template_version_id is not None:
        version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote_template_version_id))
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template version not found")
        if quote_template_id is not None and version.quote_template_id != quote_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Quote template version does not match quote_template_id")
        quote_template_id = version.quote_template_id
    if quote_template_id is not None:
        template = db.scalar(select(QuoteTemplate.id).where(QuoteTemplate.id == quote_template_id))
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote template not found")

    if terms_template_version_id is not None:
        version = db.scalar(select(TermsTemplateVersion).where(TermsTemplateVersion.id == terms_template_version_id))
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template version not found")
        if terms_template_id is not None and version.terms_template_id != terms_template_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Terms template version does not match terms_template_id")
        terms_template_id = version.terms_template_id
    if terms_template_id is not None:
        template = db.scalar(select(TermsTemplate.id).where(TermsTemplate.id == terms_template_id))
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms template not found")

    row.prospect_type = _normalized_match_value(payload.prospect_type)
    row.context_type = _normalized_match_value(payload.context_type)
    row.activity_family = _normalized_match_value(payload.activity_family)
    row.activity_id = payload.activity_id
    row.quote_type_id = payload.quote_type_id
    row.language = _normalized_match_value(payload.language)
    row.currency = _normalized_match_value(payload.currency.upper() if payload.currency else None)
    row.quote_template_id = quote_template_id
    row.quote_template_version_id = quote_template_version_id
    row.terms_template_id = terms_template_id
    row.terms_template_version_id = terms_template_version_id
    row.priority = payload.priority
    row.is_active = payload.is_active
    row.notes = payload.notes
    row.updated_at = _utcnow()
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote document binding already exists for this scope") from exc
    db.refresh(row)
    return _quote_document_binding_out(row)


@router.delete("/quote-document-bindings/{binding_id}", status_code=status.HTTP_200_OK)
def delete_quote_document_binding(
    binding_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(QuoteDocumentBinding).where(QuoteDocumentBinding.id == binding_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote document binding not found")
    db.delete(row)
    db.commit()


@router.get("/quote-types", response_model=list[QuoteTypeOut])
def list_quote_types(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteTypeOut]:
    stmt = select(QuoteType)
    if active_only:
        stmt = stmt.where(QuoteType.is_active.is_(True))
    rows = db.scalars(stmt.order_by(QuoteType.name.asc())).all()
    return [_quote_type_out(row) for row in rows]


@router.post("/quote-types", response_model=QuoteTypeOut, status_code=status.HTTP_201_CREATED)
def create_quote_type(
    payload: QuoteTypeUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTypeOut:
    now = _utcnow()
    requested_code = (payload.code or "").strip().upper()
    base_code = requested_code or _quote_type_code_from_name(payload.name)
    generated_code = _next_available_quote_type_code(db, base_code=base_code)
    row = QuoteType(
        code=generated_code,
        name=payload.name.strip(),
        description=payload.description,
        default_expiry_days=payload.default_expiry_days,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote type code already exists") from exc
    db.refresh(row)
    return _quote_type_out(row)


@router.patch("/quote-types/{quote_type_id}", response_model=QuoteTypeOut)
def update_quote_type(
    quote_type_id: UUID,
    payload: QuoteTypeUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTypeOut:
    row = db.scalar(select(QuoteType).where(QuoteType.id == quote_type_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote type not found")
    requested_code = (payload.code or "").strip().upper()
    if requested_code:
        row.code = _next_available_quote_type_code(db, base_code=requested_code, exclude_id=row.id)
    elif not (row.code or "").strip():
        row.code = _next_available_quote_type_code(
            db,
            base_code=_quote_type_code_from_name(payload.name),
            exclude_id=row.id,
        )
    row.name = payload.name.strip()
    row.description = payload.description
    row.default_expiry_days = payload.default_expiry_days
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote type code already exists") from exc
    db.refresh(row)
    return _quote_type_out(row)


@router.delete("/quote-types/{quote_type_id}", status_code=status.HTTP_200_OK)
def delete_quote_type(
    quote_type_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(QuoteType).where(QuoteType.id == quote_type_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote type not found")
    in_use = db.scalar(select(Quote.id).where(Quote.quote_type_id == quote_type_id).limit(1))
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote type is used by quotes")
    db.delete(row)
    db.commit()


@router.get("/pricing-catalogs", response_model=list[PricingCatalogOut])
def list_pricing_catalogs(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingCatalogOut]:
    stmt = select(PricingCatalog)
    if active_only:
        stmt = stmt.where(PricingCatalog.is_active.is_(True))
    rows = db.scalars(stmt.order_by(PricingCatalog.effective_from.desc())).all()
    return [_pricing_catalog_out(row) for row in rows]


@router.post("/pricing-catalogs", response_model=PricingCatalogOut, status_code=status.HTTP_201_CREATED)
def create_pricing_catalog(
    payload: PricingCatalogUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingCatalogOut:
    now = _utcnow()
    row = PricingCatalog(
        name=payload.name.strip(),
        school_year_label=payload.school_year_label,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_default=payload.is_default,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    if payload.effective_to is not None and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="effective_to must be >= effective_from")
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_catalog_out(row)


@router.patch("/pricing-catalogs/{catalog_id}", response_model=PricingCatalogOut)
def update_pricing_catalog(
    catalog_id: UUID,
    payload: PricingCatalogUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingCatalogOut:
    row = db.scalar(select(PricingCatalog).where(PricingCatalog.id == catalog_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing catalog not found")
    if payload.effective_to is not None and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="effective_to must be >= effective_from")
    row.name = payload.name.strip()
    row.school_year_label = payload.school_year_label
    row.effective_from = payload.effective_from
    row.effective_to = payload.effective_to
    row.is_default = payload.is_default
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_catalog_out(row)


@router.delete("/pricing-catalogs/{catalog_id}", status_code=status.HTTP_200_OK)
def delete_pricing_catalog(
    catalog_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingCatalog).where(PricingCatalog.id == catalog_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing catalog not found")
    in_use = db.scalar(select(Quote.id).where(Quote.pricing_catalog_id == catalog_id).limit(1))
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pricing catalog is used by quotes")
    db.delete(row)
    db.commit()


@router.get("/pricing-activity-prices", response_model=list[PricingActivityPriceOut])
def list_pricing_activity_prices(
    catalog_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingActivityPriceOut]:
    stmt = select(PricingActivityPrice)
    if catalog_id is not None:
        stmt = stmt.where(PricingActivityPrice.catalog_id == catalog_id)
    rows = db.scalars(stmt.order_by(PricingActivityPrice.created_at.desc())).all()
    return [_pricing_activity_price_out(row) for row in rows]


@router.post("/pricing-activity-prices", response_model=PricingActivityPriceOut, status_code=status.HTTP_201_CREATED)
def upsert_pricing_activity_price(
    payload: PricingActivityPriceUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingActivityPriceOut:
    row = db.scalar(
        select(PricingActivityPrice)
        .where(
            PricingActivityPrice.catalog_id == payload.catalog_id,
            PricingActivityPrice.activity_id == payload.activity_id,
            PricingActivityPrice.location_id.is_(payload.location_id) if payload.location_id is None else PricingActivityPrice.location_id == payload.location_id,
            PricingActivityPrice.student_category.is_(payload.student_category) if payload.student_category is None else PricingActivityPrice.student_category == payload.student_category,
            PricingActivityPrice.pricing_unit == payload.pricing_unit,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = PricingActivityPrice(
            catalog_id=payload.catalog_id,
            activity_id=payload.activity_id,
            location_id=payload.location_id,
            student_category=payload.student_category,
            pricing_unit=payload.pricing_unit,
            unit_price_ttc=payload.unit_price_ttc,
            currency=payload.currency.upper(),
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.unit_price_ttc = payload.unit_price_ttc
        row.currency = payload.currency.upper()
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_activity_price_out(row)


@router.delete("/pricing-activity-prices/{price_id}", status_code=status.HTTP_200_OK)
def delete_pricing_activity_price(
    price_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingActivityPrice).where(PricingActivityPrice.id == price_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing activity price not found")
    db.delete(row)
    db.commit()


@router.get("/pricing-product-prices", response_model=list[PricingProductPriceOut])
def list_pricing_product_prices(
    catalog_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingProductPriceOut]:
    stmt = select(PricingProductPrice)
    if catalog_id is not None:
        stmt = stmt.where(PricingProductPrice.catalog_id == catalog_id)
    rows = db.scalars(stmt.order_by(PricingProductPrice.created_at.desc())).all()
    return [_pricing_product_price_out(row) for row in rows]


@router.post("/pricing-product-prices", response_model=PricingProductPriceOut, status_code=status.HTTP_201_CREATED)
def upsert_pricing_product_price(
    payload: PricingProductPriceUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingProductPriceOut:
    row = db.scalar(
        select(PricingProductPrice)
        .where(
            PricingProductPrice.catalog_id == payload.catalog_id,
            PricingProductPrice.product_id == payload.product_id,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = PricingProductPrice(
            catalog_id=payload.catalog_id,
            product_id=payload.product_id,
            unit_price_ttc=payload.unit_price_ttc,
            currency=payload.currency.upper(),
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.unit_price_ttc = payload.unit_price_ttc
        row.currency = payload.currency.upper()
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_product_price_out(row)


@router.delete("/pricing-product-prices/{price_id}", status_code=status.HTTP_200_OK)
def delete_pricing_product_price(
    price_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingProductPrice).where(PricingProductPrice.id == price_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing product price not found")
    db.delete(row)
    db.commit()


@router.get("/pricing-kit-prices", response_model=list[PricingKitPriceOut])
def list_pricing_kit_prices(
    catalog_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingKitPriceOut]:
    stmt = select(PricingKitPrice)
    if catalog_id is not None:
        stmt = stmt.where(PricingKitPrice.catalog_id == catalog_id)
    rows = db.scalars(stmt.order_by(PricingKitPrice.created_at.desc())).all()
    return [_pricing_kit_price_out(row) for row in rows]


@router.post("/pricing-kit-prices", response_model=PricingKitPriceOut, status_code=status.HTTP_201_CREATED)
def upsert_pricing_kit_price(
    payload: PricingKitPriceUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingKitPriceOut:
    row = db.scalar(
        select(PricingKitPrice)
        .where(
            PricingKitPrice.catalog_id == payload.catalog_id,
            PricingKitPrice.kit_id == payload.kit_id,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = PricingKitPrice(
            catalog_id=payload.catalog_id,
            kit_id=payload.kit_id,
            unit_price_ttc=payload.unit_price_ttc,
            currency=payload.currency.upper(),
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.unit_price_ttc = payload.unit_price_ttc
        row.currency = payload.currency.upper()
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_kit_price_out(row)


@router.delete("/pricing-kit-prices/{price_id}", status_code=status.HTTP_200_OK)
def delete_pricing_kit_price(
    price_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingKitPrice).where(PricingKitPrice.id == price_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing kit price not found")
    db.delete(row)
    db.commit()


@router.get("/solfege-level-rules", response_model=list[SolfegeLevelRuleOut])
def list_solfege_level_rules(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[SolfegeLevelRuleOut]:
    stmt = select(SolfegeLevelRule)
    if active_only:
        stmt = stmt.where(SolfegeLevelRule.is_active.is_(True))
    rows = db.scalars(stmt.order_by(SolfegeLevelRule.level_code.asc(), SolfegeLevelRule.created_at.desc())).all()
    return [_solfege_rule_out(row) for row in rows]


@router.post("/solfege-level-rules", response_model=SolfegeLevelRuleOut, status_code=status.HTTP_201_CREATED)
def upsert_solfege_level_rule(
    payload: SolfegeLevelRuleUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SolfegeLevelRuleOut:
    row = db.scalar(
        select(SolfegeLevelRule)
        .where(
            SolfegeLevelRule.level_code == payload.level_code,
            SolfegeLevelRule.location_id.is_(payload.location_id) if payload.location_id is None else SolfegeLevelRule.location_id == payload.location_id,
            SolfegeLevelRule.modality.is_(payload.modality) if payload.modality is None else SolfegeLevelRule.modality == payload.modality,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = SolfegeLevelRule(
            level_code=payload.level_code,
            duration_minutes=payload.duration_minutes,
            allowed_weekdays=payload.allowed_weekdays,
            allowed_time_slots=payload.allowed_time_slots,
            location_id=payload.location_id,
            modality=payload.modality,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.duration_minutes = payload.duration_minutes
        row.allowed_weekdays = payload.allowed_weekdays
        row.allowed_time_slots = payload.allowed_time_slots
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _solfege_rule_out(row)


@router.delete("/solfege-level-rules/{rule_id}", status_code=status.HTTP_200_OK)
def delete_solfege_level_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(SolfegeLevelRule).where(SolfegeLevelRule.id == rule_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solfege rule not found")
    db.delete(row)
    db.commit()


@router.get("/quote-school-calendars", response_model=list[QuoteSchoolCalendarOut])
def list_quote_school_calendars(
    active_only: bool = Query(default=False),
    location_id: UUID | None = None,
    school_year_label: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteSchoolCalendarOut]:
    rows = _load_quote_school_calendars(db)
    out: list[QuoteSchoolCalendarOut] = []
    normalized_year = (school_year_label or "").strip().lower()
    for raw in rows:
        try:
            item = _calendar_out(raw)
        except Exception:
            continue
        if active_only and not item.is_active:
            continue
        if location_id is not None and item.location_id != location_id:
            continue
        if normalized_year and item.school_year_label.strip().lower() != normalized_year:
            continue
        out.append(item)
    out.sort(key=lambda item: item.updated_at, reverse=True)
    return out


@router.post("/quote-school-calendars", response_model=QuoteSchoolCalendarOut, status_code=status.HTTP_201_CREATED)
def create_quote_school_calendar(
    payload: QuoteSchoolCalendarUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarOut:
    location_ids = _calendar_location_ids_from_payload(payload)
    _validate_calendar_locations_exist(db, location_ids)
    for period in payload.vacation_periods:
        if period.end_date < period.start_date:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Vacation period end date must be after start date")
    rows = _load_quote_school_calendars(db)
    created_records: list[dict[str, object]] = []
    for location_id in location_ids:
        record = _calendar_record_from_payload(payload, row_id=uuid4(), created_at=None, location_id=location_id)
        rows.append(record)
        created_records.append(record)
    _save_quote_school_calendars(db, rows)
    if payload.apply_to_management_planning:
        _apply_school_calendar_to_management_planning(
            db,
            payload=payload,
            location_ids=location_ids,
        )
    db.commit()
    refreshed_rows = _load_quote_school_calendars(db)
    refreshed = next(
        (item for item in refreshed_rows if str(item.get("id") or "") == str(created_records[0].get("id"))),
        created_records[0],
    )
    return _calendar_out(refreshed)


@router.patch("/quote-school-calendars/{calendar_id}", response_model=QuoteSchoolCalendarOut)
def update_quote_school_calendar(
    calendar_id: UUID,
    payload: QuoteSchoolCalendarUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarOut:
    location_ids = _calendar_location_ids_from_payload(payload)
    _validate_calendar_locations_exist(db, location_ids)
    for period in payload.vacation_periods:
        if period.end_date < period.start_date:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Vacation period end date must be after start date")
    rows = _load_quote_school_calendars(db)
    updated: dict[str, object] | None = None
    primary_location_id = location_ids[0]
    for index, raw in enumerate(rows):
        if str(raw.get("id") or "") != str(calendar_id):
            continue
        created_at = _parse_iso_datetime(str(raw.get("created_at") or _utcnow().isoformat()))
        old_row = dict(raw)
        record = _calendar_record_from_payload(
            payload,
            row_id=calendar_id,
            created_at=created_at,
            location_id=primary_location_id,
        )
        _sync_deployed_status_after_payload_change(old_row=old_row, new_row=record)
        rows[index] = record
        updated = record
        break
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")

    for location_id in location_ids[1:]:
        existing_index = next(
            (
                idx
                for idx, raw in enumerate(rows)
                if str(raw.get("location_id") or "") == str(location_id)
                and str(raw.get("school_year_label") or "").strip().lower() == payload.school_year_label.strip().lower()
                and str(raw.get("name") or "").strip().lower() == payload.name.strip().lower()
            ),
            None,
        )
        if existing_index is not None:
            existing_raw = rows[existing_index]
            existing_id = UUID(str(existing_raw.get("id")))
            existing_created_at = _parse_iso_datetime(str(existing_raw.get("created_at") or _utcnow().isoformat()))
            replacement = _calendar_record_from_payload(
                payload,
                row_id=existing_id,
                created_at=existing_created_at,
                location_id=location_id,
            )
            _sync_deployed_status_after_payload_change(old_row=existing_raw, new_row=replacement)
            rows[existing_index] = replacement
            continue
        rows.append(
            _calendar_record_from_payload(
                payload,
                row_id=uuid4(),
                created_at=None,
                location_id=location_id,
            )
        )

    _save_quote_school_calendars(db, rows)
    if payload.apply_to_management_planning:
        _apply_school_calendar_to_management_planning(
            db,
            payload=payload,
            location_ids=location_ids,
        )
    db.commit()
    refreshed_rows = _load_quote_school_calendars(db)
    refreshed = next(
        (item for item in refreshed_rows if str(item.get("id") or "") == str(updated.get("id"))),
        updated,
    )
    return _calendar_out(refreshed)


@router.delete("/quote-school-calendars/{calendar_id}", status_code=status.HTTP_200_OK)
def delete_quote_school_calendar(
    calendar_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    rows = _load_quote_school_calendars(db)
    filtered = [raw for raw in rows if str(raw.get("id") or "") != str(calendar_id)]
    if len(filtered) == len(rows):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    _save_quote_school_calendars(db, filtered)
    db.commit()


@router.get(
    "/quote-school-calendars/{calendar_id}/deployment/preview",
    response_model=QuoteSchoolCalendarDeploymentPreviewOut,
)
def preview_quote_school_calendar_deployment(
    calendar_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarDeploymentPreviewOut:
    rows = _load_quote_school_calendars(db)
    row = next((item for item in rows if str(item.get("id") or "") == str(calendar_id)), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    return _calendar_preview_for_row(db, row=row)


@router.post(
    "/quote-school-calendars/{calendar_id}/deployment",
    response_model=QuoteSchoolCalendarDeploymentActionOut,
)
def deploy_quote_school_calendar(
    calendar_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarDeploymentActionOut:
    rows = _load_quote_school_calendars(db)
    row = next((item for item in rows if str(item.get("id") or "") == str(calendar_id)), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    action = _deploy_calendar_row(db, row=row, actor=user)
    _save_quote_school_calendars(db, rows)
    db.commit()
    return action


@router.post(
    "/quote-school-calendars/{calendar_id}/deployment/sync",
    response_model=QuoteSchoolCalendarDeploymentActionOut,
)
def sync_quote_school_calendar_deployment(
    calendar_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarDeploymentActionOut:
    rows = _load_quote_school_calendars(db)
    row = next((item for item in rows if str(item.get("id") or "") == str(calendar_id)), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    action = _deploy_calendar_row(db, row=row, actor=user)
    _save_quote_school_calendars(db, rows)
    db.commit()
    return action


@router.delete(
    "/quote-school-calendars/{calendar_id}/deployment",
    response_model=QuoteSchoolCalendarDeploymentActionOut,
)
def remove_quote_school_calendar_deployment(
    calendar_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarDeploymentActionOut:
    rows = _load_quote_school_calendars(db)
    row = next((item for item in rows if str(item.get("id") or "") == str(calendar_id)), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    action = _remove_calendar_deployment(db, row=row)
    _save_quote_school_calendars(db, rows)
    db.commit()
    return action


@router.get(
    "/quote-school-calendars/{calendar_id}/generated-blocking-slots",
    response_model=list[QuoteSchoolCalendarGeneratedSlotOut],
)
def list_quote_school_calendar_generated_slots(
    calendar_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteSchoolCalendarGeneratedSlotOut]:
    rows = _load_quote_school_calendars(db)
    row = next((item for item in rows if str(item.get("id") or "") == str(calendar_id)), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    location_id = UUID(str(row.get("location_id")))
    return _list_calendar_generated_slots(db, calendar_id=calendar_id, location_id=location_id)


@router.get("/quote-school-calendars/active/by-location/{location_id}", response_model=QuoteSchoolCalendarResolveOut)
def resolve_quote_school_calendar_for_location(
    location_id: UUID,
    school_year_label: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteSchoolCalendarResolveOut:
    rows = _load_quote_school_calendars(db)
    normalized_year = (school_year_label or "").strip().lower()
    selected: QuoteSchoolCalendarOut | None = None
    for raw in rows:
        try:
            item = _calendar_out(raw)
        except Exception:
            continue
        if not item.is_active:
            continue
        if item.location_id != location_id:
            continue
        if normalized_year and item.school_year_label.strip().lower() != normalized_year:
            continue
        if selected is None or item.updated_at > selected.updated_at:
            selected = item
    if selected is None:
        return QuoteSchoolCalendarResolveOut(calendar=None, holiday_dates=[], closure_dates=[])
    holiday_days = set(selected.holiday_dates)
    closure_days = set(selected.closure_dates)
    deployment_slots = _list_calendar_generated_slots(db, calendar_id=selected.id, location_id=selected.location_id)
    if deployment_slots:
        generated_holidays: set[date] = set()
        generated_closures: set[date] = set()
        for slot in deployment_slots:
            if slot.status.upper() == "CANCELLED":
                continue
            if CALENDAR_DEPLOYMENT_REASON_HOLIDAY in slot.reason_types:
                generated_holidays.add(slot.date)
            if CALENDAR_DEPLOYMENT_REASON_VACATION in slot.reason_types or CALENDAR_DEPLOYMENT_REASON_CLOSURE in slot.reason_types:
                generated_closures.add(slot.date)
        if generated_holidays or generated_closures:
            holiday_days = generated_holidays
            closure_days = generated_closures
    vacation_days = _expand_vacation_periods(selected.vacation_periods)
    merged_closure_days = sorted({*closure_days, *vacation_days})
    return QuoteSchoolCalendarResolveOut(
        calendar=selected,
        holiday_dates=sorted(holiday_days),
        closure_dates=merged_closure_days,
    )


@router.get("/payment-plans", response_model=list[PaymentPlanOut])
def list_payment_plans(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PaymentPlanOut]:
    stmt = select(PaymentPlan)
    if active_only:
        stmt = stmt.where(PaymentPlan.is_active.is_(True))
    rows = db.scalars(stmt.order_by(PaymentPlan.name.asc())).all()
    return [_payment_plan_out(row) for row in rows]


@router.post("/payment-plans", response_model=PaymentPlanOut, status_code=status.HTTP_201_CREATED)
def create_payment_plan(
    payload: PaymentPlanUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentPlanOut:
    now = _utcnow()
    requested_code = (payload.code or "").strip()
    base_code = requested_code or _payment_plan_code_from_name(payload.name)
    generated_code = _next_available_payment_plan_code(db, base_code=base_code)
    row = PaymentPlan(
        code=generated_code,
        name=payload.name.strip(),
        payment_method=payload.payment_method.strip().upper(),
        schedule_type=payload.schedule_type.strip().lower(),
        schedule_rules=payload.schedule_rules,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment plan code already exists") from exc
    db.refresh(row)
    return _payment_plan_out(row)


@router.patch("/payment-plans/{plan_id}", response_model=PaymentPlanOut)
def update_payment_plan(
    plan_id: UUID,
    payload: PaymentPlanUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentPlanOut:
    row = db.scalar(select(PaymentPlan).where(PaymentPlan.id == plan_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment plan not found")
    requested_code = (payload.code or "").strip()
    base_code = requested_code or _payment_plan_code_from_name(payload.name)
    row.code = _next_available_payment_plan_code(db, base_code=base_code, exclude_id=row.id)
    row.name = payload.name.strip()
    row.payment_method = payload.payment_method.strip().upper()
    row.schedule_type = payload.schedule_type.strip().lower()
    row.schedule_rules = payload.schedule_rules
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment plan code already exists") from exc
    db.refresh(row)
    return _payment_plan_out(row)


@router.delete("/payment-plans/{plan_id}", status_code=status.HTTP_200_OK)
def delete_payment_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PaymentPlan).where(PaymentPlan.id == plan_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment plan not found")
    in_use = db.scalar(select(Quote.id).where(Quote.payment_plan_id == row.id).limit(1))
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment plan is used by quotes")
    db.delete(row)
    db.commit()
