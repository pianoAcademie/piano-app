from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import html
import json
import logging
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
import jwt
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db, require_roles
from app.api.routes.bookings import (
    _count_booked,
    _effective_session_booking_rules,
    _normalize_course_access_key,
    _select_eligible_subscription,
    book_session,
    create_or_refresh_pending_payment_booking,
)
from app.core.config import settings
from app.models.catalog import (
    BOOKING_STATUSES_CONFIRMED,
    BOOKING_STATUSES_CONSUMING_CAPACITY,
    Booking,
    BookingStatus,
    CourseSession,
    CourseType,
    DeliveryMode,
    Location,
    Professor,
    SessionAudienceScope,
    SessionStatus,
)
from app.models.client_record import ClientInvoiceLine, ClientManualCreditBalance, ClientManualTransaction, ClientNoteEntry
from app.models.external_content import (
    CourseTypeContentMapping,
    ExternalContentCourse,
    ExternalContentLesson,
    ExternalContentSection,
    ExternalContentStatus,
)
from app.models.family import ClientFamilyLink
from app.models.plan import (
    ClientForfaitActivityPricing,
    ClientPlanSubscription,
    Plan,
    PlanCreditGrant,
    PlanEntitlement,
    PlanKind,
    PlanPriceTaxMode,
    SubscriptionStatus,
)
from app.models.ops import (
    AppSetting,
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationLog,
    EmailReminder,
    LegalEntity,
    MessageFormat,
)
from app.models.product_catalog import CatalogKit, CatalogKitItem, CatalogProduct, ProductCategory
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.user import ClientKind, User, UserRole
from app.schemas.catalog import SessionCourseTypeOut, SessionLocationOut, SessionOut, SessionProfessorOut
from app.schemas.booking import BookingCreateRequest
from app.schemas.user import (
    ClientCatalogProductOut,
    ClientContentCourseOut,
    ClientContentLessonOut,
    ClientContentMemberAccessOut,
    ClientContentSectionOut,
    ClientFamilyOverviewOut,
    ClientInvoiceOut,
    ClientPaymentConfirmOut,
    ClientMessageOut,
    ClientMessageScope,
    ClientOfferOptionOut,
    ClientPaymentCheckoutOut,
    ClientSessionFormulaOptionOut,
    ClientSessionCheckoutOut,
    ClientSessionPurchaseCatalogOut,
    ClientSessionReservationMemberOptionOut,
    ClientSessionReservationOptionsOut,
    ClientMeUpdateRequest,
    ClientPaymentOut,
    FamilyBookingOut,
    FamilyLinkOut,
    FamilyMemberOut,
    FamilyPlanMiniOut,
    FamilySessionMiniOut,
    FamilySubscriptionOut,
    UserOut,
)
from app.services.family_billing import resolve_billing_profile
from app.services.client_purchase_notifications import send_client_payment_success_notifications
from app.services.i18n import normalize_language
from app.services.invoice_documents import (
    InvoiceAppliedPaymentLine,
    InvoicePeriodLine,
    build_company_identity_snapshot,
    company_identity_from_snapshot,
    render_invoice_period_pdf,
    reserve_next_invoice_number,
    summarize_invoice_period_lines,
)
from app.services.invoice_number_service import InvoiceNumberService
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.payment_checkout import (
    CheckoutCreateRequest,
    create_checkout_session,
    create_stripe_payment_method_setup_session,
    lookup_payment,
    with_webhook_secret,
)
from app.services.payment_receipts import (
    build_booking_receipt_snapshot,
    get_or_create_pending_booking_payment_receipt,
    is_single_booking_invoice_scope,
    payment_receipt_public_payment_url,
    remaining_booking_amount_due,
    should_defer_booking_invoice,
)
from app.services.payment_provider import PaymentProvider, detect_provider_from_reference, resolve_provider, resolve_webhook_secret
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate
from app.services.session_audience import (
    allowed_plan_kinds_for_scopes,
    primary_session_audience_scope,
    resolve_session_booking_scopes,
    resolve_session_visibility_scopes,
    scopes_allow_external_visibility,
    scopes_allow_plan_kind,
    scopes_allow_planless_booking,
)
from app.services.subscriptions import add_months_utc, reconcile_subscription_status

router = APIRouter()
logger = logging.getLogger(__name__)
HTML_TAG_RE = re.compile(r"<[^>]+>")

PAID_PAYMENT_STATUSES = {"PAID", "SUCCEEDED", "COMPLETED"}
CANCELLED_PAYMENT_STATUSES = {"CANCELLED", "EXPIRED", "INACTIVE", "ARCHIVED"}
PENDING_PAYMENT_STATUSES = {
    "PENDING",
    "PENDING_PAYMENT",
    "WAITLISTED",
    "TRIAL",
    "OPEN",
    "CREATED",
    "PROCESSING",
    "WAITING_PAYMENT",
    "FAILED",
    "BOOKED",
    "ATTENDED",
    "NO_SHOW",
}
FAILED_PAYMENT_STATUSES = {"NOT_SUPPORTED", "MISSING_KEY", "MISSING_CUSTOMER_REF", "MISSING_MANDATE_REF", "NETWORK_ERROR", "UNEXPECTED_ERROR"}
ONLINE_COLLECTION_METHOD_CODES = {"CARD_ONLINE", "SEPA_DEBIT", "PAYPAL"}
INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::"
INVOICE_RANGE_PUBLIC_PAYMENT_TOKEN_SCOPE = "INVOICE_RANGE_PUBLIC_PAY"
COUNTRY_NAME_BY_CODE = {
    "FR": "France",
    "BE": "Belgique",
    "CH": "Suisse",
    "LU": "Luxembourg",
    "ES": "Espagne",
    "IT": "Italie",
    "GB": "Royaume-Uni",
    "UK": "Royaume-Uni",
    "US": "Etats-Unis",
    "CA": "Canada",
    "DE": "Allemagne",
}
ACCOUNT_DEFAULT_CURRENCY_KEY = "config_account_default_currency"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _frontend_url(*, path: str) -> str:
    candidate = resolve_frontend_base_url()
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _checkout_urls(*, owner_id: UUID, subscription_id: UUID) -> tuple[str, str, str]:
    query = f"tab=finance&finance_view=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}"
    success_url = _frontend_url(path=f"/client?{query}&payment_return=success")
    cancel_url = _frontend_url(path=f"/client?{query}&payment_return=cancel")
    webhook_url = _frontend_url(path=f"/api/v1/public/payments/webhook?client_id={owner_id}&subscription_id={subscription_id}")
    return success_url, cancel_url, webhook_url


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _is_synthetic_client_email(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    return normalized.endswith("@piano-academie.invalid") or normalized.endswith("@no-email.local")


def _public_client_email(user: User | None) -> str | None:
    if user is None:
        return None
    email = (user.email or "").strip()
    if not email or _is_synthetic_client_email(email):
        return None
    return email


def _account_default_currency(db: Session) -> str:
    raw = db.scalar(select(AppSetting.value).where(AppSetting.key == ACCOUNT_DEFAULT_CURRENCY_KEY))
    candidate = str(raw or "").strip().upper()
    return candidate if len(candidate) == 3 else "EUR"


def _billing_entity_text(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if normalized is None:
        return None
    return " ".join(normalized.split())


def _active_legal_entities_by_id(db: Session) -> dict[UUID, LegalEntity]:
    rows = db.scalars(select(LegalEntity).where(LegalEntity.is_active.is_(True))).all()
    return {row.id: row for row in rows}


def _billing_entity_from_seller_id(
    *,
    legal_entities_by_id: dict[UUID, LegalEntity],
    seller_legal_entity_id: UUID | None,
    fallback_text: str | None = None,
) -> str | None:
    if seller_legal_entity_id is not None:
        entity = legal_entities_by_id.get(seller_legal_entity_id)
        if entity is not None:
            return _billing_entity_text(entity.name)
    return _billing_entity_text(fallback_text)


def _normalize_required(value: str | None, field_name: str) -> str:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be null",
        )
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be empty",
        )
    return normalized


def _validate_timezone(value: str) -> str:
    timezone_name = _normalize_required(value, "timezone")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc
    return timezone_name


def _normalize_optout_channel(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"EMAIL", "SMS", "ALL"}:
        return normalized
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Invalid optout channel",
    )


def _member_out(user: User) -> FamilyMemberOut:
    return FamilyMemberOut(
        id=user.id,
        email=_public_client_email(user),
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.mobile_phone_1 or user.phone,
        mobile_phone_1=user.mobile_phone_1,
        mobile_phone_2=user.mobile_phone_2,
        home_phone=user.home_phone,
        address_line=user.address_line,
        postal_code=user.postal_code,
        city=user.city,
        address_country=user.address_country,
        client_kind=user.client_kind,
        is_active=user.is_active,
    )


def _display_name(user: User) -> str:
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return full_name or _public_client_email(user) or "Membre"


def _message_preview(value: str | None, *, max_length: int = 180) -> str | None:
    normalized = " ".join((value or "").split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[:max_length].rstrip()}..."


def _message_preview_from_html(value: str | None, *, max_length: int = 180) -> str | None:
    if not value:
        return None
    text_value = HTML_TAG_RE.sub(" ", value)
    return _message_preview(text_value, max_length=max_length)


def _client_message_context_label(source: str | None) -> str:
    normalized = (source or "").strip().upper()
    if "PAYMENT_RECEIPT" in normalized:
        return "Justificatif de paiement"
    if "FINAL_INVOICE" in normalized or normalized.startswith("CLIENT_INVOICE"):
        return "Facture"
    if "PAYMENT" in normalized:
        return "Paiement"
    if "BOOKING" in normalized:
        return "Reservation"
    if "REMINDER" in normalized:
        return "Rappel"
    return "Message transactionnel"


def _country_display_name(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    code = value.upper()
    if len(code) == 2:
        return COUNTRY_NAME_BY_CODE.get(code, code)
    return value[:1].upper() + value[1:].lower()


def _billing_address_label(user: User) -> str:
    line_1 = (user.address_line or "").strip()
    city_line = " ".join(part for part in [(user.postal_code or "").strip(), (user.city or "").strip()] if part).strip()
    country = _country_display_name(user.address_country or user.residence_country)
    parts = [line_1, city_line, country]
    return ", ".join(part for part in parts if part) or "-"


def _invoice_recipient_snapshot_for_user(db: Session, user: User) -> dict[str, str]:
    billing_profile = resolve_billing_profile(db, user)
    return {
        "client_name": _display_name(billing_profile),
        "client_billing_address": _billing_address_label(billing_profile),
    }


def _invoice_recipient_name_from_metadata(metadata: dict[str, object], *, fallback: str) -> str:
    return (str(metadata.get("client_name") or "").strip() or fallback)


def _invoice_recipient_address_from_metadata(metadata: dict[str, object], *, fallback: str) -> str:
    return (str(metadata.get("client_billing_address") or "").strip() or fallback)


def _invoice_applied_payment_lines_from_metadata(metadata: dict[str, object]) -> list[InvoiceAppliedPaymentLine]:
    raw_lines = metadata.get("applied_payment_lines")
    if not isinstance(raw_lines, list):
        return []
    out: list[InvoiceAppliedPaymentLine] = []
    for raw_line in raw_lines:
        if not isinstance(raw_line, dict):
            continue
        try:
            amount = Decimal(str(raw_line.get("amount") or "0.00")).quantize(Decimal("0.01"))
        except Exception:
            continue
        if amount == Decimal("0.00"):
            continue
        currency = str(raw_line.get("currency") or "EUR").strip().upper() or "EUR"
        out.append(
            InvoiceAppliedPaymentLine(
                date_label=str(raw_line.get("date") or "").strip() or "-",
                method_label=str(raw_line.get("method") or "").strip() or "Paiement",
                reference_label=str(raw_line.get("reference") or "").strip() or "-",
                amount=amount,
                currency=currency,
            )
        )
    return out


def _is_failed_payment_status(status_value: str) -> bool:
    normalized = (status_value or "").strip().upper()
    if not normalized:
        return False
    if normalized in FAILED_PAYMENT_STATUSES:
        return True
    if normalized.startswith("HTTP_"):
        suffix = normalized[5:]
        if suffix.startswith(("4", "5")) or suffix == "0":
            return True
        return False
    if normalized.startswith("FAILED"):
        return True
    if normalized.endswith("_ERROR"):
        return True
    return False


def _is_success_http_payment_status(status_value: str) -> bool:
    normalized = (status_value or "").strip().upper()
    if not normalized.startswith("HTTP_"):
        return False
    suffix = normalized[5:]
    return suffix.startswith("2")


def _subscription_payment_status(subscription: ClientPlanSubscription) -> str:
    subscription_status = (subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)).strip().upper()
    if subscription_status in CANCELLED_PAYMENT_STATUSES:
        return "CANCELLED"
    if subscription_status == "PENDING":
        return "PENDING"
    due_at = getattr(subscription, "next_payment_at", None) or getattr(subscription, "current_period_end", None)
    if (
        bool(getattr(subscription, "payment_method_setup_required", False))
        and subscription_status in {"ACTIVE", "PAYMENT_ALERT"}
        and due_at is not None
        and due_at <= datetime.now(timezone.utc)
    ):
        return "PENDING"

    last_payment_status = (subscription.last_payment_status or "").strip().upper()
    if last_payment_status:
        if last_payment_status in PAID_PAYMENT_STATUSES:
            return "PAID"
        if _is_success_http_payment_status(last_payment_status):
            return "PAID"
        if last_payment_status in CANCELLED_PAYMENT_STATUSES:
            return "CANCELLED"
        if _is_failed_payment_status(last_payment_status):
            return "FAILED"
        if last_payment_status in PENDING_PAYMENT_STATUSES:
            return "PENDING"
        return "PENDING"

    billing_method = (subscription.billing_method_code or "").strip().upper()
    if billing_method in ONLINE_COLLECTION_METHOD_CODES:
        return "PENDING"
    if billing_method:
        return "PAID"
    return "PENDING"


def _payment_source_label(source: str) -> str:
    normalized = (source or "").strip().upper()
    if normalized == "PLAN_PURCHASE":
        return "Achat formule"
    if normalized == "BOOKING":
        return "Reservation"
    return normalized or "Paiement"


def _invoice_status_from_payment_status(status_value: str) -> str:
    normalized = (status_value or "").strip().upper()
    if normalized in PAID_PAYMENT_STATUSES:
        return "PAID"
    if _is_success_http_payment_status(normalized):
        return "PAID"
    if normalized in CANCELLED_PAYMENT_STATUSES or normalized in {"NOT_BILLABLE", "REFUNDED"}:
        return "CANCELLED"
    return "PENDING"


