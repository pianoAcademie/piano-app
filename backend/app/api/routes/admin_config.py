from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.catalog import CourseSession, CourseType, CreditType, DeliveryMode, SessionStatus
from app.models.external_content import (
    CourseTypeContentMapping,
    ExternalContentCourse,
    ExternalContentLesson,
    ExternalContentProvider,
    ExternalContentSection,
    ExternalContentStatus,
)
from app.models.ops import AppSetting, LegalEntity
from app.models.payout import ProfessorPayGridBracket, ProfessorPayGridPeriod, ProfessorPayGridRule
from app.models.product_catalog import ProductCategory
from app.models.plan import (
    Plan,
    PlanCreditGrant,
    PlanCreditGrantsRelation,
    PlanEntitlement,
    PlanKind,
    PlanPriceTaxMode,
    PlanRestrictionPeriod,
)
from app.models.subscription_engine import SubscriptionNotificationPolicy, SubscriptionRetryPolicy
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminActivityOut,
    AdminActivityContentMappingOut,
    AdminActivityContentMappingsReplaceRequest,
    AdminActivityUpdateRequest,
    AdminActivityUpsertRequest,
    AdminCreditTypeOut,
    AdminCreditTypeUpdateRequest,
    AdminCreditTypeUpsertRequest,
    AdminConfigAccountOut,
    AdminConfigAccountUpdateRequest,
    AdminExternalContentCourseOut,
    AdminExternalContentSettingsOut,
    AdminExternalContentSettingsUpdateRequest,
    AdminExternalContentSyncOut,
    AdminFormulaOut,
    AdminFormulaCreditGrantIn,
    AdminFormulaCreditGrantOut,
    AdminFormulaRestrictionIn,
    AdminFormulaRestrictionOut,
    AdminFormulaUpdateRequest,
    AdminFormulaUpsertRequest,
    AdminPaymentMethodOptionOut,
    AdminPaymentMethodsOut,
    AdminPaymentMethodsUpdateRequest,
    AdminProductCategoriesOut,
    AdminProductCategoriesUpdateRequest,
    AdminReferralCategorySettingsOut,
    AdminReferralProgramSettingsOut,
    AdminReferralProgramSettingsUpdateRequest,
    AdminPaymentProviderOut,
    AdminPaymentProviderUpdateRequest,
    AdminMessagingChannel,
    AdminMessagingCustomTemplateCreateRequest,
    AdminMessagingCustomTemplateUpdateRequest,
    AdminMessagingSettingsOut,
    AdminMessagingSettingsUpdateRequest,
    AdminMessagingTemplateKind,
    AdminMessagingTemplateOut,
    AdminMessagingPredefinedTemplateUpdateRequest,
    AdminInvoiceTemplateOut,
    AdminInvoiceTemplateUpdateRequest,
    AdminInvoiceNumberingOut,
    AdminInvoiceNumberingUpdateRequest,
    AdminLegalEntityCreateRequest,
    AdminLegalEntityOut,
    AdminLegalEntityUpdateRequest,
    AdminProfessorDefaultGridLineInput,
    AdminProfessorDefaultGridLineOut,
    AdminProfessorDefaultGridOut,
    AdminProfessorDefaultGridRuleOut,
    AdminProfessorDefaultGridUpdateRequest,
    AdminProfessorPayGridPeriodCreateRequest,
    AdminProfessorPayGridPeriodDetailOut,
    AdminProfessorPayGridPeriodOut,
    AdminProfessorPayGridPeriodRulesUpdateRequest,
    AdminProfessorPayGridPeriodUpdateRequest,
    AdminSubscriptionSettingsOut,
    AdminSubscriptionSettingsUpdateRequest,
)
from app.services.external_content import (
    DEFAULT_WORDPRESS_LEARNDASH_COURSES_PATH,
    WORDPRESS_LEARNDASH_BASE_URL_SETTING_KEY,
    WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY,
    WORDPRESS_LEARNDASH_COURSES_ENDPOINT_SETTING_KEY,
    WORDPRESS_LEARNDASH_TIMEOUT_SECONDS_SETTING_KEY,
    list_content_course_mappings_for_course_type,
    replace_course_type_content_mappings,
    resolve_wordpress_learndash_sync_endpoint,
    sync_wordpress_learndash_catalog,
)
from app.services.professor_contracts import contract_mode_from_course_type
from app.services.professor_default_grid import (
    DefaultProfessorGridLine,
    DefaultProfessorGridRule,
    archive_default_professor_grid_period,
    create_default_professor_grid_period,
    get_default_professor_grid_period_snapshot,
    list_default_professor_grid_periods,
    load_default_professor_grid,
    load_default_professor_grid_for_period,
    save_default_professor_grid,
    save_default_professor_grid_for_period,
    update_default_professor_grid_period,
)
from app.services.payment_provider import (
    CAPABILITIES_BY_PROVIDER,
    MOLLIE_LIVE_API_KEY_SETTING_KEY,
    MOLLIE_TEST_API_KEY_SETTING_KEY,
    PAYMENT_MODE_SETTING_KEY,
    PAYMENT_PROVIDER_SETTING_KEY,
    PAYMENT_WEBHOOK_SECRET_SETTING_KEY,
    PAYPLUG_LIVE_SECRET_SETTING_KEY,
    PAYPLUG_TEST_SECRET_SETTING_KEY,
    STRIPE_LIVE_SECRET_SETTING_KEY,
    STRIPE_TEST_SECRET_SETTING_KEY,
    STRIPE_WEBHOOK_SECRET_SETTING_KEY,
    PaymentMode,
    PaymentProvider,
    mask_secret as mask_payment_secret,
    parse_mode as parse_payment_mode,
    parse_provider as parse_payment_provider,
    resolve_mode as resolve_payment_mode,
    resolve_provider as resolve_payment_provider,
    resolve_secret_values as resolve_payment_secret_values,
    set_setting_value as set_payment_setting_value,
)
from app.services.referrals import REFERRAL_CATEGORIES, REFERRAL_PROGRAM_SETTING_KEY, referral_program_config
from app.services.messaging_templates import (
    create_custom_template,
    delete_custom_template,
    list_messaging_templates,
    load_messaging_settings,
    reset_predefined_template,
    save_messaging_settings,
    update_custom_template,
    upsert_predefined_template,
)
from app.services.invoice_documents import (
    INVOICE_TEMPLATE_VARIABLES_HINT,
    get_invoice_template,
    get_invoice_numbering,
    preview_invoice_number,
    save_invoice_numbering,
    save_invoice_template,
)

router = APIRouter(prefix="/admin")

PAYMENT_METHOD_CATALOG: list[tuple[str, str]] = [
    ("CARD_ONLINE", "CB en ligne (Stripe pour les abonnements, Payplug sinon)"),
    ("CARD_TERMINAL", "CB sur place (TPE)"),
    ("CHECK", "Cheque"),
    ("CASH", "Especes"),
    ("PAYPAL", "PayPal"),
    ("SEPA_DEBIT", "Prelevement SEPA"),
    ("BANK_TRANSFER", "Virement bancaire"),
    ("FACTURATION_AUTO", "Paiement sur facture"),
]
PAYMENT_METHOD_CODES = {code for code, _ in PAYMENT_METHOD_CATALOG}
SUPPORTED_CURRENCIES = {"EUR", "USD"}
ACCOUNT_ALLOWED_CURRENCIES_KEY = "config_account_allowed_currencies"
ACCOUNT_DEFAULT_CURRENCY_KEY = "config_account_default_currency"
ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODE_KEY = "config_account_client_balance_default_date_mode"
ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODES = {"TODAY", "PACKAGE_END"}

ACCOUNT_SETTING_MAP = {
    "contact_first_name": "config_account_contact_first_name",
    "contact_last_name": "config_account_contact_last_name",
    "contact_email": "config_account_contact_email",
    "contact_phone": "config_account_contact_phone",
    "company_name": "config_account_company_name",
    "club_name": "config_account_club_name",
    "siret": "config_account_siret",
    "vat_number": "config_account_vat_number",
    "vat_default_rate": "config_account_vat_default_rate",
    "website": "config_account_website",
    "address_line": "config_account_address_line",
    "postal_code": "config_account_postal_code",
    "city": "config_account_city",
    "country": "config_account_country",
    "bank_transfer_account_holder": "bank_transfer_account_holder",
    "bank_transfer_iban": "bank_transfer_iban",
    "bank_transfer_bic": "bank_transfer_bic",
    "legal_terms": "config_account_legal_terms",
    "logo_data_url": "config_account_logo_data_url",
}

SUBSCRIPTION_SETTING_DEFAULTS = {
    "config_subscription_direct_debit_day": "",
    "config_subscription_allow_card_subscriptions": "true",
    "config_subscription_add_contract_signature": "true",
    "config_subscription_close_expired_subscriptions": "true",
    "config_subscription_allow_promotional_start_period": "false",
    "config_subscription_allow_prorata_card": "false",
    "config_subscription_allow_prorata_sepa": "false",
    "config_subscription_online_resiliation_enabled": "true",
    "config_subscription_allow_booking_during_payment_alert": "true",
}
DEFAULT_SUBSCRIPTION_RETRY_POLICY_CODE = "DEFAULT_MONTHLY"
DEFAULT_SUBSCRIPTION_NOTIFICATION_POLICY_CODE = "DEFAULT_SUBSCRIPTION_NOTIFICATIONS"

PAYMENT_METHODS_SETTING_KEY = "config_payment_methods_enabled"
PAYMENT_METHODS_LEGAL_ENTITY_MAP_SETTING_KEY = "config_payment_methods_legal_entity_map_v1"
PRODUCT_CATEGORIES_SETTING_KEY = "config_products_categories_v1"
MANUAL_PAYMENT_METHOD_CODES_WITH_DEFAULT_ENTITY = {"BANK_TRANSFER", "CHECK", "CASH"}
LEGAL_ENTITY_LEGAL_FORMS = {"SAS", "SA", "SARL", "EURL"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_product_categories(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = str(raw or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized[:120])
    return out


def _parse_product_categories(raw: str) -> list[str]:
    if not raw.strip():
        return []
    tokens = re.split(r"[\n,;]+", raw)
    return _normalize_product_categories(tokens)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().upper())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "FORMULE"


def _new_plan_code(base_name: str) -> str:
    return f"FORM_{_slugify(base_name)[:40]}_{uuid4().hex[:6].upper()}"


def _new_activity_code(base_name: str) -> str:
    return f"ACT_{_slugify(base_name)[:40]}_{uuid4().hex[:6].upper()}"


def _new_credit_type_code(base_name: str) -> str:
    return f"CREDIT_{_slugify(base_name)[:36]}_{uuid4().hex[:4].upper()}"


def _normalize_activity_code(raw_code: str | None, *, fallback_name: str) -> str:
    if raw_code and raw_code.strip():
        return _slugify(raw_code)
    return _new_activity_code(fallback_name)


def _normalize_credit_type_code(raw_code: str | None, *, fallback_name: str) -> str:
    if raw_code and raw_code.strip():
        normalized = _slugify(raw_code)
        if not normalized.startswith("CREDIT_"):
            return f"CREDIT_{normalized}"
        return normalized
    return _new_credit_type_code(fallback_name)


def _normalize_color_hex(raw_color: str | None) -> str:
    value = (raw_color or "").strip()
    if not value:
        return "#94C973"
    normalized = value.upper()
    if not normalized.startswith("#"):
        normalized = f"#{normalized}"
    if not re.fullmatch(r"#[0-9A-F]{6}", normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid color_hex (expected #RRGGBB)",
        )
    return normalized


def _is_vacation_service_code(service_code: str | None) -> bool:
    normalized = (service_code or "").strip().upper()
    return normalized.startswith("VACATION")


def _validate_activity_duration(*, service_code: str | None, duration_minutes: int) -> None:
    if _is_vacation_service_code(service_code):
        if duration_minutes < 600 or duration_minutes > 1440:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="For VACATION activities, duration_minutes must be between 600 and 1440",
            )


def _normalize_activity_capacity(*, allows_student_bookings: bool, capacity: int) -> int:
    if not allows_student_bookings:
        return 0
    return capacity


def _serialize_activity(
    activity: CourseType,
    *,
    credit_type_by_id: dict[UUID, CreditType],
    legal_entity_by_id: dict[UUID, LegalEntity],
    content_course_rows: list[tuple[UUID, str]] | None = None,
) -> AdminActivityOut:
    credit_type = credit_type_by_id.get(activity.credit_type_id) if activity.credit_type_id is not None else None
    legal_entity = (
        legal_entity_by_id.get(activity.seller_legal_entity_id) if activity.seller_legal_entity_id is not None else None
    )
    payor_legal_entity = (
        legal_entity_by_id.get(activity.payor_legal_entity_id) if activity.payor_legal_entity_id is not None else None
    )
    return AdminActivityOut(
        id=activity.id,
        code=activity.code,
        name=activity.name,
        description=activity.description,
        service_code=activity.service_code,
        seller_legal_entity_id=activity.seller_legal_entity_id,
        seller_legal_entity_name=legal_entity.name if legal_entity is not None else None,
        payor_legal_entity_id=activity.payor_legal_entity_id,
        payor_legal_entity_name=payor_legal_entity.name if payor_legal_entity is not None else None,
        credit_type_id=credit_type.id if credit_type is not None else None,
        credit_type_code=credit_type.code if credit_type is not None else None,
        credit_type_name=credit_type.name if credit_type is not None else None,
        duration_minutes=activity.duration_minutes,
        color_hex=activity.color_hex,
        mode=activity.mode,
        requires_professor=bool(activity.requires_professor),
        allows_student_bookings=bool(activity.allows_student_bookings),
        supports_student_time_overrides=bool(activity.supports_student_time_overrides),
        default_capacity=activity.default_capacity,
        default_hourly_rate=activity.default_hourly_rate,
        default_course_rate_ttc=activity.default_course_rate_ttc,
        email_reminder_hours_before_start=activity.email_reminder_hours_before_start,
        sms_reminder_hours_before_start=activity.sms_reminder_hours_before_start,
        min_booking_notice_hours_override=activity.min_booking_notice_hours_override,
        cancellation_deadline_hours_override=activity.cancellation_deadline_hours_override,
        auto_cancel_if_booked_less_than_override=activity.auto_cancel_if_booked_less_than_override,
        auto_cancel_hours_before_start_override=activity.auto_cancel_hours_before_start_override,
        auto_cancel_rule_enabled=bool(activity.auto_cancel_rule_enabled),
        exclude_holidays_in_recurrence=bool(activity.exclude_holidays_in_recurrence),
        exclude_school_vacations_in_recurrence=bool(activity.exclude_school_vacations_in_recurrence),
        active=activity.active,
        content_course_ids=[content_course_id for content_course_id, _ in (content_course_rows or [])],
        content_course_titles=[content_course_title for _, content_course_title in (content_course_rows or [])],
    )


def _serialize_credit_type(
    credit_type: CreditType,
    *,
    activity_rows: list[tuple[UUID, str]],
) -> AdminCreditTypeOut:
    return AdminCreditTypeOut(
        id=credit_type.id,
        code=credit_type.code,
        name=credit_type.name,
        description=credit_type.description,
        active=credit_type.active,
        activity_ids=[activity_id for activity_id, _ in activity_rows],
        activity_names=[name for _, name in activity_rows],
        activity_count=len(activity_rows),
    )


def _activities_by_credit_type_id(
    db: Session,
    *,
    include_inactive: bool = True,
) -> dict[UUID, list[tuple[UUID, str]]]:
    stmt = select(CourseType.id, CourseType.name, CourseType.credit_type_id).where(CourseType.credit_type_id.is_not(None))
    if not include_inactive:
        stmt = stmt.where(CourseType.active.is_(True))

    rows = db.execute(stmt).all()
    result: dict[UUID, list[tuple[UUID, str]]] = {}
    for activity_id, activity_name, credit_type_id in rows:
        if credit_type_id is None:
            continue
        result.setdefault(credit_type_id, []).append((activity_id, activity_name))

    for credit_type_id in result:
        result[credit_type_id].sort(key=lambda row: row[1].casefold())
    return result


def _content_courses_by_activity_id(
    db: Session,
    *,
    active_only: bool = True,
) -> dict[UUID, list[tuple[UUID, str]]]:
    stmt = (
        select(
            CourseTypeContentMapping.course_type_id,
            ExternalContentCourse.id,
            ExternalContentCourse.title,
        )
        .join(ExternalContentCourse, ExternalContentCourse.id == CourseTypeContentMapping.content_course_id)
        .order_by(
            CourseTypeContentMapping.course_type_id.asc(),
            CourseTypeContentMapping.sort_order.asc(),
            ExternalContentCourse.title.asc(),
        )
    )
    if active_only:
        stmt = stmt.where(CourseTypeContentMapping.active.is_(True))
    rows = db.execute(stmt).all()
    result: dict[UUID, list[tuple[UUID, str]]] = {}
    for course_type_id, content_course_id, title in rows:
        result.setdefault(course_type_id, []).append((content_course_id, title))
    return result


def _serialize_external_content_course(
    course: ExternalContentCourse,
    *,
    sections_count: int,
    lessons_count: int,
) -> AdminExternalContentCourseOut:
    return AdminExternalContentCourseOut(
        id=course.id,
        provider=course.provider.value,
        external_id=course.external_id,
        slug=course.slug,
        title=course.title,
        summary=course.summary,
        level_code=course.level_code,
        status=course.status.value,
        cover_image_url=course.cover_image_url,
        sections_count=sections_count,
        lessons_count=lessons_count,
        last_synced_at=course.last_synced_at,
    )


def _serialize_activity_content_mapping(
    mapping: CourseTypeContentMapping,
    course: ExternalContentCourse,
) -> AdminActivityContentMappingOut:
    return AdminActivityContentMappingOut(
        id=mapping.id,
        course_type_id=mapping.course_type_id,
        content_course_id=mapping.content_course_id,
        access_rule=mapping.access_rule.value,
        sort_order=mapping.sort_order,
        active=bool(mapping.active),
        content_course_title=course.title,
        content_course_level_code=course.level_code,
        content_course_status=course.status.value,
        content_course_provider=course.provider.value,
        content_course_external_id=course.external_id,
    )


def _credit_type_by_id(db: Session) -> dict[UUID, CreditType]:
    rows = db.scalars(select(CreditType).order_by(CreditType.name.asc())).all()
    return {row.id: row for row in rows}


def _resolve_credit_type(
    db: Session,
    *,
    credit_type_id: UUID,
    allow_inactive: bool = False,
) -> CreditType:
    credit_type = db.scalar(select(CreditType).where(CreditType.id == credit_type_id))
    if credit_type is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown credit type")
    if not allow_inactive and not credit_type.active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected credit type is inactive")
    return credit_type


def _normalize_legal_entity_text(value: str | None, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    if not normalized:
        return None
    if max_length is not None:
        return normalized[:max_length]
    return normalized


def _normalize_country_code(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="country_code must contain exactly 2 letters",
        )
    return normalized


def _normalize_invoice_prefix(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9_-]+", "", value.strip().upper())
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invoice_prefix is required",
        )
    return normalized[:20]


def _ensure_legal_entity_minimum_fields(*, name: str | None, country_code: str | None, invoice_prefix: str | None) -> None:
    if not (name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is required",
        )
    if not (country_code or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="country_code is required",
        )
    if not (invoice_prefix or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invoice_prefix is required",
        )


def _normalize_legal_form(value: str | None) -> str | None:
    normalized = _normalize_legal_entity_text(value, max_length=20)
    if normalized is None:
        return None
    upper_value = normalized.upper()
    if upper_value not in LEGAL_ENTITY_LEGAL_FORMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="legal_form is invalid",
        )
    return upper_value


