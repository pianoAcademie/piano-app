from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import CourseType, CreditType, DeliveryMode
from app.models.ops import AppSetting
from app.models.plan import (
    Plan,
    PlanCreditGrant,
    PlanCreditGrantsRelation,
    PlanEntitlement,
    PlanKind,
    PlanPriceTaxMode,
    PlanRestrictionPeriod,
)
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminActivityOut,
    AdminActivityUpdateRequest,
    AdminActivityUpsertRequest,
    AdminCreditTypeOut,
    AdminCreditTypeUpdateRequest,
    AdminCreditTypeUpsertRequest,
    AdminConfigAccountOut,
    AdminConfigAccountUpdateRequest,
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
    AdminProfessorDefaultGridLineInput,
    AdminProfessorDefaultGridLineOut,
    AdminProfessorDefaultGridOut,
    AdminProfessorDefaultGridRuleOut,
    AdminProfessorDefaultGridUpdateRequest,
    AdminSubscriptionSettingsOut,
    AdminSubscriptionSettingsUpdateRequest,
)
from app.services.professor_contracts import contract_mode_from_course_type
from app.services.professor_default_grid import (
    DefaultProfessorGridLine,
    DefaultProfessorGridRule,
    load_default_professor_grid,
    save_default_professor_grid,
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
    ("CARD_ONLINE", "CB en ligne (Mollie / Payplug)"),
    ("CARD_TERMINAL", "CB sur place (TPE)"),
    ("CHECK", "Cheque"),
    ("CASH", "Especes"),
    ("PAYPAL", "PayPal"),
    ("SEPA_DEBIT", "Prelevement SEPA"),
    ("BANK_TRANSFER", "Virement bancaire"),
]
PAYMENT_METHOD_CODES = {code for code, _ in PAYMENT_METHOD_CATALOG}
SUPPORTED_CURRENCIES = {"EUR", "USD"}
ACCOUNT_ALLOWED_CURRENCIES_KEY = "config_account_allowed_currencies"
ACCOUNT_DEFAULT_CURRENCY_KEY = "config_account_default_currency"

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
    "legal_terms": "config_account_legal_terms",
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
}

PAYMENT_METHODS_SETTING_KEY = "config_payment_methods_enabled"
PRODUCT_CATEGORIES_SETTING_KEY = "config_products_categories_v1"


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