def _parse_invoice_range_note_entry(note: ClientNoteEntry) -> dict[str, object] | None:
    message = (note.message or "").strip()
    prefix_index = message.find(INVOICE_RANGE_NOTE_PREFIX)
    if prefix_index < 0:
        return None
    raw_payload = message[prefix_index + len(INVOICE_RANGE_NOTE_PREFIX) :].strip()
    if not raw_payload:
        return None
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _parse_optional_uuid(raw_value: object) -> UUID | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _normalize_invoice_range_payment_keys(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        candidate = str(item or "").strip()
        if not candidate:
            continue
        parts = candidate.split(":", 1)
        if len(parts) != 2:
            continue
        source = parts[0].strip().upper()
        payment_id_raw = parts[1].strip()
        if not source or not payment_id_raw:
            continue
        try:
            payment_id = UUID(payment_id_raw)
        except ValueError:
            continue
        normalized = f"{source}:{payment_id}"
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _first_currency_total(metadata: dict[str, object]) -> tuple[Decimal, str]:
    raw_auto_include_previous_balance = metadata.get("auto_include_previous_balance")
    auto_include_previous_balance = (
        bool(raw_auto_include_previous_balance)
        if isinstance(raw_auto_include_previous_balance, bool)
        else True
    )
    if not auto_include_previous_balance:
        totals = metadata.get("totals_by_currency")
        applied_payments = metadata.get("applied_payment_totals_by_currency")
        if isinstance(totals, dict) and totals:
            currencies = set(totals.keys())
            if isinstance(applied_payments, dict):
                currencies |= set(applied_payments.keys())
            for first_currency in sorted(currencies):
                currency_code = str(first_currency).strip().upper() or "EUR"
                try:
                    amount = Decimal(str(totals.get(first_currency, "0.00"))).quantize(Decimal("0.01"))
                    if isinstance(applied_payments, dict):
                        amount += Decimal(str(applied_payments.get(first_currency, "0.00"))).quantize(
                            Decimal("0.01")
                        )
                except Exception:
                    continue
                return amount.quantize(Decimal("0.01")), currency_code

    for key in ("total_to_pay_by_currency", "totals_by_currency"):
        totals = metadata.get(key)
        if not isinstance(totals, dict) or not totals:
            continue
        first_currency = next(iter(sorted(totals.keys())))
        currency_code = str(first_currency).strip().upper() or "EUR"
        raw_amount = totals.get(first_currency)
        try:
            amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
        except Exception:
            continue
        return amount, currency_code
    return Decimal("0.00"), "EUR"


def _invoice_range_status_for_client(raw_status: object) -> str:
    normalized = str(raw_status or "ISSUED").strip().upper()
    if normalized == "PAID":
        return "PAID"
    if normalized == "CANCELLED":
        return "CANCELLED"
    return "PENDING"


def _invoice_range_type_label(metadata: dict[str, object]) -> str:
    generation_mode = str(metadata.get("generation_mode") or "MANUAL").strip().upper()
    return "Facture periode auto" if generation_mode == "AUTO" else "Facture periode"


def _invoice_range_label(metadata: dict[str, object]) -> str:
    start_date = str(metadata.get("start_date") or "").strip()
    end_date = str(metadata.get("end_date") or "").strip()
    if start_date and end_date:
        return f"{start_date} - {end_date}"
    if start_date:
        return start_date
    if end_date:
        return end_date
    return "Facture"


def _create_invoice_range_public_payment_token(
    *,
    client_id: UUID,
    note_id: UUID,
    metadata: dict[str, object],
) -> str:
    payload = {
        "scope": INVOICE_RANGE_PUBLIC_PAYMENT_TOKEN_SCOPE,
        "client_id": str(client_id),
        "note_id": str(note_id),
        "invoice_number": str(metadata.get("invoice_number") or ""),
        "exp": int((_utcnow() + timedelta(days=365)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _invoice_range_public_payment_url(*, client_id: UUID, note_id: UUID, metadata: dict[str, object]) -> str:
    token = _create_invoice_range_public_payment_token(client_id=client_id, note_id=note_id, metadata=metadata)
    return f"{_frontend_url(path='')}/api/v1/public/payments/invoices/range/{client_id}/{note_id}?token={token}"


def _normalize_public_invoice_payment_url(raw_url: str | None) -> str:
    normalized = (raw_url or "").strip()
    if not normalized or "/api/v1/admin/clients/" not in normalized or "/public-pay" not in normalized:
        return normalized
    normalized = normalized.replace(
        "/api/v1/admin/clients/",
        "/api/v1/public/payments/invoices/range/",
        1,
    )
    normalized = normalized.replace("/invoices/range/", "/", 1)
    normalized = normalized.replace("/public-pay/return", "/return")
    normalized = normalized.replace("/public-pay/webhook", "/webhook")
    normalized = normalized.replace("/public-pay", "")
    return normalized


def _payment_key(*, source: str, payment_id: UUID) -> str:
    return f"{(source or '').strip().upper()}:{payment_id}"


def _allocate_invoice_number_for_seller_entity(
    db: Session,
    *,
    seller_legal_entity_id: UUID | None,
    issued_at: datetime,
) -> str:
    if seller_legal_entity_id is None:
        return reserve_next_invoice_number(db, issued_at=issued_at)
    try:
        return InvoiceNumberService.allocate_invoice_number(
            db,
            legal_entity_id=seller_legal_entity_id,
            issued_at=issued_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown seller legal entity for invoice numbering",
        ) from exc


def _build_invoice_range_note_message(metadata: dict[str, object]) -> str:
    start_date = str(metadata.get("start_date") or "")
    end_date = str(metadata.get("end_date") or "")
    issued_date = str(metadata.get("issued_date") or "")
    due_date = str(metadata.get("due_date") or "")
    invoice_number = str(metadata.get("invoice_number") or "")
    summary = (
        f"Facture {invoice_number} generee ({start_date} - {end_date}, "
        f"emise le {issued_date}, echeance {due_date})."
    )
    payload_json = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
    return f"{summary}\n{INVOICE_RANGE_NOTE_PREFIX}{payload_json}"


def _active_booking_invoice_note(
    db: Session,
    *,
    client_id: UUID,
    booking_id: UUID,
) -> tuple[ClientNoteEntry, dict[str, object]] | None:
    note_ids = db.scalars(
        select(ClientInvoiceLine.note_id)
        .where(
            ClientInvoiceLine.user_id == client_id,
            ClientInvoiceLine.source == "BOOKING",
            ClientInvoiceLine.source_payment_id == booking_id,
        )
        .order_by(ClientInvoiceLine.created_at.desc(), ClientInvoiceLine.id.desc())
    ).all()
    seen: set[UUID] = set()
    for note_id in note_ids:
        if note_id in seen:
            continue
        seen.add(note_id)
        note = db.scalar(
            select(ClientNoteEntry).where(
                ClientNoteEntry.id == note_id,
                ClientNoteEntry.user_id == client_id,
            )
        )
        if note is None:
            continue
        metadata = _parse_invoice_range_note_entry(note)
        if metadata is None:
            continue
        if str(metadata.get("invoice_status") or "ISSUED").strip().upper() == "CANCELLED":
            continue
        return note, metadata
    return None


def _create_booking_invoice_note(
    db: Session,
    *,
    booking: Booking,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
    owner: User,
    author_user_id: UUID,
) -> tuple[ClientNoteEntry, dict[str, object]]:
    issued_at = _utcnow()
    issued_date = issued_at.date()
    session_date = session_obj.start_at_utc.astimezone(timezone.utc).date()
    seller_legal_entity_id = session_obj.snapshot_seller_legal_entity_id or course_type.seller_legal_entity_id
    legal_entities_by_id = _active_legal_entities_by_id(db)
    billing_entity = _billing_entity_from_seller_id(
        legal_entities_by_id=legal_entities_by_id,
        seller_legal_entity_id=seller_legal_entity_id,
        fallback_text=session_obj.billing_entity_snapshot,
    )
    resolved_billing_entity = _billing_entity_text(billing_entity) or "ENTITE_NON_DEFINIE"
    currency = (booking.currency_snapshot or "EUR").upper()
    total_incl_vat = Decimal(booking.total_incl_vat_snapshot).quantize(Decimal("0.01"))
    recipient_snapshot = _invoice_recipient_snapshot_for_user(db, owner)
    invoice_number = _allocate_invoice_number_for_seller_entity(
        db,
        seller_legal_entity_id=seller_legal_entity_id,
        issued_at=issued_at,
    )
    metadata: dict[str, object] = {
        "kind": "INVOICE_RANGE",
        "invoice_number": invoice_number,
        "issued_date": issued_date.isoformat(),
        "due_date": issued_date.isoformat(),
        "no_due_date": False,
        "start_date": session_date.isoformat(),
        "end_date": session_date.isoformat(),
        "layout": "DETAILED",
        "billing_entity": resolved_billing_entity,
        "seller_legal_entity_id": str(seller_legal_entity_id) if seller_legal_entity_id is not None else None,
        "generation_mode": "MANUAL",
        "group_adjustments_by_type": False,
        "include_discount_adjustments": False,
        "include_supplement_adjustments": False,
        "include_pending": True,
        "include_cancelled": False,
        "included_payment_keys": [_payment_key(source="BOOKING", payment_id=booking.id)],
        "totals_by_currency": {currency: f"{total_incl_vat:.2f}"},
        "total_to_pay_by_currency": {currency: f"{total_incl_vat:.2f}"},
        "invoice_status": "ISSUED",
        "public_note": f"Reservation {course_type.name} - {location.name}",
        "client_name": recipient_snapshot["client_name"],
        "client_billing_address": recipient_snapshot["client_billing_address"],
        "issuer_snapshot": build_company_identity_snapshot(
            db,
            legal_entity_id=seller_legal_entity_id,
            billing_entity=resolved_billing_entity,
        ),
    }

    note = ClientNoteEntry(
        user_id=owner.id,
        author_user_id=author_user_id,
        entry_type="AUTO",
        message=_build_invoice_range_note_message(metadata),
    )
    db.add(note)
    db.flush()

    invoice_line = ClientInvoiceLine(
        note_id=note.id,
        user_id=owner.id,
        source="BOOKING",
        source_payment_id=booking.id,
        occurred_at=booking.booked_at,
        label=f"{course_type.name} - {location.name}",
        amount_excl_vat=Decimal(booking.price_excl_vat_snapshot).quantize(Decimal("0.01")),
        vat_rate=Decimal(booking.vat_rate_snapshot).quantize(Decimal("0.001")),
        vat_amount=Decimal(booking.vat_amount_snapshot).quantize(Decimal("0.01")),
        total_incl_vat=total_incl_vat,
        currency=currency,
        billing_entity=resolved_billing_entity,
        seller_legal_entity_id=seller_legal_entity_id,
    )
    db.add(invoice_line)
    return note, metadata


def _invoice_period_line_from_invoice_line(line: ClientInvoiceLine) -> InvoicePeriodLine:
    return InvoicePeriodLine(
        date_label=line.occurred_at.strftime("%d/%m/%Y"),
        type_label=_payment_source_label(line.source),
        label=line.label,
        quantity=1,
        amount_excl_vat=Decimal(line.amount_excl_vat).quantize(Decimal("0.01")),
        vat_rate=Decimal(line.vat_rate).quantize(Decimal("0.01")),
        vat_amount=Decimal(line.vat_amount).quantize(Decimal("0.01")),
        total_incl_vat=Decimal(line.total_incl_vat).quantize(Decimal("0.01")),
        currency=(line.currency or "EUR").upper(),
    )


def _client_invoice_quote_row_line_id_from_reference(reference: str | None) -> UUID | None:
    raw = (reference or "").strip()
    if raw.upper().startswith("MODE:") and "|REF:" in raw:
        raw = raw.split("|REF:", maxsplit=1)[1].strip()
    match = re.match(r"^QUOTE:[0-9a-fA-F-]{36}:ROW:(?P<row_id>.+)$", raw)
    if match is None:
        return None
    row_id = match.group("row_id").strip()
    if row_id.startswith("extra-"):
        row_id = row_id[6:].strip()
    try:
        return UUID(row_id)
    except ValueError:
        return None


def _client_invoice_compact_detail(value: str | None, *, max_length: int = 220) -> str | None:
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    if not normalized:
        return None
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _client_invoice_detail_lines(value: str | None, *, max_lines: int = 4, max_chars_per_line: int = 120) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    lines: list[str] = []
    for chunk in raw.splitlines():
        normalized = re.sub(r"\s+", " ", chunk).strip()
        if not normalized:
            continue
        if len(normalized) > max_chars_per_line:
            normalized = normalized[: max_chars_per_line - 3].rstrip() + "..."
        lines.append(normalized)
        if len(lines) >= max_lines:
            break
    if not lines:
        fallback = _client_invoice_compact_detail(raw, max_length=max_chars_per_line)
        if fallback:
            lines.append(fallback)
    return lines


def _client_invoice_kit_details_by_quote_line_id(
    db: Session,
    *,
    quote_line_ids: set[UUID],
) -> dict[UUID, str]:
    if not quote_line_ids:
        return {}

    quote_lines = db.execute(
        select(QuoteLine.id, QuoteLine.kit_id, QuoteLine.description)
        .where(QuoteLine.id.in_(quote_line_ids), QuoteLine.kit_id.is_not(None))
    ).all()
    kit_ids = {kit_id for _line_id, kit_id, _description in quote_lines if kit_id is not None}
    if not kit_ids:
        return {}

    kit_descriptions = {
        kit_id: _client_invoice_compact_detail(long_description) or _client_invoice_compact_detail(short_description)
        for kit_id, short_description, long_description in db.execute(
            select(CatalogKit.id, CatalogKit.short_description, CatalogKit.long_description).where(CatalogKit.id.in_(kit_ids))
        ).all()
    }
    kit_items: dict[UUID, list[str]] = {}
    item_rows = db.execute(
        select(CatalogKitItem.kit_id, CatalogKitItem.quantity, CatalogProduct.title)
        .select_from(CatalogKitItem)
        .join(CatalogProduct, CatalogProduct.id == CatalogKitItem.product_id)
        .where(CatalogKitItem.kit_id.in_(kit_ids))
        .order_by(CatalogKitItem.kit_id.asc(), CatalogKitItem.display_order.asc(), CatalogKitItem.created_at.asc())
    ).all()
    for kit_id, quantity, product_title in item_rows:
        quantity_value = int(quantity or 1)
        prefix = f"{quantity_value} x " if quantity_value > 1 else ""
        kit_items.setdefault(kit_id, []).append(f"{prefix}{product_title}")

    details_by_line_id: dict[UUID, str] = {}
    for line_id, kit_id, quote_line_description in quote_lines:
        if kit_id is None:
            continue
        parts: list[str] = []
        description_lines = _client_invoice_detail_lines(
            quote_line_description,
            max_lines=3,
        ) or _client_invoice_detail_lines(kit_descriptions.get(kit_id), max_lines=3)
        if description_lines:
            parts.append("Description:")
            parts.extend(f"- {line}" for line in description_lines)
        composition = kit_items.get(kit_id, [])
        if composition:
            parts.append("Contenu:")
            parts.extend(f"- {item}" for item in composition)
        if parts:
            details_by_line_id[line_id] = "\n".join(parts)
    return details_by_line_id


def _invoice_period_lines_from_invoice_lines(db: Session, rows: list[ClientInvoiceLine]) -> list[InvoicePeriodLine]:
    manual_line_ids = [
        row.source_payment_id
        for row in rows
        if (row.source or "").strip().upper() == "MANUAL"
    ]
    manual_rows_by_id = {
        row.id: row
        for row in db.scalars(select(ClientManualTransaction).where(ClientManualTransaction.id.in_(manual_line_ids))).all()
    } if manual_line_ids else {}
    quote_line_id_by_invoice_line_id: dict[UUID, UUID] = {}
    for row in rows:
        manual_row = manual_rows_by_id.get(row.source_payment_id)
        if manual_row is None:
            continue
        quote_line_id = _client_invoice_quote_row_line_id_from_reference(manual_row.reference)
        if quote_line_id is not None:
            quote_line_id_by_invoice_line_id[row.id] = quote_line_id
    kit_details_by_quote_line_id = _client_invoice_kit_details_by_quote_line_id(
        db,
        quote_line_ids=set(quote_line_id_by_invoice_line_id.values()),
    )
    invoice_lines: list[InvoicePeriodLine] = []
    for row in rows:
        quote_line_id = quote_line_id_by_invoice_line_id.get(row.id)
        base_line = _invoice_period_line_from_invoice_line(row)
        invoice_lines.append(
            InvoicePeriodLine(
                date_label=base_line.date_label,
                type_label=base_line.type_label,
                label=base_line.label,
                quantity=base_line.quantity,
                amount_excl_vat=base_line.amount_excl_vat,
                vat_rate=base_line.vat_rate,
                vat_amount=base_line.vat_amount,
                total_incl_vat=base_line.total_incl_vat,
                currency=base_line.currency,
                is_section_header=base_line.is_section_header,
                detail_label=kit_details_by_quote_line_id.get(quote_line_id) if quote_line_id is not None else None,
            )
        )
    return invoice_lines


def _invoice_period_totals_from_lines_or_metadata(
    invoice_lines: list[InvoicePeriodLine],
    metadata: dict[str, object],
) -> dict[str, dict[str, Decimal]]:
    totals_by_currency: dict[str, dict[str, Decimal]] = {}
    if invoice_lines:
        totals_by_currency, _ = summarize_invoice_period_lines(invoice_lines)
        if totals_by_currency:
            return totals_by_currency

    raw_totals = metadata.get("totals_by_currency")
    if isinstance(raw_totals, dict):
        for currency_code, total_text in raw_totals.items():
            currency = str(currency_code).strip().upper() or "EUR"
            try:
                total = Decimal(str(total_text)).quantize(Decimal("0.01"))
            except Exception:
                continue
            totals_by_currency[currency] = {
                "amount_excl_vat": total,
                "vat_amount": Decimal("0.00"),
                "total_incl_vat": total,
            }
    if totals_by_currency:
        return totals_by_currency

    amount, currency_code = _first_currency_total(metadata)
    return {
        currency_code: {
            "amount_excl_vat": amount,
            "vat_amount": Decimal("0.00"),
            "total_incl_vat": amount,
        }
    }


def _booking_uuid_from_payment_id(payment_id: str) -> UUID | None:
    raw_id = str(payment_id or "").split(":", maxsplit=1)[-1].strip()
    if not raw_id:
        return None
    try:
        return UUID(raw_id)
    except ValueError:
        return None


def _forfait_booking_ids(db: Session, booking_ids: list[UUID]) -> set[UUID]:
    unique_ids = list({booking_id for booking_id in booking_ids if booking_id is not None})
    if not unique_ids:
        return set()

    rows = db.execute(
        select(Booking.id)
        .select_from(Booking)
        .join(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id, isouter=True)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id, isouter=True)
        .where(
            Booking.id.in_(unique_ids),
            Plan.kind == PlanKind.FORFAIT,
        )
    ).all()
    return {row[0] for row in rows}


def _non_negative_money(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    quantized = Decimal(value).quantize(Decimal("0.01"))
    if quantized < Decimal("0.00"):
        return Decimal("0.00")
    return quantized


def _forfait_subscription_pricing_applies(
    subscription: ClientPlanSubscription | None,
    *,
    session_start_at: datetime,
) -> bool:
    if subscription is None:
        return False
    if session_start_at < subscription.started_at:
        return False
    if subscription.ends_at is not None and session_start_at >= subscription.ends_at:
        return False
    return True


def _forfait_hourly_ttc_with_overrides(
    *,
    base_hourly_ttc: Decimal,
    subscription: ClientPlanSubscription | None,
    session_start_at: datetime,
    course_type_id: UUID,
    session_timezone: str,
    booking_id: UUID | None,
    db: Session,
    pricing_map: dict[tuple[UUID, UUID], tuple[Decimal, Decimal, Decimal, Decimal]] | None = None,
) -> Decimal:
    if not _forfait_subscription_pricing_applies(subscription, session_start_at=session_start_at):
        return base_hourly_ttc

    loyalty_discount = Decimal("0.00")
    family_discount = Decimal("0.00")
    short_commitment_supplement = Decimal("0.00")
    second_course_weekly_discount = Decimal("0.00")
    if subscription is not None:
        key = (subscription.id, course_type_id)
        values = pricing_map.get(key) if pricing_map is not None else None
        if values is None:
            row = db.execute(
                select(
                    ClientForfaitActivityPricing.loyalty_discount_per_hour_ttc,
                    ClientForfaitActivityPricing.family_discount_per_hour_ttc,
                    ClientForfaitActivityPricing.short_commitment_supplement_per_hour_ttc,
                    ClientForfaitActivityPricing.second_course_weekly_discount_per_hour_ttc,
                ).where(
                    ClientForfaitActivityPricing.subscription_id == subscription.id,
                    ClientForfaitActivityPricing.course_type_id == course_type_id,
                )
            ).first()
            if row is not None:
                values = (
                    _non_negative_money(row[0]),
                    _non_negative_money(row[1]),
                    _non_negative_money(row[2]),
                    _non_negative_money(row[3]),
                )
        if values is not None:
            loyalty_discount, family_discount, short_commitment_supplement, second_course_weekly_discount = values
    second_course_weekly_applies = (
        second_course_weekly_discount > Decimal("0.00")
        and subscription is not None
        and _forfait_second_course_weekly_applies(
            db,
            subscription=subscription,
            course_type_id=course_type_id,
            session_start_at=session_start_at,
            session_timezone=session_timezone,
            booking_id=booking_id,
        )
    )
    if second_course_weekly_applies and second_course_weekly_discount > loyalty_discount:
        # "2e cours semaine" replaces fidelity discount when it is more favorable.
        loyalty_discount = second_course_weekly_discount
    if (
        loyalty_discount <= Decimal("0.00")
        and family_discount <= Decimal("0.00")
        and short_commitment_supplement <= Decimal("0.00")
    ):
        return base_hourly_ttc
    adjusted = (base_hourly_ttc - loyalty_discount - family_discount + short_commitment_supplement).quantize(Decimal("0.01"))
    if adjusted < Decimal("0.00"):
        return Decimal("0.00")
    return adjusted


def _forfait_week_utc_bounds(*, session_start_at: datetime, session_timezone: str) -> tuple[datetime, datetime]:
    tz_name = (session_timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    local_start = session_start_at.astimezone(tz)
    week_start_local = (local_start - timedelta(days=local_start.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_end_local = week_start_local + timedelta(days=7)
    return week_start_local.astimezone(timezone.utc), week_end_local.astimezone(timezone.utc)


def _forfait_second_course_weekly_applies(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    course_type_id: UUID,
    session_start_at: datetime,
    session_timezone: str,
    booking_id: UUID | None,
) -> bool:
    week_start_utc, week_end_utc = _forfait_week_utc_bounds(
        session_start_at=session_start_at,
        session_timezone=session_timezone,
    )
    counted_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )
    earlier_filters = [CourseSession.start_at_utc < session_start_at]
    if booking_id is not None:
        earlier_filters.append((CourseSession.start_at_utc == session_start_at) & (Booking.id < booking_id))
    earlier_count = int(
        db.scalar(
            select(func.count(Booking.id))
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == subscription.user_id,
                Booking.client_plan_subscription_id == subscription.id,
                Booking.status.in_(counted_statuses),
                CourseSession.status != SessionStatus.CANCELLED,
                CourseSession.course_type_id == course_type_id,
                CourseSession.start_at_utc >= week_start_utc,
                CourseSession.start_at_utc < week_end_utc,
                or_(*earlier_filters),
            )
        )
        or 0
    )
    return earlier_count >= 1


def _forfait_activity_pricing_map(
    db: Session,
    *,
    subscription_ids: set[UUID],
) -> dict[tuple[UUID, UUID], tuple[Decimal, Decimal, Decimal, Decimal]]:
    if not subscription_ids:
        return {}
    rows = db.execute(
        select(
            ClientForfaitActivityPricing.subscription_id,
            ClientForfaitActivityPricing.course_type_id,
            ClientForfaitActivityPricing.loyalty_discount_per_hour_ttc,
            ClientForfaitActivityPricing.family_discount_per_hour_ttc,
            ClientForfaitActivityPricing.short_commitment_supplement_per_hour_ttc,
            ClientForfaitActivityPricing.second_course_weekly_discount_per_hour_ttc,
        ).where(ClientForfaitActivityPricing.subscription_id.in_(subscription_ids))
    ).all()
    out: dict[tuple[UUID, UUID], tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    for subscription_id, course_type_id, loyalty_discount, family_discount, short_commitment_supplement, second_course_weekly_discount in rows:
        out[(subscription_id, course_type_id)] = (
            _non_negative_money(loyalty_discount),
            _non_negative_money(family_discount),
            _non_negative_money(short_commitment_supplement),
            _non_negative_money(second_course_weekly_discount),
        )
    return out


def _resolve_activity_base_hourly_ttc(course_type: CourseType) -> Decimal | None:
    if course_type.default_course_rate_ttc is not None:
        reference_minutes = int(course_type.duration_minutes or 0)
        if reference_minutes <= 0:
            return None
        reference_hours = Decimal(reference_minutes) / Decimal("60")
        if reference_hours <= Decimal("0.00"):
            return None
        return Decimal(course_type.default_course_rate_ttc) / reference_hours
    if course_type.default_hourly_rate is not None:
        return Decimal(course_type.default_hourly_rate).quantize(Decimal("0.01"))
    return None


def _booking_vat_country(
    *,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location | None,
    billing_profile: User,
) -> str:
    if course_type.mode == DeliveryMode.ONLINE:
        is_online = True
    elif course_type.mode == DeliveryMode.ONSITE:
        is_online = False
    else:
        is_online = bool(location.is_online) if location is not None else False

    if is_online:
        return (billing_profile.residence_country or "FR").upper()
    if location is not None:
        return (location.country_code or "FR").upper()
    return "FR"


def _booking_amounts_from_activity(
    *,
    booking: Booking,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location | None,
    billing_profile: User,
    forfait_subscription: ClientPlanSubscription | None,
    db: Session,
    pricing_map: dict[tuple[UUID, UUID], tuple[Decimal, Decimal, Decimal, Decimal]] | None = None,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str] | None:
    base_hourly_ttc = _resolve_activity_base_hourly_ttc(course_type)
    if base_hourly_ttc is None:
        return None

    duration_seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
    if duration_seconds <= 0:
        duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
    duration_hours = Decimal(duration_seconds) / Decimal("3600")
    hourly_ttc = _forfait_hourly_ttc_with_overrides(
        base_hourly_ttc=base_hourly_ttc,
        subscription=forfait_subscription,
        session_start_at=session_obj.start_at_utc,
        course_type_id=course_type.id,
        session_timezone=session_obj.timezone,
        booking_id=booking.id,
        db=db,
        pricing_map=pricing_map,
    )
    total_incl_vat = (hourly_ttc * duration_hours).quantize(Decimal("0.01"))

    country_code = _booking_vat_country(
        session_obj=session_obj,
        course_type=course_type,
        location=location,
        billing_profile=billing_profile,
    )
    vat_rate = resolve_vat_rate(
        db,
        country=country_code,
        service_code=course_type.service_code,
        on_date=session_obj.start_at_utc.date(),
    ).quantize(Decimal("0.01"))

    if vat_rate <= Decimal("0.00"):
        amount_excl_vat = total_incl_vat
        vat_amount = Decimal("0.00")
    else:
        divisor = Decimal("1.00") + (vat_rate / Decimal("100.00"))
        amount_excl_vat = (total_incl_vat / divisor).quantize(Decimal("0.01")) if divisor > Decimal("0.00") else total_incl_vat
        vat_amount = (total_incl_vat - amount_excl_vat).quantize(Decimal("0.01"))

    currency = (booking.currency_snapshot or billing_profile.preferred_currency or "EUR").upper()
    return amount_excl_vat, vat_rate, vat_amount, total_incl_vat, currency


def _managed_client_ids_for_sessions(db: Session, current_user: User) -> set[UUID]:
    managed_ids: set[UUID] = {current_user.id}
    if current_user.client_kind != ClientKind.ADULT:
        return managed_ids

    child_ids = db.scalars(
        select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == current_user.id)
    ).all()
    managed_ids.update(child_ids)
    return managed_ids


def _plan_payment_methods(plan: Plan) -> list[str]:
    raw = plan.payment_methods_json
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in raw:
        code = str(value or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _formula_frequency_label(kind: PlanKind) -> str | None:
    if kind == PlanKind.SUBSCRIPTION:
        return "Mensuel"
    return None


def _formula_purchase_link_allowed(plan: Plan) -> bool:
    raw = plan.options_json if isinstance(plan.options_json, list) else []
    normalized = {str(value or "").strip().lower() for value in raw if str(value or "").strip()}
    if normalized & {"achat_par_lien_desactive", "purchase_link_disabled", "buy_link_disabled"}:
        return False
    return True


def _formula_price_snapshot(plan: Plan) -> tuple[Decimal | None, str]:
    if plan.monthly_price_value is not None:
        return Decimal(plan.monthly_price_value).quantize(Decimal("0.01")), (plan.currency_code or "EUR").upper()
    if plan.monthly_price_excl_vat is not None:
        return Decimal(plan.monthly_price_excl_vat).quantize(Decimal("0.01")), (plan.currency_code or "EUR").upper()
    return None, (plan.currency_code or "EUR").upper()


def _formula_option_out(plan: Plan, *, restriction_labels: list[str]) -> ClientSessionFormulaOptionOut:
    price_snapshot, currency = _formula_price_snapshot(plan)
    return ClientSessionFormulaOptionOut(
        formula_id=plan.id,
        formula_code=plan.code,
        formula_type=plan.kind,
        name=plan.name,
        description=plan.description,
        price_ttc=price_snapshot,
        currency=currency,
        frequency_label=_formula_frequency_label(plan.kind),
        restriction_labels=restriction_labels,
        payment_methods=_plan_payment_methods(plan),
    )


def _active_formula_options_for_course_type(
    db: Session,
    *,
    course_type_id: UUID,
    course_type_name: str,
    course_type_service_code: str | None,
    credit_type_id: UUID | None,
    allowed_plan_kinds: set[PlanKind],
) -> list[ClientSessionFormulaOptionOut]:
    if not allowed_plan_kinds:
        return []
    target_keys = {
        normalized
        for normalized in (
            _normalize_course_access_key(course_type_name),
            _normalize_course_access_key(course_type_service_code),
        )
        if normalized
    }

    try:
        candidate_rows = db.execute(
            select(
                Plan,
                PlanEntitlement.course_type_id,
                CourseType.name,
                CourseType.service_code,
                PlanCreditGrant.credit_type_id,
            )
            .select_from(Plan)
            .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id, isouter=True)
            .join(CourseType, CourseType.id == PlanEntitlement.course_type_id, isouter=True)
            .join(PlanCreditGrant, PlanCreditGrant.plan_id == Plan.id, isouter=True)
            .where(
                Plan.active.is_(True),
                Plan.is_private.is_(False),
                Plan.kind.in_(tuple(allowed_plan_kinds)),
            )
            .order_by(Plan.kind.asc(), Plan.name.asc())
        ).all()
    except Exception:
        logger.exception(
            "Failed to query formula options for course_type %s",
            course_type_id,
        )
        return []

    matched_plans: dict[UUID, Plan] = {}
    for plan, entitlement_course_type_id, entitlement_name, entitlement_service_code, grant_credit_type_id in candidate_rows:
        matches_exact_entitlement = entitlement_course_type_id == course_type_id
        matches_credit_type = (
            credit_type_id is not None
            and plan.kind == PlanKind.PACK
            and grant_credit_type_id == credit_type_id
        )
        entitlement_keys = {
            normalized
            for normalized in (
                _normalize_course_access_key(entitlement_name),
                _normalize_course_access_key(entitlement_service_code),
            )
            if normalized
        }
        matches_normalized_activity = bool(entitlement_keys & target_keys)
        if not (matches_exact_entitlement or matches_credit_type or matches_normalized_activity):
            continue
        if not _formula_purchase_link_allowed(plan):
            continue
        matched_plans.setdefault(plan.id, plan)

    options: list[ClientSessionFormulaOptionOut] = []
    for plan in matched_plans.values():
        try:
            options.append(_formula_option_out(plan, restriction_labels=[course_type_name]))
        except Exception:
            logger.exception(
                "Failed to normalize formula option for course_type %s and plan %s",
                course_type_id,
                getattr(plan, "id", None),
            )
    return options


def _session_purchase_catalog(
    db: Session,
    *,
    session_obj: CourseSession,
    course_type: CourseType,
) -> tuple[list[ClientSessionFormulaOptionOut], Decimal | None, str | None, list[SessionAudienceScope]]:
    session_booking_scopes = resolve_session_booking_scopes(
        session_obj,
        allows_student_bookings=bool(course_type.allows_student_bookings),
    )
    allows_planless_booking = scopes_allow_planless_booking(session_booking_scopes)
    allowed_plan_kinds = allowed_plan_kinds_for_scopes(session_booking_scopes)
    formula_options = _active_formula_options_for_course_type(
        db,
        course_type_id=course_type.id,
        course_type_name=course_type.name,
        course_type_service_code=course_type.service_code,
        credit_type_id=course_type.credit_type_id,
        allowed_plan_kinds=allowed_plan_kinds,
    )
    direct_payment_amount = None
    if allows_planless_booking and session_obj.external_booking_price_ttc is not None:
        duration_seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
        if duration_seconds <= 0:
            duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
        duration_hours = Decimal(duration_seconds) / Decimal("3600")
        direct_payment_amount = (Decimal(session_obj.external_booking_price_ttc) * duration_hours).quantize(Decimal("0.01"))
    direct_payment_currency = (
        (getattr(session_obj, "external_booking_currency", None) or _account_default_currency(db)).upper()
        if direct_payment_amount is not None
        else None
    )
    return formula_options, direct_payment_amount, direct_payment_currency, session_booking_scopes


def _clean_external_content_text(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if normalized is None:
        return None
    decoded = html.unescape(normalized)
    cleaned = decoded.replace("\ufffc", "").replace("\xa0", " ")
    collapsed = " ".join(cleaned.split())
    return collapsed or None


def _clean_external_content_summary(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if normalized is None:
        return None
    decoded = html.unescape(normalized).replace("\ufffc", "").replace("\xa0", " ")
    stripped = HTML_TAG_RE.sub(" ", decoded)
    collapsed = " ".join(stripped.split())
    return collapsed or None


def _clean_external_content_html(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if normalized is None:
        return None
    cleaned = html.unescape(normalized).replace("\ufffc", "")
    for source, target in (
        ("http://www.cloudlearning.fr/", "https://www.cloudlearning.fr/"),
        ("http://cloudlearning.fr/", "https://cloudlearning.fr/"),
        ("http://www.piano-academie.com/", "https://www.piano-academie.com/"),
        ("http://piano-academie.com/", "https://piano-academie.com/"),
    ):
        cleaned = cleaned.replace(source, target)
    return cleaned or None


def _client_content_lesson_out(lesson: ExternalContentLesson) -> ClientContentLessonOut:
    return ClientContentLessonOut(
        id=lesson.id,
        external_id=lesson.external_id,
        slug=lesson.slug,
        title=_clean_external_content_text(lesson.title) or lesson.title,
        position=lesson.position,
        summary=_clean_external_content_summary(lesson.summary),
        content_html=_clean_external_content_html(lesson.content_html),
        video_url=lesson.video_url,
        resource_url=lesson.resource_url,
        status=lesson.status.value if hasattr(lesson.status, "value") else str(lesson.status),
    )


def _client_content_courses(
    db: Session,
    *,
    current_user: User,
    member_id: UUID | None = None,
) -> list[ClientContentCourseOut]:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    target_member_ids = managed_client_ids
    if member_id is not None:
        if member_id not in managed_client_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        target_member_ids = {member_id}

    member_rows = db.scalars(select(User).where(User.id.in_(target_member_ids))).all() if target_member_ids else []
    members_by_id = {member.id: member for member in member_rows}
    if not members_by_id:
        return []

    now = _utcnow()
    entitlement_rows = db.execute(
        select(
            ClientPlanSubscription.user_id,
            PlanEntitlement.course_type_id,
            CourseType.name,
        )
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(PlanEntitlement, PlanEntitlement.plan_id == ClientPlanSubscription.plan_id)
        .join(CourseType, CourseType.id == PlanEntitlement.course_type_id)
        .where(
            ClientPlanSubscription.user_id.in_(target_member_ids),
            ClientPlanSubscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAYMENT_ALERT,
                SubscriptionStatus.PAUSED,
            ]),
            ClientPlanSubscription.started_at <= now,
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > now),
            Plan.active.is_(True),
        )
    ).all()

    course_type_ids_by_member: dict[UUID, set[UUID]] = defaultdict(set)
    course_type_names_by_member: dict[UUID, dict[UUID, str]] = defaultdict(dict)
    for owner_id, course_type_id, course_type_name in entitlement_rows:
        course_type_ids_by_member[owner_id].add(course_type_id)
        course_type_names_by_member[owner_id][course_type_id] = course_type_name

    all_course_type_ids = sorted(
        {course_type_id for values in course_type_ids_by_member.values() for course_type_id in values},
        key=lambda value: str(value),
    )
    if not all_course_type_ids:
        return []

    mapping_rows = db.execute(
        select(CourseTypeContentMapping, ExternalContentCourse, CourseType)
        .join(ExternalContentCourse, ExternalContentCourse.id == CourseTypeContentMapping.content_course_id)
        .join(CourseType, CourseType.id == CourseTypeContentMapping.course_type_id)
        .where(
            CourseTypeContentMapping.course_type_id.in_(all_course_type_ids),
            CourseTypeContentMapping.active.is_(True),
            ExternalContentCourse.status == ExternalContentStatus.PUBLISHED,
        )
        .order_by(
            ExternalContentCourse.level_code.asc().nulls_last(),
            CourseTypeContentMapping.sort_order.asc(),
            ExternalContentCourse.title.asc(),
        )
    ).all()
    if not mapping_rows:
        return []

    course_ids = [course.id for _, course, _ in mapping_rows]
    section_rows = db.scalars(
        select(ExternalContentSection)
        .where(ExternalContentSection.course_id.in_(course_ids))
        .order_by(
            ExternalContentSection.course_id.asc(),
            ExternalContentSection.position.asc(),
            ExternalContentSection.title.asc(),
        )
    ).all()
    lesson_rows = db.scalars(
        select(ExternalContentLesson)
        .where(
            ExternalContentLesson.course_id.in_(course_ids),
            ExternalContentLesson.status == ExternalContentStatus.PUBLISHED,
        )
        .order_by(
            ExternalContentLesson.course_id.asc(),
            ExternalContentLesson.section_id.asc().nulls_first(),
            ExternalContentLesson.position.asc(),
            ExternalContentLesson.title.asc(),
        )
    ).all()

    sections_by_course: dict[UUID, list[ExternalContentSection]] = defaultdict(list)
    for section in section_rows:
        sections_by_course[section.course_id].append(section)

    lessons_by_section: dict[UUID, list[ExternalContentLesson]] = defaultdict(list)
    standalone_lessons_by_course: dict[UUID, list[ExternalContentLesson]] = defaultdict(list)
    for lesson in lesson_rows:
        if lesson.section_id is None:
            standalone_lessons_by_course[lesson.course_id].append(lesson)
        else:
            lessons_by_section[lesson.section_id].append(lesson)

    course_entries: dict[UUID, dict[str, object]] = {}
    for mapping, course, course_type in mapping_rows:
        entitled_member_ids = [
            member_uuid
            for member_uuid, member_course_type_ids in course_type_ids_by_member.items()
            if mapping.course_type_id in member_course_type_ids
        ]
        if not entitled_member_ids:
            continue

        if course.id not in course_entries:
            course_entries[course.id] = {
                "course": course,
                "member_accesses": {},
            }
        access_map: dict[UUID, dict[str, object]] = course_entries[course.id]["member_accesses"]  # type: ignore[assignment]

        for member_uuid in entitled_member_ids:
            member = members_by_id.get(member_uuid)
            if member is None:
                continue
            access_entry = access_map.get(member_uuid)
            if access_entry is None:
                access_entry = {
                    "member": member,
                    "course_type_ids": [],
                    "course_type_names": [],
                }
                access_map[member_uuid] = access_entry
            course_type_ids_list: list[UUID] = access_entry["course_type_ids"]  # type: ignore[assignment]
            course_type_names_list: list[str] = access_entry["course_type_names"]  # type: ignore[assignment]
            if mapping.course_type_id not in course_type_ids_list:
                course_type_ids_list.append(mapping.course_type_id)
            if course_type.name not in course_type_names_list:
                course_type_names_list.append(course_type.name)

    payload: list[ClientContentCourseOut] = []
    for entry in course_entries.values():
        course: ExternalContentCourse = entry["course"]  # type: ignore[assignment]
        access_map: dict[UUID, dict[str, object]] = entry["member_accesses"]  # type: ignore[assignment]
        section_payload = [
            ClientContentSectionOut(
                id=section.id,
                external_id=section.external_id,
                title=_clean_external_content_text(section.title) or section.title,
                position=section.position,
                lessons=[_client_content_lesson_out(lesson) for lesson in lessons_by_section.get(section.id, [])],
            )
            for section in sections_by_course.get(course.id, [])
        ]
        member_accesses = sorted(
            [
                ClientContentMemberAccessOut(
                    member_id=member_uuid,
                    member_display_name=_display_name(access_entry["member"]),  # type: ignore[arg-type]
                    member_email=access_entry["member"].email,  # type: ignore[index]
                    course_type_ids=sorted(access_entry["course_type_ids"], key=lambda value: str(value)),  # type: ignore[arg-type]
                    course_type_names=sorted(access_entry["course_type_names"], key=str.lower),  # type: ignore[arg-type]
                )
                for member_uuid, access_entry in access_map.items()
            ],
            key=lambda row: row.member_display_name.lower(),
        )
        payload.append(
            ClientContentCourseOut(
                id=course.id,
                provider=course.provider.value if hasattr(course.provider, "value") else str(course.provider),
                external_id=course.external_id,
                slug=course.slug,
                title=_clean_external_content_text(course.title) or course.title,
                summary=_clean_external_content_summary(course.summary),
                level_code=_clean_external_content_text(course.level_code),
                status=course.status.value if hasattr(course.status, "value") else str(course.status),
                cover_image_url=course.cover_image_url,
                last_synced_at=course.last_synced_at,
                member_accesses=member_accesses,
                sections=section_payload,
                standalone_lessons=[_client_content_lesson_out(lesson) for lesson in standalone_lessons_by_course.get(course.id, [])],
            )
        )

    payload.sort(key=lambda row: ((row.level_code or "").lower(), row.title.lower()))
    return payload


def _message_scope_since(scope: ClientMessageScope) -> datetime | None:
    now = _utcnow()
    if scope == ClientMessageScope.LAST_3_MONTHS:
        return now.replace(microsecond=0) - timedelta(days=90)
    if scope == ClientMessageScope.CURRENT_YEAR:
        return datetime(now.year, 1, 1, tzinfo=timezone.utc)
    return None


def _format_session_datetime(session_obj: CourseSession, timezone_name: str) -> str:
    tz_name = timezone_name or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    return session_obj.start_at_utc.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def _link_out(link: ClientFamilyLink, users_by_id: dict[UUID, User]) -> FamilyLinkOut:
    adult = users_by_id.get(link.adult_user_id)
    child = users_by_id.get(link.child_user_id)
    if adult is None or child is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Family link integrity error")
    return FamilyLinkOut(
        id=link.id,
        adult=_member_out(adult),
        child=_member_out(child),
        relationship_label=link.relationship_label,
        is_billing_recipient=link.is_billing_recipient,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _plan_amount_due_and_currency(
    db: Session,
    *,
    plan: Plan,
    country: str,
    currency: str,
    on_date: datetime,
) -> tuple[Decimal, str]:
    currency_code = (plan.currency_code or currency or "EUR").upper()
    if plan.kind == PlanKind.FORFAIT:
        return Decimal("0.00"), currency_code

    vat_rate = resolve_vat_rate(
        db,
        country=country,
        service_code=plan_service_code(plan.kind.value),
        on_date=on_date.date(),
    )

    price_excl_vat: Decimal | None = None
    if plan.monthly_price_value is not None:
        raw_price = Decimal(plan.monthly_price_value)
        if plan.price_tax_mode == PlanPriceTaxMode.TTC:
            return raw_price.quantize(Decimal("0.01")), currency_code
        price_excl_vat = raw_price
    elif plan.monthly_price_excl_vat is not None:
        price_excl_vat = Decimal(plan.monthly_price_excl_vat)
    else:
        resolved_price = resolve_plan_price(
            db,
            plan_id=plan.id,
            country=country,
            currency=currency,
            on_date=on_date.date(),
        )
        if resolved_price is not None:
            price_excl_vat = Decimal(resolved_price.price_excl_vat)
            currency_code = resolved_price.currency_code

    if price_excl_vat is None:
        return Decimal("0.00"), currency_code

    _, _, total_incl_vat = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)
    return total_incl_vat.quantize(Decimal("0.01")), currency_code


def _family_plan_mini_out(
    db: Session,
    *,
    plan: Plan,
    owner: User,
    on_date: datetime,
) -> FamilyPlanMiniOut:
    price_ttc, currency_code = _plan_amount_due_and_currency(
        db,
        plan=plan,
        country=(owner.residence_country or "FR").upper(),
        currency=(owner.preferred_currency or "EUR").upper(),
        on_date=on_date,
    )
    return FamilyPlanMiniOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        kind=plan.kind,
        price_ttc=price_ttc,
        currency_code=currency_code,
    )


@router.get("/clients/me", response_model=UserOut)
def get_client_me(current_user: User = Depends(require_roles(UserRole.CLIENT))) -> UserOut:
    return current_user


@router.get("/clients/catalog/products", response_model=list[ClientCatalogProductOut])
def list_client_catalog_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientCatalogProductOut]:
    del current_user
    products = db.scalars(
        select(CatalogProduct)
        .where(
            CatalogProduct.active.is_(True),
            CatalogProduct.is_public.is_(True),
            CatalogProduct.purchasable_online.is_(True),
        )
        .order_by(CatalogProduct.title.asc())
    ).all()

    category_ids = {product.category_id for product in products if product.category_id}
    location_ids = {product.primary_location_id for product in products if product.primary_location_id}
    category_names = (
        dict(db.execute(select(ProductCategory.id, ProductCategory.name).where(ProductCategory.id.in_(category_ids))).all())
        if category_ids
        else {}
    )
    location_names = (
        dict(db.execute(select(Location.id, Location.name).where(Location.id.in_(location_ids))).all())
        if location_ids
        else {}
    )

    return [
        ClientCatalogProductOut(
            id=product.id,
            category_name=category_names.get(product.category_id),
            primary_location_name=location_names.get(product.primary_location_id),
            title=product.title,
            price_incl_vat=product.price_incl_vat,
            vat_rate=product.vat_rate,
            stock_global_quantity=product.stock_global_quantity,
            image_url=product.image_url,
            short_description=product.short_description,
            web_link=product.web_link,
            nature=product.nature.value if hasattr(product.nature, "value") else str(product.nature),
            is_virtual=product.is_virtual,
        )
        for product in products
    ]


@router.get("/clients/me/sessions", response_model=list[SessionOut])
def list_client_visible_sessions(
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    timezone: str = "UTC",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[SessionOut]:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before 'to'",
        )

    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc

    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    visible_booked_session_ids_stmt = (
        select(Booking.session_id)
        .where(
            Booking.user_id.in_(managed_client_ids),
            Booking.status.in_(BOOKING_STATUSES_CONFIRMED),
        )
        .distinct()
    )
    visible_booked_session_ids = {
        row[0]
        for row in db.execute(visible_booked_session_ids_stmt).all()
    }
    now = _utcnow()
    active_entitlement_rows = db.execute(
        select(
            ClientPlanSubscription.user_id,
            Plan.kind,
            PlanEntitlement.course_type_id,
        )
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(PlanEntitlement, PlanEntitlement.plan_id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id.in_(managed_client_ids),
            ClientPlanSubscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAYMENT_ALERT,
                SubscriptionStatus.PAUSED,
            ]),
            ClientPlanSubscription.started_at <= now,
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > now),
            Plan.active.is_(True),
        )
    ).all()
    subscription_entitlements_by_user: dict[UUID, set[UUID]] = defaultdict(set)
    forfait_entitlements_by_user: dict[UUID, set[UUID]] = defaultdict(set)
    for owner_id, plan_kind, entitlement_course_type_id in active_entitlement_rows:
        if plan_kind in {PlanKind.SUBSCRIPTION, PlanKind.PACK}:
            subscription_entitlements_by_user[owner_id].add(entitlement_course_type_id)
        elif plan_kind == PlanKind.FORFAIT:
            forfait_entitlements_by_user[owner_id].add(entitlement_course_type_id)

    booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("booked_count"),
        )
        .where(Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY))
        .group_by(Booking.session_id)
        .subquery()
    )
    substitute_professor = aliased(Professor, name="substitute_professor")

    stmt = (
        select(
            CourseSession,
            CourseType,
            Location,
            Professor,
            substitute_professor,
            func.coalesce(booked_counts.c.booked_count, 0).label("booked_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Professor, Professor.id == CourseSession.professor_id)
        .outerjoin(substitute_professor, substitute_professor.id == CourseSession.substitute_teacher_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            (
                CourseSession.is_private.is_(False)
                | CourseSession.id.in_(visible_booked_session_ids_stmt)
            ),
        )
    )

    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)

    stmt = stmt.order_by(CourseSession.start_at_utc.asc())
    rows = db.execute(stmt).all()
    external_booking_currency = _account_default_currency(db)

    payload: list[SessionOut] = []
    for session, course_type, location, professor, substitute, booked_count in rows:
        visibility_scopes = resolve_session_visibility_scopes(session)
        booking_scopes = resolve_session_booking_scopes(
            session,
            allows_student_bookings=bool(course_type.allows_student_bookings),
        )
        visibility_scope = primary_session_audience_scope(visibility_scopes)
        booking_scope = primary_session_audience_scope(booking_scopes, fallback=SessionAudienceScope.PRIVATE)
        if session.id not in visible_booked_session_ids:
            if visibility_scopes == [SessionAudienceScope.PRIVATE]:
                continue
            if scopes_allow_external_visibility(visibility_scopes):
                pass
            elif scopes_allow_plan_kind(visibility_scopes, plan_kind=PlanKind.SUBSCRIPTION) or scopes_allow_plan_kind(visibility_scopes, plan_kind=PlanKind.PACK):
                if not any(
                    session.course_type_id in subscription_entitlements_by_user.get(owner_id, set())
                    for owner_id in managed_client_ids
                ):
                    continue
            elif scopes_allow_plan_kind(visibility_scopes, plan_kind=PlanKind.FORFAIT):
                if not any(
                    session.course_type_id in forfait_entitlements_by_user.get(owner_id, set())
                    for owner_id in managed_client_ids
                ):
                    continue
            else:
                continue
        effective_professor = substitute or professor
        substitute_display_name = (
            f"{(substitute.first_name or '').strip()} {(substitute.last_name or '').strip()}".strip()
            if substitute is not None
            else None
        )
        effective_display_name = (
            f"{(effective_professor.first_name or '').strip()} {(effective_professor.last_name or '').strip()}".strip()
            if effective_professor is not None
            else None
        )
        booked = int(booked_count or 0)
        seats_remaining = max(session.capacity_max - booked, 0)
        external_booking_price_ttc = None
        if session.external_booking_price_ttc is not None:
            duration_seconds = int(max((session.end_at_utc - session.start_at_utc).total_seconds(), 0))
            if duration_seconds <= 0:
                duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
            duration_hours = Decimal(duration_seconds) / Decimal("3600")
            external_booking_price_ttc = (Decimal(session.external_booking_price_ttc) * duration_hours).quantize(Decimal("0.01"))
        payload.append(
            SessionOut(
                id=session.id,
                title=session.title,
                description=session.description,
                start_at_utc=session.start_at_utc,
                end_at_utc=session.end_at_utc,
                start_at_local=session.start_at_utc.astimezone(tz),
                end_at_local=session.end_at_utc.astimezone(tz),
                timezone=timezone,
                session_timezone=session.timezone,
                status=session.status,
                capacity_max=session.capacity_max,
                booked_count=booked,
                seats_remaining=seats_remaining,
                visibility_scopes=visibility_scopes,
                booking_scopes=booking_scopes,
                visibility_scope=visibility_scope,
                booking_scope=booking_scope,
                online_booking_enabled=booking_scopes != [SessionAudienceScope.PRIVATE],
                external_booking_price_ttc=external_booking_price_ttc,
                external_booking_currency=external_booking_currency if session.external_booking_price_ttc is not None else None,
                show_external_remaining_seats=bool(session.show_external_remaining_seats),
                zoom_link=session.zoom_link,
                substitute_teacher_id=session.substitute_teacher_id,
                substitute_teacher_display_name=substitute_display_name,
                effective_teacher_id=effective_professor.id if effective_professor is not None else None,
                effective_teacher_display_name=effective_display_name,
                course_type=SessionCourseTypeOut(
                    id=course_type.id,
                    code=course_type.code,
                    name=course_type.name,
                ),
                location=SessionLocationOut(
                    id=location.id,
                    code=location.code,
                    name=location.name,
                    is_online=location.is_online,
                ),
                professor=(
                    SessionProfessorOut(
                        id=effective_professor.id,
                        first_name=effective_professor.first_name,
                        last_name=effective_professor.last_name,
                    )
                    if effective_professor is not None
                    else None
                ),
            )
        )

    return payload


@router.patch("/clients/me", response_model=UserOut)
def patch_client_me(
    payload: ClientMeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> UserOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return current_user

    if "first_name" in changes:
        current_user.first_name = _normalize_optional(changes["first_name"])

    if "last_name" in changes:
        current_user.last_name = _normalize_optional(changes["last_name"])

    if "address_line" in changes:
        current_user.address_line = _normalize_optional(changes["address_line"])

    if "postal_code" in changes:
        current_user.postal_code = _normalize_optional(changes["postal_code"])

    if "city" in changes:
        current_user.city = _normalize_optional(changes["city"])

    if "address_country" in changes:
        current_user.address_country = _normalize_required(changes["address_country"], "address_country").upper()

    if "phone" in changes:
        normalized_phone = _normalize_optional(changes["phone"])
        current_user.phone = normalized_phone
        if "mobile_phone_1" not in changes:
            current_user.mobile_phone_1 = normalized_phone

    if "mobile_phone_1" in changes:
        current_user.mobile_phone_1 = _normalize_optional(changes["mobile_phone_1"])
        current_user.phone = current_user.mobile_phone_1

    if "mobile_phone_2" in changes:
        current_user.mobile_phone_2 = _normalize_optional(changes["mobile_phone_2"])

    if "home_phone" in changes:
        current_user.home_phone = _normalize_optional(changes["home_phone"])

    if "important_info" in changes:
        current_user.important_info = _normalize_optional(changes["important_info"])

    if "portal_contact_visible" in changes and changes["portal_contact_visible"] is not None:
        current_user.portal_contact_visible = bool(changes["portal_contact_visible"])

    if "email_opt_in" in changes and changes["email_opt_in"] is not None:
        current_user.email_opt_in = bool(changes["email_opt_in"])

    if "sms_opt_in" in changes and changes["sms_opt_in"] is not None:
        current_user.sms_opt_in = bool(changes["sms_opt_in"])

    if "lesson_reminder_email_opt_in" in changes and changes["lesson_reminder_email_opt_in"] is not None:
        current_user.lesson_reminder_email_opt_in = bool(changes["lesson_reminder_email_opt_in"])

    if "lesson_reminder_sms_opt_in" in changes and changes["lesson_reminder_sms_opt_in"] is not None:
        current_user.lesson_reminder_sms_opt_in = bool(changes["lesson_reminder_sms_opt_in"])

    if "residence_country" in changes:
        current_user.residence_country = _normalize_required(changes["residence_country"], "residence_country").upper()

    if "preferred_language" in changes:
        preferred_language = _normalize_required(changes["preferred_language"], "preferred_language").lower()
        if preferred_language not in {"fr", "en"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid preferred_language")
        current_user.preferred_language = preferred_language

    if "preferred_currency" in changes:
        current_user.preferred_currency = _normalize_required(changes["preferred_currency"], "preferred_currency").upper()

    if "timezone" in changes:
        current_user.timezone = _validate_timezone(changes["timezone"])

    current_user.updated_at = _utcnow()

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/clients/communication/optout")
def client_communication_optout(
    token: str = Query(min_length=8, max_length=64),
    channel: str = Query(default="EMAIL"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    normalized_channel = _normalize_optout_channel(channel)
    user = db.scalar(
        select(User).where(
            User.communication_optout_token == token,
            User.role == UserRole.CLIENT,
        )
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optout token not found")

    if normalized_channel in {"EMAIL", "ALL"}:
        user.email_opt_in = False
        user.lesson_reminder_email_opt_in = False

    if normalized_channel in {"SMS", "ALL"}:
        user.sms_opt_in = False
        user.lesson_reminder_sms_opt_in = False

    user.updated_at = _utcnow()
    db.add(user)
    db.commit()

    return {
        "ok": "true",
        "message": "Preferences de communication mises a jour",
    }


def _client_offer_fields(
    *,
    subscription_id: UUID,
    quote_by_subscription_id: dict[UUID, Quote],
    option_rows_by_quote_id: dict[UUID, list[ClientOfferOptionOut]],
    deposit_metadata_by_quote_id: dict[UUID, tuple[ClientNoteEntry, dict[str, object]]],
) -> dict[str, object]:
    quote = quote_by_subscription_id.get(subscription_id)
    if quote is None:
        return {}

    quote_meta = quote.meta if isinstance(quote.meta, dict) else {}
    raw_deposit = quote_meta.get("pre_registration_deposit")
    deposit = raw_deposit if isinstance(raw_deposit, dict) else {}
    deposit_enabled = str(deposit.get("enabled") or "").strip().lower() in {"1", "true", "yes", "oui"}
    try:
        deposit_amount = Decimal(str(deposit.get("amount_ttc") or "0")).quantize(Decimal("0.01"))
    except (ValueError, ArithmeticError):
        deposit_amount = Decimal("0.00")
    if not deposit_enabled or deposit_amount <= Decimal("0.00"):
        deposit_amount = Decimal("0.00")

    invoice_entry = deposit_metadata_by_quote_id.get(quote.id)
    invoice_note = invoice_entry[0] if invoice_entry is not None else None
    invoice_metadata = invoice_entry[1] if invoice_entry is not None else {}
    deposit_status = str(invoice_metadata.get("invoice_status") or "PENDING").strip().upper() if deposit_amount > 0 else None
    paid_at: datetime | None = None
    if deposit_status == "PAID":
        raw_paid_at = str(invoice_metadata.get("paid_at") or "").strip()
        if raw_paid_at:
            try:
                paid_at = datetime.fromisoformat(raw_paid_at.replace("Z", "+00:00"))
            except ValueError:
                paid_at = None

    total_ttc = Decimal(quote.total_ttc or 0).quantize(Decimal("0.01"))
    paid_deposit = deposit_amount if deposit_status == "PAID" else Decimal("0.00")
    remaining_ttc = max(Decimal("0.00"), total_ttc - paid_deposit)
    return {
        "offer_quote_id": quote.id,
        "offer_quote_number": quote.quote_number,
        "offer_school_year_label": quote.school_year_label,
        "offer_total_ttc": total_ttc,
        "offer_currency": (quote.currency or "EUR").upper(),
        "offer_options": option_rows_by_quote_id.get(quote.id, []),
        "offer_deposit_amount_ttc": deposit_amount if deposit_amount > 0 else None,
        "offer_deposit_status": deposit_status,
        "offer_deposit_paid_at": paid_at,
        "offer_deposit_invoice_id": f"invoice-range:{invoice_note.id}" if invoice_note is not None else None,
        "offer_remaining_ttc": remaining_ttc,
    }


@router.get("/clients/me/family", response_model=ClientFamilyOverviewOut)
def get_client_family_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientFamilyOverviewOut:
    links_as_adult = db.scalars(
        select(ClientFamilyLink)
        .where(ClientFamilyLink.adult_user_id == current_user.id)
        .order_by(ClientFamilyLink.created_at.desc())
    ).all()
    links_as_child = db.scalars(
        select(ClientFamilyLink)
        .where(ClientFamilyLink.child_user_id == current_user.id)
        .order_by(ClientFamilyLink.created_at.desc())
    ).all()

    user_ids: set[UUID] = {current_user.id}
    for link in links_as_adult:
        user_ids.add(link.adult_user_id)
        user_ids.add(link.child_user_id)
    for link in links_as_child:
        user_ids.add(link.adult_user_id)
        user_ids.add(link.child_user_id)

    users = db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    users_by_id = {user.id: user for user in users}

    managed_client_ids: set[UUID] = {current_user.id}
    if current_user.client_kind == ClientKind.ADULT:
        managed_client_ids.update(link.child_user_id for link in links_as_adult)

    rows_subscriptions = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(ClientPlanSubscription.user_id.in_(managed_client_ids))
        .order_by(ClientPlanSubscription.created_at.desc())
    ).all()
    now = _utcnow()
    changed = False
    for sub, plan, _ in rows_subscriptions:
        if reconcile_subscription_status(sub, now=now, plan_kind=plan.kind):
            changed = True
    if changed:
        db.commit()
    plan_ids = list({plan.id for _, plan, _ in rows_subscriptions})
    entitlement_rows = db.execute(
        select(PlanEntitlement.plan_id, PlanEntitlement.course_type_id, CourseType.name)
        .join(CourseType, CourseType.id == PlanEntitlement.course_type_id)
        .where(PlanEntitlement.plan_id.in_(plan_ids))
        .order_by(PlanEntitlement.plan_id.asc(), CourseType.name.asc())
    ).all() if plan_ids else []
    entitlement_course_type_ids_by_plan: dict[UUID, list[UUID]] = defaultdict(list)
    entitlement_course_type_names_by_plan: dict[UUID, list[str]] = defaultdict(list)
    for plan_id, course_type_id, course_type_name in entitlement_rows:
        entitlement_course_type_ids_by_plan[plan_id].append(course_type_id)
        entitlement_course_type_names_by_plan[plan_id].append(course_type_name)

    subscription_ids = {sub.id for sub, _, _ in rows_subscriptions}
    quote_by_subscription_id: dict[UUID, Quote] = {}
    if subscription_ids:
        followup_rows = db.execute(
            select(QuoteAcceptanceFollowup, Quote)
            .join(Quote, Quote.id == QuoteAcceptanceFollowup.quote_id)
            .where(
                or_(
                    QuoteAcceptanceFollowup.target_client_id.in_(managed_client_ids),
                    Quote.client_id.in_(managed_client_ids),
                )
            )
            .order_by(QuoteAcceptanceFollowup.updated_at.desc(), Quote.updated_at.desc())
        ).all()
        for followup, quote in followup_rows:
            payload = followup.payload if isinstance(followup.payload, dict) else {}
            execution = payload.get("quote_to_enrollment_execution")
            execution = execution if isinstance(execution, dict) else {}
            raw_ids = [execution.get("subscription_id")]
            created_ids = execution.get("created_subscription_ids")
            if isinstance(created_ids, list):
                raw_ids.extend(created_ids)
            for raw_id in raw_ids:
                try:
                    resolved_id = UUID(str(raw_id))
                except (TypeError, ValueError):
                    continue
                if resolved_id in subscription_ids and resolved_id not in quote_by_subscription_id:
                    quote_by_subscription_id[resolved_id] = quote

    option_rows_by_quote_id: dict[UUID, list[ClientOfferOptionOut]] = defaultdict(list)
    offer_quote_ids = {quote.id for quote in quote_by_subscription_id.values()}
    if offer_quote_ids:
        option_rows = db.scalars(
            select(QuoteLine)
            .where(
                QuoteLine.quote_id.in_(offer_quote_ids),
                QuoteLine.line_type == "item",
                QuoteLine.activity_id.is_(None),
                QuoteLine.amount_ttc >= 0,
            )
            .order_by(QuoteLine.quote_id.asc(), QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
        ).all()
        for line in option_rows:
            option_rows_by_quote_id[line.quote_id].append(
                ClientOfferOptionOut(
                    id=line.id,
                    title=line.title,
                    description=line.description,
                    quantity=Decimal(line.quantity or 0),
                    amount_ttc=Decimal(line.amount_ttc or 0),
                )
            )

    deposit_metadata_by_quote_id: dict[UUID, tuple[ClientNoteEntry, dict[str, object]]] = {}
    if offer_quote_ids:
        offer_notes = db.scalars(
            select(ClientNoteEntry)
            .where(ClientNoteEntry.user_id.in_(managed_client_ids))
            .order_by(ClientNoteEntry.created_at.desc())
        ).all()
        for note in offer_notes:
            metadata = _parse_invoice_range_note_entry(note)
            if metadata is None:
                continue
            try:
                source_quote_id = UUID(str(metadata.get("source_quote_id")))
            except (TypeError, ValueError):
                continue
            if source_quote_id in offer_quote_ids and source_quote_id not in deposit_metadata_by_quote_id:
                deposit_metadata_by_quote_id[source_quote_id] = (note, metadata)

    rows_bookings = db.execute(
        select(Booking, CourseSession, User, Location)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(User, User.id == Booking.user_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(Booking.user_id.in_(managed_client_ids))
        .order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())
    ).all()

    billing_recipient_adult_id: UUID | None = None
    for link in links_as_child:
        if link.is_billing_recipient:
            billing_recipient_adult_id = link.adult_user_id
            break

    return ClientFamilyOverviewOut(
        me=_member_out(current_user),
        links_as_adult=[_link_out(link, users_by_id) for link in links_as_adult],
        links_as_child=[_link_out(link, users_by_id) for link in links_as_child],
        billing_recipient_adult_id=billing_recipient_adult_id,
        managed_client_ids=sorted(managed_client_ids, key=lambda value: str(value)),
        subscriptions=[
            FamilySubscriptionOut(
                id=sub.id,
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                owner_email=owner.email,
                status=sub.status,
                started_at=sub.started_at,
                ends_at=sub.ends_at,
                next_payment_at=sub.next_payment_at,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                credits_initial=sub.credits_initial,
                credits_remaining=sub.credits_remaining,
                auto_renew=sub.auto_renew,
                bookings_blocked=bool(sub.bookings_blocked),
                billing_method_code=sub.billing_method_code,
                payment_method_setup_required=bool(sub.payment_method_setup_required),
                payment_method_setup_completed_at=sub.payment_method_setup_completed_at,
                last_successful_charge_at=sub.last_successful_charge_at,
                payment_alert_started_at=sub.payment_alert_started_at,
                pre_termination_at=sub.pre_termination_at,
                direct_payment_recovery_url=sub.direct_payment_recovery_url,
                suspension_starts_at=sub.suspension_starts_at,
                suspension_ends_at=sub.suspension_ends_at,
                cancellation_requested_at=sub.cancellation_requested_at,
                cancellation_effective_at=sub.cancellation_effective_at,
                plan=_family_plan_mini_out(
                    db,
                    plan=plan,
                    owner=owner,
                    on_date=now,
                ),
                entitlement_course_type_ids=entitlement_course_type_ids_by_plan.get(plan.id, []),
                entitlement_course_type_names=entitlement_course_type_names_by_plan.get(plan.id, []),
                **_client_offer_fields(
                    subscription_id=sub.id,
                    quote_by_subscription_id=quote_by_subscription_id,
                    option_rows_by_quote_id=option_rows_by_quote_id,
                    deposit_metadata_by_quote_id=deposit_metadata_by_quote_id,
                ),
            )
            for sub, plan, owner in rows_subscriptions
        ],
        bookings=[
            FamilyBookingOut(
                id=booking.id,
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                owner_email=owner.email,
                client_plan_subscription_id=booking.client_plan_subscription_id,
                status=booking.status,
                booked_at=booking.booked_at,
                cancelled_at=booking.cancelled_at,
                cancellation_reason=booking.cancellation_reason,
                price_excl_vat_snapshot=booking.price_excl_vat_snapshot,
                vat_rate_snapshot=booking.vat_rate_snapshot,
                vat_amount_snapshot=booking.vat_amount_snapshot,
                total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
                currency_snapshot=booking.currency_snapshot,
                session=FamilySessionMiniOut(
                    id=session.id,
                    title=session.title,
                    start_at_utc=session.start_at_utc,
                    end_at_utc=session.end_at_utc,
                    status=session.status,
                    location_name=location.name,
                ),
            )
            for booking, session, owner, location in rows_bookings
        ],
    )


@router.get("/clients/me/content-courses", response_model=list[ClientContentCourseOut])
def list_client_content_courses(
    member_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientContentCourseOut]:
    return _client_content_courses(
        db,
        current_user=current_user,
        member_id=member_id,
    )


@router.get("/clients/me/messages", response_model=list[ClientMessageOut])
def list_client_messages(
    scope: ClientMessageScope = Query(default=ClientMessageScope.LAST_3_MONTHS),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientMessageOut]:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    owners = db.scalars(select(User).where(User.id.in_(managed_client_ids))).all()
    owners_by_id = {owner.id: owner for owner in owners}
    owners_by_email = {
        (owner.email or "").strip().lower(): owner
        for owner in owners
        if (owner.email or "").strip()
    }
    since = _message_scope_since(scope)
    now = _utcnow()
    billing_profile = resolve_billing_profile(db, current_user)
    recipient_emails = set(owners_by_email.keys())
    billing_email = (billing_profile.email or "").strip().lower()
    if billing_email:
        recipient_emails.add(billing_email)

    communication_filters = [CommunicationLog.recipient_user_id.in_(managed_client_ids)]
    if recipient_emails:
        communication_filters.append(func.lower(CommunicationLog.recipient).in_(list(recipient_emails)))

    communication_stmt = (
        select(CommunicationLog)
        .where(or_(*communication_filters))
        .where(CommunicationLog.occurred_at <= now)
    )
    if since is not None:
        communication_stmt = communication_stmt.where(CommunicationLog.occurred_at >= since)
    communication_rows = db.scalars(
        communication_stmt.order_by(CommunicationLog.occurred_at.desc()).limit(max(limit * 4, limit))
    ).all()
    communication_provider_ids = {
        (row.provider_message_id or "").strip()
        for row in communication_rows
        if (row.provider_message_id or "").strip()
    }

    stmt = (
        select(EmailReminder, Booking, CourseSession, CourseType, Location, User)
        .join(Booking, Booking.id == EmailReminder.booking_id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(User, User.id == Booking.user_id)
        .where(Booking.user_id.in_(managed_client_ids))
        .where(EmailReminder.sent_at.is_not(None))
        .where(EmailReminder.sent_at <= now)
        .order_by(EmailReminder.created_at.desc())
        .limit(max(limit * 4, limit))
    )
    if since is not None:
        stmt = stmt.where(EmailReminder.sent_at >= since)

    rows = db.execute(stmt).all()
    payload: list[ClientMessageOut] = []

    for row in communication_rows:
        recipient_user = owners_by_id.get(row.recipient_user_id) if row.recipient_user_id is not None else None
        if recipient_user is None:
            recipient_user = owners_by_email.get((row.recipient or "").strip().lower())
        if recipient_user is None:
            recipient_user = current_user
        owner_display = _display_name(recipient_user)
        recipient_email = _public_client_email(recipient_user)
        if recipient_email is None:
            raw_recipient = (row.recipient or "").strip()
            recipient_email = raw_recipient if raw_recipient and not _is_synthetic_client_email(raw_recipient) else None
        is_html_message = row.content_format == MessageFormat.HTML or str(row.content_format or "").strip().upper() == "HTML"
        content_preview = (
            _message_preview_from_html(row.content)
            if is_html_message
            else _message_preview(row.content)
        )
        status_value = (
            row.delivery_status.value
            if isinstance(row.delivery_status, CommunicationDeliveryStatus)
            else str(row.delivery_status or "UNKNOWN").strip().upper()
        )
        payload.append(
            ClientMessageOut(
                id=row.id,
                owner_client_id=recipient_user.id,
                owner_display_name=owner_display,
                recipient_email=recipient_email,
                channel=row.channel.value if isinstance(row.channel, CommunicationChannel) else str(row.channel or "EMAIL").strip().upper(),
                booking_id=None,
                session_id=None,
                session_title=_client_message_context_label(row.source),
                scheduled_for_utc=row.occurred_at,
                sent_at=row.delivered_at or row.failed_at or row.occurred_at,
                status=status_value or "UNKNOWN",
                provider_message_id=row.provider_message_id,
                error_message=row.error_message,
                subject_preview=(row.subject or "").strip() or _client_message_context_label(row.source),
                content_preview=content_preview,
                content_text=None if is_html_message else row.content,
                content_html=row.content if is_html_message else None,
            )
        )

    for reminder, booking, session_obj, course_type, location, owner in rows:
        provider_message_id = (reminder.provider_message_id or "").strip()
        if provider_message_id and provider_message_id in communication_provider_ids:
            continue
        owner_display = _display_name(owners_by_id.get(owner.id, owner))
        start_human = _format_session_datetime(session_obj, owner.timezone)
        subject_preview = f"Rappel cours: {course_type.name} - {start_human}"
        content_preview = ""
        if not content_preview:
            content_preview = (
                f"Bonjour {owner_display},\n\n"
                f"Rappel cours: {course_type.name}\n"
                f"Date: {start_human}\n"
                f"Lieu: {location.name}\n\n"
                "Ce message est genere automatiquement selon vos preferences de rappel."
            )
        payload.append(
            ClientMessageOut(
                id=reminder.id,
                owner_client_id=owner.id,
                owner_display_name=owner_display,
                recipient_email=_public_client_email(owner),
                channel="EMAIL",
                booking_id=booking.id,
                session_id=session_obj.id,
                session_title=session_obj.title,
                scheduled_for_utc=reminder.scheduled_for_utc,
                sent_at=reminder.sent_at,
                status=reminder.status,
                provider_message_id=reminder.provider_message_id,
                error_message=reminder.error_message,
                subject_preview=subject_preview,
                content_preview=content_preview,
                content_text=content_preview,
                content_html=None,
            )
        )

    payload.sort(
        key=lambda item: (
            item.sent_at or item.scheduled_for_utc,
            item.scheduled_for_utc,
        ),
        reverse=True,
    )
    return payload[:limit]


def _format_ics_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape_ics_text(value: str | None) -> str:
    normalized = " ".join((value or "").split()).strip()
    if not normalized:
        return ""
    return (
        normalized
        .replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


@router.get("/clients/me/bookings/{booking_id}/calendar.ics")
def download_client_booking_calendar_event(
    booking_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    row = db.execute(
        select(Booking, CourseSession, CourseType, Location, Professor, User)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Professor, Professor.id == CourseSession.professor_id)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.id == booking_id,
            Booking.user_id.in_(managed_client_ids),
        )
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation introuvable")

    booking, session_obj, course_type, location, professor, owner = row
    if normalize_status := str(booking.status or "").strip().upper():
        if normalize_status == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reservation annulee")

    professor_name = ""
    if professor is not None:
        professor_name = " ".join(part for part in [professor.first_name, professor.last_name] if part).strip()

    description_lines = [
        f"Activite: {course_type.name}",
        f"Membre: {_display_name(owner)}",
        f"Lieu: {location.name}",
    ]
    if professor_name:
        description_lines.append(f"Professeur: {professor_name}")
    if session_obj.description:
        description_lines.append("")
        description_lines.append(session_obj.description.strip())

    event_uid = f"booking-{booking.id}@piano-academie.com"
    calendar_content = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Piano Academie//Reservations//FR",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{event_uid}",
            f"DTSTAMP:{_format_ics_datetime(_utcnow())}",
            f"DTSTART:{_format_ics_datetime(session_obj.start_at_utc)}",
            f"DTEND:{_format_ics_datetime(session_obj.end_at_utc)}",
            f"SUMMARY:{_escape_ics_text(session_obj.title or course_type.name)}",
            f"DESCRIPTION:{_escape_ics_text(chr(10).join(description_lines))}",
            f"LOCATION:{_escape_ics_text(location.name)}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    filename = f"reservation-{session_obj.start_at_utc.astimezone(timezone.utc).strftime('%Y%m%d-%H%M')}.ics"
    return Response(
        content=calendar_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "content-disposition": f'attachment; filename="{filename}"',
            "cache-control": "no-store",
        },
    )


def _build_client_payments(db: Session, current_user: User) -> list[ClientPaymentOut]:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    legal_entities_by_id = _active_legal_entities_by_id(db)

    rows_subs = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(ClientPlanSubscription.user_id.in_(managed_client_ids))
    ).all()

    rows_bookings = db.execute(
        select(Booking, CourseSession, CourseType, Location, User, ClientPlanSubscription, Plan)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id)
        .outerjoin(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == Booking.user_id)
        .where(Booking.user_id.in_(managed_client_ids))
    ).all()

    manual_rows = db.scalars(
        select(ClientManualTransaction)
        .where(
            or_(
                ClientManualTransaction.user_id.in_(managed_client_ids),
                ClientManualTransaction.student_user_id.in_(managed_client_ids),
            ),
            ClientManualTransaction.transaction_type.in_(["PAYMENT", "REFUND"]),
        )
        .order_by(ClientManualTransaction.occurred_at.desc())
    ).all()
    manual_owner_ids = {
        row.student_user_id if row.student_user_id in managed_client_ids else row.user_id
        for row in manual_rows
    }
    manual_owners = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_(manual_owner_ids))).all()
    } if manual_owner_ids else {}

    items: list[ClientPaymentOut] = []
    forfait_pricing_map = _forfait_activity_pricing_map(
        db,
        subscription_ids={
            forfait_subscription.id
            for _, _, _, _, _, forfait_subscription, plan in rows_bookings
            if forfait_subscription is not None and (plan is None or plan.kind == PlanKind.FORFAIT)
        },
    )

    for sub, plan, owner in rows_subs:
        if plan.kind == PlanKind.FORFAIT:
            continue

        billing_profile = resolve_billing_profile(db, owner)
        country_code = (billing_profile.residence_country or "FR").upper()
        preferred_currency = (billing_profile.preferred_currency or "EUR").upper()

        vat_rate = resolve_vat_rate(
            db,
            country=country_code,
            service_code=plan_service_code(plan.kind.value),
            on_date=sub.started_at.date(),
        )

        price_excl_vat: Decimal | None = None
        currency_code = (plan.currency_code or preferred_currency).upper()
        if plan.monthly_price_value is not None:
            raw_price = Decimal(plan.monthly_price_value)
            if plan.price_tax_mode == PlanPriceTaxMode.TTC:
                divisor = Decimal("1") + (vat_rate / Decimal("100"))
                price_excl_vat = raw_price if divisor <= 0 else (raw_price / divisor)
            else:
                price_excl_vat = raw_price
        elif plan.monthly_price_excl_vat is not None:
            price_excl_vat = Decimal(plan.monthly_price_excl_vat)
        else:
            resolved_price = resolve_plan_price(
                db,
                plan_id=plan.id,
                country=country_code,
                currency=preferred_currency,
                on_date=sub.started_at.date(),
            )
            if resolved_price is not None:
                price_excl_vat = Decimal(resolved_price.price_excl_vat)
                currency_code = resolved_price.currency_code

        if price_excl_vat is not None:
            price_excl_vat, vat_amount, total_incl_vat = compute_tax_totals(
                price_excl_vat=price_excl_vat,
                vat_rate=vat_rate,
            )
        else:
            price_excl_vat = Decimal("0.00")
            vat_amount = Decimal("0.00")
            total_incl_vat = Decimal("0.00")

        items.append(
            ClientPaymentOut(
                id=f"plan:{sub.id}",
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                source="PLAN_PURCHASE",
                occurred_at=sub.started_at,
                label=plan.name,
                status=_subscription_payment_status(sub),
                amount_excl_vat=price_excl_vat,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                total_incl_vat=total_incl_vat,
                currency=currency_code or "EUR",
                reference=plan.code,
                seller_legal_entity_id=None,
                billing_entity=None,
                payment_url=_frontend_url(path=f"/client?tab=finance&finance_view=transactions&source=PLAN_PURCHASE&payment_id={sub.id}"),
            )
        )

    for booking, session_obj, course_type, location, owner, forfait_subscription, plan in rows_bookings:
        status_value = booking.status.value if hasattr(booking.status, "value") else str(booking.status)
        is_billable = True
        amount_excl_vat = booking.price_excl_vat_snapshot
        vat_rate = booking.vat_rate_snapshot
        vat_amount = booking.vat_amount_snapshot
        total_incl_vat = booking.total_incl_vat_snapshot
        currency = booking.currency_snapshot

        if plan is None or (plan is not None and plan.kind == PlanKind.FORFAIT):
            is_billable = (
                session_obj.status != SessionStatus.CANCELLED
                and booking.status not in {BookingStatus.WAITLISTED, BookingStatus.CANCELLED, BookingStatus.EXCUSED_ABSENCE}
            )
            if not is_billable:
                status_value = "NOT_BILLABLE"
            else:
                billing_profile = resolve_billing_profile(db, owner)
                computed = _booking_amounts_from_activity(
                    booking=booking,
                    session_obj=session_obj,
                    course_type=course_type,
                    location=location,
                    billing_profile=billing_profile,
                    forfait_subscription=forfait_subscription,
                    db=db,
                    pricing_map=forfait_pricing_map,
                )
                if computed is not None:
                    amount_excl_vat, vat_rate, vat_amount, total_incl_vat, currency = computed
        elif booking.status == BookingStatus.EXCUSED_ABSENCE:
            is_billable = False
        seller_legal_entity_id = session_obj.snapshot_seller_legal_entity_id or course_type.seller_legal_entity_id
        items.append(
            ClientPaymentOut(
                id=f"booking:{booking.id}",
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                source="BOOKING",
                occurred_at=session_obj.start_at_utc,
                label=f"{course_type.name} - {location.name}",
                status=status_value,
                amount_excl_vat=Decimal("0.00") if not is_billable else amount_excl_vat,
                vat_rate=Decimal("0.00") if not is_billable else vat_rate,
                vat_amount=Decimal("0.00") if not is_billable else vat_amount,
                total_incl_vat=Decimal("0.00") if not is_billable else total_incl_vat,
                currency=currency,
                reference=str(session_obj.id),
                seller_legal_entity_id=seller_legal_entity_id,
                billing_entity=_billing_entity_from_seller_id(
                    legal_entities_by_id=legal_entities_by_id,
                    seller_legal_entity_id=seller_legal_entity_id,
                    fallback_text=session_obj.billing_entity_snapshot or course_type.billing_entity_code,
                ),
                payment_url=None,
            )
        )

    for transaction in manual_rows:
        owner_id = transaction.student_user_id if transaction.student_user_id in managed_client_ids else transaction.user_id
        owner = manual_owners.get(owner_id)
        items.append(
            ClientPaymentOut(
                id=f"manual:{transaction.id}",
                owner_client_id=owner_id,
                owner_display_name=_display_name(owner) if owner is not None else str(owner_id),
                source="MANUAL",
                occurred_at=transaction.occurred_at,
                label=transaction.label,
                status=transaction.status,
                amount_excl_vat=abs(Decimal(transaction.amount_excl_vat or 0)),
                vat_rate=abs(Decimal(transaction.vat_rate or 0)),
                vat_amount=abs(Decimal(transaction.vat_amount or 0)),
                total_incl_vat=abs(Decimal(transaction.total_incl_vat or 0)),
                currency=(transaction.currency or "EUR").upper(),
                reference=transaction.reference,
                seller_legal_entity_id=transaction.legal_entity_id,
                billing_entity=_billing_entity_from_seller_id(
                    legal_entities_by_id=legal_entities_by_id,
                    seller_legal_entity_id=transaction.legal_entity_id,
                ),
                payment_url=None,
            )
        )

    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items


@router.post("/clients/me/payments/{payment_id}/checkout", response_model=ClientPaymentCheckoutOut)
def create_client_payment_checkout(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientPaymentCheckoutOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    row = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(
            ClientPlanSubscription.id == payment_id,
            ClientPlanSubscription.user_id.in_(managed_ids),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")

    subscription, plan, owner = row
    normalized_status = (subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)).strip().upper()
    if normalized_status in {"CANCELLED", "EXPIRED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce paiement est clos")

    method_code = (subscription.billing_method_code or "").strip().upper()
    if method_code not in ONLINE_COLLECTION_METHOD_CODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ce paiement n'utilise pas un moyen en ligne")
    now = _utcnow()
    is_sepa_setup = (
        plan.kind == PlanKind.SUBSCRIPTION
        and subscription.payment_method_setup_required
        and subscription.status == SubscriptionStatus.ACTIVE
        and method_code == "SEPA_DEBIT"
    )
    if is_sepa_setup:
        customer_reference = (subscription.payment_provider_customer_ref or "").strip()
        if not customer_reference.startswith("cus_"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Le premier paiement Stripe doit etre confirme avant la creation du mandat SEPA",
            )
        setup_query = f"tab=offers&offer_detail_id={subscription.id}&source=SEPA_SETUP&payment_id={subscription.id}"
        setup = create_stripe_payment_method_setup_session(
            db,
            customer_reference=customer_reference,
            success_return_url=_frontend_url(
                path=f"/client?{setup_query}&payment_return=success&setup_session_id={{CHECKOUT_SESSION_ID}}"
            ),
            cancel_return_url=_frontend_url(path=f"/client?{setup_query}&payment_return=cancel"),
            metadata={
                "source": "SEPA_SETUP",
                "client_id": str(owner.id),
                "subscription_id": str(subscription.id),
                "plan_id": str(plan.id),
            },
        )
        if not setup.success or not setup.checkout_url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Impossible de creer le mandat SEPA ({setup.message})",
            )
        return ClientPaymentCheckoutOut(
            payment_id=f"plan:{subscription.id}",
            checkout_url=setup.checkout_url,
            provider_reference=setup.provider_reference,
        )

    if (
        plan.kind == PlanKind.SUBSCRIPTION
        and subscription.payment_method_setup_required
        and subscription.status == SubscriptionStatus.ACTIVE
        and subscription.next_payment_at is not None
        and subscription.next_payment_at > now
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le moyen de paiement sera demande a la prochaine echeance",
        )

    amount_due, currency_code = _plan_amount_due_and_currency(
        db,
        plan=plan,
        country=(owner.residence_country or "FR").upper(),
        currency=(owner.preferred_currency or "EUR").upper(),
        on_date=subscription.started_at,
    )
    if amount_due <= Decimal("0.00"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun montant a regler pour ce paiement")

    success_url, cancel_url, webhook_url = _checkout_urls(owner_id=owner.id, subscription_id=subscription.id)
    checkout = create_checkout_session(
        db,
        CheckoutCreateRequest(
            amount=amount_due,
            currency=currency_code,
            description=f"{plan.name} ({owner.email})",
            customer_email=owner.email,
            customer_first_name=owner.first_name,
            customer_last_name=owner.last_name,
            customer_country=(owner.residence_country or "FR"),
            success_return_url=success_url,
            cancel_return_url=cancel_url,
            webhook_url=with_webhook_secret(webhook_url, resolve_webhook_secret(db)),
            save_payment_method=(plan.kind == PlanKind.SUBSCRIPTION),
            metadata={
                "client_id": str(owner.id),
                "subscription_id": str(subscription.id),
                "plan_id": str(plan.id),
                "plan_code": plan.code,
            },
        ),
        provider_override=(PaymentProvider.STRIPE if plan.kind == PlanKind.SUBSCRIPTION else None),
    )
    if not checkout.success or not checkout.checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Impossible de creer la session de paiement ({checkout.message})",
        )

    subscription.payment_provider_subscription_ref = checkout.provider_reference or subscription.payment_provider_subscription_ref
    subscription.payment_provider_code = checkout.provider.value
    subscription.last_payment_status = (checkout.status or "WAITING_PAYMENT").strip().upper() or "WAITING_PAYMENT"
    if plan.kind == PlanKind.SUBSCRIPTION:
        subscription.payment_method_setup_required = True
    if subscription.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED}:
        subscription.status = SubscriptionStatus.PENDING
        subscription.auto_renew = False
        subscription.bookings_blocked = False
    db.add(subscription)
    db.commit()

    return ClientPaymentCheckoutOut(
        payment_id=f"plan:{subscription.id}",
        checkout_url=checkout.checkout_url,
        provider_reference=subscription.payment_provider_subscription_ref,
    )


@router.post("/clients/me/subscriptions/{subscription_id}/payment-method-setup/confirm", response_model=ClientPaymentConfirmOut)
def confirm_client_subscription_payment_method_setup(
    subscription_id: UUID,
    checkout_session_id: str = Query(min_length=4, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientPaymentConfirmOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    subscription = db.scalar(
        select(ClientPlanSubscription)
        .where(
            ClientPlanSubscription.id == subscription_id,
            ClientPlanSubscription.user_id.in_(managed_ids),
        )
        .with_for_update()
    )
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abonnement introuvable")
    if (subscription.billing_method_code or "").strip().upper() != "SEPA_DEBIT":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cet abonnement ne demande pas de mandat SEPA")
    if not checkout_session_id.startswith("cs_"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Session Stripe invalide")

    lookup = lookup_payment(db, provider=PaymentProvider.STRIPE, payment_reference=checkout_session_id)
    metadata_subscription_id = (lookup.metadata.get("subscription_id") or "").strip()
    if metadata_subscription_id != str(subscription.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session Stripe non rattachee a cet abonnement")
    lookup_customer_reference = (lookup.metadata.get("customer_reference") or "").strip()
    if lookup_customer_reference != (subscription.payment_provider_customer_ref or "").strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client Stripe non rattache a cet abonnement")
    setup_complete = bool(
        lookup.setup_complete
        and lookup.payment_method_type == "sepa_debit"
        and lookup.payment_method_reference
    )
    if setup_complete:
        now = _utcnow()
        subscription.payment_provider_code = PaymentProvider.STRIPE.value
        subscription.payment_provider_payment_method_ref = lookup.payment_method_reference
        subscription.payment_provider_mandate_ref = (lookup.metadata.get("mandate_reference") or "").strip() or None
        subscription.payment_method_setup_required = False
        subscription.payment_method_setup_completed_at = now
        subscription.last_payment_status = "SEPA_MANDATE_ACTIVE"
        subscription.auto_renew = True
        db.add(subscription)
        db.commit()

    return ClientPaymentConfirmOut(
        payment_id=f"plan:{subscription.id}",
        subscription_status=(subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)),
        last_payment_status=subscription.last_payment_status,
        paid=setup_complete,
        cancelled=lookup.cancelled,
        failed=lookup.failed,
        processed=setup_complete,
        message="Mandat SEPA active" if setup_complete else "Mandat SEPA en attente",
    )


@router.post("/clients/me/sessions/{session_id}/checkout", response_model=ClientSessionCheckoutOut)
def create_client_session_checkout(
    session_id: UUID,
    payload: BookingCreateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSessionCheckoutOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    checkout_payload = payload or BookingCreateRequest()
    requested_user_id = checkout_payload.user_id
    if requested_user_id is not None and requested_user_id not in managed_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Target member is not attached to this adult account")
    lookup_user_ids = [requested_user_id] if requested_user_id is not None else managed_ids

    existing_booking = db.scalar(
        select(Booking)
        .where(
            Booking.session_id == session_id,
            Booking.user_id.in_(lookup_user_ids),
        )
        .order_by(Booking.booked_at.desc(), Booking.id.desc())
        .with_for_update()
        .limit(1)
    )

    session_for_checkout = db.scalar(select(CourseSession).where(CourseSession.id == session_id))
    uses_payment_hold = session_for_checkout is not None and should_defer_booking_invoice(session_for_checkout)

    booking_id: UUID | None = None
    should_create_or_refresh = (
        existing_booking is None
        or existing_booking.status == BookingStatus.CANCELLED
        or (uses_payment_hold and existing_booking.status == BookingStatus.PENDING_PAYMENT)
    )
    if should_create_or_refresh:
        try:
            if uses_payment_hold:
                booking_out = create_or_refresh_pending_payment_booking(
                    session_id=session_id,
                    payload=BookingCreateRequest(user_id=requested_user_id),
                    db=db,
                    current_user=current_user,
                )
            else:
                booking_out = book_session(
                    session_id=session_id,
                    payload=BookingCreateRequest(user_id=requested_user_id),
                    db=db,
                    current_user=current_user,
                )
            booking_id = booking_out.id
        except HTTPException as exc:
            detail = str(exc.detail or "").strip()
            if exc.status_code not in {status.HTTP_409_CONFLICT} or detail not in {"Already booked", "Already in waitlist", "Payment pending"}:
                raise
            existing_booking = db.scalar(
                select(Booking)
                .where(
                    Booking.session_id == session_id,
                    Booking.user_id.in_(lookup_user_ids),
                )
                .order_by(Booking.booked_at.desc(), Booking.id.desc())
                .limit(1)
            )
            if existing_booking is None:
                raise
            booking_id = existing_booking.id
    else:
        booking_id = existing_booking.id

    row = db.execute(
        select(Booking, CourseSession, CourseType, Location, User)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.id == booking_id,
            Booking.user_id.in_(lookup_user_ids),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation introuvable")

    booking, session_obj, course_type, location, owner = row
    booking_status = booking.status.value if hasattr(booking.status, "value") else str(booking.status)

    if booking.status == BookingStatus.WAITLISTED:
        return ClientSessionCheckoutOut(
            booking_id=booking.id,
            booking_status=booking_status,
            checkout_url=None,
            invoice_status=None,
        )

    if booking.status == BookingStatus.PENDING_PAYMENT and should_defer_booking_invoice(session_obj):
        amount_due = remaining_booking_amount_due(db, booking=booking)
        if amount_due <= Decimal("0.00"):
            return ClientSessionCheckoutOut(
                booking_id=booking.id,
                booking_status=booking_status,
                checkout_url=None,
                invoice_status="PAID",
            )
        receipt_snapshot = build_booking_receipt_snapshot(
            db,
            booking=booking,
            session_obj=session_obj,
            course_type=course_type,
            location=location,
            owner=owner,
        )
        receipt = get_or_create_pending_booking_payment_receipt(
            db,
            booking=booking,
            snapshot=receipt_snapshot,
        )
        db.commit()
        return ClientSessionCheckoutOut(
            booking_id=booking.id,
            booking_status=booking_status,
            checkout_url=payment_receipt_public_payment_url(
                client_id=receipt_snapshot.customer_id,
                receipt_id=receipt.id,
            ),
            invoice_status="PAYMENT_PENDING",
        )

    if booking.status != BookingStatus.BOOKED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce creneau n est pas reservable pour un paiement")

    if booking.client_plan_subscription_id is not None:
        return ClientSessionCheckoutOut(
            booking_id=booking.id,
            booking_status=booking_status,
            checkout_url=None,
            invoice_status="COVERED",
        )

    if should_defer_booking_invoice(session_obj):
        amount_due = remaining_booking_amount_due(db, booking=booking)
        if amount_due <= Decimal("0.00"):
            return ClientSessionCheckoutOut(
                booking_id=booking.id,
                booking_status=booking_status,
                checkout_url=None,
                invoice_status="PAID",
            )
        receipt_snapshot = build_booking_receipt_snapshot(
            db,
            booking=booking,
            session_obj=session_obj,
            course_type=course_type,
            location=location,
            owner=owner,
        )
        receipt = get_or_create_pending_booking_payment_receipt(
            db,
            booking=booking,
            snapshot=receipt_snapshot,
        )
        db.commit()
        return ClientSessionCheckoutOut(
            booking_id=booking.id,
            booking_status=booking_status,
            checkout_url=payment_receipt_public_payment_url(
                client_id=receipt_snapshot.customer_id,
                receipt_id=receipt.id,
            ),
            invoice_status="PAYMENT_PENDING",
        )

    amount_due = Decimal(booking.total_incl_vat_snapshot).quantize(Decimal("0.01"))
    if amount_due <= Decimal("0.00"):
        return ClientSessionCheckoutOut(
            booking_id=booking.id,
            booking_status=booking_status,
            checkout_url=None,
            invoice_status="PAID",
        )

    active_note = _active_booking_invoice_note(
        db,
        client_id=owner.id,
        booking_id=booking.id,
    )
    if active_note is not None:
        note, metadata = active_note
        invoice_status = str(metadata.get("invoice_status") or "ISSUED").strip().upper() or "ISSUED"
        checkout_url = None if invoice_status == "PAID" else _invoice_range_public_payment_url(
            client_id=owner.id,
            note_id=note.id,
            metadata=metadata,
        )
        return ClientSessionCheckoutOut(
            booking_id=booking.id,
            booking_status=booking_status,
            checkout_url=checkout_url,
            invoice_status=invoice_status,
        )

    note, metadata = _create_booking_invoice_note(
        db,
        booking=booking,
        session_obj=session_obj,
        course_type=course_type,
        location=location,
        owner=owner,
        author_user_id=current_user.id,
    )
    db.commit()

    return ClientSessionCheckoutOut(
        booking_id=booking.id,
        booking_status=booking_status,
        checkout_url=_invoice_range_public_payment_url(
            client_id=owner.id,
            note_id=note.id,
            metadata=metadata,
        ),
        invoice_status="ISSUED",
    )


@router.get("/clients/me/sessions/{session_id}/reservation-options", response_model=ClientSessionReservationOptionsOut)
def get_client_session_reservation_options(
    session_id: UUID,
    member_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSessionReservationOptionsOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    target_member_ids = managed_ids
    if member_id is not None:
        if member_id not in managed_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        target_member_ids = {member_id}
    members = db.scalars(
        select(User)
        .where(
            User.id.in_(target_member_ids),
            User.role == UserRole.CLIENT,
        )
        .order_by(User.client_kind.asc(), User.first_name.asc(), User.last_name.asc(), User.email.asc())
    ).all()
    member_by_id = {member.id: member for member in members}

    row = db.execute(
        select(CourseSession, CourseType)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(CourseSession.id == session_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_obj, course_type = row

    if not bool(course_type.allows_student_bookings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This slot does not accept student bookings")

    formula_options, direct_payment_amount, direct_payment_currency, session_booking_scopes = _session_purchase_catalog(
        db,
        session_obj=session_obj,
        course_type=course_type,
    )
    online_booking_enabled = session_booking_scopes != [SessionAudienceScope.PRIVATE]
    allowed_plan_kinds = allowed_plan_kinds_for_scopes(session_booking_scopes)
    now = _utcnow()
    min_booking_notice_hours, _, _ = _effective_session_booking_rules(db, session_obj=session_obj)
    booking_deadline_reached = session_obj.start_at_utc < now + timedelta(hours=min_booking_notice_hours)
    session_started = session_obj.start_at_utc <= now
    is_full = _count_booked(db, session_obj.id) >= session_obj.capacity_max

    existing_bookings = db.scalars(
        select(Booking)
        .where(
            Booking.session_id == session_id,
            Booking.user_id.in_(managed_ids),
        )
        .order_by(Booking.booked_at.desc(), Booking.id.desc())
    ).all()
    booking_by_user: dict[UUID, Booking] = {}
    for booking in existing_bookings:
        booking_by_user.setdefault(booking.user_id, booking)

    member_options: list[ClientSessionReservationMemberOptionOut] = []
    for member in members:
        try:
            existing = booking_by_user.get(member.id)
            booking_status = existing.status.value if existing is not None and hasattr(existing.status, "value") else (
                str(existing.status) if existing is not None else None
            )
            if existing is not None:
                normalized_existing = booking_status or ""
                if normalized_existing in {"BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"}:
                    member_options.append(
                        ClientSessionReservationMemberOptionOut(
                            member_id=member.id,
                            member_display_name=_display_name(member),
                            member_kind=member.client_kind,
                            booking_id=existing.id,
                            booking_status=booking_status,
                            action_code="ALREADY_BOOKED",
                            action_label="Voir la reservation",
                            status_label="Reserve",
                            reason="Reservation deja confirmee pour ce membre.",
                            has_credit_coverage=existing.client_plan_subscription_id is not None or existing.manual_credit_type_id is not None,
                            coverage_source="PLAN" if existing.client_plan_subscription_id is not None else ("MANUAL_CREDIT" if existing.manual_credit_type_id is not None else None),
                        )
                    )
                    continue
                if normalized_existing == "WAITLISTED":
                    member_options.append(
                        ClientSessionReservationMemberOptionOut(
                            member_id=member.id,
                            member_display_name=_display_name(member),
                            member_kind=member.client_kind,
                            booking_id=existing.id,
                            booking_status=booking_status,
                            action_code="ALREADY_WAITLISTED",
                            action_label="Voir la reservation",
                            status_label="Liste d attente",
                            reason="Ce membre est deja en liste d attente pour ce creneau.",
                        )
                    )
                    continue
                if normalized_existing == "PENDING_PAYMENT":
                    amount_due = remaining_booking_amount_due(db, booking=existing)
                    member_options.append(
                        ClientSessionReservationMemberOptionOut(
                            member_id=member.id,
                            member_display_name=_display_name(member),
                            member_kind=member.client_kind,
                            booking_id=existing.id,
                            booking_status=booking_status,
                            action_code="FINALIZE_PAYMENT",
                            action_label="Finaliser le paiement",
                            status_label="Paiement en attente",
                            reason="Une reservation provisoire existe deja pour ce membre. Finalisez le paiement pour confirmer la place.",
                            direct_payment_amount_ttc=amount_due if amount_due > Decimal("0.00") else None,
                            direct_payment_currency=existing.currency_snapshot or direct_payment_currency,
                        )
                    )
                    continue

            if session_obj.status != SessionStatus.SCHEDULED:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="UNAVAILABLE",
                        action_label="Non reservable",
                        status_label="Reservation fermee",
                        reason="Ce creneau n est plus ouvert a la reservation.",
                    )
                )
                continue

            if not online_booking_enabled:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="UNAVAILABLE",
                        action_label="Non reservable",
                        status_label="Reservation fermee",
                        reason="La reservation en ligne est fermee pour ce creneau.",
                    )
                )
                continue

            if session_started or booking_deadline_reached:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="UNAVAILABLE",
                        action_label="Non reservable",
                        status_label="Reservation fermee",
                        reason="Le delai de reservation pour ce creneau est depasse.",
                    )
                )
                continue

            if is_full:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="JOIN_WAITLIST",
                        action_label="Rejoindre la liste d attente",
                        status_label="Liste d attente",
                        reason="Le creneau est complet. Vous pouvez rejoindre la liste d attente.",
                    )
                )
                continue

            selected_subscription = _select_eligible_subscription(
                db,
                user_id=member.id,
                course_type_id=course_type.id,
                now=now,
                requested_subscription_id=None,
                allowed_plan_kinds=allowed_plan_kinds,
            )
            if selected_subscription is not None:
                _, selected_plan = selected_subscription
                coverage_source = selected_plan.kind.value if hasattr(selected_plan.kind, "value") else str(selected_plan.kind or "")
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="BOOK_WITH_CREDIT",
                        action_label="Reserver maintenant",
                        status_label="Credit disponible",
                        reason="Cette reservation sera confirmee sans paiement supplementaire.",
                        has_credit_coverage=True,
                        coverage_source=coverage_source or None,
                    )
                )
                continue

            manual_credit_balance = (
                db.scalar(
                    select(ClientManualCreditBalance)
                    .where(
                        ClientManualCreditBalance.user_id == member.id,
                        ClientManualCreditBalance.credit_type_id == course_type.credit_type_id,
                    )
                )
                if course_type.credit_type_id is not None
                else None
            )
            if manual_credit_balance is not None and int(manual_credit_balance.credits_count or 0) > 0:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="BOOK_WITH_CREDIT",
                        action_label="Reserver maintenant",
                        status_label="Credit disponible",
                        reason="Cette reservation utilisera un credit manuel disponible.",
                        has_credit_coverage=True,
                        coverage_source="MANUAL_CREDIT",
                    )
                )
                continue

            if direct_payment_amount is not None and formula_options:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="BUY_FORMULA_OR_PAY_UNIT",
                        action_label="Choisir votre option",
                        status_label="Paiement requis",
                        reason="Aucun credit disponible. Vous pouvez acheter une formule compatible ou payer cette reservation a l unite.",
                        direct_payment_amount_ttc=direct_payment_amount,
                        direct_payment_currency=direct_payment_currency,
                        formula_options=formula_options,
                    )
                )
                continue

            if formula_options:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="BUY_FORMULA",
                        action_label="Acheter une formule",
                        status_label="Aucune couverture",
                        reason="Selectionnez une formule compatible pour confirmer la reservation.",
                        formula_options=formula_options,
                    )
                )
                continue

            if direct_payment_amount is not None:
                member_options.append(
                    ClientSessionReservationMemberOptionOut(
                        member_id=member.id,
                        member_display_name=_display_name(member),
                        member_kind=member.client_kind,
                        action_code="PAY_UNIT",
                        action_label="Payer et reserver",
                        status_label="Paiement requis",
                        reason="Aucun credit disponible. Cette reservation peut etre payee a l unite.",
                        direct_payment_amount_ttc=direct_payment_amount,
                        direct_payment_currency=direct_payment_currency,
                    )
                )
                continue

            member_options.append(
                ClientSessionReservationMemberOptionOut(
                    member_id=member.id,
                    member_display_name=_display_name(member),
                    member_kind=member.client_kind,
                    action_code="UNAVAILABLE",
                    action_label="Non reservable",
                    status_label="Aucune couverture",
                    reason="Aucune formule ni paiement unitaire n est disponible pour ce creneau.",
                )
            )
        except Exception:
            logger.exception(
                "Failed to resolve reservation options for session %s and member %s",
                session_id,
                member.id,
            )
            member_options.append(
                ClientSessionReservationMemberOptionOut(
                    member_id=member.id,
                    member_display_name=_display_name(member),
                    member_kind=member.client_kind,
                    action_code="UNAVAILABLE",
                    action_label="Non reservable",
                    status_label="Indisponible",
                    reason="Impossible de calculer les options de reservation pour ce membre pour le moment.",
                )
            )

    return ClientSessionReservationOptionsOut(
        session_id=session_obj.id,
        session_title=course_type.name,
        session_status=session_obj.status.value if hasattr(session_obj.status, "value") else str(session_obj.status),
        is_full=is_full,
        online_booking_enabled=online_booking_enabled,
        waitlist_enabled=online_booking_enabled,
        members=member_options,
    )