def _legal_entity_by_id(db: Session) -> dict[UUID, LegalEntity]:
    rows = db.scalars(select(LegalEntity).order_by(LegalEntity.name.asc())).all()
    return {row.id: row for row in rows}


def _resolve_legal_entity(
    db: Session,
    *,
    legal_entity_id: UUID,
    allow_inactive: bool = False,
) -> LegalEntity:
    entity = db.scalar(select(LegalEntity).where(LegalEntity.id == legal_entity_id))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown legal entity")
    if not allow_inactive and not entity.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected legal entity is inactive")
    return entity


def _legacy_billing_entity_code_from_legal_entity(entity: LegalEntity) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", (entity.name or "").strip().upper())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = "LEGAL_ENTITY"
    return normalized[:40]


def _serialize_legal_entity(entity: LegalEntity) -> AdminLegalEntityOut:
    return AdminLegalEntityOut(
        id=entity.id,
        name=entity.name,
        siren=entity.siren,
        siret=entity.siret,
        vat_number=entity.vat_number,
        address_text=entity.address_text,
        accounting_email=entity.accounting_email,
        phone=entity.phone,
        legal_form=entity.legal_form,
        share_capital=entity.share_capital,
        country_code=entity.country_code,
        invoice_prefix=entity.invoice_prefix,
        invoice_next_number=entity.invoice_next_number,
        default_payment_provider=(entity.default_payment_provider or PaymentProvider.PAYPLUG.value),
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _get_setting(db: Session, key: str) -> AppSetting | None:
    return db.scalar(select(AppSetting).where(AppSetting.key == key))


def _set_setting(db: Session, key: str, value: str) -> None:
    setting = _get_setting(db, key)
    now = _utcnow()
    if setting is None:
        setting = AppSetting(key=key, value=value, updated_at=now)
        db.add(setting)
        return

    setting.value = value
    setting.updated_at = now


def _get_setting_value(db: Session, key: str, default: str = "") -> str:
    setting = _get_setting(db, key)
    if setting is None:
        return default
    return setting.value


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = int(stripped)
    except ValueError:
        return None
    return parsed


def _external_content_settings_updated_at(db: Session) -> datetime | None:
    keys = (
        WORDPRESS_LEARNDASH_BASE_URL_SETTING_KEY,
        WORDPRESS_LEARNDASH_COURSES_ENDPOINT_SETTING_KEY,
        WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY,
        WORDPRESS_LEARNDASH_TIMEOUT_SECONDS_SETTING_KEY,
    )
    rows = db.scalars(select(AppSetting).where(AppSetting.key.in_(keys))).all()
    if not rows:
        return None
    return max((row.updated_at for row in rows if row.updated_at is not None), default=None)


def _serialize_external_content_settings(db: Session) -> AdminExternalContentSettingsOut:
    base_url = _get_setting_value(db, WORDPRESS_LEARNDASH_BASE_URL_SETTING_KEY, "").strip()
    courses_endpoint = _get_setting_value(db, WORDPRESS_LEARNDASH_COURSES_ENDPOINT_SETTING_KEY, "").strip()
    bearer_token = _get_setting_value(db, WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY, "").strip()
    timeout_seconds = _as_int_or_none(_get_setting_value(db, WORDPRESS_LEARNDASH_TIMEOUT_SECONDS_SETTING_KEY, "")) or 20
    resolved_endpoint_url: str | None = None
    try:
        resolved_endpoint_url, _, _ = resolve_wordpress_learndash_sync_endpoint(db)
    except ValueError:
        if base_url:
            resolved_endpoint_url = f"{base_url.rstrip('/')}{DEFAULT_WORDPRESS_LEARNDASH_COURSES_PATH}"
    return AdminExternalContentSettingsOut(
        base_url=base_url,
        courses_endpoint=courses_endpoint,
        resolved_endpoint_url=resolved_endpoint_url,
        bearer_token_configured=bool(bearer_token),
        bearer_token_masked=mask_payment_secret(bearer_token),
        timeout_seconds=max(5, timeout_seconds),
        updated_at=_external_content_settings_updated_at(db),
    )


def _default_subscription_retry_policy(db: Session) -> SubscriptionRetryPolicy:
    row = db.scalar(
        select(SubscriptionRetryPolicy).where(
            SubscriptionRetryPolicy.code == DEFAULT_SUBSCRIPTION_RETRY_POLICY_CODE
        )
    )
    if row is not None:
        return row

    now = _utcnow()
    row = SubscriptionRetryPolicy(
        code=DEFAULT_SUBSCRIPTION_RETRY_POLICY_CODE,
        name="Default monthly retry policy",
        first_retry_delay_days=1,
        max_auto_attempts=2,
        move_to_pre_termination_after_failed_attempts=2,
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _default_subscription_notification_policy(db: Session) -> SubscriptionNotificationPolicy:
    row = db.scalar(
        select(SubscriptionNotificationPolicy).where(
            SubscriptionNotificationPolicy.code == DEFAULT_SUBSCRIPTION_NOTIFICATION_POLICY_CODE
        )
    )
    if row is not None:
        return row

    now = _utcnow()
    row = SubscriptionNotificationPolicy(
        code=DEFAULT_SUBSCRIPTION_NOTIFICATION_POLICY_CODE,
        name="Default subscription notifications",
        on_success_customer_enabled=True,
        on_success_admin_enabled=True,
        on_first_failure_customer_enabled=True,
        on_first_failure_admin_enabled=True,
        on_final_failure_customer_enabled=True,
        on_final_failure_admin_enabled=True,
        active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _normalize_methods(codes: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = raw.strip().upper()
        if not code:
            continue
        if code not in PAYMENT_METHOD_CODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Payment method not supported: {code}",
            )
        if code in seen:
            continue
        seen.add(code)
        unique.append(code)
    return unique


def _load_payment_method_legal_entity_map(db: Session) -> dict[str, UUID]:
    raw = _get_setting_value(db, PAYMENT_METHODS_LEGAL_ENTITY_MAP_SETTING_KEY, "")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, UUID] = {}
    for raw_code, raw_entity_id in parsed.items():
        code = str(raw_code or "").strip().upper()
        if code not in MANUAL_PAYMENT_METHOD_CODES_WITH_DEFAULT_ENTITY:
            continue
        entity_id_text = str(raw_entity_id or "").strip()
        if not entity_id_text:
            continue
        try:
            out[code] = UUID(entity_id_text)
        except ValueError:
            continue
    return out


def _validate_default_grid_rules(line: AdminProfessorDefaultGridLineInput, *, line_index: int) -> None:
    ranges: list[tuple[int, int | None]] = []
    for rule_index, rule in enumerate(line.rules):
        if rule.max_students is not None and rule.max_students < rule.min_students:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Line {line_index + 1} rule {rule_index + 1}: max_students must be >= min_students",
            )
        ranges.append((rule.min_students, rule.max_students))

    ranges.sort(key=lambda item: (item[0], item[1] if item[1] is not None else 10**9))
    for idx, (min_students, _) in enumerate(ranges):
        if idx == 0:
            continue
        previous_min, previous_max = ranges[idx - 1]
        if previous_max is None or min_students <= previous_max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Line {line_index + 1}: overlapping headcount rules",
            )


def _normalize_default_grid_lines(
    *,
    db: Session,
    lines: list[AdminProfessorDefaultGridLineInput],
) -> list[DefaultProfessorGridLine]:
    deduped_lines: list[AdminProfessorDefaultGridLineInput] = []
    seen: set[UUID] = set()
    for line in lines:
        if line.course_type_id in seen:
            continue
        seen.add(line.course_type_id)
        deduped_lines.append(line)

    if not deduped_lines:
        return []

    course_type_ids = [line.course_type_id for line in deduped_lines]
    course_types = db.scalars(select(CourseType.id).where(CourseType.id.in_(course_type_ids))).all()
    found_ids = set(course_types)
    missing_ids = [str(course_type_id) for course_type_id in course_type_ids if course_type_id not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course type(s) not found: {', '.join(missing_ids)}",
        )

    normalized: list[DefaultProfessorGridLine] = []
    for line_index, line in enumerate(deduped_lines):
        if line.default_hourly_rate is None and not line.rules:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Line {line_index + 1}: default_hourly_rate or at least one headcount rule is required",
            )
        _validate_default_grid_rules(line, line_index=line_index)

        rules = [
            DefaultProfessorGridRule(
                min_students=rule.min_students,
                max_students=rule.max_students,
                hourly_rate=Decimal(rule.hourly_rate),
            )
            for rule in line.rules
        ]
        normalized.append(
            DefaultProfessorGridLine(
                course_type_id=line.course_type_id,
                default_hourly_rate=Decimal(line.default_hourly_rate) if line.default_hourly_rate is not None else None,
                rules=rules,
            )
        )
    return normalized


def _serialize_default_professor_grid_lines(
    db: Session,
    *,
    lines: list[DefaultProfessorGridLine],
) -> list[AdminProfessorDefaultGridLineOut]:
    if not lines:
        return []
    course_type_ids = [line.course_type_id for line in lines]
    rows = db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all()
    by_id = {row.id: row for row in rows}

    serialized_lines: list[AdminProfessorDefaultGridLineOut] = []
    for index, line in enumerate(lines):
        course_type = by_id.get(line.course_type_id)
        if course_type is None:
            continue

        serialized_lines.append(
            AdminProfessorDefaultGridLineOut(
                course_type_id=course_type.id,
                course_type_name=course_type.name,
                mode=contract_mode_from_course_type(course_type),
                reference_duration_minutes=course_type.duration_minutes,
                default_hourly_rate=line.default_hourly_rate,
                display_order=index,
                rules=[
                    AdminProfessorDefaultGridRuleOut(
                        min_students=rule.min_students,
                        max_students=rule.max_students,
                        hourly_rate=rule.hourly_rate,
                        display_order=rule_index,
                    )
                    for rule_index, rule in enumerate(line.rules)
                ],
            )
        )
    return serialized_lines


def _serialize_default_professor_grid(db: Session) -> AdminProfessorDefaultGridOut:
    lines, updated_at = load_default_professor_grid(db)
    periods = list_default_professor_grid_periods(db)
    active_period = next((period for period in periods if period.is_active), None)
    serialized_lines = _serialize_default_professor_grid_lines(db, lines=lines)
    return AdminProfessorDefaultGridOut(
        lines=serialized_lines,
        updated_at=updated_at,
        active_period_id=active_period.id if active_period is not None else None,
        active_period_start_date=active_period.start_date if active_period is not None else None,
        active_period_end_date=active_period.end_date if active_period is not None else None,
    )


def _serialize_default_professor_grid_period(period: object) -> AdminProfessorPayGridPeriodOut:
    if isinstance(period, AdminProfessorPayGridPeriodOut):
        return period
    return AdminProfessorPayGridPeriodOut(
        id=period.id,
        start_date=period.start_date,
        end_date=period.end_date,
        status=period.status,
        notes=period.notes,
        is_active=period.is_active,
        is_future=period.is_future,
        is_archived=period.is_archived,
        created_at=period.created_at,
        updated_at=period.updated_at,
        rules_count=period.rules_count,
    )