def _serialize_activity(activity: CourseType, *, credit_type_by_id: dict[UUID, CreditType]) -> AdminActivityOut:
    credit_type = credit_type_by_id.get(activity.credit_type_id) if activity.credit_type_id is not None else None
    return AdminActivityOut(
        id=activity.id,
        code=activity.code,
        name=activity.name,
        description=activity.description,
        service_code=activity.service_code,
        credit_type_id=credit_type.id if credit_type is not None else None,
        credit_type_code=credit_type.code if credit_type is not None else None,
        credit_type_name=credit_type.name if credit_type is not None else None,
        duration_minutes=activity.duration_minutes,
        color_hex=activity.color_hex,
        mode=activity.mode,
        default_capacity=activity.default_capacity,
        default_hourly_rate=activity.default_hourly_rate,
        active=activity.active,
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


def _serialize_default_professor_grid(db: Session) -> AdminProfessorDefaultGridOut:
    lines, updated_at = load_default_professor_grid(db)
    if not lines:
        return AdminProfessorDefaultGridOut(lines=[], updated_at=updated_at)

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

    return AdminProfessorDefaultGridOut(lines=serialized_lines, updated_at=updated_at)


def _normalize_payment_provider(raw: str) -> PaymentProvider:
    return parse_payment_provider(raw)


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
) -> None:
    if payplug_test_secret and not payplug_test_secret.startswith("sk_test_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payplug test key must start with sk_test_")
    if payplug_live_secret and not payplug_live_secret.startswith("sk_live_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payplug live key must start with sk_live_")
    if mollie_test_api_key and not mollie_test_api_key.startswith("test_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mollie test key must start with test_")
    if mollie_live_api_key and not mollie_live_api_key.startswith("live_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mollie live key must start with live_")


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
        credit_grants=credit_grants_out,
        credit_grants_relation=plan.credit_grants_relation,
        monthly_price_value=monthly_price_value,
        signup_fee_value=signup_fee_value,
        price_tax_mode=plan.price_tax_mode,
        monthly_price_excl_vat=plan.monthly_price_excl_vat,
        currency_code=plan.currency_code,
        signup_fee_excl_vat=plan.signup_fee_excl_vat,
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
        body=str(raw.get("body") or ""),
        body_format="HTML" if str(raw.get("body_format") or "").strip().upper() == "HTML" else "TEXT",
        active=bool(raw.get("active", True)),
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
    return [_serialize_activity(row, credit_type_by_id=credit_type_by_id) for row in rows]


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

    credit_type = _resolve_credit_type(db, credit_type_id=payload.credit_type_id)

    requested_code = _normalize_activity_code(payload.code, fallback_name=name)
    if payload.code and db.scalar(select(CourseType.id).where(CourseType.code == requested_code)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Activity code already exists")

    code = requested_code
    if not payload.code:
        while db.scalar(select(CourseType.id).where(CourseType.code == code)) is not None:
            code = _new_activity_code(name)

    activity = CourseType(
        code=code,
        name=name,
        description=(payload.description or "").strip() or None,
        service_code=payload.service_code.strip().upper(),
        credit_type_id=credit_type.id,
        duration_minutes=int(payload.duration_minutes),
        color_hex=_normalize_color_hex(payload.color_hex),
        mode=DeliveryMode(payload.mode),
        default_capacity=int(payload.default_capacity),
        default_hourly_rate=payload.default_hourly_rate,
        active=bool(payload.active),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _serialize_activity(activity, credit_type_by_id=_credit_type_by_id(db))


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
        return _serialize_activity(activity, credit_type_by_id=_credit_type_by_id(db))

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

    if "credit_type_id" in changes:
        credit_type_id = changes["credit_type_id"]
        if credit_type_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="credit_type_id is required")
        activity.credit_type_id = _resolve_credit_type(db, credit_type_id=credit_type_id).id

    if "duration_minutes" in changes:
        activity.duration_minutes = int(changes["duration_minutes"])

    if "color_hex" in changes:
        activity.color_hex = _normalize_color_hex(changes["color_hex"])

    if "mode" in changes:
        activity.mode = DeliveryMode(changes["mode"])

    if "default_capacity" in changes:
        activity.default_capacity = int(changes["default_capacity"])

    if "default_hourly_rate" in changes:
        activity.default_hourly_rate = changes["default_hourly_rate"]

    if "active" in changes:
        activity.active = bool(changes["active"])

    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _serialize_activity(activity, credit_type_by_id=_credit_type_by_id(db))


@router.get("/config/account", response_model=AdminConfigAccountOut)
def get_admin_config_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminConfigAccountOut:
    allowed_currencies = _parse_allowed_currencies(_get_setting_value(db, ACCOUNT_ALLOWED_CURRENCIES_KEY, "EUR,USD"))
    default_currency = _parse_default_currency(
        _get_setting_value(db, ACCOUNT_DEFAULT_CURRENCY_KEY, "EUR"),
        allowed_currencies,
    )

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
        legal_terms=_get_setting_value(db, ACCOUNT_SETTING_MAP["legal_terms"], ""),
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

    for field_name, setting_key in ACCOUNT_SETTING_MAP.items():
        _set_setting(db, setting_key, values[field_name].strip())
    _set_setting(db, ACCOUNT_ALLOWED_CURRENCIES_KEY, ",".join(allowed_currencies))
    _set_setting(db, ACCOUNT_DEFAULT_CURRENCY_KEY, default_currency)
    db.commit()
    return get_admin_config_account(db=db, current_user=current_user)


@router.get("/config/subscriptions", response_model=AdminSubscriptionSettingsOut)
def get_admin_subscription_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionSettingsOut:
    return AdminSubscriptionSettingsOut(
        direct_debit_day=_as_int_or_none(_get_setting_value(db, "config_subscription_direct_debit_day", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_direct_debit_day"])),
        allow_card_subscriptions=_as_bool(_get_setting_value(db, "config_subscription_allow_card_subscriptions", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_card_subscriptions"]), True),
        add_contract_signature=_as_bool(_get_setting_value(db, "config_subscription_add_contract_signature", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_add_contract_signature"]), True),
        close_expired_subscriptions=_as_bool(_get_setting_value(db, "config_subscription_close_expired_subscriptions", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_close_expired_subscriptions"]), True),
        allow_promotional_start_period=_as_bool(_get_setting_value(db, "config_subscription_allow_promotional_start_period", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_promotional_start_period"]), False),
        allow_prorata_card=_as_bool(_get_setting_value(db, "config_subscription_allow_prorata_card", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_prorata_card"]), False),
        allow_prorata_sepa=_as_bool(_get_setting_value(db, "config_subscription_allow_prorata_sepa", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_allow_prorata_sepa"]), False),
        online_resiliation_enabled=_as_bool(_get_setting_value(db, "config_subscription_online_resiliation_enabled", SUBSCRIPTION_SETTING_DEFAULTS["config_subscription_online_resiliation_enabled"]), True),
    )


@router.put("/config/subscriptions", response_model=AdminSubscriptionSettingsOut)
def update_admin_subscription_settings(
    payload: AdminSubscriptionSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionSettingsOut:
    _set_setting(db, "config_subscription_direct_debit_day", str(payload.direct_debit_day or ""))
    _set_setting(db, "config_subscription_allow_card_subscriptions", "true" if payload.allow_card_subscriptions else "false")
    _set_setting(db, "config_subscription_add_contract_signature", "true" if payload.add_contract_signature else "false")
    _set_setting(db, "config_subscription_close_expired_subscriptions", "true" if payload.close_expired_subscriptions else "false")
    _set_setting(db, "config_subscription_allow_promotional_start_period", "true" if payload.allow_promotional_start_period else "false")
    _set_setting(db, "config_subscription_allow_prorata_card", "true" if payload.allow_prorata_card else "false")
    _set_setting(db, "config_subscription_allow_prorata_sepa", "true" if payload.allow_prorata_sepa else "false")
    _set_setting(db, "config_subscription_online_resiliation_enabled", "true" if payload.online_resiliation_enabled else "false")
    db.commit()
    return get_admin_subscription_settings(db=db)


@router.get("/config/payment-methods", response_model=AdminPaymentMethodsOut)
def get_admin_payment_methods(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPaymentMethodsOut:
    raw = _get_setting_value(db, PAYMENT_METHODS_SETTING_KEY, "")
    if raw:
        enabled_codes = _normalize_methods(raw.split(","))
    else:
        enabled_codes = [code for code, _ in PAYMENT_METHOD_CATALOG]

    enabled_set = set(enabled_codes)
    return AdminPaymentMethodsOut(
        methods=[
            AdminPaymentMethodOptionOut(code=code, label=label, enabled=code in enabled_set)
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
    db.commit()
    return get_admin_payment_methods(db=db)


@router.get("/config/product-categories", response_model=AdminProductCategoriesOut)
def get_admin_product_categories(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProductCategoriesOut:
    setting = _get_setting(db, PRODUCT_CATEGORIES_SETTING_KEY)
    categories = _parse_product_categories(setting.value) if setting is not None else []
    return AdminProductCategoriesOut(categories=categories, updated_at=setting.updated_at if setting is not None else None)


@router.put("/config/product-categories", response_model=AdminProductCategoriesOut)
def update_admin_product_categories(
    payload: AdminProductCategoriesUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminProductCategoriesOut:
    categories = _normalize_product_categories(payload.categories)
    _set_setting(db, PRODUCT_CATEGORIES_SETTING_KEY, "\n".join(categories))
    db.commit()
    setting = _get_setting(db, PRODUCT_CATEGORIES_SETTING_KEY)
    return AdminProductCategoriesOut(categories=categories, updated_at=setting.updated_at if setting is not None else _utcnow())


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
        payplug_test_secret_masked=mask_payment_secret(values["payplug_test_secret"]),
        payplug_live_secret_masked=mask_payment_secret(values["payplug_live_secret"]),
        mollie_test_api_key_masked=mask_payment_secret(values["mollie_test_api_key"]),
        mollie_live_api_key_masked=mask_payment_secret(values["mollie_live_api_key"]),
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
    webhook_secret = _normalized_secret(payload.webhook_secret) or current_values["webhook_secret"]

    _validate_provider_keys(
        payplug_test_secret=payplug_test_secret,
        payplug_live_secret=payplug_live_secret,
        mollie_test_api_key=mollie_test_api_key,
        mollie_live_api_key=mollie_live_api_key,
    )

    active_secret = payplug_live_secret if provider == PaymentProvider.PAYPLUG and mode == PaymentMode.LIVE else (
        payplug_test_secret if provider == PaymentProvider.PAYPLUG else (
            mollie_live_api_key if mode == PaymentMode.LIVE else mollie_test_api_key
        )
    )
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
    )
    db.commit()
    return AdminMessagingSettingsOut(**updated_payload)


@router.get("/config/messaging-templates", response_model=list[AdminMessagingTemplateOut])
def get_admin_messaging_templates(
    channel: AdminMessagingChannel | None = Query(default=None),
    kind: AdminMessagingTemplateKind | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminMessagingTemplateOut]:
    items = list_messaging_templates(
        db,
        channel=channel.value if channel is not None else None,
        kind=kind.value if kind is not None else None,
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
            body=payload.body,
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
            body=payload.body,
            body_format=payload.body_format,
            active=payload.active,
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
            body=payload.body,
            body_format=payload.body_format,
            active=payload.active,
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


@router.get("/formulas", response_model=list[AdminFormulaOut])
def list_admin_formulas(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
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
    _: User = Depends(require_roles(UserRole.ADMIN)),
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
    _validate_formula_payload(
        kind=payload.kind,
        credits_count=payload.credits_count,
        pack_validity_months=payload.pack_validity_months if payload.kind == PlanKind.PACK else None,
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
        credit_grants_relation=payload.credit_grants_relation if payload.kind == PlanKind.PACK else PlanCreditGrantsRelation.OR,
        monthly_price_value=monthly_price_value,
        price_tax_mode=payload.price_tax_mode,
        monthly_price_excl_vat=monthly_price_value,
        currency_code=currency_code,
        description=(payload.description or "").strip() or None,
        signup_fee_value=signup_fee_value,
        signup_fee_excl_vat=signup_fee_value,
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
        credit_grants_relation=source.credit_grants_relation,
        monthly_price_value=source.monthly_price_value,
        price_tax_mode=source.price_tax_mode,
        monthly_price_excl_vat=source.monthly_price_excl_vat,
        currency_code=source.currency_code,
        description=source.description,
        signup_fee_value=source.signup_fee_value,
        signup_fee_excl_vat=source.signup_fee_excl_vat,
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