@router.get("/clients/me/sessions/{session_id}/purchase-catalog", response_model=ClientSessionPurchaseCatalogOut)
def get_client_session_purchase_catalog(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSessionPurchaseCatalogOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    if not managed_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Aucun membre rattaché au compte")

    row = db.execute(
        select(CourseSession, CourseType)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(CourseSession.id == session_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_obj, course_type = row

    if not bool(course_type.allows_student_bookings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This slot does not accept student bookings")

    formula_options, direct_payment_amount, direct_payment_currency, _ = _session_purchase_catalog(
        db,
        session_obj=session_obj,
        course_type=course_type,
    )
    return ClientSessionPurchaseCatalogOut(
        session_id=session_obj.id,
        formula_options=formula_options,
        direct_payment_amount_ttc=direct_payment_amount,
        direct_payment_currency=direct_payment_currency,
    )


@router.post("/clients/me/payments/{payment_id}/confirm", response_model=ClientPaymentConfirmOut)
def confirm_client_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientPaymentConfirmOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    row = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.id == payment_id,
            ClientPlanSubscription.user_id.in_(managed_ids),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")

    subscription, plan = row
    was_paid_before = subscription.last_payment_at is not None
    status_before = subscription.status
    was_setup_required = bool(subscription.payment_method_setup_required)
    payment_reference = (subscription.payment_provider_subscription_ref or "").strip()
    if not payment_reference:
        return ClientPaymentConfirmOut(
            payment_id=f"plan:{subscription.id}",
            subscription_status=(subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)),
            last_payment_status=subscription.last_payment_status,
            paid=False,
            cancelled=False,
            failed=False,
            processed=False,
            message="Reference PSP absente",
        )

    provider = detect_provider_from_reference(payment_reference) or resolve_provider(db)
    lookup = lookup_payment(db, provider=provider, payment_reference=payment_reference)
    status_text = (lookup.status or "").strip().upper() or "UNKNOWN"

    changed = False
    if (subscription.last_payment_status or "") != status_text:
        subscription.last_payment_status = status_text
        changed = True

    mandate_missing_for_recurring = False
    if lookup.paid:
        customer_reference = (lookup.metadata.get("customer_reference") or "").strip()
        mandate_reference = (lookup.metadata.get("mandate_reference") or "").strip()
        if customer_reference and subscription.payment_provider_customer_ref != customer_reference:
            subscription.payment_provider_customer_ref = customer_reference
            changed = True
        if mandate_reference and subscription.payment_provider_mandate_ref != mandate_reference:
            subscription.payment_provider_mandate_ref = mandate_reference
            changed = True
        if provider == PaymentProvider.PAYPLUG and lookup.payment_method_reference:
            subscription.payment_provider_code = provider.value
            subscription.payment_provider_payment_method_ref = lookup.payment_method_reference
            subscription.payment_method_exp_month = lookup.payment_method_exp_month
            subscription.payment_method_exp_year = lookup.payment_method_exp_year
            subscription.payment_method_setup_required = False
            subscription.payment_method_setup_completed_at = _utcnow()
            subscription.billing_method_code = "CARD_ONLINE"
            changed = True
        elif provider == PaymentProvider.STRIPE and lookup.payment_method_reference:
            subscription.payment_provider_code = provider.value
            subscription.payment_provider_payment_method_ref = lookup.payment_method_reference
            subscription.payment_method_exp_month = lookup.payment_method_exp_month
            subscription.payment_method_exp_year = lookup.payment_method_exp_year
            if (subscription.billing_method_code or "").strip().upper() == "CARD_ONLINE":
                subscription.payment_method_setup_required = False
                subscription.payment_method_setup_completed_at = _utcnow()
            else:
                subscription.payment_method_setup_required = True
            changed = True
        if subscription.last_payment_at is None:
            subscription.last_payment_at = _utcnow()
            changed = True
        subscription.last_successful_charge_at = subscription.last_payment_at
        if subscription.status in {
            SubscriptionStatus.PENDING,
            SubscriptionStatus.PAUSED,
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PAYMENT_ALERT,
            SubscriptionStatus.PRE_TERMINATION,
            SubscriptionStatus.TERMINATED,
        }:
            if subscription.status != SubscriptionStatus.ACTIVE and status_before != SubscriptionStatus.PAUSED:
                subscription.status = SubscriptionStatus.ACTIVE
                changed = True
        if subscription.bookings_blocked:
            subscription.bookings_blocked = False
            changed = True
        if subscription.payment_alert_started_at is not None:
            subscription.payment_alert_started_at = None
            changed = True
        if subscription.pre_termination_at is not None:
            subscription.pre_termination_at = None
            changed = True
        if subscription.direct_payment_recovery_url is not None:
            subscription.direct_payment_recovery_url = None
            changed = True
        if plan.kind == PlanKind.SUBSCRIPTION:
            billing_method_code = (subscription.billing_method_code or "").strip().upper()
            requires_stored_card = billing_method_code == "CARD_ONLINE"
            if provider == PaymentProvider.PAYPLUG:
                payment_method_ready = bool((subscription.payment_provider_payment_method_ref or "").strip())
            elif provider == PaymentProvider.STRIPE:
                payment_method_ready = bool((subscription.payment_provider_customer_ref or "").strip()) and bool(
                    (subscription.payment_provider_payment_method_ref or "").strip()
                )
            else:
                payment_method_ready = bool((subscription.payment_provider_customer_ref or "").strip()) and bool(
                    (subscription.payment_provider_mandate_ref or "").strip()
                )
            mandate_missing_for_recurring = requires_stored_card and not payment_method_ready
            if mandate_missing_for_recurring:
                if subscription.auto_renew:
                    subscription.auto_renew = False
                    changed = True
                subscription.payment_method_setup_required = True
                if (subscription.last_payment_status or "") != "PAID_PAYMENT_METHOD_MISSING":
                    subscription.last_payment_status = "PAID_PAYMENT_METHOD_MISSING"
                    changed = True
            elif billing_method_code == "SEPA_DEBIT" and subscription.payment_method_setup_required:
                if subscription.auto_renew:
                    subscription.auto_renew = False
                    changed = True
            elif not subscription.auto_renew:
                subscription.auto_renew = True
                changed = True
            paid_at = subscription.last_payment_at or _utcnow()
            due_at = subscription.next_payment_at or subscription.current_period_end
            if (
                was_setup_required
                and status_before in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_ALERT}
                and due_at is not None
                and due_at <= paid_at
            ):
                next_end = add_months_utc(due_at, 1)
                subscription.current_period_start = due_at
                subscription.current_period_end = next_end
                subscription.next_payment_at = next_end
                subscription.ends_at = next_end
                changed = True
    elif lookup.cancelled:
        if subscription.status == SubscriptionStatus.PENDING:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.auto_renew = False
            subscription.next_payment_at = None
            changed = True

    if changed:
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
    else:
        db.rollback()

    if lookup.paid and not was_paid_before:
        owner = db.scalar(select(User).where(User.id == subscription.user_id))
        if owner is not None and owner.email:
            try:
                amount_due, currency_code = _plan_amount_due_and_currency(
                    db,
                    plan=plan,
                    country=(owner.residence_country or "FR").upper(),
                    currency=(owner.preferred_currency or "EUR").upper(),
                    on_date=subscription.started_at,
                )
                send_client_payment_success_notifications(
                    db,
                    to_email=owner.email,
                    first_name=owner.first_name,
                    last_name=owner.last_name,
                    plan_name=plan.name,
                    subscription_id=subscription.id,
                    paid_at=subscription.last_payment_at or _utcnow(),
                    amount_paid=amount_due,
                    currency=currency_code,
                    language=owner.preferred_language,
                )
            except Exception:
                logger.exception("Unable to send paid confirmation emails for subscription=%s", subscription.id)

    return ClientPaymentConfirmOut(
        payment_id=f"plan:{subscription.id}",
        subscription_status=(subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)),
        last_payment_status=subscription.last_payment_status,
        paid=lookup.paid,
        cancelled=lookup.cancelled,
        failed=lookup.failed,
        processed=lookup.success,
        message=(
            "Paiement confirme mais mandat de prelevement recurrent introuvable. L auto-renouvellement est desactive."
            if mandate_missing_for_recurring
            else lookup.message
        ),
    )


@router.get("/clients/me/payments", response_model=list[ClientPaymentOut])
def list_client_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientPaymentOut]:
    return _build_client_payments(db, current_user)