def _normalize_payment_provider(raw: str) -> PaymentProvider:
    normalized = (raw or "").strip().upper()
    allowed = {provider.value for provider in PaymentProvider}
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payment provider not supported: {raw}",
        )
    return parse_payment_provider(normalized)


def _normalize_payment_mode(raw: str) -> PaymentMode:
    return parse_payment_mode(raw)


def _normalized_secret(raw: str | None, *, max_length: int = 255) -> str:
    if raw is None:
        return ""
    candidate = raw.strip()
    if not candidate:
        return ""
    if len(candidate) > max_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment secret too long",
        )
    return candidate


def _validate_provider_keys(
    *,
    payplug_test_secret: str,
    payplug_live_secret: str,
    mollie_test_api_key: str,
    mollie_live_api_key: str,
    stripe_test_secret: str,
    stripe_live_secret: str,
    stripe_webhook_secret: str,
) -> None:
    if payplug_test_secret and not payplug_test_secret.startswith("sk_test_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payplug test key must start with sk_test_")
    if payplug_live_secret and not payplug_live_secret.startswith("sk_live_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payplug live key must start with sk_live_")
    if mollie_test_api_key and not mollie_test_api_key.startswith("test_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mollie test key must start with test_")
    if mollie_live_api_key and not mollie_live_api_key.startswith("live_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mollie live key must start with live_")
    if stripe_test_secret and not stripe_test_secret.startswith("sk_test_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe test key must start with sk_test_")
    if stripe_live_secret and not stripe_live_secret.startswith("sk_live_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe live key must start with sk_live_")
    if stripe_webhook_secret and not stripe_webhook_secret.startswith("whsec_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe webhook secret must start with whsec_")


def _normalize_currency_codes(codes: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = raw.strip().upper()
        if not code:
            continue
        if code not in SUPPORTED_CURRENCIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Currency not supported: {code}",
            )
        if code in seen:
            continue
        seen.add(code)
        unique.append(code)
    return unique


def _parse_allowed_currencies(raw: str | None) -> list[str]:
    if raw is None:
        return ["EUR", "USD"]
    parsed: list[str] = []
    seen: set[str] = set()
    for value in raw.split(","):
        code = value.strip().upper()
        if not code or code in seen or code not in SUPPORTED_CURRENCIES:
            continue
        seen.add(code)
        parsed.append(code)
    if not parsed:
        return ["EUR"]
    return parsed


def _parse_default_currency(raw: str | None, allowed: list[str]) -> str:
    candidate = (raw or "").strip().upper()
    if not candidate or candidate not in SUPPORTED_CURRENCIES:
        candidate = "EUR"
    if candidate not in allowed:
        return allowed[0] if allowed else "EUR"
    return candidate


def _normalize_option_values(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _normalize_entitlement_ids(
    db: Session,
    course_type_ids: list[UUID],
    *,
    require_credit_mapping: bool = False,
) -> list[UUID]:
    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for course_type_id in course_type_ids:
        if course_type_id in seen:
            continue
        seen.add(course_type_id)
        unique_ids.append(course_type_id)

    if not unique_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one course type entitlement is required",
        )

    rows = db.execute(
        select(CourseType.id, CourseType.name, CourseType.active, CourseType.credit_type_id).where(CourseType.id.in_(unique_ids))
    ).all()
    by_id = {
        course_type_id: {
            "name": course_type_name,
            "active": bool(is_active),
            "credit_type_id": credit_type_id,
        }
        for course_type_id, course_type_name, is_active, credit_type_id in rows
    }

    missing = [
        str(course_type_id)
        for course_type_id in unique_ids
        if course_type_id not in by_id or not bool(by_id[course_type_id]["active"])
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown course type ids: {', '.join(missing)}",
        )

    if require_credit_mapping:
        unmapped_names = [
            str(by_id[course_type_id]["name"])
            for course_type_id in unique_ids
            if by_id[course_type_id]["credit_type_id"] is None
        ]
        if unmapped_names:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "PACK formulas require a credit type on each activity. "
                    f"Unmapped activities: {', '.join(unmapped_names)}"
                ),
            )

    return unique_ids


def _normalize_restrictions(
    restrictions: list[AdminFormulaRestrictionIn | dict[str, object]],
    *,
    entitlement_course_type_ids: set[UUID],
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for restriction in restrictions:
        if isinstance(restriction, AdminFormulaRestrictionIn):
            period = restriction.period
            max_bookings = int(restriction.max_bookings)
            input_course_type_ids = list(restriction.course_type_ids)
        else:
            period = _restriction_period_from_raw(restriction.get("period"))
            max_bookings = _restriction_max_from_raw(restriction.get("max_bookings"))
            input_course_type_ids = _course_type_ids_from_raw(restriction.get("course_type_ids"))

        course_ids: list[UUID] = []
        seen: set[UUID] = set()
        for course_type_id in input_course_type_ids:
            if course_type_id in seen:
                continue
            seen.add(course_type_id)
            course_ids.append(course_type_id)

        if course_ids:
            for course_type_id in course_ids:
                if course_type_id not in entitlement_course_type_ids:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Restriction course type must be part of entitled course types",
                    )

        normalized.append(
            {
                "id": uuid4().hex,
                "period": period.value,
                "max_bookings": max_bookings,
                "course_type_ids": [str(course_type_id) for course_type_id in course_ids],
            }
        )

    return normalized


def _restriction_period_from_raw(raw: object) -> PlanRestrictionPeriod:
    if not isinstance(raw, str):
        return PlanRestrictionPeriod.WEEK
    normalized = raw.upper()
    for candidate in PlanRestrictionPeriod:
        if normalized == candidate.value:
            return candidate
    return PlanRestrictionPeriod.WEEK


def _restriction_max_from_raw(raw: object) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return 1
    return max(1, parsed)


def _course_type_ids_from_raw(raw: object) -> list[UUID]:
    if not isinstance(raw, list):
        return []

    out: list[UUID] = []
    seen: set[UUID] = set()
    for value in raw:
        try:
            parsed = UUID(str(value))
        except (TypeError, ValueError):
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        out.append(parsed)
    return out


def _normalize_credit_grants(
    db: Session,
    grants: list[AdminFormulaCreditGrantIn | dict[str, object]],
) -> list[tuple[UUID, int]]:
    merged: dict[UUID, int] = {}
    for grant in grants:
        if isinstance(grant, dict):
            credit_type_raw = grant.get("credit_type_id")
            credits_count_raw = grant.get("credits_count")
        else:
            credit_type_raw = grant.credit_type_id
            credits_count_raw = grant.credits_count

        try:
            credit_type_id = UUID(str(credit_type_raw))
            credits_count = int(credits_count_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid credit grant payload",
            ) from exc

        _resolve_credit_type(db, credit_type_id=credit_type_id, allow_inactive=False)
        merged[credit_type_id] = merged.get(credit_type_id, 0) + credits_count
    return [(credit_type_id, credits_count) for credit_type_id, credits_count in merged.items() if credits_count > 0]


def _effective_pack_credits_count(
    grants: list[tuple[UUID, int]] | list[AdminFormulaCreditGrantOut],
    relation: PlanCreditGrantsRelation,
) -> int:
    counts: list[int] = []
    for grant in grants:
        if isinstance(grant, tuple):
            _, credits = grant
            count = int(credits)
        else:
            count = int(grant.credits_count)
        if count > 0:
            counts.append(count)

    if not counts:
        return 0
    if relation == PlanCreditGrantsRelation.OR:
        return max(counts)
    return sum(counts)


def _resolved_formula_price_values(
    *,
    monthly_price_value: Decimal | None,
    monthly_price_excl_vat: Decimal | None,
    signup_fee_value: Decimal | None,
    signup_fee_excl_vat: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    resolved_monthly = monthly_price_value if monthly_price_value is not None else monthly_price_excl_vat
    resolved_signup = signup_fee_value if signup_fee_value is not None else signup_fee_excl_vat
    return resolved_monthly, resolved_signup


def _serialize_formula(
    db: Session,
    plan: Plan,
    *,
    entitlements_by_plan: dict[UUID, list[UUID]] | None = None,
    course_name_by_id: dict[UUID, str] | None = None,
    credit_grants_by_plan: dict[UUID, list[AdminFormulaCreditGrantOut]] | None = None,
) -> AdminFormulaOut:
    if entitlements_by_plan is None:
        entitlements_by_plan = {}
    if course_name_by_id is None:
        course_name_by_id = {}
    if credit_grants_by_plan is None:
        credit_grants_by_plan = {}

    ent_ids = entitlements_by_plan.get(plan.id)
    if ent_ids is None:
        ent_ids = db.scalars(select(PlanEntitlement.course_type_id).where(PlanEntitlement.plan_id == plan.id)).all()
    ent_ids = list(ent_ids)
    ent_names = [course_name_by_id.get(course_type_id, str(course_type_id)) for course_type_id in ent_ids]

    credit_grants_out = credit_grants_by_plan.get(plan.id)
    if credit_grants_out is None:
        credit_rows = db.execute(
            select(
                PlanCreditGrant.id,
                PlanCreditGrant.credit_type_id,
                PlanCreditGrant.credits_count,
                CreditType.code,
                CreditType.name,
            )
            .join(CreditType, CreditType.id == PlanCreditGrant.credit_type_id, isouter=True)
            .where(PlanCreditGrant.plan_id == plan.id)
            .order_by(CreditType.name.asc().nulls_last(), PlanCreditGrant.created_at.asc())
        ).all()
        credit_grants_out = [
            AdminFormulaCreditGrantOut(
                id=str(grant_id),
                credit_type_id=credit_type_id,
                credit_type_code=credit_type_code,
                credit_type_name=credit_type_name,
                credits_count=int(credits_count),
            )
            for grant_id, credit_type_id, credits_count, credit_type_code, credit_type_name in credit_rows
        ]

    monthly_price_value = plan.monthly_price_value if plan.monthly_price_value is not None else plan.monthly_price_excl_vat
    signup_fee_value = plan.signup_fee_value if plan.signup_fee_value is not None else plan.signup_fee_excl_vat

    restrictions_out: list[AdminFormulaRestrictionOut] = []
    raw_restrictions = plan.restrictions_json if isinstance(plan.restrictions_json, list) else []
    for raw in raw_restrictions:
        if not isinstance(raw, dict):
            continue
        course_ids = _course_type_ids_from_raw(raw.get("course_type_ids"))
        restrictions_out.append(
            AdminFormulaRestrictionOut(
                id=str(raw.get("id") or uuid4().hex),
                period=_restriction_period_from_raw(raw.get("period")),
                max_bookings=_restriction_max_from_raw(raw.get("max_bookings")),
                course_type_ids=course_ids,
                course_type_names=[course_name_by_id.get(course_type_id, str(course_type_id)) for course_type_id in course_ids],
            )
        )

    payment_methods = _normalize_methods(plan.payment_methods_json if isinstance(plan.payment_methods_json, list) else [])
    options = _normalize_option_values(plan.options_json if isinstance(plan.options_json, list) else [])

    effective_credits_count = plan.credits_count
    if plan.kind == PlanKind.PACK:
        computed = _effective_pack_credits_count(credit_grants_out, plan.credit_grants_relation)
        effective_credits_count = computed if computed > 0 else int(plan.credits_count or 0)

    return AdminFormulaOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        kind=plan.kind,
        active=plan.active,
        is_private=plan.is_private,
        description=plan.description,
        credits_count=effective_credits_count,
        pack_validity_months=plan.pack_validity_months,
        forfait_start_date=plan.forfait_start_date,
        forfait_end_date=plan.forfait_end_date,
        credit_grants=credit_grants_out,
        credit_grants_relation=plan.credit_grants_relation,
        monthly_price_value=monthly_price_value,
        signup_fee_value=signup_fee_value,
        price_tax_mode=plan.price_tax_mode,
        monthly_price_excl_vat=plan.monthly_price_excl_vat,
        currency_code=plan.currency_code,
        signup_fee_excl_vat=plan.signup_fee_excl_vat,
        first_purchase_signup_fee_enabled=bool(plan.first_purchase_signup_fee_enabled),
        first_purchase_partitions_enabled=bool(plan.first_purchase_partitions_enabled),
        first_purchase_partitions_price_value=plan.first_purchase_partitions_price_value,
        options=options,
        payment_methods=payment_methods,
        entitlement_course_type_ids=ent_ids,
        entitlement_course_type_names=ent_names,
        restrictions=restrictions_out,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _validate_formula_payload(
    *,
    kind: PlanKind,
    credits_count: int | None,
    pack_validity_months: int | None,
    forfait_start_date: date | None,
    forfait_end_date: date | None,
    monthly_price_value: Decimal | None,
    currency_code: str | None,
    credit_grants: list[tuple[UUID, int]] | None = None,
) -> None:
    if kind != PlanKind.FORFAIT and monthly_price_value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formula price is required",
        )
    if currency_code is None or not currency_code.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formula currency is required",
        )

    if kind == PlanKind.PACK and (credits_count is None or credits_count <= 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="credits_count is required for PACK formulas",
        )
    if kind == PlanKind.PACK and (pack_validity_months is None or pack_validity_months < 1 or pack_validity_months > 12):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pack_validity_months is required for PACK formulas (1-12)",
        )
    if kind == PlanKind.PACK and credit_grants is not None and len(credit_grants) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one credit type is required for PACK formulas",
        )
    if kind == PlanKind.FORFAIT:
        if forfait_start_date is None or forfait_end_date is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="forfait_start_date and forfait_end_date are required for FORFAIT formulas",
            )
        if forfait_end_date <= forfait_start_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="forfait_end_date must be after forfait_start_date",
            )


def _course_name_map(db: Session) -> dict[UUID, str]:
    rows = db.execute(select(CourseType.id, CourseType.name)).all()
    return {course_type_id: name for course_type_id, name in rows}


def _serialize_messaging_template(raw: dict[str, object]) -> AdminMessagingTemplateOut:
    return AdminMessagingTemplateOut(
        id=str(raw.get("id") or ""),
        code=(str(raw["code"]) if raw.get("code") is not None else None),
        name=str(raw.get("name") or ""),
        channel=AdminMessagingChannel(str(raw.get("channel") or "EMAIL")),
        kind=AdminMessagingTemplateKind(str(raw.get("kind") or "CUSTOM")),
        subject=(str(raw["subject"]) if raw.get("subject") is not None else None),
        subject_translations=(
            {str(key): str(value) for key, value in raw.get("subject_translations", {}).items()}
            if isinstance(raw.get("subject_translations"), dict)
            else {}
        ),
        body=str(raw.get("body") or ""),
        body_translations=(
            {str(key): str(value) for key, value in raw.get("body_translations", {}).items()}
            if isinstance(raw.get("body_translations"), dict)
            else {}
        ),
        body_format="HTML" if str(raw.get("body_format") or "").strip().upper() == "HTML" else "TEXT",
        active=bool(raw.get("active", True)),
        usage_contexts=[
            str(item).strip()
            for item in (raw.get("usage_contexts") if isinstance(raw.get("usage_contexts"), list) else [])
            if str(item).strip()
        ],
        description=(str(raw["description"]) if raw.get("description") is not None else None),
        variables_hint=(str(raw["variables_hint"]) if raw.get("variables_hint") is not None else None),
        created_at=raw.get("created_at") if isinstance(raw.get("created_at"), datetime) else None,
        updated_at=raw.get("updated_at") if isinstance(raw.get("updated_at"), datetime) else None,
    )