@router.get("/clients/me/invoices", response_model=list[ClientInvoiceOut])
def list_client_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientInvoiceOut]:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    users_by_id = {
        row.id: row
        for row in db.scalars(
            select(User).where(User.id.in_(managed_client_ids), User.role == UserRole.CLIENT)
        ).all()
    }

    payments = _build_client_payments(db, current_user)
    booking_payment_ids = [
        booking_id
        for payment in payments
        for booking_id in (_booking_uuid_from_payment_id(payment.id),)
        if (payment.source or "").strip().upper() == "BOOKING" and booking_id is not None
    ]
    forfait_bookings = _forfait_booking_ids(db, booking_payment_ids)
    invoices: list[ClientInvoiceOut] = []

    range_notes = db.scalars(
        select(ClientNoteEntry)
        .where(ClientNoteEntry.user_id.in_(managed_client_ids))
        .order_by(ClientNoteEntry.created_at.desc())
    ).all()
    range_note_ids = [note.id for note in range_notes]
    payment_keys_by_note_id: dict[UUID, list[str]] = defaultdict(list)
    if range_note_ids:
        line_rows = db.execute(
            select(ClientInvoiceLine.note_id, ClientInvoiceLine.source, ClientInvoiceLine.source_payment_id).where(
                ClientInvoiceLine.note_id.in_(range_note_ids)
            )
        ).all()
        for note_id, source, source_payment_id in line_rows:
            source_code = str(source or "").strip().upper()
            if not source_code or source_payment_id is None:
                continue
            normalized_key = f"{source_code}:{source_payment_id}"
            bucket = payment_keys_by_note_id[note_id]
            if normalized_key not in bucket:
                bucket.append(normalized_key)
    for note in range_notes:
        metadata = _parse_invoice_range_note_entry(note)
        if metadata is None:
            continue
        invoice_number = str(metadata.get("invoice_number") or "").strip()
        if not invoice_number:
            continue
        issued_date_text = str(metadata.get("issued_date") or "").strip()
        try:
            issued_date = date.fromisoformat(issued_date_text)
        except ValueError:
            continue
        total_amount, currency_code = _first_currency_total(metadata)
        invoice_status = _invoice_range_status_for_client(metadata.get("invoice_status"))
        if invoice_status == "CANCELLED":
            continue
        owner = users_by_id.get(note.user_id)
        owner_display_name = _display_name(owner) if owner is not None else str(note.user_id)
        payment_keys = _normalize_invoice_range_payment_keys(metadata.get("included_payment_keys"))
        if note.id in payment_keys_by_note_id:
            existing = set(payment_keys)
            for key in payment_keys_by_note_id[note.id]:
                if key in existing:
                    continue
                existing.add(key)
                payment_keys.append(key)
        invoices.append(
            ClientInvoiceOut(
                id=f"invoice-range:{note.id}",
                owner_client_id=note.user_id,
                owner_display_name=owner_display_name,
                invoice_number=invoice_number,
                issued_at=datetime.combine(issued_date, datetime.min.time(), tzinfo=timezone.utc),
                source="INVOICE_RANGE",
                status=invoice_status,
                label=_invoice_range_label(metadata),
                total_incl_vat=total_amount,
                currency=currency_code,
                reference=str(note.id),
                download_url=f"/client/invoices/invoice-range:{note.id}/download",
                payment_url=_normalize_public_invoice_payment_url(str(metadata.get("payment_url") or "").strip())
                or _invoice_range_public_payment_url(client_id=note.user_id, note_id=note.id, metadata=metadata),
                included_payment_keys=payment_keys,
                source_quote_id=metadata.get("source_quote_id"),
                source_quote_number=str(metadata.get("source_quote_number") or "").strip() or None,
                invoice_kind="DEPOSIT" if metadata.get("source_quote_id") else str(metadata.get("kind") or "").strip() or None,
            )
        )

    for payment in payments:
        if (payment.source or "").strip().upper() == "MANUAL":
            continue
        if (payment.source or "").strip().upper() == "BOOKING":
            booking_id = _booking_uuid_from_payment_id(payment.id)
            if booking_id is not None and booking_id in forfait_bookings:
                continue

        invoice_status = _invoice_status_from_payment_status(payment.status)
        if invoice_status != "PAID":
            continue

        raw_id = payment.id.split(":", maxsplit=1)[-1]
        compact = raw_id.replace("-", "").upper()
        short = compact[:8] if compact else "XXXX0000"
        number = f"FAC-{payment.occurred_at.strftime('%Y%m%d')}-{short}"

        invoices.append(
            ClientInvoiceOut(
                id=f"invoice:{payment.id}",
                owner_client_id=payment.owner_client_id,
                owner_display_name=payment.owner_display_name,
                invoice_number=number,
                issued_at=payment.occurred_at,
                source=payment.source,
                status=invoice_status,
                label=payment.label,
                total_incl_vat=payment.total_incl_vat,
                currency=payment.currency,
                reference=payment.reference,
                download_url=f"/client/invoices/{payment.id}/download",
                payment_url=payment.payment_url,
                included_payment_keys=[f"{(payment.source or '').strip().upper()}:{raw_id}"],
            )
        )

    invoices.sort(key=lambda row: row.issued_at, reverse=True)
    return invoices


@router.get("/clients/me/invoices/{invoice_id}/download")
def download_client_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    invoice_ref = invoice_id.strip()
    if invoice_ref.startswith("invoice:"):
        invoice_ref = invoice_ref[len("invoice:") :]
    invoice_ref = invoice_ref.strip()
    if not invoice_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if invoice_ref.startswith("invoice-range:"):
        note_id_raw = invoice_ref[len("invoice-range:") :].strip()
        try:
            note_id = UUID(note_id_raw)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found") from exc

        note = db.scalar(
            select(ClientNoteEntry).where(
                ClientNoteEntry.id == note_id,
                ClientNoteEntry.user_id.in_(managed_client_ids),
            )
        )
        if note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        metadata = _parse_invoice_range_note_entry(note)
        if metadata is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

        owner = db.scalar(select(User).where(User.id == note.user_id, User.role == UserRole.CLIENT))
        if owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        recipient_snapshot = _invoice_recipient_snapshot_for_user(db, owner)

        invoice_number = _normalize_optional(str(metadata.get("invoice_number") or "")) or f"INV-{note.id}"
        issued_date_text = str(metadata.get("issued_date") or "").strip()
        due_date_text = str(metadata.get("due_date") or "").strip()
        try:
            issued_date = date.fromisoformat(issued_date_text)
        except ValueError:
            issued_date = note.created_at.date()
        try:
            due_date_value = date.fromisoformat(due_date_text) if due_date_text else issued_date
        except ValueError:
            due_date_value = issued_date
        issued_at = datetime.combine(issued_date, datetime.min.time(), tzinfo=timezone.utc)

        invoice_lines_rows = db.scalars(
            select(ClientInvoiceLine)
            .where(ClientInvoiceLine.note_id == note.id)
            .order_by(ClientInvoiceLine.occurred_at.asc(), ClientInvoiceLine.id.asc())
        ).all()
        invoice_lines = _invoice_period_lines_from_invoice_lines(db, invoice_lines_rows)

        totals_by_currency = _invoice_period_totals_from_lines_or_metadata(invoice_lines, metadata)

        raw_auto_include_previous_balance = metadata.get("auto_include_previous_balance")
        auto_include_previous_balance = (
            bool(raw_auto_include_previous_balance)
            if isinstance(raw_auto_include_previous_balance, bool)
            else True
        )

        opening_balance_by_currency: dict[str, Decimal] = {}
        if auto_include_previous_balance and not is_single_booking_invoice_scope(metadata):
            raw_opening = metadata.get("opening_balance_by_currency")
            if isinstance(raw_opening, dict):
                for currency_code, value in raw_opening.items():
                    try:
                        opening_balance_by_currency[str(currency_code).strip().upper() or "EUR"] = Decimal(str(value)).quantize(Decimal("0.01"))
                    except Exception:
                        continue
        total_to_pay_by_currency: dict[str, Decimal] = {}
        raw_total_to_pay = metadata.get("total_to_pay_by_currency")
        if isinstance(raw_total_to_pay, dict):
            for currency_code, value in raw_total_to_pay.items():
                try:
                    total_to_pay_by_currency[str(currency_code).strip().upper() or "EUR"] = Decimal(str(value)).quantize(Decimal("0.01"))
                except Exception:
                    continue
        applied_payment_totals_by_currency: dict[str, Decimal] = {}
        raw_applied_payments = metadata.get("applied_payment_totals_by_currency")
        if isinstance(raw_applied_payments, dict):
            for currency_code, value in raw_applied_payments.items():
                try:
                    applied_payment_totals_by_currency[str(currency_code).strip().upper() or "EUR"] = Decimal(str(value)).quantize(Decimal("0.01"))
                except Exception:
                    continue
        if not auto_include_previous_balance:
            total_to_pay_by_currency = {}
            for currency_code in sorted(set(totals_by_currency.keys()) | set(applied_payment_totals_by_currency.keys())):
                period_amount = Decimal(totals_by_currency.get(currency_code, Decimal("0.00"))).quantize(Decimal("0.01"))
                applied_amount = Decimal(
                    applied_payment_totals_by_currency.get(currency_code, Decimal("0.00"))
                ).quantize(Decimal("0.01"))
                total_to_pay_by_currency[currency_code] = (period_amount + applied_amount).quantize(Decimal("0.01"))
        applied_payment_lines = _invoice_applied_payment_lines_from_metadata(metadata)

        public_note = _normalize_optional(str(metadata.get("public_note") or ""))
        legal_entity_id = _parse_optional_uuid(metadata.get("seller_legal_entity_id"))
        billing_entity = _billing_entity_text(str(metadata.get("billing_entity") or "")) if metadata.get("billing_entity") else None
        frozen_company_identity = company_identity_from_snapshot(metadata.get("issuer_snapshot"))
        payment_link_url = _invoice_range_public_payment_url(
            client_id=note.user_id,
            note_id=note.id,
            metadata=metadata,
        )
        invoice_status = str(metadata.get("invoice_status") or "ISSUED").strip().upper()

        content = render_invoice_period_pdf(
            db,
            invoice_number=invoice_number,
            issued_at=issued_at,
            client_id=str(note.user_id),
            client_name=_invoice_recipient_name_from_metadata(metadata, fallback=recipient_snapshot["client_name"]),
            period_label=_invoice_range_label(metadata),
            lines=invoice_lines,
            totals_by_currency=totals_by_currency,
            note=public_note,
            client_billing_address=_invoice_recipient_address_from_metadata(
                metadata,
                fallback=recipient_snapshot["client_billing_address"],
            ),
            due_date=due_date_value,
            opening_balance_by_currency=opening_balance_by_currency,
            applied_payment_totals_by_currency=applied_payment_totals_by_currency,
            applied_payment_lines=applied_payment_lines,
            total_to_pay_by_currency=total_to_pay_by_currency,
            payment_link_url=payment_link_url,
            watermark=("PAYE" if invoice_status == "PAID" else None),
            legal_entity_id=legal_entity_id,
            billing_entity=billing_entity,
            company_identity_override=frozen_company_identity,
            language=normalize_language(current_user.preferred_language),
        )

        file_name = f"{invoice_number}.pdf".replace('"', "")
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "Cache-Control": "no-store",
            },
        )

    payments = _build_client_payments(db, current_user)
    payment = next((row for row in payments if row.id == invoice_ref), None)
    if payment is None and ":" not in invoice_ref:
        payment = next((row for row in payments if row.id in {f"plan:{invoice_ref}", f"booking:{invoice_ref}"}), None)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if (payment.source or "").strip().upper() == "BOOKING":
        booking_id = _booking_uuid_from_payment_id(payment.id)
        if booking_id is not None and booking_id in _forfait_booking_ids(db, [booking_id]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Forfait booking invoices are generated manually from back office.",
            )
    if payment.owner_client_id not in managed_client_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    payment_user = db.scalar(select(User).where(User.id == payment.owner_client_id))
    if payment_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return _render_client_payment_invoice_response(db, payment=payment, payment_user=payment_user)