@router.get("/activities", response_model=list[AdminActivityOut])
def list_admin_activities(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminActivityOut]:
    stmt = select(CourseType).order_by(CourseType.name.asc())
    if not include_inactive:
        stmt = stmt.where(CourseType.active.is_(True))
    rows = db.scalars(stmt).all()
    credit_type_by_id = _credit_type_by_id(db)
    legal_entity_by_id = _legal_entity_by_id(db)
    content_courses_by_activity_id = _content_courses_by_activity_id(db, active_only=True)
    return [
        _serialize_activity(
            row,
            credit_type_by_id=credit_type_by_id,
            legal_entity_by_id=legal_entity_by_id,
            content_course_rows=content_courses_by_activity_id.get(row.id, []),
        )
        for row in rows
    ]


@router.get("/external-content/courses", response_model=list[AdminExternalContentCourseOut])
def list_admin_external_content_courses(
    provider: str = Query(default=ExternalContentProvider.WORDPRESS_LEARNDASH.value),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminExternalContentCourseOut]:
    normalized_provider = (provider or ExternalContentProvider.WORDPRESS_LEARNDASH.value).strip().upper()
    try:
        provider_enum = ExternalContentProvider(normalized_provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown external content provider") from exc

    stmt = select(ExternalContentCourse).where(ExternalContentCourse.provider == provider_enum).order_by(
        ExternalContentCourse.level_code.asc().nulls_last(),
        ExternalContentCourse.title.asc(),
    )
    if not include_archived:
        stmt = stmt.where(ExternalContentCourse.status != ExternalContentStatus.ARCHIVED)
    rows = db.scalars(stmt).all()
    course_ids = [row.id for row in rows]
    section_counts_by_course_id: dict[UUID, int] = {}
    lesson_counts_by_course_id: dict[UUID, int] = {}
    if course_ids:
        section_count_rows = db.execute(
            select(ExternalContentSection.course_id, func.count(ExternalContentSection.id))
            .where(ExternalContentSection.course_id.in_(course_ids))
            .group_by(ExternalContentSection.course_id)
        ).all()
        lesson_count_rows = db.execute(
            select(ExternalContentLesson.course_id, func.count(ExternalContentLesson.id))
            .where(ExternalContentLesson.course_id.in_(course_ids))
            .group_by(ExternalContentLesson.course_id)
        ).all()
        section_counts_by_course_id = {course_id: int(count) for course_id, count in section_count_rows}
        lesson_counts_by_course_id = {course_id: int(count) for course_id, count in lesson_count_rows}
    return [
        _serialize_external_content_course(
            row,
            sections_count=section_counts_by_course_id.get(row.id, 0),
            lessons_count=lesson_counts_by_course_id.get(row.id, 0),
        )
        for row in rows
    ]


@router.get("/config/external-content/wordpress-learndash", response_model=AdminExternalContentSettingsOut)
def get_admin_external_content_wordpress_learndash_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminExternalContentSettingsOut:
    return _serialize_external_content_settings(db)


@router.put("/config/external-content/wordpress-learndash", response_model=AdminExternalContentSettingsOut)
def update_admin_external_content_wordpress_learndash_settings(
    payload: AdminExternalContentSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminExternalContentSettingsOut:
    base_url = payload.base_url.strip().rstrip("/")
    courses_endpoint = payload.courses_endpoint.strip()
    timeout_seconds = max(5, payload.timeout_seconds)
    current_token = _get_setting_value(db, WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY, "").strip()
    next_token = ""
    if payload.clear_bearer_token:
        next_token = ""
    else:
        submitted_token = (payload.bearer_token or "").strip()
        next_token = submitted_token or current_token

    _set_setting(db, WORDPRESS_LEARNDASH_BASE_URL_SETTING_KEY, base_url)
    _set_setting(db, WORDPRESS_LEARNDASH_COURSES_ENDPOINT_SETTING_KEY, courses_endpoint)
    _set_setting(db, WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY, next_token)
    _set_setting(db, WORDPRESS_LEARNDASH_TIMEOUT_SECONDS_SETTING_KEY, str(timeout_seconds))
    db.commit()
    return _serialize_external_content_settings(db)


@router.post("/external-content/sync/wordpress-learndash", response_model=AdminExternalContentSyncOut)
def sync_admin_external_content_wordpress_learndash(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminExternalContentSyncOut:
    try:
        summary = sync_wordpress_learndash_catalog(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    db.commit()
    return AdminExternalContentSyncOut(
        provider=summary.provider.value,
        fetched_at=summary.fetched_at,
        courses_seen=summary.courses_seen,
        courses_created=summary.courses_created,
        courses_updated=summary.courses_updated,
        sections_seen=summary.sections_seen,
        sections_created=summary.sections_created,
        sections_updated=summary.sections_updated,
        sections_deleted=summary.sections_deleted,
        lessons_seen=summary.lessons_seen,
        lessons_created=summary.lessons_created,
        lessons_updated=summary.lessons_updated,
        lessons_deleted=summary.lessons_deleted,
    )


@router.get("/legal-entities", response_model=list[AdminLegalEntityOut])
def list_admin_legal_entities(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients", "can_view_quotes")),
) -> list[AdminLegalEntityOut]:
    stmt = select(LegalEntity).order_by(LegalEntity.name.asc())
    if not include_inactive:
        stmt = stmt.where(LegalEntity.is_active.is_(True))
    rows = db.scalars(stmt).all()
    return [_serialize_legal_entity(row) for row in rows]


@router.post("/legal-entities", response_model=AdminLegalEntityOut, status_code=status.HTTP_201_CREATED)
def create_admin_legal_entity(
    payload: AdminLegalEntityCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminLegalEntityOut:
    name = _normalize_legal_entity_text(payload.name, max_length=255)
    if name is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")
    invoice_prefix = _normalize_invoice_prefix(payload.invoice_prefix)
    existing_name = db.scalar(select(LegalEntity.id).where(LegalEntity.name == name))
    if existing_name is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Legal entity name already exists")

    existing_prefix = db.scalar(select(LegalEntity.id).where(LegalEntity.invoice_prefix == invoice_prefix))
    if existing_prefix is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice prefix already exists")

    now = _utcnow()
    entity = LegalEntity(
        name=name,
        siren=_normalize_legal_entity_text(payload.siren, max_length=64),
        siret=_normalize_legal_entity_text(payload.siret, max_length=64),
        vat_number=_normalize_legal_entity_text(payload.vat_number, max_length=64),
        address_text=_normalize_legal_entity_text(payload.address_text, max_length=2000),
        accounting_email=_normalize_legal_entity_text(payload.accounting_email, max_length=320),
        phone=_normalize_legal_entity_text(payload.phone, max_length=30),
        legal_form=_normalize_legal_form(payload.legal_form),
        share_capital=_normalize_legal_entity_text(payload.share_capital, max_length=120),
        country_code=_normalize_country_code(payload.country_code),
        invoice_prefix=invoice_prefix,
        invoice_next_number=int(payload.invoice_next_number),
        default_payment_provider=_normalize_payment_provider(payload.default_payment_provider).value,
        is_active=bool(payload.is_active),
        updated_at=now,
    )
    _ensure_legal_entity_minimum_fields(
        name=entity.name,
        country_code=entity.country_code,
        invoice_prefix=entity.invoice_prefix,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return _serialize_legal_entity(entity)


@router.patch("/legal-entities/{legal_entity_id}", response_model=AdminLegalEntityOut)
def update_admin_legal_entity(
    legal_entity_id: UUID,
    payload: AdminLegalEntityUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminLegalEntityOut:
    entity = db.scalar(select(LegalEntity).where(LegalEntity.id == legal_entity_id).with_for_update())
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal entity not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _serialize_legal_entity(entity)

    if "name" in changes:
        name = _normalize_legal_entity_text(changes["name"], max_length=255)
        if name is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")
        existing = db.scalar(select(LegalEntity.id).where(LegalEntity.name == name, LegalEntity.id != entity.id))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Legal entity name already exists")
        entity.name = name

    if "siren" in changes:
        entity.siren = _normalize_legal_entity_text(changes["siren"], max_length=64)
    if "siret" in changes:
        entity.siret = _normalize_legal_entity_text(changes["siret"], max_length=64)
    if "vat_number" in changes:
        entity.vat_number = _normalize_legal_entity_text(changes["vat_number"], max_length=64)
    if "address_text" in changes:
        entity.address_text = _normalize_legal_entity_text(changes["address_text"], max_length=2000)
    if "accounting_email" in changes:
        entity.accounting_email = _normalize_legal_entity_text(changes["accounting_email"], max_length=320)
    if "phone" in changes:
        entity.phone = _normalize_legal_entity_text(changes["phone"], max_length=30)
    if "legal_form" in changes:
        entity.legal_form = _normalize_legal_form(changes["legal_form"])
    if "share_capital" in changes:
        entity.share_capital = _normalize_legal_entity_text(changes["share_capital"], max_length=120)

    if "country_code" in changes:
        entity.country_code = _normalize_country_code(changes["country_code"])

    if "invoice_prefix" in changes:
        invoice_prefix = _normalize_invoice_prefix(changes["invoice_prefix"])
        existing = db.scalar(
            select(LegalEntity.id).where(
                LegalEntity.invoice_prefix == invoice_prefix,
                LegalEntity.id != entity.id,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice prefix already exists")
        entity.invoice_prefix = invoice_prefix

    if "invoice_next_number" in changes:
        next_number = changes["invoice_next_number"]
        if next_number is None or int(next_number) < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invoice_next_number must be >= 1",
            )
        entity.invoice_next_number = int(next_number)

    if "default_payment_provider" in changes:
        provider = _normalize_payment_provider(str(changes["default_payment_provider"] or ""))
        entity.default_payment_provider = provider.value

    if "is_active" in changes:
        entity.is_active = bool(changes["is_active"])

    _ensure_legal_entity_minimum_fields(
        name=entity.name,
        country_code=entity.country_code,
        invoice_prefix=entity.invoice_prefix,
    )
    entity.updated_at = _utcnow()
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return _serialize_legal_entity(entity)


@router.post("/legal-entities/{legal_entity_id}/disable", response_model=AdminLegalEntityOut)
def disable_admin_legal_entity(
    legal_entity_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminLegalEntityOut:
    entity = db.scalar(select(LegalEntity).where(LegalEntity.id == legal_entity_id).with_for_update())
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal entity not found")
    if not entity.is_active:
        return _serialize_legal_entity(entity)
    entity.is_active = False
    entity.updated_at = _utcnow()
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return _serialize_legal_entity(entity)


@router.get("/credit-types", response_model=list[AdminCreditTypeOut])
def list_admin_credit_types(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCreditTypeOut]:
    stmt = select(CreditType).order_by(CreditType.name.asc())
    if not include_inactive:
        stmt = stmt.where(CreditType.active.is_(True))

    rows = db.scalars(stmt).all()
    activities_by_credit_type_id = _activities_by_credit_type_id(db, include_inactive=True)
    return [
        _serialize_credit_type(
            row,
            activity_rows=activities_by_credit_type_id.get(row.id, []),
        )
        for row in rows
    ]


@router.post("/credit-types", response_model=AdminCreditTypeOut, status_code=status.HTTP_201_CREATED)
def create_admin_credit_type(
    payload: AdminCreditTypeUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCreditTypeOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")

    requested_code = _normalize_credit_type_code(payload.code, fallback_name=name)
    if payload.code and db.scalar(select(CreditType.id).where(CreditType.code == requested_code)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Credit type code already exists")

    code = requested_code
    if not payload.code:
        while db.scalar(select(CreditType.id).where(CreditType.code == code)) is not None:
            code = _new_credit_type_code(name)

    credit_type = CreditType(
        code=code,
        name=name,
        description=(payload.description or "").strip() or None,
        active=bool(payload.active),
        updated_at=_utcnow(),
    )
    db.add(credit_type)
    db.commit()
    db.refresh(credit_type)
    return _serialize_credit_type(credit_type, activity_rows=[])


@router.patch("/credit-types/{credit_type_id}", response_model=AdminCreditTypeOut)
def update_admin_credit_type(
    credit_type_id: UUID,
    payload: AdminCreditTypeUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCreditTypeOut:
    credit_type = db.scalar(select(CreditType).where(CreditType.id == credit_type_id).with_for_update())
    if credit_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit type not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        rows = _activities_by_credit_type_id(db, include_inactive=True).get(credit_type.id, [])
        return _serialize_credit_type(credit_type, activity_rows=rows)

    if "code" in changes:
        next_code = _normalize_credit_type_code(changes["code"], fallback_name=credit_type.name)
        existing = db.scalar(select(CreditType.id).where(CreditType.code == next_code, CreditType.id != credit_type.id))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Credit type code already exists")
        credit_type.code = next_code

    if "name" in changes:
        next_name = (changes["name"] or "").strip()
        if not next_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")
        credit_type.name = next_name

    if "description" in changes:
        credit_type.description = (changes["description"] or "").strip() or None

    if "active" in changes:
        credit_type.active = bool(changes["active"])

    credit_type.updated_at = _utcnow()
    db.add(credit_type)
    db.commit()
    db.refresh(credit_type)
    rows = _activities_by_credit_type_id(db, include_inactive=True).get(credit_type.id, [])
    return _serialize_credit_type(credit_type, activity_rows=rows)


@router.delete("/credit-types/{credit_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_credit_type(
    credit_type_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    credit_type = db.scalar(select(CreditType).where(CreditType.id == credit_type_id).with_for_update())
    if credit_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit type not found")

    linked_activity = db.scalar(
        select(CourseType.id).where(CourseType.credit_type_id == credit_type.id).limit(1)
    )
    if linked_activity is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Credit type is linked to activities. Update those activities before deletion.",
        )

    db.delete(credit_type)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/activities", response_model=AdminActivityOut, status_code=status.HTTP_201_CREATED)
def create_admin_activity(
    payload: AdminActivityUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminActivityOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")
    _validate_activity_duration(service_code=payload.service_code, duration_minutes=int(payload.duration_minutes))

    credit_type = (
        _resolve_credit_type(db, credit_type_id=payload.credit_type_id)
        if payload.credit_type_id is not None
        else None
    )
    seller_legal_entity = _resolve_legal_entity(db, legal_entity_id=payload.seller_legal_entity_id)
    payor_legal_entity = (
        _resolve_legal_entity(db, legal_entity_id=payload.payor_legal_entity_id)
        if payload.payor_legal_entity_id is not None
        else seller_legal_entity
    )

    requested_code = _normalize_activity_code(payload.code, fallback_name=name)
    if payload.code and db.scalar(select(CourseType.id).where(CourseType.code == requested_code)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Activity code already exists")

    code = requested_code
    if not payload.code:
        while db.scalar(select(CourseType.id).where(CourseType.code == code)) is not None:
            code = _new_activity_code(name)

    if payload.auto_cancel_rule_enabled and (
        payload.auto_cancel_if_booked_less_than_override is None
        or payload.auto_cancel_if_booked_less_than_override < 1
        or payload.auto_cancel_hours_before_start_override is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Automatic cancellation requires a minimum attendee count and a check delay",
        )

    activity = CourseType(
        code=code,
        name=name,
        description=(payload.description or "").strip() or None,
        service_code=payload.service_code.strip().upper(),
        billing_entity_code=_legacy_billing_entity_code_from_legal_entity(seller_legal_entity),
        seller_legal_entity_id=seller_legal_entity.id,
        payor_legal_entity_id=payor_legal_entity.id,
        credit_type_id=credit_type.id if credit_type is not None else None,
        duration_minutes=int(payload.duration_minutes),
        color_hex=_normalize_color_hex(payload.color_hex),
        mode=DeliveryMode(payload.mode),
        requires_professor=bool(payload.requires_professor) if payload.allows_student_bookings else False,
        allows_student_bookings=bool(payload.allows_student_bookings),
        supports_student_time_overrides=(
            bool(payload.supports_student_time_overrides) if payload.allows_student_bookings else False
        ),
        default_capacity=_normalize_activity_capacity(
            allows_student_bookings=bool(payload.allows_student_bookings),
            capacity=int(payload.default_capacity),
        ),
        default_hourly_rate=payload.default_hourly_rate,
        default_course_rate_ttc=payload.default_course_rate_ttc,
        email_reminder_hours_before_start=payload.email_reminder_hours_before_start,
        sms_reminder_hours_before_start=payload.sms_reminder_hours_before_start,
        min_booking_notice_hours_override=payload.min_booking_notice_hours_override,
        cancellation_deadline_hours_override=payload.cancellation_deadline_hours_override,
        auto_cancel_if_booked_less_than_override=payload.auto_cancel_if_booked_less_than_override,
        auto_cancel_hours_before_start_override=payload.auto_cancel_hours_before_start_override,
        auto_cancel_rule_enabled=bool(payload.auto_cancel_rule_enabled),
        exclude_holidays_in_recurrence=bool(payload.exclude_holidays_in_recurrence),
        exclude_school_vacations_in_recurrence=bool(payload.exclude_school_vacations_in_recurrence),
        active=bool(payload.active),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _serialize_activity(
        activity,
        credit_type_by_id=_credit_type_by_id(db),
        legal_entity_by_id=_legal_entity_by_id(db),
        content_course_rows=[],
    )


@router.patch("/activities/{activity_id}", response_model=AdminActivityOut)
def update_admin_activity(
    activity_id: UUID,
    payload: AdminActivityUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminActivityOut:
    activity = db.scalar(select(CourseType).where(CourseType.id == activity_id).with_for_update())
    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _serialize_activity(
            activity,
            credit_type_by_id=_credit_type_by_id(db),
            legal_entity_by_id=_legal_entity_by_id(db),
            content_course_rows=_content_courses_by_activity_id(db, active_only=True).get(activity.id, []),
        )

    if "code" in changes:
        next_code = _normalize_activity_code(changes["code"], fallback_name=activity.name)
        existing = db.scalar(select(CourseType.id).where(CourseType.code == next_code, CourseType.id != activity.id))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Activity code already exists")
        activity.code = next_code

    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")
        activity.name = name

    if "description" in changes:
        activity.description = (changes["description"] or "").strip() or None

    if "service_code" in changes:
        service_code = (changes["service_code"] or "").strip().upper()
        if not service_code:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="service_code is required")
        activity.service_code = service_code

    if "seller_legal_entity_id" in changes:
        seller_legal_entity_id = changes["seller_legal_entity_id"]
        if seller_legal_entity_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="seller_legal_entity_id is required",
            )
        seller_legal_entity = _resolve_legal_entity(db, legal_entity_id=seller_legal_entity_id)
        activity.seller_legal_entity_id = seller_legal_entity.id
        activity.billing_entity_code = _legacy_billing_entity_code_from_legal_entity(seller_legal_entity)
        if "payor_legal_entity_id" not in changes and activity.payor_legal_entity_id is None:
            activity.payor_legal_entity_id = seller_legal_entity.id

    if "payor_legal_entity_id" in changes:
        payor_legal_entity_id = changes["payor_legal_entity_id"]
        if payor_legal_entity_id is None:
            if activity.seller_legal_entity_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="payor_legal_entity_id is required",
                )
            activity.payor_legal_entity_id = activity.seller_legal_entity_id
        else:
            payor_legal_entity = _resolve_legal_entity(db, legal_entity_id=payor_legal_entity_id)
            activity.payor_legal_entity_id = payor_legal_entity.id

    if "credit_type_id" in changes:
        credit_type_id = changes["credit_type_id"]
        if credit_type_id is None:
            activity.credit_type_id = None
        else:
            activity.credit_type_id = _resolve_credit_type(db, credit_type_id=credit_type_id).id

    if "duration_minutes" in changes:
        next_duration = int(changes["duration_minutes"])
        _validate_activity_duration(service_code=activity.service_code, duration_minutes=next_duration)
        activity.duration_minutes = next_duration

    if "color_hex" in changes:
        activity.color_hex = _normalize_color_hex(changes["color_hex"])

    if "mode" in changes:
        activity.mode = DeliveryMode(changes["mode"])

    if "requires_professor" in changes:
        activity.requires_professor = bool(changes["requires_professor"]) if activity.allows_student_bookings else False

    if "allows_student_bookings" in changes:
        activity.allows_student_bookings = bool(changes["allows_student_bookings"])
        if not activity.allows_student_bookings:
            activity.requires_professor = False
            activity.supports_student_time_overrides = False
            activity.default_capacity = 0

    if "supports_student_time_overrides" in changes:
        activity.supports_student_time_overrides = (
            bool(changes["supports_student_time_overrides"]) if activity.allows_student_bookings else False
        )

    if "default_capacity" in changes:
        activity.default_capacity = _normalize_activity_capacity(
            allows_student_bookings=bool(activity.allows_student_bookings),
            capacity=int(changes["default_capacity"]),
        )

    if not activity.allows_student_bookings:
        activity.requires_professor = False
        activity.supports_student_time_overrides = False
        activity.default_capacity = 0

    _validate_activity_duration(
        service_code=activity.service_code,
        duration_minutes=int(activity.duration_minutes),
    )

    if "default_hourly_rate" in changes:
        activity.default_hourly_rate = changes["default_hourly_rate"]

    if "default_course_rate_ttc" in changes:
        activity.default_course_rate_ttc = changes["default_course_rate_ttc"]

    if "email_reminder_hours_before_start" in changes:
        activity.email_reminder_hours_before_start = changes["email_reminder_hours_before_start"]

    if "sms_reminder_hours_before_start" in changes:
        activity.sms_reminder_hours_before_start = changes["sms_reminder_hours_before_start"]

    if "min_booking_notice_hours_override" in changes:
        activity.min_booking_notice_hours_override = changes["min_booking_notice_hours_override"]

    if "cancellation_deadline_hours_override" in changes:
        activity.cancellation_deadline_hours_override = changes["cancellation_deadline_hours_override"]

    if "auto_cancel_if_booked_less_than_override" in changes:
        activity.auto_cancel_if_booked_less_than_override = changes["auto_cancel_if_booked_less_than_override"]

    if "auto_cancel_hours_before_start_override" in changes:
        activity.auto_cancel_hours_before_start_override = changes["auto_cancel_hours_before_start_override"]

    if "auto_cancel_rule_enabled" in changes:
        activity.auto_cancel_rule_enabled = bool(changes["auto_cancel_rule_enabled"])

    if "exclude_holidays_in_recurrence" in changes:
        activity.exclude_holidays_in_recurrence = bool(changes["exclude_holidays_in_recurrence"])

    if "exclude_school_vacations_in_recurrence" in changes:
        activity.exclude_school_vacations_in_recurrence = bool(changes["exclude_school_vacations_in_recurrence"])

    if "active" in changes:
        activity.active = bool(changes["active"])

    if bool(activity.auto_cancel_rule_enabled) and (
        activity.auto_cancel_if_booked_less_than_override is None
        or int(activity.auto_cancel_if_booked_less_than_override) < 1
        or activity.auto_cancel_hours_before_start_override is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Automatic cancellation requires a minimum attendee count and a check delay",
        )

    if any(
        field in changes
        for field in (
            "auto_cancel_rule_enabled",
            "auto_cancel_if_booked_less_than_override",
            "auto_cancel_hours_before_start_override",
        )
    ):
        inherited_sessions = db.scalars(
            select(CourseSession).where(
                CourseSession.course_type_id == activity.id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.auto_cancel_rule_enabled_override.is_(None),
                CourseSession.start_at_utc > datetime.now(timezone.utc),
            )
        ).all()
        hours = int(activity.auto_cancel_hours_before_start_override or 0)
        for session_obj in inherited_sessions:
            session_obj.auto_cancel_checked_at = None
            session_obj.auto_cancel_deadline_utc = (
                session_obj.start_at_utc - timedelta(hours=hours)
                if bool(activity.auto_cancel_rule_enabled) and hours > 0
                else session_obj.start_at_utc - timedelta(minutes=1)
            )

    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _serialize_activity(
        activity,
        credit_type_by_id=_credit_type_by_id(db),
        legal_entity_by_id=_legal_entity_by_id(db),
        content_course_rows=_content_courses_by_activity_id(db, active_only=True).get(activity.id, []),
    )


@router.get("/activities/{activity_id}/content-mappings", response_model=list[AdminActivityContentMappingOut])
def list_admin_activity_content_mappings(
    activity_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminActivityContentMappingOut]:
    activity = db.scalar(select(CourseType.id).where(CourseType.id == activity_id))
    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    return [
        _serialize_activity_content_mapping(mapping, course)
        for mapping, course in list_content_course_mappings_for_course_type(
            db,
            course_type_id=activity_id,
            active_only=False,
        )
    ]


@router.put("/activities/{activity_id}/content-mappings", response_model=list[AdminActivityContentMappingOut])
def replace_admin_activity_content_mappings(
    activity_id: UUID,
    payload: AdminActivityContentMappingsReplaceRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminActivityContentMappingOut]:
    try:
        replace_course_type_content_mappings(
            db,
            course_type_id=activity_id,
            content_course_ids=payload.content_course_ids,
            access_rule=payload.access_rule,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return [
        _serialize_activity_content_mapping(mapping, course)
        for mapping, course in list_content_course_mappings_for_course_type(
            db,
            course_type_id=activity_id,
            active_only=False,
        )
    ]


@router.get("/config/account", response_model=AdminConfigAccountOut)
def get_admin_config_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_permissions("can_view_clients", "can_view_quotes")),
) -> AdminConfigAccountOut:
    allowed_currencies = _parse_allowed_currencies(_get_setting_value(db, ACCOUNT_ALLOWED_CURRENCIES_KEY, "EUR,USD"))
    default_currency = _parse_default_currency(
        _get_setting_value(db, ACCOUNT_DEFAULT_CURRENCY_KEY, "EUR"),
        allowed_currencies,
    )
    client_balance_default_date_mode = _get_setting_value(
        db,
        ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODE_KEY,
        "TODAY",
    ).strip().upper()
    if client_balance_default_date_mode not in ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODES:
        client_balance_default_date_mode = "TODAY"

    return AdminConfigAccountOut(
        contact_first_name=_get_setting_value(db, ACCOUNT_SETTING_MAP["contact_first_name"], current_user.first_name or ""),
        contact_last_name=_get_setting_value(db, ACCOUNT_SETTING_MAP["contact_last_name"], current_user.last_name or ""),
        contact_email=_get_setting_value(db, ACCOUNT_SETTING_MAP["contact_email"], current_user.email),
        contact_phone=_get_setting_value(db, ACCOUNT_SETTING_MAP["contact_phone"], current_user.phone or ""),
        company_name=_get_setting_value(db, ACCOUNT_SETTING_MAP["company_name"], "Piano Academie"),
        club_name=_get_setting_value(db, ACCOUNT_SETTING_MAP["club_name"], "Piano Academie"),
        siret=_get_setting_value(db, ACCOUNT_SETTING_MAP["siret"], ""),
        vat_number=_get_setting_value(db, ACCOUNT_SETTING_MAP["vat_number"], ""),
        vat_default_rate=_get_setting_value(db, ACCOUNT_SETTING_MAP["vat_default_rate"], "20"),
        website=_get_setting_value(db, ACCOUNT_SETTING_MAP["website"], ""),
        address_line=_get_setting_value(db, ACCOUNT_SETTING_MAP["address_line"], ""),
        postal_code=_get_setting_value(db, ACCOUNT_SETTING_MAP["postal_code"], ""),
        city=_get_setting_value(db, ACCOUNT_SETTING_MAP["city"], ""),
        country=_get_setting_value(db, ACCOUNT_SETTING_MAP["country"], "FRANCE"),
        allowed_currencies=allowed_currencies,
        default_currency=default_currency,
        client_balance_default_date_mode=client_balance_default_date_mode,
        bank_transfer_account_holder=_get_setting_value(db, ACCOUNT_SETTING_MAP["bank_transfer_account_holder"], "SAS PIANO ACADEMIE"),
        bank_transfer_iban=_get_setting_value(db, ACCOUNT_SETTING_MAP["bank_transfer_iban"], "FR76 1020 7000 9822 2117 9625 586"),
        bank_transfer_bic=_get_setting_value(db, ACCOUNT_SETTING_MAP["bank_transfer_bic"], "CCBPFRPPMTG"),
        legal_terms=_get_setting_value(db, ACCOUNT_SETTING_MAP["legal_terms"], ""),
        logo_data_url=_get_setting_value(db, ACCOUNT_SETTING_MAP["logo_data_url"], ""),
    )


@router.put("/config/account", response_model=AdminConfigAccountOut)
def update_admin_config_account(
    payload: AdminConfigAccountUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminConfigAccountOut:
    values = payload.model_dump()
    allowed_currencies = _normalize_currency_codes(values["allowed_currencies"])
    if not allowed_currencies:
        allowed_currencies = ["EUR"]

    default_currency = values["default_currency"].strip().upper()
    if default_currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported default currency")
    if default_currency not in allowed_currencies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Default currency must be in allowed currencies",
        )
    client_balance_default_date_mode = str(values.get("client_balance_default_date_mode") or "TODAY").strip().upper()
    if client_balance_default_date_mode not in ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported balance default date mode")

    for field_name, setting_key in ACCOUNT_SETTING_MAP.items():
        _set_setting(db, setting_key, values[field_name].strip())
    _set_setting(db, ACCOUNT_ALLOWED_CURRENCIES_KEY, ",".join(allowed_currencies))
    _set_setting(db, ACCOUNT_DEFAULT_CURRENCY_KEY, default_currency)
    _set_setting(db, ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODE_KEY, client_balance_default_date_mode)
    db.commit()
    return get_admin_config_account(db=db, current_user=current_user)


@router.get("/config/subscriptions", response_model=AdminSubscriptionSettingsOut)
def get_admin_subscription_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionSettingsOut:
    retry_policy = _default_subscription_retry_policy(db)
    notification_policy = _default_subscription_notification_policy(db)
    return AdminSubscriptionSettingsOut(
        direct_debit_day=_as_int_or_none(_get_setting_value(db, "config_subscription_direct_debit_day", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_direct_debit_day"])),
        allow_card_subscriptions=_as_bool(_get_setting_value(db, "config_subscription_allow_card_subscriptions", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_card_subscriptions"]), True),
        add_contract_signature=_as_bool(_get_setting_value(db, "config_subscription_add_contract_signature", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_add_contract_signature"]), True),
        close_expired_subscriptions=_as_bool(_get_setting_value(db, "config_subscription_close_expired_subscriptions", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_close_expired_subscriptions"]), True),
        allow_promotional_start_period=_as_bool(_get_setting_value(db, "config_subscription_allow_promotional_start_period", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_promotional_start_period"]), False),
        allow_prorata_card=_as_bool(_get_setting_value(db, "config_subscription_allow_prorata_card", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_prorata_card"]), False),
        allow_prorata_sepa=_as_bool(_get_setting_value(db, "config_subscription_allow_prorata_sepa", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_prorata_sepa"]), False),
        online_resiliation_enabled=_as_bool(_get_setting_value(db, "config_subscription_online_resiliation_enabled", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_online_resiliation_enabled"]), True),
        allow_booking_during_payment_alert=_as_bool(
            _get_setting_value(
                db,
                "config_subscription_allow_booking_during_payment_alert",
                SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_booking_during_payment_alert"],
            ),
            True,
        ),
        retry_first_delay_days=int(retry_policy.first_retry_delay_days or 1),
        retry_max_auto_attempts=int(retry_policy.max_auto_attempts or 2),
        retry_move_to_pre_termination_after_failed_attempts=int(
            retry_policy.move_to_pre_termination_after_failed_attempts or retry_policy.max_auto_attempts or 2
        ),
        notify_success_customer_enabled=bool(notification_policy.on_success_customer_enabled),
        notify_success_admin_enabled=bool(notification_policy.on_success_admin_enabled),
        notify_first_failure_customer_enabled=bool(notification_policy.on_first_failure_customer_enabled),
        notify_first_failure_admin_enabled=bool(notification_policy.on_first_failure_admin_enabled),
        notify_final_failure_customer_enabled=bool(notification_policy.on_final_failure_customer_enabled),
        notify_final_failure_admin_enabled=bool(notification_policy.on_final_failure_admin_enabled),
    )


@router.put("/config/subscriptions", response_model=AdminSubscriptionSettingsOut)
def update_admin_subscription_settings(
    payload: AdminSubscriptionSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionSettingsOut:
    if payload.retry_move_to_pre_termination_after_failed_attempts > payload.retry_max_auto_attempts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le seuil pre-resiliation ne peut pas depasser le nombre max de tentatives",
        )

    _set_setting(db, "config_subscription_direct_debit_day", str(payload.direct_debit_day or ""))
    _set_setting(db, "config_subscription_allow_card_subscriptions", "true" if payload.allow_card_subscriptions else "false")
    _set_setting(db, "config_subscription_add_contract_signature", "true" if payload.add_contract_signature else "false")
    _set_setting(db, "config_subscription_close_expired_subscriptions", "true" if payload.close_expired_subscriptions else "false")
    _set_setting(db, "config_subscription_allow_promotional_start_period", "true" if payload.allow_promotional_start_period else "false")
    _set_setting(db, "config_subscription_allow_prorata_card", "true" if payload.allow_prorata_card else "false")
    _set_setting(db, "config_subscription_allow_prorata_sepa", "true" if payload.allow_prorata_sepa else "false")
    _set_setting(db, "config_subscription_online_resiliation_enabled", "true" if payload.online_resiliation_enabled else "false")
    _set_setting(
        db,
        "config_subscription_allow_booking_during_payment_alert",
        "true" if payload.allow_booking_during_payment_alert else "false",
    )

    retry_policy = _default_subscription_retry_policy(db)
    retry_policy.first_retry_delay_days = int(payload.retry_first_delay_days)
    retry_policy.max_auto_attempts = int(payload.retry_max_auto_attempts)
    retry_policy.move_to_pre_termination_after_failed_attempts = int(
        payload.retry_move_to_pre_termination_after_failed_attempts
    )
    retry_policy.active = True
    retry_policy.updated_at = _utcnow()
    db.add(retry_policy)

    notification_policy = _default_subscription_notification_policy(db)
    notification_policy.on_success_customer_enabled = bool(payload.notify_success_customer_enabled)
    notification_policy.on_success_admin_enabled = bool(payload.notify_success_admin_enabled)
    notification_policy.on_first_failure_customer_enabled = bool(payload.notify_first_failure_customer_enabled)
    notification_policy.on_first_failure_admin_enabled = bool(payload.notify_first_failure_admin_enabled)
    notification_policy.on_final_failure_customer_enabled = bool(payload.notify_final_failure_customer_enabled)
    notification_policy.on_final_failure_admin_enabled = bool(payload.notify_final_failure_admin_enabled)
    notification_policy.active = True
    notification_policy.updated_at = _utcnow()
    db.add(notification_policy)

    db.commit()
    return get_admin_subscription_settings(db=db)


@router.get("/config/payment-methods", response_model=AdminPaymentMethodsOut)
def get_admin_payment_methods(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients", "can_view_quotes")),
) -> AdminPaymentMethodsOut:
    raw = _get_setting_value(db, PAYMENT_METHODS_SETTING_KEY, "")
    if raw:
        enabled_codes = _normalize_methods(raw.split(","))
        legacy_default_codes = [code for code, _ in PAYMENT_METHOD_CATALOG if code != "FACTURATION_AUTO"]
        if set(enabled_codes) == set(legacy_default_codes):
            enabled_codes.append("FACTURATION_AUTO")
    else:
        enabled_codes = [code for code, _ in PAYMENT_METHOD_CATALOG]

    enabled_set = set(enabled_codes)
    configured_entity_by_method = _load_payment_method_legal_entity_map(db)
    legal_entities = db.scalars(select(LegalEntity)).all()
    legal_entity_name_by_id = {
        row.id: row.name
        for row in legal_entities
    }
    return AdminPaymentMethodsOut(
        methods=[
            AdminPaymentMethodOptionOut(
                code=code,
                label=label,
                enabled=code in enabled_set,
                default_legal_entity_id=(
                    configured_entity_by_method.get(code)
                    if code in MANUAL_PAYMENT_METHOD_CODES_WITH_DEFAULT_ENTITY
                    else None
                ),
                default_legal_entity_name=(
                    legal_entity_name_by_id.get(configured_entity_by_method.get(code))
                    if code in MANUAL_PAYMENT_METHOD_CODES_WITH_DEFAULT_ENTITY and configured_entity_by_method.get(code) is not None
                    else None
                ),
            )
            for code, label in PAYMENT_METHOD_CATALOG
        ]
    )


@router.put("/config/payment-methods", response_model=AdminPaymentMethodsOut)
def update_admin_payment_methods(
    payload: AdminPaymentMethodsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPaymentMethodsOut:
    enabled_codes = _normalize_methods(payload.enabled_codes)
    _set_setting(db, PAYMENT_METHODS_SETTING_KEY, ",".join(enabled_codes))
    if payload.legal_entity_by_method_code is not None:
        active_entities = db.scalars(select(LegalEntity).where(LegalEntity.is_active.is_(True))).all()
        active_entity_ids = {row.id for row in active_entities}
        normalized_map: dict[str, str] = {}
        for raw_code, raw_legal_entity_id in payload.legal_entity_by_method_code.items():
            code = (raw_code or "").strip().upper()
            if code not in MANUAL_PAYMENT_METHOD_CODES_WITH_DEFAULT_ENTITY:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unsupported payment method for legal entity binding: {code}",
                )
            if raw_legal_entity_id is None:
                continue
            legal_entity_id = UUID(str(raw_legal_entity_id))
            if legal_entity_id not in active_entity_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unknown or inactive legal entity id for {code}",
                )
            normalized_map[code] = str(legal_entity_id)
        _set_setting(
            db,
            PAYMENT_METHODS_LEGAL_ENTITY_MAP_SETTING_KEY,
            json.dumps(normalized_map, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
        )
    db.commit()
    return get_admin_payment_methods(db=db)


@router.get("/config/product-categories", response_model=AdminProductCategoriesOut)
def get_admin_product_categories(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients", "can_view_quotes")),
) -> AdminProductCategoriesOut:
    categories_rows = db.scalars(
        select(ProductCategory)
        .where(ProductCategory.active.is_(True))
        .order_by(ProductCategory.name.asc())
    ).all()
    if categories_rows:
        return AdminProductCategoriesOut(
            categories=[row.name for row in categories_rows],
            updated_at=max((row.updated_at for row in categories_rows), default=None),
        )

    setting = _get_setting(db, PRODUCT_CATEGORIES_SETTING_KEY)
    categories = _parse_product_categories(setting.value) if setting is not None else []
    return AdminProductCategoriesOut(
        categories=categories,
        updated_at=setting.updated_at if setting is not None else None,
    )


@router.put("/config/product-categories", response_model=AdminProductCategoriesOut)
def update_admin_product_categories(
    payload: AdminProductCategoriesUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProductCategoriesOut:
    categories = _normalize_product_categories(payload.categories)
    now = _utcnow()
    existing_rows = db.scalars(select(ProductCategory).order_by(ProductCategory.created_at.asc())).all()
    existing_by_key = {row.name.casefold(): row for row in existing_rows}
    target_keys = {name.casefold() for name in categories}

    for name in categories:
        key = name.casefold()
        row = existing_by_key.get(key)
        if row is None:
            db.add(ProductCategory(name=name, active=True, updated_at=now))
            continue
        row.name = name
        row.active = True
        row.updated_at = now
        db.add(row)

    for row in existing_rows:
        if row.name.casefold() in target_keys:
            continue
        row.active = False
        row.updated_at = now
        db.add(row)

    _set_setting(db, PRODUCT_CATEGORIES_SETTING_KEY, "\n".join(categories))
    db.commit()
    return AdminProductCategoriesOut(categories=categories, updated_at=now)


@router.get("/config/referral-program", response_model=AdminReferralProgramSettingsOut)
def get_admin_referral_program(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminReferralProgramSettingsOut:
    config = referral_program_config(db)
    return AdminReferralProgramSettingsOut(
        enabled=config.enabled,
        currency=config.currency,
        trigger_ratio=config.trigger_ratio,
        announcement_email_enabled=config.announcement_email_enabled,
        credit_email_enabled=config.credit_email_enabled,
        categories={
            code: AdminReferralCategorySettingsOut(
                label=config.category_labels.get(code, code),
                amount=config.category_amounts.get(code, Decimal("0.00")),
                active=config.category_active.get(code, True),
            )
            for code in REFERRAL_CATEGORIES
        },
    )


@router.put("/config/referral-program", response_model=AdminReferralProgramSettingsOut)
def update_admin_referral_program(
    payload: AdminReferralProgramSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminReferralProgramSettingsOut:
    categories: dict[str, dict[str, object]] = {}
    for code in REFERRAL_CATEGORIES:
        source = payload.categories.get(code)
        categories[code] = {
            "label": (source.label if source is not None and source.label else code),
            "amount": f"{Decimal(source.amount if source is not None else Decimal('50.00')).quantize(Decimal('0.01')):.2f}",
            "active": bool(source.active) if source is not None else True,
        }
    value = {
        "enabled": payload.enabled,
        "currency": payload.currency.strip().upper(),
        "trigger_ratio": f"{Decimal(payload.trigger_ratio).quantize(Decimal('0.0001')):.4f}",
        "announcement_email_enabled": payload.announcement_email_enabled,
        "credit_email_enabled": payload.credit_email_enabled,
        "categories": categories,
    }
    _set_setting(db, REFERRAL_PROGRAM_SETTING_KEY, json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    db.commit()
    return get_admin_referral_program(db=db)


@router.get("/config/payment-provider", response_model=AdminPaymentProviderOut)
def get_admin_payment_provider(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPaymentProviderOut:
    provider = resolve_payment_provider(db)
    mode = resolve_payment_mode(db)
    capabilities = CAPABILITIES_BY_PROVIDER[provider]
    values = resolve_payment_secret_values(db)

    return AdminPaymentProviderOut(
        provider=provider.value,
        mode=mode.value,
        subscriptions_supported=capabilities.subscriptions_supported,
        subscriptions_managed_by_psp=capabilities.subscriptions_managed_by_psp,
        recommendation=capabilities.recommendation,
        payplug_test_secret_configured=bool(values["payplug_test_secret"]),
        payplug_live_secret_configured=bool(values["payplug_live_secret"]),
        mollie_test_api_key_configured=bool(values["mollie_test_api_key"]),
        mollie_live_api_key_configured=bool(values["mollie_live_api_key"]),
        stripe_test_secret_configured=bool(values["stripe_test_secret"]),
        stripe_live_secret_configured=bool(values["stripe_live_secret"]),
        stripe_webhook_secret_configured=bool(values["stripe_webhook_secret"]),
        payplug_test_secret_masked=mask_payment_secret(values["payplug_test_secret"]),
        payplug_live_secret_masked=mask_payment_secret(values["payplug_live_secret"]),
        mollie_test_api_key_masked=mask_payment_secret(values["mollie_test_api_key"]),
        mollie_live_api_key_masked=mask_payment_secret(values["mollie_live_api_key"]),
        stripe_test_secret_masked=mask_payment_secret(values["stripe_test_secret"]),
        stripe_live_secret_masked=mask_payment_secret(values["stripe_live_secret"]),
        stripe_webhook_secret_masked=mask_payment_secret(values["stripe_webhook_secret"]),
        webhook_secret_masked=mask_payment_secret(values["webhook_secret"]),
    )


@router.put("/config/payment-provider", response_model=AdminPaymentProviderOut)
def update_admin_payment_provider(
    payload: AdminPaymentProviderUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPaymentProviderOut:
    provider = _normalize_payment_provider(payload.provider)
    mode = _normalize_payment_mode(payload.mode)

    current_values = resolve_payment_secret_values(db)
    payplug_test_secret = _normalized_secret(payload.payplug_test_secret) or current_values["payplug_test_secret"]
    payplug_live_secret = _normalized_secret(payload.payplug_live_secret) or current_values["payplug_live_secret"]
    mollie_test_api_key = _normalized_secret(payload.mollie_test_api_key) or current_values["mollie_test_api_key"]
    mollie_live_api_key = _normalized_secret(payload.mollie_live_api_key) or current_values["mollie_live_api_key"]
    stripe_test_secret = _normalized_secret(payload.stripe_test_secret) or current_values["stripe_test_secret"]
    stripe_live_secret = _normalized_secret(payload.stripe_live_secret) or current_values["stripe_live_secret"]
    stripe_webhook_secret = _normalized_secret(payload.stripe_webhook_secret) or current_values["stripe_webhook_secret"]
    webhook_secret = _normalized_secret(payload.webhook_secret) or current_values["webhook_secret"]

    _validate_provider_keys(
        payplug_test_secret=payplug_test_secret,
        payplug_live_secret=payplug_live_secret,
        mollie_test_api_key=mollie_test_api_key,
        mollie_live_api_key=mollie_live_api_key,
        stripe_test_secret=stripe_test_secret,
        stripe_live_secret=stripe_live_secret,
        stripe_webhook_secret=stripe_webhook_secret,
    )
    active_secret = ""
    if provider == PaymentProvider.PAYPLUG:
        active_secret = payplug_live_secret if mode == PaymentMode.LIVE else payplug_test_secret
    elif provider == PaymentProvider.MOLLIE:
        active_secret = mollie_live_api_key if mode == PaymentMode.LIVE else mollie_test_api_key
    else:
        active_secret = stripe_live_secret if mode == PaymentMode.LIVE else stripe_test_secret
    if not active_secret:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing active API key for selected provider and mode",
        )

    set_payment_setting_value(db, PAYMENT_PROVIDER_SETTING_KEY, provider.value)
    set_payment_setting_value(db, PAYMENT_MODE_SETTING_KEY, mode.value)
    set_payment_setting_value(db, PAYPLUG_TEST_SECRET_SETTING_KEY, payplug_test_secret)
    set_payment_setting_value(db, PAYPLUG_LIVE_SECRET_SETTING_KEY, payplug_live_secret)
    set_payment_setting_value(db, MOLLIE_TEST_API_KEY_SETTING_KEY, mollie_test_api_key)
    set_payment_setting_value(db, MOLLIE_LIVE_API_KEY_SETTING_KEY, mollie_live_api_key)
    set_payment_setting_value(db, STRIPE_TEST_SECRET_SETTING_KEY, stripe_test_secret)
    set_payment_setting_value(db, STRIPE_LIVE_SECRET_SETTING_KEY, stripe_live_secret)
    set_payment_setting_value(db, STRIPE_WEBHOOK_SECRET_SETTING_KEY, stripe_webhook_secret)
    set_payment_setting_value(db, PAYMENT_WEBHOOK_SECRET_SETTING_KEY, webhook_secret)
    db.commit()
    return get_admin_payment_provider(db=db)


@router.get("/config/messaging-settings", response_model=AdminMessagingSettingsOut)
def get_admin_messaging_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMessagingSettingsOut:
    payload, _ = load_messaging_settings(db)
    return AdminMessagingSettingsOut(**payload)


@router.put("/config/messaging-settings", response_model=AdminMessagingSettingsOut)
def update_admin_messaging_settings(
    payload: AdminMessagingSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMessagingSettingsOut:
    updated_payload = save_messaging_settings(
        db,
        studio_email=payload.studio_email,
        studio_sender_name=payload.studio_sender_name,
        teacher_sender_name=payload.teacher_sender_name,
        use_studio_name_as_default_sender=payload.use_studio_name_as_default_sender,
        use_studio_email_for_reminders=payload.use_studio_email_for_reminders,
        use_studio_email_for_lesson_notes=payload.use_studio_email_for_lesson_notes,
        send_birthday_emails=payload.send_birthday_emails,
        email_provider=payload.email_provider,
        email_reply_to=payload.email_reply_to,
        email_subject_prefix=payload.email_subject_prefix,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_username=payload.smtp_username,
        smtp_password=payload.smtp_password,
        smtp_use_tls=payload.smtp_use_tls,
        smtp_use_ssl=payload.smtp_use_ssl,
        smtp_timeout_seconds=payload.smtp_timeout_seconds,
        sms_provider=payload.sms_provider,
        sms_sender=payload.sms_sender,
        brevo_sms_api_key=payload.brevo_sms_api_key,
        frontend_base_url=payload.frontend_base_url,
        quote_send_template_ref=payload.quote_send_template_ref,
        quote_send_sms_template_ref=payload.quote_send_sms_template_ref,
        quote_reminder_template_ref=payload.quote_reminder_template_ref,
        quote_reminder_sms_template_ref=payload.quote_reminder_sms_template_ref,
        quote_cancel_template_ref=payload.quote_cancel_template_ref,
        quote_cancel_sms_template_ref=payload.quote_cancel_sms_template_ref,
        quote_expired_template_ref=payload.quote_expired_template_ref,
        quote_expired_sms_template_ref=payload.quote_expired_sms_template_ref,
        quote_approved_template_ref=payload.quote_approved_template_ref,
        quote_rejected_template_ref=payload.quote_rejected_template_ref,
        quote_change_requested_template_ref=payload.quote_change_requested_template_ref,
        quote_reminder_enabled=payload.quote_reminder_enabled,
        quote_reminder_sms_enabled=payload.quote_reminder_sms_enabled,
        quote_reminder_lead_hours=payload.quote_reminder_lead_hours,
        quote_reminder_lead_hours_csv=payload.quote_reminder_lead_hours_csv,
        quote_daily_job_local_time=payload.quote_daily_job_local_time,
        quote_auto_cancel_enabled=payload.quote_auto_cancel_enabled,
        quote_auto_cancel_delay_hours=payload.quote_auto_cancel_delay_hours,
        quote_cancel_notification_enabled=payload.quote_cancel_notification_enabled,
        quote_cancel_sms_notification_enabled=payload.quote_cancel_sms_notification_enabled,
        quote_expired_notification_enabled=payload.quote_expired_notification_enabled,
        quote_expired_sms_notification_enabled=payload.quote_expired_sms_notification_enabled,
    )
    db.commit()
    return AdminMessagingSettingsOut(**updated_payload)


@router.get("/config/messaging-templates", response_model=list[AdminMessagingTemplateOut])
def get_admin_messaging_templates(
    channel: AdminMessagingChannel | None = Query(default=None),
    kind: AdminMessagingTemplateKind | None = Query(default=None),
    usage_context: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> list[AdminMessagingTemplateOut]:
    items = list_messaging_templates(
        db,
        channel=channel.value if channel is not None else None,
        kind=kind.value if kind is not None else None,
        usage_context=usage_context,
        active_only=active_only,
    )
    return [_serialize_messaging_template(item) for item in items]


@router.put("/config/messaging-templates/predefined/{template_code}", response_model=AdminMessagingTemplateOut)
def update_admin_predefined_messaging_template(
    template_code: str,
    payload: AdminMessagingPredefinedTemplateUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMessagingTemplateOut:
    try:
        item = upsert_predefined_template(
            db,
            code=template_code,
            subject=payload.subject,
            subject_translations=payload.subject_translations,
            body=payload.body,
            body_translations=payload.body_translations,
            body_format=payload.body_format,
            active=payload.active,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _serialize_messaging_template(item)


@router.delete("/config/messaging-templates/predefined/{template_code}", response_model=AdminMessagingTemplateOut)
def reset_admin_predefined_messaging_template(
    template_code: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMessagingTemplateOut:
    try:
        item = reset_predefined_template(db, code=template_code)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    return _serialize_messaging_template(item)


@router.post("/config/messaging-templates/custom", response_model=AdminMessagingTemplateOut, status_code=status.HTTP_201_CREATED)
def create_admin_custom_messaging_template(
    payload: AdminMessagingCustomTemplateCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMessagingTemplateOut:
    try:
        item = create_custom_template(
            db,
            channel=payload.channel.value,
            name=payload.name,
            subject=payload.subject,
            subject_translations=payload.subject_translations,
            body=payload.body,
            body_translations=payload.body_translations,
            body_format=payload.body_format,
            active=payload.active,
            usage_contexts=payload.usage_contexts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _serialize_messaging_template(item)


@router.patch("/config/messaging-templates/custom/{template_id}", response_model=AdminMessagingTemplateOut)
def update_admin_custom_messaging_template(
    template_id: str,
    payload: AdminMessagingCustomTemplateUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMessagingTemplateOut:
    try:
        item = update_custom_template(
            db,
            template_id=template_id,
            name=payload.name,
            subject=payload.subject,
            subject_translations=payload.subject_translations,
            body=payload.body,
            body_translations=payload.body_translations,
            body_format=payload.body_format,
            active=payload.active,
            usage_contexts=payload.usage_contexts,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _serialize_messaging_template(item)


@router.delete("/config/messaging-templates/custom/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_custom_messaging_template(
    template_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    deleted = delete_custom_template(db, template_id=template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom template not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/config/invoice-template", response_model=AdminInvoiceTemplateOut)
def get_admin_invoice_template(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminInvoiceTemplateOut:
    body, updated_at = get_invoice_template(db)
    return AdminInvoiceTemplateOut(
        body=body,
        variables_hint=INVOICE_TEMPLATE_VARIABLES_HINT,
        updated_at=updated_at,
    )


@router.put("/config/invoice-template", response_model=AdminInvoiceTemplateOut)
def update_admin_invoice_template(
    payload: AdminInvoiceTemplateUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminInvoiceTemplateOut:
    updated_at = save_invoice_template(db, body=payload.body)
    db.commit()
    body, _ = get_invoice_template(db)
    return AdminInvoiceTemplateOut(
        body=body,
        variables_hint=INVOICE_TEMPLATE_VARIABLES_HINT,
        updated_at=updated_at,
    )


@router.get("/config/invoice-numbering", response_model=AdminInvoiceNumberingOut)
def get_admin_invoice_numbering(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminInvoiceNumberingOut:
    pattern, next_number, updated_at = get_invoice_numbering(db)
    return AdminInvoiceNumberingOut(
        format_pattern=pattern,
        next_number=next_number,
        preview=preview_invoice_number(pattern=pattern, next_number=next_number),
        updated_at=updated_at,
    )


@router.put("/config/invoice-numbering", response_model=AdminInvoiceNumberingOut)
def update_admin_invoice_numbering(
    payload: AdminInvoiceNumberingUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminInvoiceNumberingOut:
    updated_at = save_invoice_numbering(
        db,
        pattern=payload.format_pattern,
        next_number=payload.next_number,
    )
    db.commit()
    pattern, next_number, _ = get_invoice_numbering(db)
    return AdminInvoiceNumberingOut(
        format_pattern=pattern,
        next_number=next_number,
        preview=preview_invoice_number(pattern=pattern, next_number=next_number),
        updated_at=updated_at,
    )


@router.get("/config/professor-default-grid", response_model=AdminProfessorDefaultGridOut)
def get_admin_professor_default_grid(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorDefaultGridOut:
    return _serialize_default_professor_grid(db)


@router.put("/config/professor-default-grid", response_model=AdminProfessorDefaultGridOut)
def update_admin_professor_default_grid(
    payload: AdminProfessorDefaultGridUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorDefaultGridOut:
    normalized_lines = _normalize_default_grid_lines(db=db, lines=payload.lines)
    save_default_professor_grid(db, lines=normalized_lines)
    db.commit()
    return _serialize_default_professor_grid(db)


@router.get("/config/professor-default-grid/periods", response_model=list[AdminProfessorPayGridPeriodOut])
def list_admin_professor_default_grid_periods(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorPayGridPeriodOut]:
    snapshots = list_default_professor_grid_periods(db)
    return [_serialize_default_professor_grid_period(period) for period in snapshots]


@router.get("/config/professor-default-grid/periods/{period_id}", response_model=AdminProfessorPayGridPeriodDetailOut)
def get_admin_professor_default_grid_period(
    period_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorPayGridPeriodDetailOut:
    snapshot = get_default_professor_grid_period_snapshot(db, period_id=period_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grid period not found")
    lines, _ = load_default_professor_grid_for_period(db, period_id=period_id)
    serialized = _serialize_default_professor_grid_lines(db, lines=lines)
    return AdminProfessorPayGridPeriodDetailOut(
        period=_serialize_default_professor_grid_period(snapshot),
        lines=serialized,
    )


@router.post("/config/professor-default-grid/periods", response_model=AdminProfessorPayGridPeriodOut, status_code=status.HTTP_201_CREATED)
def create_admin_professor_default_grid_period(
    payload: AdminProfessorPayGridPeriodCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorPayGridPeriodOut:
    try:
        period = create_default_professor_grid_period(
            db,
            start_date=payload.start_date,
            end_date=payload.end_date,
            notes=payload.notes,
            clone_from_period_id=payload.clone_from_period_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    snapshot = get_default_professor_grid_period_snapshot(db, period_id=period.id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to load created period")
    return _serialize_default_professor_grid_period(snapshot)


@router.patch("/config/professor-default-grid/periods/{period_id}", response_model=AdminProfessorPayGridPeriodOut)
def update_admin_professor_default_grid_period(
    period_id: UUID,
    payload: AdminProfessorPayGridPeriodUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorPayGridPeriodOut:
    try:
        period = update_default_professor_grid_period(
            db,
            period_id=period_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            notes=payload.notes,
            status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grid period not found")
    db.commit()
    snapshot = get_default_professor_grid_period_snapshot(db, period_id=period.id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to load updated period")
    return _serialize_default_professor_grid_period(snapshot)


@router.post("/config/professor-default-grid/periods/{period_id}/archive", response_model=AdminProfessorPayGridPeriodOut)
def archive_admin_professor_default_grid_period(
    period_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorPayGridPeriodOut:
    period = archive_default_professor_grid_period(db, period_id=period_id)
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grid period not found")
    db.commit()
    snapshot = get_default_professor_grid_period_snapshot(db, period_id=period.id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to load archived period")
    return _serialize_default_professor_grid_period(snapshot)


@router.put("/config/professor-default-grid/periods/{period_id}/rules", response_model=AdminProfessorPayGridPeriodDetailOut)
def update_admin_professor_default_grid_period_rules(
    period_id: UUID,
    payload: AdminProfessorPayGridPeriodRulesUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProfessorPayGridPeriodDetailOut:
    normalized_lines = _normalize_default_grid_lines(db=db, lines=payload.lines)
    try:
        save_default_professor_grid_for_period(
            db,
            period_id=period_id,
            lines=normalized_lines,
            currency_code=(payload.currency_code or "EUR"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    snapshot = get_default_professor_grid_period_snapshot(db, period_id=period_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grid period not found")
    lines, _ = load_default_professor_grid_for_period(db, period_id=period_id)
    serialized = _serialize_default_professor_grid_lines(db, lines=lines)
    return AdminProfessorPayGridPeriodDetailOut(
        period=_serialize_default_professor_grid_period(snapshot),
        lines=serialized,
    )


@router.get("/formulas", response_model=list[AdminFormulaOut])
def list_admin_formulas(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients", "can_view_quotes")),
) -> list[AdminFormulaOut]:
    stmt = select(Plan).order_by(Plan.created_at.asc())
    if not include_inactive:
        stmt = stmt.where(Plan.active.is_(True))
    plans = db.scalars(stmt).all()
    if not plans:
        return []

    plan_ids = [plan.id for plan in plans]
    course_name_by_id = _course_name_map(db)
    rows = db.execute(
        select(PlanEntitlement.plan_id, PlanEntitlement.course_type_id)
        .where(PlanEntitlement.plan_id.in_(plan_ids))
    ).all()
    entitlements_by_plan: dict[UUID, list[UUID]] = {plan_id: [] for plan_id in plan_ids}
    for plan_id, course_type_id in rows:
        entitlements_by_plan.setdefault(plan_id, []).append(course_type_id)

    grant_rows = db.execute(
        select(
            PlanCreditGrant.plan_id,
            PlanCreditGrant.id,
            PlanCreditGrant.credit_type_id,
            PlanCreditGrant.credits_count,
            CreditType.code,
            CreditType.name,
        )
        .join(CreditType, CreditType.id == PlanCreditGrant.credit_type_id, isouter=True)
        .where(PlanCreditGrant.plan_id.in_(plan_ids))
        .order_by(PlanCreditGrant.plan_id.asc(), CreditType.name.asc().nulls_last(), PlanCreditGrant.created_at.asc())
    ).all()
    credit_grants_by_plan: dict[UUID, list[AdminFormulaCreditGrantOut]] = {plan_id: [] for plan_id in plan_ids}
    for plan_id, grant_id, credit_type_id, credits_count, credit_type_code, credit_type_name in grant_rows:
        credit_grants_by_plan.setdefault(plan_id, []).append(
            AdminFormulaCreditGrantOut(
                id=str(grant_id),
                credit_type_id=credit_type_id,
                credit_type_code=credit_type_code,
                credit_type_name=credit_type_name,
                credits_count=int(credits_count),
            )
        )

    return [
        _serialize_formula(
            db,
            plan,
            entitlements_by_plan=entitlements_by_plan,
            course_name_by_id=course_name_by_id,
            credit_grants_by_plan=credit_grants_by_plan,
        )
        for plan in plans
    ]


@router.get("/formulas/{plan_id}", response_model=AdminFormulaOut)
def get_admin_formula(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients", "can_view_quotes")),
) -> AdminFormulaOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formula not found")
    return _serialize_formula(db, plan, course_name_by_id=_course_name_map(db))


@router.post("/formulas", response_model=AdminFormulaOut, status_code=status.HTTP_201_CREATED)
def create_admin_formula(
    payload: AdminFormulaUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminFormulaOut:
    currency_code = payload.currency_code.upper() if payload.currency_code else None
    monthly_price_value, signup_fee_value = _resolved_formula_price_values(
        monthly_price_value=payload.monthly_price_value,
        monthly_price_excl_vat=payload.monthly_price_excl_vat,
        signup_fee_value=payload.signup_fee_value,
        signup_fee_excl_vat=payload.signup_fee_excl_vat,
    )
    if payload.first_purchase_signup_fee_enabled and Decimal(signup_fee_value or 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le montant des frais de dossier du premier achat est obligatoire",
        )
    if payload.first_purchase_partitions_enabled and Decimal(payload.first_purchase_partitions_price_value or 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le tarif des partitions du premier achat est obligatoire",
        )
    _validate_formula_payload(
        kind=payload.kind,
        credits_count=payload.credits_count,
        pack_validity_months=payload.pack_validity_months if payload.kind == PlanKind.PACK else None,
        forfait_start_date=payload.forfait_start_date if payload.kind == PlanKind.FORFAIT else None,
        forfait_end_date=payload.forfait_end_date if payload.kind == PlanKind.FORFAIT else None,
        monthly_price_value=monthly_price_value,
        currency_code=currency_code,
        credit_grants=_normalize_credit_grants(db, payload.credit_grants) if payload.kind == PlanKind.PACK else [],
    )
    entitlement_ids = _normalize_entitlement_ids(
        db,
        payload.entitlement_course_type_ids,
        require_credit_mapping=payload.kind == PlanKind.PACK,
    )
    restrictions_json = _normalize_restrictions(
        payload.restrictions,
        entitlement_course_type_ids=set(entitlement_ids),
    )
    payment_methods = _normalize_methods(payload.payment_methods)
    options = _normalize_option_values(payload.options)
    credit_grants = _normalize_credit_grants(db, payload.credit_grants) if payload.kind == PlanKind.PACK else []
    effective_credits_count = (
        _effective_pack_credits_count(credit_grants, payload.credit_grants_relation)
        if payload.kind == PlanKind.PACK
        else None
    )
    now = _utcnow()

    plan = Plan(
        code=_new_plan_code(payload.name),
        name=payload.name.strip(),
        kind=payload.kind,
        credits_count=effective_credits_count if payload.kind == PlanKind.PACK else None,
        pack_validity_months=payload.pack_validity_months if payload.kind == PlanKind.PACK else None,
        forfait_start_date=payload.forfait_start_date if payload.kind == PlanKind.FORFAIT else None,
        forfait_end_date=payload.forfait_end_date if payload.kind == PlanKind.FORFAIT else None,
        credit_grants_relation=payload.credit_grants_relation if payload.kind == PlanKind.PACK else PlanCreditGrantsRelation.OR,
        monthly_price_value=monthly_price_value,
        price_tax_mode=payload.price_tax_mode,
        monthly_price_excl_vat=monthly_price_value,
        currency_code=currency_code,
        description=(payload.description or "").strip() or None,
        signup_fee_value=signup_fee_value,
        signup_fee_excl_vat=signup_fee_value,
        first_purchase_signup_fee_enabled=payload.first_purchase_signup_fee_enabled,
        first_purchase_partitions_enabled=payload.first_purchase_partitions_enabled,
        first_purchase_partitions_price_value=payload.first_purchase_partitions_price_value,
        is_private=payload.is_private,
        options_json=options,
        payment_methods_json=payment_methods,
        restrictions_json=restrictions_json,
        active=payload.active,
        updated_at=now,
    )
    db.add(plan)
    db.flush()

    for course_type_id in entitlement_ids:
        db.add(PlanEntitlement(plan_id=plan.id, course_type_id=course_type_id))
    for credit_type_id, credits_count in credit_grants:
        db.add(
            PlanCreditGrant(
                plan_id=plan.id,
                credit_type_id=credit_type_id,
                credits_count=credits_count,
                updated_at=now,
            )
        )

    db.commit()
    db.refresh(plan)
    return _serialize_formula(db, plan, course_name_by_id=_course_name_map(db))


@router.patch("/formulas/{plan_id}", response_model=AdminFormulaOut)
def update_admin_formula(
    plan_id: UUID,
    payload: AdminFormulaUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminFormulaOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id).with_for_update())
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formula not found")

    updates = payload.model_dump(exclude_unset=True)
    if "credit_grants" in updates and updates["credit_grants"] is None:
        updates.pop("credit_grants")
    target_kind = updates.get("kind", plan.kind)
    target_monthly_price_value, target_signup_fee_value = _resolved_formula_price_values(
        monthly_price_value=updates.get("monthly_price_value", plan.monthly_price_value),
        monthly_price_excl_vat=updates.get("monthly_price_excl_vat", plan.monthly_price_excl_vat),
        signup_fee_value=updates.get("signup_fee_value", plan.signup_fee_value),
        signup_fee_excl_vat=updates.get("signup_fee_excl_vat", plan.signup_fee_excl_vat),
    )
    target_signup_fee_enabled = bool(
        updates.get("first_purchase_signup_fee_enabled", plan.first_purchase_signup_fee_enabled)
    )
    target_partitions_enabled = bool(
        updates.get("first_purchase_partitions_enabled", plan.first_purchase_partitions_enabled)
    )
    target_partitions_price = updates.get(
        "first_purchase_partitions_price_value",
        plan.first_purchase_partitions_price_value,
    )
    if target_signup_fee_enabled and Decimal(target_signup_fee_value or 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le montant des frais de dossier du premier achat est obligatoire",
        )
    if target_partitions_enabled and Decimal(target_partitions_price or 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le tarif des partitions du premier achat est obligatoire",
        )
    target_credit_grants = (
        _normalize_credit_grants(db, updates["credit_grants"])
        if "credit_grants" in updates and target_kind == PlanKind.PACK
        else None
    )
    if target_credit_grants is None:
        existing_grants = db.execute(
            select(PlanCreditGrant.credit_type_id, PlanCreditGrant.credits_count).where(PlanCreditGrant.plan_id == plan.id)
        ).all()
        target_credit_grants = [(credit_type_id, int(credits_count)) for credit_type_id, credits_count in existing_grants]
    target_credit_relation = (
        updates.get("credit_grants_relation", plan.credit_grants_relation)
        if target_kind == PlanKind.PACK
        else PlanCreditGrantsRelation.OR
    )
    target_credits = _effective_pack_credits_count(target_credit_grants, target_credit_relation) if target_kind == PlanKind.PACK else None
    target_pack_validity_months = (
        updates.get("pack_validity_months", plan.pack_validity_months)
        if target_kind == PlanKind.PACK
        else None
    )
    target_currency_raw = updates.get("currency_code", plan.currency_code)
    target_currency = target_currency_raw.upper() if isinstance(target_currency_raw, str) else target_currency_raw
    _validate_formula_payload(
        kind=target_kind,
        credits_count=target_credits,
        pack_validity_months=target_pack_validity_months,
        forfait_start_date=(
            updates.get("forfait_start_date", plan.forfait_start_date) if target_kind == PlanKind.FORFAIT else None
        ),
        forfait_end_date=updates.get("forfait_end_date", plan.forfait_end_date) if target_kind == PlanKind.FORFAIT else None,
        monthly_price_value=target_monthly_price_value,
        currency_code=target_currency,
        credit_grants=target_credit_grants if target_kind == PlanKind.PACK else [],
    )

    if "name" in updates:
        plan.name = updates["name"].strip()
    if "kind" in updates:
        plan.kind = target_kind
        if target_kind != PlanKind.PACK:
            plan.pack_validity_months = None
        if target_kind != PlanKind.FORFAIT:
            plan.forfait_start_date = None
            plan.forfait_end_date = None
    if "credit_grants_relation" in updates:
        plan.credit_grants_relation = updates["credit_grants_relation"] or PlanCreditGrantsRelation.OR
    if "active" in updates:
        plan.active = bool(updates["active"])
    if "is_private" in updates:
        plan.is_private = bool(updates["is_private"])
    if "description" in updates:
        plan.description = (updates["description"] or "").strip() or None
    if "signup_fee_excl_vat" in updates:
        plan.signup_fee_excl_vat = updates["signup_fee_excl_vat"]
    if "signup_fee_value" in updates:
        plan.signup_fee_value = updates["signup_fee_value"]
    if "first_purchase_signup_fee_enabled" in updates:
        plan.first_purchase_signup_fee_enabled = bool(updates["first_purchase_signup_fee_enabled"])
    if "first_purchase_partitions_enabled" in updates:
        plan.first_purchase_partitions_enabled = bool(updates["first_purchase_partitions_enabled"])
    if "first_purchase_partitions_price_value" in updates:
        plan.first_purchase_partitions_price_value = updates["first_purchase_partitions_price_value"]
    if "monthly_price_excl_vat" in updates:
        plan.monthly_price_excl_vat = updates["monthly_price_excl_vat"]
    if "monthly_price_value" in updates:
        plan.monthly_price_value = updates["monthly_price_value"]
    if "price_tax_mode" in updates:
        plan.price_tax_mode = updates["price_tax_mode"]
    if "currency_code" in updates:
        plan.currency_code = target_currency
    if "credits_count" in updates and target_kind == PlanKind.PACK and "credit_grants" not in updates:
        plan.credits_count = updates["credits_count"]
    if target_kind == PlanKind.PACK and ("pack_validity_months" in updates or "kind" in updates):
        plan.pack_validity_months = target_pack_validity_months
    if target_kind == PlanKind.FORFAIT and ("forfait_start_date" in updates or "kind" in updates):
        plan.forfait_start_date = updates.get("forfait_start_date", plan.forfait_start_date)
    if target_kind == PlanKind.FORFAIT and ("forfait_end_date" in updates or "kind" in updates):
        plan.forfait_end_date = updates.get("forfait_end_date", plan.forfait_end_date)
    if "options" in updates:
        plan.options_json = _normalize_option_values(updates["options"])
    if "payment_methods" in updates:
        plan.payment_methods_json = _normalize_methods(updates["payment_methods"])

    entitlement_ids: list[UUID] | None = None
    if "entitlement_course_type_ids" in updates:
        entitlement_ids = _normalize_entitlement_ids(
            db,
            updates["entitlement_course_type_ids"],
            require_credit_mapping=target_kind == PlanKind.PACK,
        )
        db.execute(delete(PlanEntitlement).where(PlanEntitlement.plan_id == plan.id))
        for course_type_id in entitlement_ids:
            db.add(PlanEntitlement(plan_id=plan.id, course_type_id=course_type_id))
    else:
        entitlement_ids = db.scalars(select(PlanEntitlement.course_type_id).where(PlanEntitlement.plan_id == plan.id)).all()

    if target_kind == PlanKind.PACK and "entitlement_course_type_ids" not in updates and "kind" in updates:
        _normalize_entitlement_ids(
            db,
            list(entitlement_ids),
            require_credit_mapping=True,
        )

    if "restrictions" in updates:
        plan.restrictions_json = _normalize_restrictions(
            updates["restrictions"],
            entitlement_course_type_ids=set(entitlement_ids),
        )

    if "credit_grants" in updates or "kind" in updates or ("credit_grants_relation" in updates and target_kind == PlanKind.PACK):
        db.execute(delete(PlanCreditGrant).where(PlanCreditGrant.plan_id == plan.id))
        now = _utcnow()
        grants_to_write = target_credit_grants if target_kind == PlanKind.PACK else []
        for credit_type_id, credits_count in grants_to_write:
            db.add(
                PlanCreditGrant(
                    plan_id=plan.id,
                    credit_type_id=credit_type_id,
                    credits_count=credits_count,
                    updated_at=now,
                )
            )
        plan.credits_count = _effective_pack_credits_count(grants_to_write, plan.credit_grants_relation) if target_kind == PlanKind.PACK else None
        if target_kind != PlanKind.PACK:
            plan.credit_grants_relation = PlanCreditGrantsRelation.OR

    plan.updated_at = _utcnow()
    db.commit()
    db.refresh(plan)
    return _serialize_formula(db, plan, course_name_by_id=_course_name_map(db))


@router.post("/formulas/{plan_id}/duplicate", response_model=AdminFormulaOut, status_code=status.HTTP_201_CREATED)
def duplicate_admin_formula(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminFormulaOut:
    source = db.scalar(select(Plan).where(Plan.id == plan_id))
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formula not found")

    now = _utcnow()
    copy = Plan(
        code=_new_plan_code(source.name),
        name=f"{source.name} - copie",
        kind=source.kind,
        credits_count=source.credits_count,
        pack_validity_months=source.pack_validity_months,
        forfait_start_date=source.forfait_start_date,
        forfait_end_date=source.forfait_end_date,
        credit_grants_relation=source.credit_grants_relation,
        monthly_price_value=source.monthly_price_value,
        price_tax_mode=source.price_tax_mode,
        monthly_price_excl_vat=source.monthly_price_excl_vat,
        currency_code=source.currency_code,
        description=source.description,
        signup_fee_value=source.signup_fee_value,
        signup_fee_excl_vat=source.signup_fee_excl_vat,
        first_purchase_signup_fee_enabled=bool(source.first_purchase_signup_fee_enabled),
        first_purchase_partitions_enabled=bool(source.first_purchase_partitions_enabled),
        first_purchase_partitions_price_value=source.first_purchase_partitions_price_value,
        is_private=source.is_private,
        options_json=_normalize_option_values(source.options_json if isinstance(source.options_json, list) else []),
        payment_methods_json=_normalize_methods(source.payment_methods_json if isinstance(source.payment_methods_json, list) else []),
        restrictions_json=source.restrictions_json if isinstance(source.restrictions_json, list) else [],
        active=False,
        updated_at=now,
    )
    db.add(copy)
    db.flush()

    entitlements = db.scalars(select(PlanEntitlement).where(PlanEntitlement.plan_id == source.id)).all()
    for entitlement in entitlements:
        db.add(PlanEntitlement(plan_id=copy.id, course_type_id=entitlement.course_type_id))
    grants = db.scalars(select(PlanCreditGrant).where(PlanCreditGrant.plan_id == source.id)).all()
    for grant in grants:
        db.add(
            PlanCreditGrant(
                plan_id=copy.id,
                credit_type_id=grant.credit_type_id,
                credits_count=grant.credits_count,
                updated_at=now,
            )
        )

    db.commit()
    db.refresh(copy)
    return _serialize_formula(db, copy, course_name_by_id=_course_name_map(db))


@router.post("/formulas/{plan_id}/disable", response_model=AdminFormulaOut)
def disable_admin_formula(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminFormulaOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id).with_for_update())
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formula not found")

    plan.active = False
    plan.updated_at = _utcnow()
    db.commit()
    db.refresh(plan)
    return _serialize_formula(db, plan, course_name_by_id=_course_name_map(db))