def _render_client_payment_invoice_response(
    db: Session,
    *,
    payment: ClientPaymentOut,
    payment_user: User,
) -> Response:
    raw_id = payment.id.split(":", maxsplit=1)[-1]
    compact = raw_id.replace("-", "").upper()
    short = compact[:8] if compact else "XXXX0000"
    invoice_number = f"FAC-{payment.occurred_at.strftime('%Y%m%d')}-{short}"
    billing_profile = resolve_billing_profile(db, payment_user)
    line = InvoicePeriodLine(
        date_label=payment.occurred_at.strftime("%d/%m/%Y"),
        type_label=_payment_source_label(payment.source),
        label=payment.label,
        quantity=1,
        amount_excl_vat=payment.amount_excl_vat,
        vat_rate=payment.vat_rate,
        vat_amount=payment.vat_amount,
        total_incl_vat=payment.total_incl_vat,
        currency=payment.currency,
    )
    currency_code = (payment.currency or "EUR").upper()
    billing_entity = _billing_entity_text(payment.billing_entity)
    totals = {
        currency_code: {
            "amount_excl_vat": payment.amount_excl_vat,
            "vat_amount": payment.vat_amount,
            "total_incl_vat": payment.total_incl_vat,
        }
    }
    content = render_invoice_period_pdf(
        db,
        invoice_number=invoice_number,
        issued_at=payment.occurred_at,
        client_id=str(payment.owner_client_id),
        client_name=_display_name(billing_profile),
        period_label=payment.occurred_at.strftime("%d/%m/%Y"),
        lines=[line],
        totals_by_currency=totals,
        note=f"Reference: {payment.reference or '-'}",
        client_billing_address=_billing_address_label(billing_profile),
        due_date=payment.occurred_at.date(),
        legal_entity_id=payment.seller_legal_entity_id,
        billing_entity=billing_entity,
        language=normalize_language(payment_user.preferred_language),
    )

    file_name = f"{invoice_number}.pdf".replace('"', "")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/public/invoices/plans/{subscription_id}/download")
def download_public_plan_purchase_invoice(
    subscription_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    subscription = db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id))
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    payment_owner = db.scalar(
        select(User).where(
            User.id == subscription.user_id,
            User.role == UserRole.CLIENT,
        )
    )
    if payment_owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    payments = _build_client_payments(db, payment_owner)
    payment = next((row for row in payments if row.id == f"plan:{subscription_id}"), None)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return _render_client_payment_invoice_response(db, payment=payment, payment_user=payment_owner)
