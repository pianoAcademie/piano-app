from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db, require_roles
from app.core.config import settings
from app.models.client_group import ClientGroup, ClientGroupMembership
from app.models.client_record import ClientManualCreditBalance, ClientManualTransaction, ClientNoteEntry, ClientPaymentRefund
from app.models.family import ClientFamilyLink
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, CreditType, Location, SessionStatus
from app.models.ops import AppSetting, EmailReminder
from app.models.plan import (
    ClientPlanSubscription,
    Plan,
    PlanCreditGrant,
    PlanCreditGrantsRelation,
    PlanKind,
    PlanPriceTaxMode,
    SubscriptionStatus,
)
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.schemas.admin import (
    AdminClientBulkAction,
    AdminClientBulkOut,
    AdminClientBulkRequest,
    AdminClientSelectionScope,
    AdminClientCreateRequest,
    AdminClientGroupsUpdateRequest,
    AdminClientFamilyLinkCreateRequest,
    AdminClientFamilyLinkOut,
    AdminClientFamilyLinkUpdateRequest,
    AdminClientFamilyOut,
    AdminClientBookingOut,
    AdminFamilyMemberOut,
    AdminClientMessageOut,
    AdminClientOut,
    AdminClientPasswordEmailTemplateOut,
    AdminClientPasswordEmailTemplateUpdateRequest,
    AdminClientPasswordResetOut,
    AdminClientPaymentOut,
    AdminClientManualTransactionCreateRequest,
    AdminClientPaymentRefundOut,
    AdminClientPaymentRefundRequest,
    AdminClientSubscriptionMiniOut,
    AdminClientSubscriptionOut,
    AdminClientSubscriptionSuspendRequest,
    AdminClientSubscriptionCancelRequest,
    AdminClientSubscriptionExpiryUpdateRequest,
    AdminClientSubscriptionBillingSetupRequest,
    AdminClientSubscriptionPaymentEmailRequest,
    AdminClientSubscriptionPaymentEmailOut,
    AdminClientPlanPurchaseRequest,
    AdminClientManualCreditOut,
    AdminClientManualCreditUpdateRequest,
    AdminClientNoteOut,
    AdminClientNoteCreateRequest,
    AdminClientUpdateRequest,
    AdminClientGroupCreateRequest,
    AdminClientGroupOut,
    AdminClientGroupUpdateRequest,
)
from app.schemas.plan import ClientSubscriptionOut, PlanMiniOut
from app.services.client_password_email import (
    generate_temporary_password,
    render_client_password_email,
    send_client_password_email,
)
from app.services.client_payment_email import (
    render_client_payment_email,
    send_client_payment_email,
)
from app.services.email_delivery import send_email
from app.services.family_billing import resolve_billing_profile
from app.services.invoice_documents import render_invoice_text
from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD,
    resolve_predefined_template,
    resolve_sender_profile,
    upsert_predefined_template,
)
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, with_webhook_secret
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate
from app.services.security import hash_password
from app.services.subscriptions import (
    add_months_utc,
    apply_suspension,
    default_next_payment_at,
    reconcile_subscription_status,
)

router = APIRouter(prefix="/admin/clients")

PAID_PAYMENT_STATUSES = {"PAID", "SUCCEEDED", "COMPLETED", "BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"}
PENDING_PAYMENT_STATUSES = {"PENDING", "WAITLISTED", "TRIAL", "OPEN", "CREATED", "PROCESSING", "WAITING_PAYMENT", "FAILED"}
CANCELLED_PAYMENT_STATUSES = {"CANCELLED", "EXPIRED", "INACTIVE", "ARCHIVED"}
FAILED_PAYMENT_STATUSES = {"NOT_SUPPORTED", "MISSING_KEY", "MISSING_CUSTOMER_REF", "MISSING_MANDATE_REF", "NETWORK_ERROR", "UNEXPECTED_ERROR"}
ONLINE_COLLECTION_METHOD_CODES = {"CARD_ONLINE", "SEPA_DEBIT", "PAYPAL"}
PRODUCT_CATEGORIES_SETTING_KEY = "config_products_categories_v1"
MANUAL_TRANSACTION_SIGN_BY_TYPE = {
    "PAYMENT": Decimal("-1"),
    "DISCOUNT": Decimal("-1"),
    "CHARGE": Decimal("1"),
    "REFUND": Decimal("1"),
}
MANUAL_TRANSACTION_STATUS_BY_TYPE = {
    "PAYMENT": "PAID",
    "DISCOUNT": "COMPLETED",
    "CHARGE": "PENDING",
    "REFUND": "COMPLETED",
}
MANUAL_TRANSACTION_LABEL_BY_TYPE = {
    "PAYMENT": "Paiement manuel",
    "DISCOUNT": "Rabais manuel",
    "CHARGE": "Montant facture",
    "REFUND": "Remboursement",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lock_user_purchase_scope(db: Session, user_id: UUID) -> None:
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())


def _has_same_subscription_in_current_month(
    db: Session,
    *,
    user_id: UUID,
    plan_id: UUID,
    now: datetime,
) -> bool:
    existing = db.scalar(
        select(ClientPlanSubscription.id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.plan_id == plan_id,
            ClientPlanSubscription.status.in_([SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED]),
            or_(ClientPlanSubscription.cancellation_effective_at.is_(None), ClientPlanSubscription.cancellation_effective_at > now),
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > now),
        )
        .limit(1)
        .with_for_update()
    )
    return existing is not None


def _has_active_pack_with_remaining_credits(db: Session, *, user_id: UUID, now: datetime) -> bool:
    existing = db.scalar(
        select(ClientPlanSubscription.id)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
            or_(ClientPlanSubscription.cancellation_effective_at.is_(None), ClientPlanSubscription.cancellation_effective_at > now),
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > now),
            Plan.active.is_(True),
            Plan.kind == PlanKind.PACK,
            ClientPlanSubscription.credits_remaining.is_not(None),
            ClientPlanSubscription.credits_remaining > 0,
        )
        .limit(1)
        .with_for_update()
    )
    return existing is not None


def _plan_payment_methods(plan: Plan) -> list[str]:
    raw = plan.payment_methods_json
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        code = str(value).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _default_subscription_billing_method(plan: Plan) -> str | None:
    methods = _plan_payment_methods(plan)
    if "CARD_ONLINE" in methods:
        return "CARD_ONLINE"
    return methods[0] if methods else None


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _normalize_currency(value: str | None, *, fallback: str = "EUR") -> str:
    candidate = (value or "").strip().upper()
    if len(candidate) != 3 or not candidate.isalpha():
        return fallback
    return candidate


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


def _get_setting_value(db: Session, key: str, default: str) -> str:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        return default
    return setting.value


def _fallback_login_url(raw_website: str) -> str:
    return _frontend_url(raw_website, path="/login")


def _main_phone(client: User) -> str | None:
    return client.mobile_phone_1 or client.phone


def _status_implies_active(client_status: ClientStatus) -> bool:
    return client_status in {ClientStatus.ACTIVE, ClientStatus.TRIAL}


def _client_status_sort_value(client_status: ClientStatus) -> int:
    order = {
        ClientStatus.ACTIVE: 0,
        ClientStatus.TRIAL: 1,
        ClientStatus.PENDING: 2,
        ClientStatus.INACTIVE: 3,
        ClientStatus.ARCHIVED: 4,
    }
    return order.get(client_status, 99)


def _safe_sort_text(value: str | None) -> str:
    return (value or "").strip().casefold()


def _display_name(first_name: str | None, last_name: str | None, email: str) -> str:
    full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return full_name or email


def _note_author_display_name(author: User | None) -> str:
    if author is None:
        return "Systeme"
    return _display_name(author.first_name, author.last_name, author.email)


def _client_note_out(note: ClientNoteEntry, *, author: User | None) -> AdminClientNoteOut:
    return AdminClientNoteOut(
        id=note.id,
        user_id=note.user_id,
        author_user_id=note.author_user_id,
        author_display_name=_note_author_display_name(author),
        entry_type=(note.entry_type or "AUTO").upper(),
        message=note.message,
        created_at=note.created_at,
    )


def _create_client_note(
    db: Session,
    *,
    client_id: UUID,
    message: str,
    entry_type: str = "AUTO",
    author_user_id: UUID | None = None,
) -> ClientNoteEntry:
    normalized = message.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Note message cannot be empty")

    note = ClientNoteEntry(
        user_id=client_id,
        author_user_id=author_user_id,
        entry_type=entry_type.strip().upper() or "AUTO",
        message=normalized,
    )
    db.add(note)
    return note


def _manual_transaction_allowed_student_ids(db: Session, *, client: User) -> set[UUID]:
    allowed = {client.id}
    if client.client_kind != ClientKind.ADULT:
        return allowed

    child_ids = db.scalars(
        select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == client.id)
    ).all()
    for child_id in child_ids:
        if child_id is not None:
            allowed.add(child_id)
    return allowed


def _manual_transaction_label(transaction_type: str, custom_label: str | None) -> str:
    normalized_type = (transaction_type or "").strip().upper()
    if custom_label:
        return custom_label
    return MANUAL_TRANSACTION_LABEL_BY_TYPE.get(normalized_type, "Transaction manuelle")


def _parse_product_categories(raw: str) -> list[str]:
    if not raw.strip():
        return []
    tokens = re.split(r"[\n,;]+", raw)
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized[:120])
    return out


def _configured_product_categories(db: Session) -> list[str]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == PRODUCT_CATEGORIES_SETTING_KEY))
    if setting is None:
        return []
    return _parse_product_categories(setting.value or "")


def _payment_source_label(source: str) -> str:
    normalized = (source or "").strip().upper()
    if normalized == "PLAN_PURCHASE":
        return "Achat formule"
    if normalized == "BOOKING":
        return "Reservation"
    if normalized == "MANUAL":
        return "Transaction manuelle"
    return normalized or "Paiement"


def _invoice_number_for_payment(payment_id: UUID, occurred_at: datetime) -> str:
    compact = str(payment_id).replace("-", "").upper()
    short = compact[:8] if compact else "XXXX0000"
    return f"FAC-{occurred_at.strftime('%Y%m%d')}-{short}"


def _invoice_status_from_payment_status(status_value: str) -> str:
    normalized = (status_value or "").strip().upper()
    if normalized == "REFUNDED":
        return "CANCELLED"
    if normalized == "NOT_BILLABLE":
        return "CANCELLED"
    if normalized in PAID_PAYMENT_STATUSES:
        return "PAID"
    if normalized in PENDING_PAYMENT_STATUSES:
        return "PENDING"
    if normalized in CANCELLED_PAYMENT_STATUSES:
        return "CANCELLED"
    return "PENDING"


def _payment_method_label(method_code: str | None) -> str:
    normalized = (method_code or "").strip().upper()
    labels = {
        "CARD_ONLINE": "CB en ligne (Mollie / Payplug)",
        "CARD_TERMINAL": "CB sur place (TPE)",
        "SEPA_DEBIT": "Prelevement SEPA",
        "BANK_TRANSFER": "Virement bancaire",
        "CHECK": "Cheque",
        "CASH": "Especes",
        "PAYPAL": "PayPal",
    }
    return labels.get(normalized, normalized or "Non defini")

def _payment_method_label_client(method_code: str | None) -> str:
    normalized = (method_code or "").strip().upper()
    labels = {
        "CARD_ONLINE": "CB en ligne",
        "CARD_TERMINAL": "CB sur place (TPE)",
        "SEPA_DEBIT": "Prelevement SEPA",
        "BANK_TRANSFER": "Virement bancaire",
        "CHECK": "Cheque",
        "CASH": "Especes",
        "PAYPAL": "PayPal",
    }
    return labels.get(normalized, normalized or "Non defini")


def _is_online_collection_method(method_code: str | None) -> bool:
    return (method_code or "").strip().upper() in ONLINE_COLLECTION_METHOD_CODES


def _fallback_dashboard_transactions_url(raw_website: str) -> str:
    return _frontend_url(raw_website, path="/dashboard?tab=transactions")


def _frontend_url(raw_website: str, *, path: str) -> str:
    candidate = raw_website.strip()
    if not candidate:
        candidate = (settings.frontend_base_url or "").strip()
    if not candidate:
        candidate = "http://localhost:3000"
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _checkout_urls(raw_website: str, *, client_id: UUID, subscription_id: UUID) -> tuple[str, str, str]:
    query = f"tab=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}"
    success_url = _frontend_url(raw_website, path=f"/dashboard?{query}&payment_return=success")
    cancel_url = _frontend_url(raw_website, path=f"/dashboard?{query}&payment_return=cancel")
    webhook_url = _frontend_url(raw_website, path=f"/api/v1/public/payments/webhook?client_id={client_id}&subscription_id={subscription_id}")
    return success_url, cancel_url, webhook_url


def _create_checkout_for_subscription(
    db: Session,
    *,
    client: User,
    subscription: ClientPlanSubscription,
    plan: Plan,
    method_code: str | None,
    amount_due: Decimal,
    currency_code: str,
    raw_website: str,
    force_pending: bool,
) -> str | None:
    normalized_method = (method_code or "").strip().upper()
    if not _is_online_collection_method(normalized_method):
        return None
    if amount_due <= Decimal("0.00"):
        return None

    success_url, cancel_url, webhook_url = _checkout_urls(raw_website, client_id=client.id, subscription_id=subscription.id)
    checkout = create_checkout_session(
        db,
        CheckoutCreateRequest(
            amount=amount_due.quantize(Decimal("0.01")),
            currency=(currency_code or "EUR").upper(),
            description=f"{plan.name} ({client.email})",
            customer_email=client.email,
            success_return_url=success_url,
            cancel_return_url=cancel_url,
            webhook_url=with_webhook_secret(webhook_url, settings.payment_webhook_secret),
            metadata={
                "client_id": str(client.id),
                "subscription_id": str(subscription.id),
                "plan_id": str(plan.id),
                "plan_code": plan.code,
            },
        ),
    )
    if not checkout.success or not checkout.checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Impossible de creer la session de paiement ({checkout.message})",
        )

    subscription.billing_method_code = normalized_method
    subscription.payment_provider_subscription_ref = checkout.provider_reference or subscription.payment_provider_subscription_ref
    subscription.last_payment_status = (checkout.status or "WAITING_PAYMENT").strip().upper() or "WAITING_PAYMENT"
    if force_pending and subscription.status != SubscriptionStatus.CANCELLED:
        subscription.status = SubscriptionStatus.PENDING
        subscription.auto_renew = False

    return checkout.checkout_url


def _send_admin_subscription_immediate_cancellation_email(
    db: Session,
    *,
    actor: User,
    client: User,
    plan: Plan,
    subscription: ClientPlanSubscription,
    requested_at: datetime,
    cancelled_at: datetime,
) -> str | None:
    admin_email = (
        _get_setting_value(db, "config_account_contact_email", actor.email).strip()
        or actor.email
        or settings.email_reply_to
        or settings.email_from
    )
    if not admin_email:
        return None

    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    actor_name = _display_name(actor.first_name, actor.last_name, actor.email)
    client_name = _display_name(client.first_name, client.last_name, client.email)

    subject = f"Resiliation immediate - {plan.name} - {client_name}"
    body = (
        "Une resiliation immediate de produit a ete executee depuis le BackOffice.\n\n"
        f"Client: {client_name} ({client.email})\n"
        f"Produit: {plan.name}\n"
        f"Reference contrat: {subscription.id}\n"
        f"Date de demande: {requested_at.isoformat()}\n"
        f"Date de resiliation effective: {cancelled_at.isoformat()}\n"
        f"Action realisee par: {actor_name}\n"
        f"ID administrateur: {actor.id}\n\n"
        + (
            "Le prelevement recurrent est desactive et aucun prochain prelevement ne sera lance."
            if plan.kind == PlanKind.SUBSCRIPTION
            else (
                "Le carnet est clos et les credits restants sont invalides."
                if plan.kind == PlanKind.PACK
                else "Le forfait est cloture et les cours futurs ne seront plus factures."
            )
        )
    )

    return send_email(
        to_email=admin_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="ADMIN_SUBSCRIPTION_IMMEDIATE_CANCELLATION",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )


def _is_failed_payment_status(status_value: str) -> bool:
    normalized = (status_value or "").strip().upper()
    if not normalized:
        return False
    if normalized in FAILED_PAYMENT_STATUSES:
        return True
    if normalized.startswith("HTTP_"):
        return True
    if normalized.startswith("FAILED"):
        return True
    if normalized.endswith("_ERROR"):
        return True
    return False


def _subscription_payment_status(subscription: ClientPlanSubscription) -> str:
    subscription_status = (subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)).strip().upper()
    if subscription_status in CANCELLED_PAYMENT_STATUSES:
        return "CANCELLED"
    if subscription_status == "PENDING":
        return "PENDING"

    last_payment_status = (subscription.last_payment_status or "").strip().upper()
    if last_payment_status:
        if last_payment_status in PAID_PAYMENT_STATUSES:
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


def _effective_pack_credits_for_plan(db: Session, *, plan: Plan) -> int:
    grant_counts = db.scalars(
        select(PlanCreditGrant.credits_count).where(PlanCreditGrant.plan_id == plan.id)
    ).all()
    normalized = [int(count) for count in grant_counts if int(count) > 0]
    if normalized:
        if plan.credit_grants_relation == PlanCreditGrantsRelation.OR:
            return max(normalized)
        return sum(normalized)
    return int(plan.credits_count or 0)


def _estimate_subscription_pricing(
    db: Session,
    *,
    plan: Plan,
    residence_country: str,
    preferred_currency: str,
    on_date: datetime,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str] | None:
    if plan.kind == PlanKind.FORFAIT:
        return None

    normalized_country = (residence_country or "FR").upper()
    normalized_currency = (preferred_currency or plan.currency_code or "EUR").upper()

    vat_rate = resolve_vat_rate(
        db,
        country=normalized_country,
        service_code=plan_service_code(plan.kind.value),
        on_date=on_date.date(),
    )

    price_excl_vat: Decimal | None = None
    currency_code = normalized_currency

    if plan.monthly_price_value is not None:
        raw_price = Decimal(plan.monthly_price_value)
        if plan.price_tax_mode == PlanPriceTaxMode.TTC:
            divisor = Decimal("1") + (vat_rate / Decimal("100"))
            price_excl_vat = raw_price if divisor <= 0 else (raw_price / divisor)
        else:
            price_excl_vat = raw_price
        currency_code = (plan.currency_code or normalized_currency).upper()
    elif plan.monthly_price_excl_vat is not None:
        price_excl_vat = Decimal(plan.monthly_price_excl_vat)
        currency_code = (plan.currency_code or normalized_currency).upper()
    else:
        resolved_price = resolve_plan_price(
            db,
            plan_id=plan.id,
            country=normalized_country,
            currency=normalized_currency,
            on_date=on_date.date(),
        )
        if resolved_price is not None:
            price_excl_vat = Decimal(resolved_price.price_excl_vat)
            currency_code = resolved_price.currency_code

    if price_excl_vat is None:
        return None

    estimated_price_excl_vat, estimated_vat_amount, estimated_total_incl_vat = compute_tax_totals(
        price_excl_vat=price_excl_vat,
        vat_rate=vat_rate,
    )
    return estimated_price_excl_vat, vat_rate, estimated_vat_amount, estimated_total_incl_vat, currency_code


def _client_out(
    client: User,
    *,
    next_session_start_at_utc: datetime | None = None,
    family_name: str | None = None,
    group_ids: list[UUID] | None = None,
    group_names: list[str] | None = None,
) -> AdminClientOut:
    return AdminClientOut(
        id=client.id,
        email=client.email,
        role=client.role,
        client_kind=client.client_kind,
        first_name=client.first_name,
        last_name=client.last_name,
        address_line=client.address_line,
        postal_code=client.postal_code,
        city=client.city,
        address_country=client.address_country,
        phone=_main_phone(client),
        mobile_phone_1=client.mobile_phone_1,
        mobile_phone_2=client.mobile_phone_2,
        home_phone=client.home_phone,
        birth_date=client.birth_date,
        important_info=client.important_info,
        private_note=client.private_note,
        residence_country=client.residence_country,
        preferred_currency=client.preferred_currency,
        timezone=client.timezone,
        first_course_at=client.first_course_at,
        portal_contact_visible=client.portal_contact_visible,
        email_opt_in=client.email_opt_in,
        sms_opt_in=client.sms_opt_in,
        lesson_reminder_email_opt_in=client.lesson_reminder_email_opt_in,
        lesson_reminder_sms_opt_in=client.lesson_reminder_sms_opt_in,
        client_status=client.client_status,
        family_name=family_name,
        group_ids=group_ids or [],
        group_names=group_names or [],
        is_active=client.is_active,
        next_session_start_at_utc=next_session_start_at_utc,
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


def _require_client(db: Session, client_id: UUID) -> User:
    client = db.scalar(select(User).where(User.id == client_id, User.role == UserRole.CLIENT))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _family_member_out(user: User) -> AdminFamilyMemberOut:
    return AdminFamilyMemberOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=_main_phone(user),
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


def _family_link_out(link: ClientFamilyLink, users_by_id: dict[UUID, User]) -> AdminClientFamilyLinkOut:
    adult = users_by_id.get(link.adult_user_id)
    child = users_by_id.get(link.child_user_id)
    if adult is None or child is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Family link integrity error")

    return AdminClientFamilyLinkOut(
        id=link.id,
        adult=_family_member_out(adult),
        child=_family_member_out(child),
        relationship_label=link.relationship_label,
        is_billing_recipient=link.is_billing_recipient,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _is_email_in_use(db: Session, *, email: str, exclude_user_id: UUID | None = None) -> bool:
    stmt = select(User.id).where(User.email == email)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.scalar(stmt.limit(1)) is not None


def _set_billing_recipient(db: Session, *, child_user_id: UUID, chosen_adult_user_id: UUID) -> None:
    links = db.scalars(
        select(ClientFamilyLink).where(ClientFamilyLink.child_user_id == child_user_id).with_for_update()
    ).all()
    target = next((link for link in links if link.adult_user_id == chosen_adult_user_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family link not found for billing recipient")

    now = _utcnow()
    db.execute(
        update(ClientFamilyLink)
        .where(ClientFamilyLink.child_user_id == child_user_id)
        .values(is_billing_recipient=False, updated_at=now)
    )
    db.flush()
    db.execute(
        update(ClientFamilyLink)
        .where(
            ClientFamilyLink.child_user_id == child_user_id,
            ClientFamilyLink.adult_user_id == chosen_adult_user_id,
        )
        .values(is_billing_recipient=True, updated_at=now)
    )


def _ensure_family_roles(adult: User, child: User) -> None:
    if adult.role != UserRole.CLIENT or child.role != UserRole.CLIENT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Family links require client accounts")
    if adult.client_kind != ClientKind.ADULT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Adult account must have kind ADULT")
    if child.client_kind != ClientKind.CHILD:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Child account must have kind CHILD")


def _family_payload(db: Session, client: User) -> AdminClientFamilyOut:
    links_as_adult = db.scalars(
        select(ClientFamilyLink).where(ClientFamilyLink.adult_user_id == client.id).order_by(ClientFamilyLink.created_at.desc())
    ).all()
    links_as_child = db.scalars(
        select(ClientFamilyLink).where(ClientFamilyLink.child_user_id == client.id).order_by(ClientFamilyLink.created_at.desc())
    ).all()

    users_needed: set[UUID] = {client.id}
    for link in links_as_adult:
        users_needed.add(link.adult_user_id)
        users_needed.add(link.child_user_id)
    for link in links_as_child:
        users_needed.add(link.adult_user_id)
        users_needed.add(link.child_user_id)

    users = db.scalars(select(User).where(User.id.in_(users_needed))).all() if users_needed else []
    users_by_id = {user.id: user for user in users}

    billing_recipient_adult_id: UUID | None = None
    if client.client_kind == ClientKind.CHILD:
        for link in links_as_child:
            if link.is_billing_recipient:
                billing_recipient_adult_id = link.adult_user_id
                break
    else:
        child_ids = {link.child_user_id for link in links_as_adult}
        if child_ids:
            billed_link = db.scalar(
                select(ClientFamilyLink)
                .where(
                    ClientFamilyLink.adult_user_id == client.id,
                    ClientFamilyLink.child_user_id.in_(child_ids),
                    ClientFamilyLink.is_billing_recipient.is_(True),
                )
                .order_by(ClientFamilyLink.created_at.asc())
            )
            if billed_link is not None:
                billing_recipient_adult_id = billed_link.adult_user_id

    return AdminClientFamilyOut(
        client_id=client.id,
        client_kind=client.client_kind,
        links_as_adult=[_family_link_out(link, users_by_id) for link in links_as_adult],
        links_as_child=[_family_link_out(link, users_by_id) for link in links_as_child],
        billing_recipient_adult_id=billing_recipient_adult_id,
    )


def _group_out(group: ClientGroup, members_count: int = 0) -> AdminClientGroupOut:
    return AdminClientGroupOut(
        id=group.id,
        code=group.code,
        name=group.name,
        active=group.active,
        members_count=members_count,
    )


def _normalize_group_code(name: str) -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in name.upper()).strip("_")
    while "__" in base:
        base = base.replace("__", "_")
    return base[:80] or "GROUP"


def _groups_for_client_ids(db: Session, client_ids: list[UUID]) -> dict[UUID, list[tuple[UUID, str]]]:
    if not client_ids:
        return {}
    rows = db.execute(
        select(ClientGroupMembership.user_id, ClientGroup.id, ClientGroup.name)
        .join(ClientGroup, ClientGroup.id == ClientGroupMembership.group_id)
        .where(
            ClientGroupMembership.user_id.in_(client_ids),
            ClientGroup.active.is_(True),
        )
        .order_by(ClientGroup.name.asc())
    ).all()
    groups_by_client: dict[UUID, list[tuple[UUID, str]]] = {}
    for user_id, current_group_id, group_name in rows:
        groups_by_client.setdefault(user_id, []).append((current_group_id, group_name))
    return groups_by_client


def _format_session_datetime(session_obj: CourseSession, timezone_preference: str | None, location: Location) -> str:
    tz_name = timezone_preference or location.timezone or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        fallback_name = location.timezone or "UTC"
        try:
            tz = ZoneInfo(fallback_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")
            fallback_name = "UTC"
        tz_name = fallback_name

    local_dt = session_obj.start_at_utc.astimezone(tz)
    return f"{local_dt.strftime('%Y-%m-%d %H:%M')} ({tz_name})"


def _filtered_clients_stmt(
    *,
    search: str | None,
    client_status: ClientStatus | None,
    group_id: UUID | None,
    include_archived: bool,
    active_only: bool,
):
    stmt = select(User).where(User.role == UserRole.CLIENT)

    if active_only:
        stmt = stmt.where(User.client_status == ClientStatus.ACTIVE)

    if not include_archived and client_status is None:
        stmt = stmt.where(User.client_status != ClientStatus.ARCHIVED)

    if client_status is not None:
        stmt = stmt.where(User.client_status == client_status)

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
        )

    if group_id is not None:
        stmt = stmt.join(ClientGroupMembership, ClientGroupMembership.user_id == User.id).where(
            ClientGroupMembership.group_id == group_id
        )

    return stmt


@router.get("", response_model=list[AdminClientOut])
def list_admin_clients(
    search: str | None = Query(default=None, min_length=1, max_length=255),
    client_status: ClientStatus | None = None,
    group_id: UUID | None = None,
    include_archived: bool = False,
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    active_only: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientOut]:
    stmt = _filtered_clients_stmt(
        search=search,
        client_status=client_status,
        group_id=group_id,
        include_archived=include_archived,
        active_only=active_only,
    )

    clients = db.scalars(stmt.order_by(User.created_at.desc()).limit(limit)).all()
    if not clients:
        return []

    now = _utcnow()
    client_ids = [client.id for client in clients]
    rows = db.execute(
        select(Booking.user_id, CourseSession.start_at_utc)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id.in_(client_ids),
            Booking.status.in_([BookingStatus.BOOKED, BookingStatus.WAITLISTED]),
            CourseSession.start_at_utc >= now,
        )
        .order_by(Booking.user_id.asc(), CourseSession.start_at_utc.asc())
    ).all()

    next_session_by_client: dict[UUID, datetime] = {}
    for user_id, start_at_utc in rows:
        if user_id not in next_session_by_client:
            next_session_by_client[user_id] = start_at_utc

    groups_by_client = _groups_for_client_ids(db, client_ids)

    child_ids = [client.id for client in clients if client.client_kind == ClientKind.CHILD]
    family_name_by_client: dict[UUID, str] = {}
    if child_ids:
        family_rows = db.execute(
            select(
                ClientFamilyLink.child_user_id,
                ClientFamilyLink.is_billing_recipient,
                User.first_name,
                User.last_name,
                User.email,
            )
            .join(User, User.id == ClientFamilyLink.adult_user_id)
            .where(ClientFamilyLink.child_user_id.in_(child_ids))
            .order_by(ClientFamilyLink.child_user_id.asc(), ClientFamilyLink.created_at.asc())
        ).all()

        for child_user_id, is_billing_recipient, first_name, last_name, email in family_rows:
            candidate = _display_name(first_name, last_name, email)
            existing = family_name_by_client.get(child_user_id)
            if existing is None or is_billing_recipient:
                family_name_by_client[child_user_id] = candidate

    items: list[AdminClientOut] = []
    for client in clients:
        if client.client_kind == ClientKind.CHILD:
            family_name = family_name_by_client.get(client.id) or (client.last_name or None)
        else:
            family_name = client.last_name or None
        group_pairs = groups_by_client.get(client.id, [])
        items.append(
            _client_out(
                client,
                next_session_start_at_utc=next_session_by_client.get(client.id),
                family_name=family_name,
                group_ids=[group_item[0] for group_item in group_pairs],
                group_names=[group_item[1] for group_item in group_pairs],
            )
        )

    normalized_sort_by = (sort_by or "").strip().lower()
    descending = (sort_dir or "").strip().lower() != "asc"

    def sort_key(item: AdminClientOut) -> tuple:
        next_sort = item.next_session_start_at_utc or datetime.max.replace(tzinfo=timezone.utc)
        mapping: dict[str, tuple] = {
            "last_name": (_safe_sort_text(item.last_name), _safe_sort_text(item.first_name), item.email.casefold()),
            "first_name": (_safe_sort_text(item.first_name), _safe_sort_text(item.last_name), item.email.casefold()),
            "family_name": (_safe_sort_text(item.family_name), _safe_sort_text(item.last_name), item.email.casefold()),
            "client_status": (
                _client_status_sort_value(item.client_status),
                _safe_sort_text(item.last_name),
                _safe_sort_text(item.first_name),
            ),
            "client_kind": (_safe_sort_text(item.client_kind.value), _safe_sort_text(item.last_name), item.email.casefold()),
            "next_session": (next_sort, _safe_sort_text(item.last_name), item.email.casefold()),
            "created_at": (item.created_at, _safe_sort_text(item.last_name), item.email.casefold()),
        }
        return mapping.get(normalized_sort_by, mapping["created_at"])

    items.sort(key=sort_key, reverse=descending)
    return items


@router.get("/password-email-template", response_model=AdminClientPasswordEmailTemplateOut)
def get_admin_client_password_email_template(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientPasswordEmailTemplateOut:
    try:
        template = resolve_predefined_template(db, code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AdminClientPasswordEmailTemplateOut(
        subject=str(template.get("subject") or ""),
        body=str(template.get("body") or ""),
        updated_at=template.get("updated_at") if isinstance(template.get("updated_at"), datetime) else None,
    )


@router.put("/password-email-template", response_model=AdminClientPasswordEmailTemplateOut)
def update_admin_client_password_email_template(
    payload: AdminClientPasswordEmailTemplateUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientPasswordEmailTemplateOut:
    subject = _normalize_required(payload.subject, "subject")
    body = _normalize_required(payload.body, "body")
    try:
        template = upsert_predefined_template(
            db,
            code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD,
            subject=subject,
            body=body,
            active=True,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return AdminClientPasswordEmailTemplateOut(
        subject=str(template.get("subject") or ""),
        body=str(template.get("body") or ""),
        updated_at=template.get("updated_at") if isinstance(template.get("updated_at"), datetime) else None,
    )


@router.get("/groups", response_model=list[AdminClientGroupOut])
def list_admin_client_groups(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientGroupOut]:
    stmt = (
        select(ClientGroup, func.count(ClientGroupMembership.id))
        .outerjoin(ClientGroupMembership, ClientGroupMembership.group_id == ClientGroup.id)
        .group_by(ClientGroup.id)
        .order_by(ClientGroup.name.asc())
    )
    if not include_inactive:
        stmt = stmt.where(ClientGroup.active.is_(True))

    rows = db.execute(stmt).all()
    return [_group_out(group, members_count=int(members_count or 0)) for group, members_count in rows]


@router.post("/groups", response_model=AdminClientGroupOut, status_code=status.HTTP_201_CREATED)
def create_admin_client_group(
    payload: AdminClientGroupCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientGroupOut:
    name = _normalize_required(payload.name, "name")
    code = _normalize_optional(payload.code)
    normalized_code = (code or _normalize_group_code(name)).upper()

    existing = db.scalar(
        select(ClientGroup.id).where(or_(ClientGroup.code == normalized_code, func.lower(ClientGroup.name) == name.lower()))
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client group already exists")

    now = _utcnow()
    group = ClientGroup(
        code=normalized_code,
        name=name,
        active=payload.active,
        updated_at=now,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _group_out(group, members_count=0)


@router.patch("/groups/{group_id}", response_model=AdminClientGroupOut)
def patch_admin_client_group(
    group_id: UUID,
    payload: AdminClientGroupUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientGroupOut:
    group = db.scalar(select(ClientGroup).where(ClientGroup.id == group_id).with_for_update())
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client group not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        members_count = db.scalar(
            select(func.count(ClientGroupMembership.id)).where(ClientGroupMembership.group_id == group.id)
        )
        return _group_out(group, members_count=int(members_count or 0))

    if "name" in changes and changes["name"] is not None:
        target_name = _normalize_required(changes["name"], "name")
        duplicate_name = db.scalar(
            select(ClientGroup.id).where(func.lower(ClientGroup.name) == target_name.lower(), ClientGroup.id != group.id)
        )
        if duplicate_name is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client group name already exists")
        group.name = target_name

    if "code" in changes and changes["code"] is not None:
        target_code = _normalize_required(changes["code"], "code").upper()
        duplicate_code = db.scalar(select(ClientGroup.id).where(ClientGroup.code == target_code, ClientGroup.id != group.id))
        if duplicate_code is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client group code already exists")
        group.code = target_code

    if "active" in changes and changes["active"] is not None:
        group.active = bool(changes["active"])

    group.updated_at = _utcnow()
    db.add(group)
    db.commit()
    db.refresh(group)

    members_count = db.scalar(select(func.count(ClientGroupMembership.id)).where(ClientGroupMembership.group_id == group.id))
    return _group_out(group, members_count=int(members_count or 0))


@router.post("/bulk", response_model=AdminClientBulkOut)
def bulk_admin_clients(
    payload: AdminClientBulkRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientBulkOut:
    unique_ids: list[UUID] = []
    if payload.selection_scope == AdminClientSelectionScope.FILTERED:
        filtered_stmt = _filtered_clients_stmt(
            search=payload.filter_search,
            client_status=payload.filter_status,
            group_id=payload.filter_group_id,
            include_archived=payload.filter_include_archived,
            active_only=payload.filter_active_only,
        ).with_only_columns(User.id)

        seen_ids: set[UUID] = set()
        for client_id in db.scalars(filtered_stmt).all():
            if client_id in seen_ids:
                continue
            seen_ids.add(client_id)
            unique_ids.append(client_id)
    else:
        seen_ids = set()
        for client_id in payload.client_ids:
            if client_id in seen_ids:
                continue
            seen_ids.add(client_id)
            unique_ids.append(client_id)

    if not unique_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No client selected",
        )

    clients = db.scalars(
        select(User)
        .where(
            User.id.in_(unique_ids),
            User.role == UserRole.CLIENT,
        )
        .with_for_update()
    ).all()
    clients_by_id = {client.id: client for client in clients}

    missing_ids = [str(client_id) for client_id in unique_ids if client_id not in clients_by_id]
    if missing_ids and payload.selection_scope != AdminClientSelectionScope.FILTERED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client(s) not found: {', '.join(missing_ids)}",
        )

    now = _utcnow()
    action = payload.action

    if action == AdminClientBulkAction.UPDATE_STATUS:
        if payload.target_status is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_status is required")

        for client in clients:
            client.client_status = payload.target_status
            client.is_active = _status_implies_active(payload.target_status)
            client.updated_at = now
            db.add(client)

        db.commit()
        return AdminClientBulkOut(
            processed_count=len(clients),
            skipped_count=0,
            message=f"Statut mis a jour: {payload.target_status.value}",
        )

    if action == AdminClientBulkAction.ASSIGN_GROUP:
        if payload.group_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="group_id is required")
        group = db.scalar(select(ClientGroup).where(ClientGroup.id == payload.group_id).with_for_update())
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client group not found")
        if not group.active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client group is inactive")

        existing_rows = db.execute(
            select(ClientGroupMembership.user_id)
            .where(
                ClientGroupMembership.user_id.in_(unique_ids),
                ClientGroupMembership.group_id == group.id,
            )
        ).all()
        existing_user_ids = {row[0] for row in existing_rows}

        created_count = 0
        for client in clients:
            if client.id in existing_user_ids:
                continue
            db.add(ClientGroupMembership(user_id=client.id, group_id=group.id))
            client.updated_at = now
            db.add(client)
            created_count += 1

        db.commit()
        return AdminClientBulkOut(
            processed_count=created_count,
            skipped_count=len(clients) - created_count,
            message=f"Groupe affecte: {group.name}",
        )

    if action == AdminClientBulkAction.ARCHIVE:
        for client in clients:
            client.client_status = ClientStatus.ARCHIVED
            client.is_active = False
            client.updated_at = now
            db.add(client)
        db.commit()
        return AdminClientBulkOut(processed_count=len(clients), skipped_count=0, message="Clients archives")

    if action == AdminClientBulkAction.DELETE:
        for client in clients:
            db.delete(client)
        db.commit()
        return AdminClientBulkOut(processed_count=len(clients), skipped_count=0, message="Clients supprimes")

    if action == AdminClientBulkAction.EMAIL_CLIENTS:
        recipients = sorted({client.email for client in clients if client.email and client.email_opt_in})
        db.commit()
        return AdminClientBulkOut(
            processed_count=len(recipients),
            skipped_count=max(len(clients) - len(recipients), 0),
            message=f"Email prepare pour {len(recipients)} client(s) opt-in",
        )

    if action == AdminClientBulkAction.EMAIL_PARENTS:
        child_ids = [client.id for client in clients if client.client_kind == ClientKind.CHILD]
        parent_rows = db.execute(
            select(ClientFamilyLink.child_user_id, User.email, User.email_opt_in)
            .join(User, User.id == ClientFamilyLink.adult_user_id)
            .where(ClientFamilyLink.child_user_id.in_(child_ids))
            .order_by(ClientFamilyLink.created_at.asc())
        ).all() if child_ids else []

        parent_by_child: dict[UUID, set[str]] = {}
        for child_id, email, email_opt_in in parent_rows:
            if not email_opt_in:
                continue
            parent_by_child.setdefault(child_id, set()).add(email)

        recipients: set[str] = set()
        for client in clients:
            if client.client_kind == ClientKind.ADULT:
                if client.email_opt_in:
                    recipients.add(client.email)
            else:
                recipients.update(parent_by_child.get(client.id, set()))

        db.commit()
        return AdminClientBulkOut(
            processed_count=len(recipients),
            skipped_count=max(len(clients) - len(recipients), 0),
            message=f"Email parents prepare pour {len(recipients)} destinataire(s) opt-in",
        )

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported bulk action")


@router.get("/export")
def export_admin_clients_csv(
    client_ids: list[UUID] = Query(default=[]),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> StreamingResponse:
    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for client_id in client_ids:
        if client_id in seen:
            continue
        seen.add(client_id)
        unique_ids.append(client_id)

    if not unique_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No client selected for export")

    clients = db.scalars(
        select(User)
        .where(
            User.id.in_(unique_ids),
            User.role == UserRole.CLIENT,
        )
        .order_by(User.last_name.asc(), User.first_name.asc(), User.email.asc())
    ).all()
    if not clients:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No client found for export")

    memberships = db.execute(
        select(ClientGroupMembership.user_id, ClientGroup.name)
        .join(ClientGroup, ClientGroup.id == ClientGroupMembership.group_id)
        .where(
            ClientGroupMembership.user_id.in_([client.id for client in clients]),
            ClientGroup.active.is_(True),
        )
        .order_by(ClientGroup.name.asc())
    ).all()
    groups_by_client: dict[UUID, list[str]] = {}
    for user_id, group_name in memberships:
        groups_by_client.setdefault(user_id, []).append(group_name)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "id",
            "email",
            "nom",
            "prenom",
            "statut",
            "type",
            "mobile_1",
            "mobile_2",
            "telephone_domicile",
            "adresse",
            "code_postal",
            "ville",
            "pays_adresse",
            "pays_residence",
            "devise",
            "fuseau_horaire",
            "date_naissance",
            "informations",
            "note_privee",
            "premier_cours",
            "visible_contacts_portail",
            "optin_email",
            "optin_sms",
            "optin_rappel_email",
            "optin_rappel_sms",
            "groupes",
            "created_at",
            "updated_at",
        ]
    )

    for client in clients:
        writer.writerow(
            [
                str(client.id),
                client.email,
                client.last_name or "",
                client.first_name or "",
                client.client_status.value,
                client.client_kind.value,
                client.mobile_phone_1 or "",
                client.mobile_phone_2 or "",
                client.home_phone or "",
                client.address_line or "",
                client.postal_code or "",
                client.city or "",
                client.address_country,
                client.residence_country,
                client.preferred_currency,
                client.timezone,
                client.birth_date.isoformat() if client.birth_date else "",
                client.important_info or "",
                client.private_note or "",
                client.first_course_at.isoformat() if client.first_course_at else "",
                "1" if client.portal_contact_visible else "0",
                "1" if client.email_opt_in else "0",
                "1" if client.sms_opt_in else "0",
                "1" if client.lesson_reminder_email_opt_in else "0",
                "1" if client.lesson_reminder_sms_opt_in else "0",
                " | ".join(groups_by_client.get(client.id, [])),
                client.created_at.isoformat(),
                client.updated_at.isoformat(),
            ]
        )

    output.seek(0)
    timestamp = _utcnow().strftime("%Y%m%d_%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="clients_export_{timestamp}.csv"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/{client_id}", response_model=AdminClientOut)
def get_admin_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientOut:
    client = _require_client(db, client_id)
    groups_by_client = _groups_for_client_ids(db, [client.id])
    group_pairs = groups_by_client.get(client.id, [])

    family_name = client.last_name or None
    if client.client_kind == ClientKind.CHILD:
        family_rows = db.execute(
            select(
                ClientFamilyLink.is_billing_recipient,
                User.first_name,
                User.last_name,
                User.email,
            )
            .join(User, User.id == ClientFamilyLink.adult_user_id)
            .where(ClientFamilyLink.child_user_id == client.id)
            .order_by(ClientFamilyLink.created_at.asc())
        ).all()
        for is_billing_recipient, first_name, last_name, email in family_rows:
            candidate = _display_name(first_name, last_name, email)
            if family_name is None or is_billing_recipient:
                family_name = candidate

    return _client_out(
        client,
        family_name=family_name,
        group_ids=[group_item[0] for group_item in group_pairs],
        group_names=[group_item[1] for group_item in group_pairs],
    )


@router.put("/{client_id}/groups", response_model=AdminClientOut)
def replace_admin_client_groups(
    client_id: UUID,
    payload: AdminClientGroupsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientOut:
    client = _require_client(db, client_id)
    now = _utcnow()

    target_ids: list[UUID] = []
    seen: set[UUID] = set()
    for group_id in payload.group_ids:
        if group_id in seen:
            continue
        seen.add(group_id)
        target_ids.append(group_id)

    if target_ids:
        active_groups = db.scalars(
            select(ClientGroup)
            .where(
                ClientGroup.id.in_(target_ids),
                ClientGroup.active.is_(True),
            )
            .with_for_update()
        ).all()
        active_group_ids = {group.id for group in active_groups}
        missing = [str(group_id) for group_id in target_ids if group_id not in active_group_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client group(s) not found or inactive: {', '.join(missing)}",
            )

    if target_ids:
        db.execute(
            delete(ClientGroupMembership).where(
                ClientGroupMembership.user_id == client.id,
                ~ClientGroupMembership.group_id.in_(target_ids),
            )
        )
    else:
        db.execute(delete(ClientGroupMembership).where(ClientGroupMembership.user_id == client.id))

    existing_ids = set(
        db.scalars(
            select(ClientGroupMembership.group_id).where(ClientGroupMembership.user_id == client.id)
        ).all()
    )
    for group_id in target_ids:
        if group_id in existing_ids:
            continue
        db.add(ClientGroupMembership(user_id=client.id, group_id=group_id))

    client.updated_at = now
    db.add(client)
    db.commit()
    db.refresh(client)

    group_pairs = _groups_for_client_ids(db, [client.id]).get(client.id, [])
    return _client_out(
        client,
        family_name=client.last_name or None,
        group_ids=[group_item[0] for group_item in group_pairs],
        group_names=[group_item[1] for group_item in group_pairs],
    )


@router.post("", response_model=AdminClientOut, status_code=status.HTTP_201_CREATED)
def create_admin_client(
    payload: AdminClientCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientOut:
    normalized_email = _normalize_optional(payload.email)
    if normalized_email:
        email = normalized_email.lower()
    else:
        synthetic_prefix = "adult" if payload.client_kind == ClientKind.ADULT else "child"
        email = f"{synthetic_prefix}-{uuid4().hex}@no-email.local"
    if _is_email_in_use(db, email=email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    first_name = _normalize_required(payload.first_name, "first_name")
    last_name = _normalize_required(payload.last_name, "last_name")
    address_line = _normalize_optional(payload.address_line)
    city = _normalize_optional(payload.city)
    mobile_phone_1 = _normalize_optional(payload.mobile_phone_1)
    legacy_phone = _normalize_optional(payload.phone)
    primary_phone = mobile_phone_1 or legacy_phone
    client_status = payload.client_status or (ClientStatus.ACTIVE if payload.is_active else ClientStatus.INACTIVE)

    now = _utcnow()
    client = User(
        email=email,
        hashed_password=hash_password(generate_temporary_password()),
        role=UserRole.CLIENT,
        client_kind=payload.client_kind,
        first_name=first_name,
        last_name=last_name,
        address_line=address_line,
        postal_code=_normalize_optional(payload.postal_code),
        city=city,
        address_country=_normalize_required(payload.address_country, "address_country").upper(),
        phone=primary_phone,
        mobile_phone_1=primary_phone,
        mobile_phone_2=_normalize_optional(payload.mobile_phone_2),
        home_phone=_normalize_optional(payload.home_phone),
        birth_date=payload.birth_date,
        important_info=_normalize_optional(payload.important_info),
        private_note=_normalize_optional(payload.private_note),
        residence_country=_normalize_required(payload.residence_country, "residence_country").upper(),
        preferred_currency=_normalize_required(payload.preferred_currency, "preferred_currency").upper(),
        timezone=_validate_timezone(payload.timezone),
        portal_contact_visible=bool(payload.portal_contact_visible),
        email_opt_in=bool(payload.email_opt_in),
        sms_opt_in=bool(payload.sms_opt_in),
        lesson_reminder_email_opt_in=bool(payload.lesson_reminder_email_opt_in),
        lesson_reminder_sms_opt_in=bool(payload.lesson_reminder_sms_opt_in),
        client_status=client_status,
        is_active=_status_implies_active(client_status),
        updated_at=now,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _client_out(client)


@router.patch("/{client_id}", response_model=AdminClientOut)
def patch_admin_client(
    client_id: UUID,
    payload: AdminClientUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientOut:
    client = db.scalar(select(User).where(User.id == client_id, User.role == UserRole.CLIENT).with_for_update())
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _client_out(client)

    if "email" in changes:
        normalized_new_email = _normalize_optional(changes["email"])
        if normalized_new_email:
            new_email = normalized_new_email.lower()
            existing = db.scalar(select(User).where(User.email == new_email, User.id != client.id))
            if existing is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
            client.email = new_email
        else:
            target_kind_for_email = changes.get("client_kind") or client.client_kind
            synthetic_prefix = "adult" if target_kind_for_email == ClientKind.ADULT else "child"
            generated_email = f"{synthetic_prefix}-{uuid4().hex}@no-email.local"
            while _is_email_in_use(db, email=generated_email):
                generated_email = f"{synthetic_prefix}-{uuid4().hex}@no-email.local"
            client.email = generated_email

    if "client_kind" in changes and changes["client_kind"] is not None:
        target_kind = changes["client_kind"]
        if target_kind != client.client_kind:
            has_family_links = db.scalar(
                select(ClientFamilyLink.id)
                .where(
                    or_(
                        ClientFamilyLink.adult_user_id == client.id,
                        ClientFamilyLink.child_user_id == client.id,
                    )
                )
                .limit(1)
            )
            if has_family_links is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Client kind cannot be changed while family links exist",
                )
            client.client_kind = target_kind

    if "first_name" in changes:
        client.first_name = _normalize_required(changes["first_name"], "first_name")

    if "last_name" in changes:
        client.last_name = _normalize_required(changes["last_name"], "last_name")

    if "address_line" in changes:
        client.address_line = _normalize_optional(changes["address_line"])

    if "postal_code" in changes:
        client.postal_code = _normalize_optional(changes["postal_code"])

    if "city" in changes:
        client.city = _normalize_optional(changes["city"])

    if "address_country" in changes:
        client.address_country = _normalize_required(changes["address_country"], "address_country").upper()

    if "phone" in changes:
        normalized_phone = _normalize_optional(changes["phone"])
        client.phone = normalized_phone
        if "mobile_phone_1" not in changes:
            client.mobile_phone_1 = normalized_phone

    if "mobile_phone_1" in changes:
        client.mobile_phone_1 = _normalize_optional(changes["mobile_phone_1"])
        client.phone = client.mobile_phone_1

    if "mobile_phone_2" in changes:
        client.mobile_phone_2 = _normalize_optional(changes["mobile_phone_2"])

    if "home_phone" in changes:
        client.home_phone = _normalize_optional(changes["home_phone"])

    if "birth_date" in changes:
        client.birth_date = changes["birth_date"]

    if "important_info" in changes:
        client.important_info = _normalize_optional(changes["important_info"])

    if "private_note" in changes:
        client.private_note = _normalize_optional(changes["private_note"])

    if "residence_country" in changes:
        client.residence_country = _normalize_required(changes["residence_country"], "residence_country").upper()

    if "preferred_currency" in changes:
        client.preferred_currency = _normalize_required(changes["preferred_currency"], "preferred_currency").upper()

    if "timezone" in changes:
        client.timezone = _validate_timezone(changes["timezone"])

    if "portal_contact_visible" in changes and changes["portal_contact_visible"] is not None:
        client.portal_contact_visible = bool(changes["portal_contact_visible"])

    if "email_opt_in" in changes and changes["email_opt_in"] is not None:
        client.email_opt_in = bool(changes["email_opt_in"])

    if "sms_opt_in" in changes and changes["sms_opt_in"] is not None:
        client.sms_opt_in = bool(changes["sms_opt_in"])

    if "lesson_reminder_email_opt_in" in changes and changes["lesson_reminder_email_opt_in"] is not None:
        client.lesson_reminder_email_opt_in = bool(changes["lesson_reminder_email_opt_in"])

    if "lesson_reminder_sms_opt_in" in changes and changes["lesson_reminder_sms_opt_in"] is not None:
        client.lesson_reminder_sms_opt_in = bool(changes["lesson_reminder_sms_opt_in"])

    if "client_status" in changes and changes["client_status"] is not None:
        client.client_status = changes["client_status"]
        client.is_active = _status_implies_active(client.client_status)
    elif "is_active" in changes:
        desired_active = bool(changes["is_active"])
        client.is_active = desired_active
        if desired_active and client.client_status in {ClientStatus.INACTIVE, ClientStatus.PENDING, ClientStatus.ARCHIVED}:
            client.client_status = ClientStatus.ACTIVE
        if not desired_active and client.client_status in {ClientStatus.ACTIVE, ClientStatus.TRIAL, ClientStatus.PENDING}:
            client.client_status = ClientStatus.INACTIVE

    client.updated_at = _utcnow()
    db.add(client)
    db.commit()
    db.refresh(client)

    group_pairs = _groups_for_client_ids(db, [client.id]).get(client.id, [])
    return _client_out(
        client,
        family_name=client.last_name or None,
        group_ids=[group_item[0] for group_item in group_pairs],
        group_names=[group_item[1] for group_item in group_pairs],
    )


@router.post("/{client_id}/send-password-email", response_model=AdminClientPasswordResetOut)
def send_admin_client_password_email(
    client_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientPasswordResetOut:
    client = db.scalar(select(User).where(User.id == client_id, User.role == UserRole.CLIENT).with_for_update())
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    temporary_password = generate_temporary_password()
    try:
        template = resolve_predefined_template(db, code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    subject_template = str(template.get("subject") or "")
    body_template = str(template.get("body") or "")
    if not subject_template or not body_template:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Client password email template is incomplete",
        )
    website = _get_setting_value(db, "config_account_website", "")
    login_url = _fallback_login_url(website)
    subject, body = render_client_password_email(
        subject_template=subject_template,
        body_template=body_template,
        first_name=(client.first_name or "").strip(),
        last_name=(client.last_name or "").strip(),
        email=client.email,
        temporary_password=temporary_password,
        login_url=login_url,
    )
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    message_id = send_client_password_email(
        to_email=client.email,
        subject=subject,
        body=body,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )

    now = _utcnow()
    _create_client_note(
        db,
        client_id=client.id,
        author_user_id=actor.id,
        entry_type="EMAIL",
        message=f"Email d'activation envoye a {client.email} (message id: {message_id}).",
    )
    client.hashed_password = hash_password(temporary_password)
    client.client_status = ClientStatus.ACTIVE
    client.is_active = True
    client.updated_at = now
    db.add(client)
    db.commit()

    return AdminClientPasswordResetOut(
        client_id=client.id,
        email=client.email,
        message_id=message_id,
        sent_at=now,
    )


@router.get("/{client_id}/family", response_model=AdminClientFamilyOut)
def get_admin_client_family(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientFamilyOut:
    client = _require_client(db, client_id)
    return _family_payload(db, client)


@router.post("/family/links", response_model=AdminClientFamilyLinkOut, status_code=status.HTTP_201_CREATED)
def create_admin_client_family_link(
    payload: AdminClientFamilyLinkCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientFamilyLinkOut:
    adult = _require_client(db, payload.adult_client_id)
    child = _require_client(db, payload.child_client_id)
    _ensure_family_roles(adult, child)

    existing = db.scalar(
        select(ClientFamilyLink)
        .where(
            ClientFamilyLink.adult_user_id == adult.id,
            ClientFamilyLink.child_user_id == child.id,
        )
        .with_for_update()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Family link already exists")

    now = _utcnow()
    link = ClientFamilyLink(
        adult_user_id=adult.id,
        child_user_id=child.id,
        relationship_label=_normalize_optional(payload.relationship_label),
        is_billing_recipient=False,
        updated_at=now,
    )
    db.add(link)
    db.flush()

    has_existing_billing = db.scalar(
        select(ClientFamilyLink.id)
        .where(
            ClientFamilyLink.child_user_id == child.id,
            ClientFamilyLink.is_billing_recipient.is_(True),
        )
        .limit(1)
        .with_for_update()
    )
    if payload.is_billing_recipient or has_existing_billing is None:
        _set_billing_recipient(db, child_user_id=child.id, chosen_adult_user_id=adult.id)

    db.commit()
    db.refresh(link)

    users_by_id = {adult.id: adult, child.id: child}
    return _family_link_out(link, users_by_id)


@router.patch("/family/links/{link_id}", response_model=AdminClientFamilyLinkOut)
def patch_admin_client_family_link(
    link_id: UUID,
    payload: AdminClientFamilyLinkUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientFamilyLinkOut:
    link = db.scalar(select(ClientFamilyLink).where(ClientFamilyLink.id == link_id).with_for_update())
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family link not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        users = db.scalars(select(User).where(User.id.in_([link.adult_user_id, link.child_user_id]))).all()
        return _family_link_out(link, {user.id: user for user in users})

    if "relationship_label" in changes:
        link.relationship_label = _normalize_optional(changes["relationship_label"])

    if "is_billing_recipient" in changes:
        target = changes["is_billing_recipient"]
        if target is True:
            _set_billing_recipient(db, child_user_id=link.child_user_id, chosen_adult_user_id=link.adult_user_id)
        elif target is False:
            link.is_billing_recipient = False

    link.updated_at = _utcnow()
    db.add(link)
    db.commit()
    db.refresh(link)

    users = db.scalars(select(User).where(User.id.in_([link.adult_user_id, link.child_user_id]))).all()
    return _family_link_out(link, {user.id: user for user in users})


@router.delete("/family/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_client_family_link(
    link_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    link = db.scalar(select(ClientFamilyLink).where(ClientFamilyLink.id == link_id).with_for_update())
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family link not found")

    siblings = db.scalars(
        select(ClientFamilyLink)
        .where(
            ClientFamilyLink.child_user_id == link.child_user_id,
            ClientFamilyLink.id != link.id,
        )
        .order_by(ClientFamilyLink.created_at.asc())
        .with_for_update()
    ).all()

    if link.is_billing_recipient and siblings:
        replacement = siblings[0]
        replacement.is_billing_recipient = True
        replacement.updated_at = _utcnow()
        db.add(replacement)

    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{client_id}/subscriptions", response_model=list[AdminClientSubscriptionOut])
def list_admin_client_subscriptions(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientSubscriptionOut]:
    client = _require_client(db, client_id)
    billing_profile = resolve_billing_profile(db, client)

    rows = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(ClientPlanSubscription.user_id == client_id)
        .order_by(ClientPlanSubscription.created_at.desc())
    ).all()

    now = _utcnow()
    has_state_changes = False
    items: list[AdminClientSubscriptionOut] = []
    for sub, plan in rows:
        if reconcile_subscription_status(sub, now=now, plan_kind=plan.kind):
            has_state_changes = True

        estimated_price_excl_vat: Decimal | None = None
        estimated_vat_rate: Decimal | None = None
        estimated_vat_amount: Decimal | None = None
        estimated_total_incl_vat: Decimal | None = None
        estimated_currency: str | None = None

        pricing = _estimate_subscription_pricing(
            db,
            plan=plan,
            residence_country=billing_profile.residence_country or "FR",
            preferred_currency=billing_profile.preferred_currency or "EUR",
            on_date=sub.started_at,
        )
        if pricing is not None:
            estimated_price_excl_vat, estimated_vat_rate, estimated_vat_amount, estimated_total_incl_vat, estimated_currency = pricing

        items.append(
            AdminClientSubscriptionOut(
                id=sub.id,
                status=sub.status,
                started_at=sub.started_at,
                ends_at=sub.ends_at,
                next_payment_at=sub.next_payment_at or sub.ends_at,
                credits_initial=sub.credits_initial,
                credits_remaining=sub.credits_remaining,
                auto_renew=sub.auto_renew,
                billing_method_code=sub.billing_method_code,
                payment_provider_subscription_ref=sub.payment_provider_subscription_ref,
                payment_provider_customer_ref=sub.payment_provider_customer_ref,
                payment_provider_mandate_ref=sub.payment_provider_mandate_ref,
                last_payment_at=sub.last_payment_at,
                last_payment_status=sub.last_payment_status,
                suspension_starts_at=sub.suspension_starts_at,
                suspension_ends_at=sub.suspension_ends_at,
                suspension_duration_value=sub.suspension_duration_value,
                suspension_duration_unit=sub.suspension_duration_unit,
                cancellation_requested_at=sub.cancellation_requested_at,
                cancellation_effective_at=sub.cancellation_effective_at,
                plan=AdminClientSubscriptionMiniOut(
                    id=plan.id,
                    code=plan.code,
                    name=plan.name,
                    kind=plan.kind,
                ),
                estimated_price_excl_vat=estimated_price_excl_vat,
                estimated_vat_rate=estimated_vat_rate,
                estimated_vat_amount=estimated_vat_amount,
                estimated_total_incl_vat=estimated_total_incl_vat,
                estimated_currency=estimated_currency,
            )
        )

    if has_state_changes:
        db.commit()

    return items


def _admin_subscription_with_plan_for_client(
    db: Session,
    *,
    client_id: UUID,
    subscription_id: UUID,
) -> tuple[ClientPlanSubscription, Plan]:
    row = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.id == subscription_id,
            ClientPlanSubscription.user_id == client_id,
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return row


@router.post("/{client_id}/subscriptions/{subscription_id}/suspend", response_model=AdminClientSubscriptionOut)
def suspend_admin_client_subscription(
    client_id: UUID,
    subscription_id: UUID,
    payload: AdminClientSubscriptionSuspendRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientSubscriptionOut:
    _require_client(db, client_id)
    sub, plan = _admin_subscription_with_plan_for_client(db, client_id=client_id, subscription_id=subscription_id)
    if plan.kind != PlanKind.SUBSCRIPTION:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only SUBSCRIPTION can be suspended")
    if sub.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscription is already cancelled")

    duration_unit = payload.duration_unit.strip().upper()
    duration_value = int(payload.duration_value)
    if duration_unit == "DAY" and duration_value > 30:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Suspension days must be between 1 and 30")
    if duration_unit == "MONTH" and duration_value > 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Suspension months must be between 1 and 12")
    if duration_unit not in {"DAY", "MONTH"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported suspension unit")

    suspension_start = payload.suspension_starts_at
    if suspension_start.tzinfo is None:
        suspension_start = suspension_start.replace(tzinfo=timezone.utc)
    else:
        suspension_start = suspension_start.astimezone(timezone.utc)

    normalized_unit = "MONTH" if duration_unit == "MONTH" else "DAY"
    suspension_end = apply_suspension(
        sub,
        start_at=suspension_start,
        unit=normalized_unit,
        amount=duration_value,
    )

    now = _utcnow()
    if suspension_start <= now < suspension_end:
        sub.status = SubscriptionStatus.PAUSED
    elif sub.status == SubscriptionStatus.PAUSED and now >= suspension_end:
        sub.status = SubscriptionStatus.ACTIVE

    db.add(sub)
    _create_client_note(
        db,
        client_id=client_id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=(
            f"Suspension abonnement '{plan.name}' du {suspension_start.date().isoformat()} "
            f"au {suspension_end.date().isoformat()} ({duration_value} {'mois' if normalized_unit == 'MONTH' else 'jours'})."
        ),
    )
    db.commit()
    db.refresh(sub)

    billing_profile = resolve_billing_profile(db, _require_client(db, client_id))

    estimated_price_excl_vat: Decimal | None = None
    estimated_vat_rate: Decimal | None = None
    estimated_vat_amount: Decimal | None = None
    estimated_total_incl_vat: Decimal | None = None
    estimated_currency: str | None = None
    pricing = _estimate_subscription_pricing(
        db,
        plan=plan,
        residence_country=billing_profile.residence_country or "FR",
        preferred_currency=billing_profile.preferred_currency or "EUR",
        on_date=sub.started_at,
    )
    if pricing is not None:
        estimated_price_excl_vat, estimated_vat_rate, estimated_vat_amount, estimated_total_incl_vat, estimated_currency = pricing

    return AdminClientSubscriptionOut(
        id=sub.id,
        status=sub.status,
        started_at=sub.started_at,
        ends_at=sub.ends_at,
        next_payment_at=sub.next_payment_at or sub.ends_at,
        credits_initial=sub.credits_initial,
        credits_remaining=sub.credits_remaining,
        auto_renew=sub.auto_renew,
        billing_method_code=sub.billing_method_code,
        payment_provider_subscription_ref=sub.payment_provider_subscription_ref,
        payment_provider_customer_ref=sub.payment_provider_customer_ref,
        payment_provider_mandate_ref=sub.payment_provider_mandate_ref,
        last_payment_at=sub.last_payment_at,
        last_payment_status=sub.last_payment_status,
        suspension_starts_at=sub.suspension_starts_at,
        suspension_ends_at=sub.suspension_ends_at,
        suspension_duration_value=sub.suspension_duration_value,
        suspension_duration_unit=sub.suspension_duration_unit,
        cancellation_requested_at=sub.cancellation_requested_at,
        cancellation_effective_at=sub.cancellation_effective_at,
        plan=AdminClientSubscriptionMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
        ),
        estimated_price_excl_vat=estimated_price_excl_vat,
        estimated_vat_rate=estimated_vat_rate,
        estimated_vat_amount=estimated_vat_amount,
        estimated_total_incl_vat=estimated_total_incl_vat,
        estimated_currency=estimated_currency,
    )


@router.post("/{client_id}/subscriptions/{subscription_id}/cancel", response_model=AdminClientSubscriptionOut)
def cancel_admin_client_subscription(
    client_id: UUID,
    subscription_id: UUID,
    payload: AdminClientSubscriptionCancelRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientSubscriptionOut:
    client = _require_client(db, client_id)
    sub, plan = _admin_subscription_with_plan_for_client(db, client_id=client_id, subscription_id=subscription_id)
    if sub.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Produit deja resilie")

    requested = payload.cancellation_requested_at or _utcnow()
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=timezone.utc)
    else:
        requested = requested.astimezone(timezone.utc)

    immediate = bool(payload.immediate)
    if immediate and not bool(payload.confirm_immediate):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Immediate cancellation requires explicit confirmation",
        )

    now = _utcnow()
    cycle_end: datetime | None = None
    if plan.kind == PlanKind.SUBSCRIPTION:
        cycle_end = sub.next_payment_at or sub.ends_at or default_next_payment_at(sub.started_at)
        if cycle_end.tzinfo is None:
            cycle_end = cycle_end.replace(tzinfo=timezone.utc)
        else:
            cycle_end = cycle_end.astimezone(timezone.utc)
        effective_at = now if immediate else cycle_end
    else:
        effective_at = now if immediate else max(requested, now)

    sub.cancellation_requested_at = requested
    sub.cancellation_effective_at = effective_at
    sub.auto_renew = False
    sub.ends_at = effective_at
    if immediate or effective_at <= now:
        sub.status = SubscriptionStatus.CANCELLED
        sub.next_payment_at = None
        if plan.kind == PlanKind.PACK:
            sub.credits_remaining = 0

    db.add(sub)
    admin_message_id: str | None = None
    if immediate:
        admin_message_id = _send_admin_subscription_immediate_cancellation_email(
            db,
            actor=actor,
            client=client,
            plan=plan,
            subscription=sub,
            requested_at=requested,
            cancelled_at=effective_at,
        )
    _create_client_note(
        db,
        client_id=client_id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=(
            (
                f"Resiliation immediate produit '{plan.name}' executee le {effective_at.date().isoformat()}."
                if immediate
                else (
                    f"Resiliation produit '{plan.name}' demandee le {requested.date().isoformat()} "
                    + (
                        f"avec fin de periode au {cycle_end.date().isoformat()}."
                        if cycle_end is not None
                        else f"avec effet au {effective_at.date().isoformat()}."
                    )
                )
            )
            + (f" Notification email admin envoyee ({admin_message_id})." if immediate and admin_message_id else "")
        ),
    )
    db.commit()
    db.refresh(sub)

    billing_profile = resolve_billing_profile(db, client)
    estimated_price_excl_vat: Decimal | None = None
    estimated_vat_rate: Decimal | None = None
    estimated_vat_amount: Decimal | None = None
    estimated_total_incl_vat: Decimal | None = None
    estimated_currency: str | None = None
    pricing = _estimate_subscription_pricing(
        db,
        plan=plan,
        residence_country=billing_profile.residence_country or "FR",
        preferred_currency=billing_profile.preferred_currency or "EUR",
        on_date=sub.started_at,
    )
    if pricing is not None:
        estimated_price_excl_vat, estimated_vat_rate, estimated_vat_amount, estimated_total_incl_vat, estimated_currency = pricing

    return AdminClientSubscriptionOut(
        id=sub.id,
        status=sub.status,
        started_at=sub.started_at,
        ends_at=sub.ends_at,
        next_payment_at=sub.next_payment_at or sub.ends_at,
        credits_initial=sub.credits_initial,
        credits_remaining=sub.credits_remaining,
        auto_renew=sub.auto_renew,
        billing_method_code=sub.billing_method_code,
        payment_provider_subscription_ref=sub.payment_provider_subscription_ref,
        payment_provider_customer_ref=sub.payment_provider_customer_ref,
        payment_provider_mandate_ref=sub.payment_provider_mandate_ref,
        last_payment_at=sub.last_payment_at,
        last_payment_status=sub.last_payment_status,
        suspension_starts_at=sub.suspension_starts_at,
        suspension_ends_at=sub.suspension_ends_at,
        suspension_duration_value=sub.suspension_duration_value,
        suspension_duration_unit=sub.suspension_duration_unit,
        cancellation_requested_at=sub.cancellation_requested_at,
        cancellation_effective_at=sub.cancellation_effective_at,
        plan=AdminClientSubscriptionMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
        ),
        estimated_price_excl_vat=estimated_price_excl_vat,
        estimated_vat_rate=estimated_vat_rate,
        estimated_vat_amount=estimated_vat_amount,
        estimated_total_incl_vat=estimated_total_incl_vat,
        estimated_currency=estimated_currency,
    )


@router.post("/{client_id}/subscriptions/{subscription_id}/expiry", response_model=AdminClientSubscriptionOut)
def update_admin_client_subscription_expiry(
    client_id: UUID,
    subscription_id: UUID,
    payload: AdminClientSubscriptionExpiryUpdateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientSubscriptionOut:
    client = _require_client(db, client_id)
    sub, plan = _admin_subscription_with_plan_for_client(db, client_id=client_id, subscription_id=subscription_id)
    if plan.kind not in {PlanKind.PACK, PlanKind.FORFAIT}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PACK or FORFAIT expiry can be updated manually",
        )

    ends_at = payload.ends_at
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    else:
        ends_at = ends_at.astimezone(timezone.utc)

    if ends_at <= sub.started_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expiry date must be after subscription start date",
        )

    now = _utcnow()
    sub.ends_at = ends_at
    if ends_at <= now:
        sub.status = SubscriptionStatus.EXPIRED
        sub.auto_renew = False
        sub.next_payment_at = None
        if plan.kind == PlanKind.PACK:
            sub.credits_remaining = 0
    elif sub.status == SubscriptionStatus.EXPIRED:
        sub.status = SubscriptionStatus.ACTIVE

    db.add(sub)
    _create_client_note(
        db,
        client_id=client_id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=(
            f"Date d'expiration du {'carnet' if plan.kind == PlanKind.PACK else 'forfait'} "
            f"'{plan.name}' modifiee au {ends_at.date().isoformat()}."
        ),
    )
    db.commit()
    db.refresh(sub)

    billing_profile = resolve_billing_profile(db, client)
    estimated_price_excl_vat: Decimal | None = None
    estimated_vat_rate: Decimal | None = None
    estimated_vat_amount: Decimal | None = None
    estimated_total_incl_vat: Decimal | None = None
    estimated_currency: str | None = None
    pricing = _estimate_subscription_pricing(
        db,
        plan=plan,
        residence_country=billing_profile.residence_country or "FR",
        preferred_currency=billing_profile.preferred_currency or "EUR",
        on_date=sub.started_at,
    )
    if pricing is not None:
        estimated_price_excl_vat, estimated_vat_rate, estimated_vat_amount, estimated_total_incl_vat, estimated_currency = pricing

    return AdminClientSubscriptionOut(
        id=sub.id,
        status=sub.status,
        started_at=sub.started_at,
        ends_at=sub.ends_at,
        next_payment_at=sub.next_payment_at or sub.ends_at,
        credits_initial=sub.credits_initial,
        credits_remaining=sub.credits_remaining,
        auto_renew=sub.auto_renew,
        billing_method_code=sub.billing_method_code,
        payment_provider_subscription_ref=sub.payment_provider_subscription_ref,
        payment_provider_customer_ref=sub.payment_provider_customer_ref,
        payment_provider_mandate_ref=sub.payment_provider_mandate_ref,
        last_payment_at=sub.last_payment_at,
        last_payment_status=sub.last_payment_status,
        suspension_starts_at=sub.suspension_starts_at,
        suspension_ends_at=sub.suspension_ends_at,
        suspension_duration_value=sub.suspension_duration_value,
        suspension_duration_unit=sub.suspension_duration_unit,
        cancellation_requested_at=sub.cancellation_requested_at,
        cancellation_effective_at=sub.cancellation_effective_at,
        plan=AdminClientSubscriptionMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
        ),
        estimated_price_excl_vat=estimated_price_excl_vat,
        estimated_vat_rate=estimated_vat_rate,
        estimated_vat_amount=estimated_vat_amount,
        estimated_total_incl_vat=estimated_total_incl_vat,
        estimated_currency=estimated_currency,
    )


@router.post("/{client_id}/subscriptions/{subscription_id}/billing-setup", response_model=AdminClientSubscriptionOut)
def setup_admin_client_subscription_billing(
    client_id: UUID,
    subscription_id: UUID,
    payload: AdminClientSubscriptionBillingSetupRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientSubscriptionOut:
    client = _require_client(db, client_id)
    sub, plan = _admin_subscription_with_plan_for_client(db, client_id=client_id, subscription_id=subscription_id)
    if plan.kind != PlanKind.SUBSCRIPTION:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only SUBSCRIPTION can be configured")

    method = _normalize_optional(payload.billing_method_code)
    if method is not None:
        sub.billing_method_code = method.upper()
    sub.payment_provider_subscription_ref = _normalize_optional(payload.payment_provider_subscription_ref)
    sub.payment_provider_customer_ref = _normalize_optional(payload.payment_provider_customer_ref)
    sub.payment_provider_mandate_ref = _normalize_optional(payload.payment_provider_mandate_ref)
    db.add(sub)
    _create_client_note(
        db,
        client_id=client_id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=f"Mise a jour des references de prelevement pour l'abonnement '{plan.name}'.",
    )
    db.commit()
    db.refresh(sub)

    billing_profile = resolve_billing_profile(db, client)
    estimated_price_excl_vat: Decimal | None = None
    estimated_vat_rate: Decimal | None = None
    estimated_vat_amount: Decimal | None = None
    estimated_total_incl_vat: Decimal | None = None
    estimated_currency: str | None = None
    pricing = _estimate_subscription_pricing(
        db,
        plan=plan,
        residence_country=billing_profile.residence_country or "FR",
        preferred_currency=billing_profile.preferred_currency or "EUR",
        on_date=sub.started_at,
    )
    if pricing is not None:
        estimated_price_excl_vat, estimated_vat_rate, estimated_vat_amount, estimated_total_incl_vat, estimated_currency = pricing

    return AdminClientSubscriptionOut(
        id=sub.id,
        status=sub.status,
        started_at=sub.started_at,
        ends_at=sub.ends_at,
        next_payment_at=sub.next_payment_at or sub.ends_at,
        credits_initial=sub.credits_initial,
        credits_remaining=sub.credits_remaining,
        auto_renew=sub.auto_renew,
        billing_method_code=sub.billing_method_code,
        payment_provider_subscription_ref=sub.payment_provider_subscription_ref,
        payment_provider_customer_ref=sub.payment_provider_customer_ref,
        payment_provider_mandate_ref=sub.payment_provider_mandate_ref,
        last_payment_at=sub.last_payment_at,
        last_payment_status=sub.last_payment_status,
        suspension_starts_at=sub.suspension_starts_at,
        suspension_ends_at=sub.suspension_ends_at,
        suspension_duration_value=sub.suspension_duration_value,
        suspension_duration_unit=sub.suspension_duration_unit,
        cancellation_requested_at=sub.cancellation_requested_at,
        cancellation_effective_at=sub.cancellation_effective_at,
        plan=AdminClientSubscriptionMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
        ),
        estimated_price_excl_vat=estimated_price_excl_vat,
        estimated_vat_rate=estimated_vat_rate,
        estimated_vat_amount=estimated_vat_amount,
        estimated_total_incl_vat=estimated_total_incl_vat,
        estimated_currency=estimated_currency,
    )


@router.post(
    "/{client_id}/subscriptions/{subscription_id}/send-payment-email",
    response_model=AdminClientSubscriptionPaymentEmailOut,
)
def send_admin_client_subscription_payment_email(
    client_id: UUID,
    subscription_id: UUID,
    payload: AdminClientSubscriptionPaymentEmailRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientSubscriptionPaymentEmailOut:
    client = _require_client(db, client_id)
    sub, plan = _admin_subscription_with_plan_for_client(db, client_id=client_id, subscription_id=subscription_id)
    if not client.email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Client email is missing")

    try:
        template = resolve_predefined_template(db, code="PAYMENT")
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not bool(template.get("active", True)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PAYMENT email template is disabled")

    subject_template = str(template.get("subject") or "")
    body_template = str(template.get("body") or "")
    if not subject_template or not body_template:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PAYMENT email template is incomplete")

    billing_profile = resolve_billing_profile(db, client)
    pricing = _estimate_subscription_pricing(
        db,
        plan=plan,
        residence_country=billing_profile.residence_country or "FR",
        preferred_currency=billing_profile.preferred_currency or "EUR",
        on_date=sub.started_at,
    )
    currency_code = (plan.currency_code or billing_profile.preferred_currency or "EUR").upper()
    amount_due = Decimal(payload.discounted_total_incl_vat) if payload.discounted_total_incl_vat is not None else None
    if amount_due is None and pricing is not None:
        amount_due = pricing[3]
        currency_code = pricing[4]
    if amount_due is None:
        amount_due = Decimal("0.00")
    amount_due = amount_due.quantize(Decimal("0.01"))

    method_code = _normalize_optional(payload.payment_method_code)
    if method_code is None:
        method_code = sub.billing_method_code or _default_subscription_billing_method(plan)
    method_code = (method_code or "").strip().upper() or "CARD_ONLINE"

    website = _get_setting_value(db, "config_account_website", "")
    payment_url = _fallback_dashboard_transactions_url(website)
    checkout_url = _create_checkout_for_subscription(
        db,
        client=client,
        subscription=sub,
        plan=plan,
        method_code=method_code,
        amount_due=amount_due,
        currency_code=currency_code,
        raw_website=website,
        force_pending=sub.status != SubscriptionStatus.ACTIVE,
    )
    if checkout_url:
        payment_url = checkout_url

    subject, body = render_client_payment_email(
        subject_template=subject_template,
        body_template=body_template,
        first_name=(client.first_name or "").strip(),
        last_name=(client.last_name or "").strip(),
        email=client.email,
        plan_name=plan.name,
        amount_due=f"{amount_due:.2f}",
        currency=currency_code,
        payment_method=_payment_method_label_client(method_code),
        payment_url=payment_url,
        subscription_reference=str(sub.id),
    )

    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    message_id = send_client_payment_email(
        to_email=client.email,
        subject=subject,
        body=body,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )

    sent_at = _utcnow()
    _create_client_note(
        db,
        client_id=client.id,
        author_user_id=actor.id,
        entry_type="EMAIL",
        message=(
            f"Demande de paiement envoyee a {client.email} pour '{plan.name}' "
            f"({amount_due:.2f} {currency_code}, {_payment_method_label(method_code)}). "
            f"Message id: {message_id}. "
            + (f"Checkout: {payment_url}." if checkout_url else "")
        ),
    )
    db.commit()

    return AdminClientSubscriptionPaymentEmailOut(
        client_id=client.id,
        subscription_id=sub.id,
        email=client.email,
        message_id=message_id,
        sent_at=sent_at,
    )


@router.get("/{client_id}/manual-credits", response_model=list[AdminClientManualCreditOut])
def list_admin_client_manual_credits(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientManualCreditOut]:
    _require_client(db, client_id)

    credit_types = db.scalars(
        select(CreditType)
        .where(CreditType.active.is_(True))
        .order_by(CreditType.name.asc())
    ).all()
    if not credit_types:
        credit_types = db.scalars(select(CreditType).order_by(CreditType.name.asc())).all()

    balances = db.scalars(
        select(ClientManualCreditBalance).where(ClientManualCreditBalance.user_id == client_id)
    ).all()
    balance_by_credit_type_id = {row.credit_type_id: row for row in balances}

    items: list[AdminClientManualCreditOut] = []
    for credit_type in credit_types:
        row = balance_by_credit_type_id.get(credit_type.id)
        items.append(
            AdminClientManualCreditOut(
                id=row.id if row is not None else None,
                credit_type_id=credit_type.id,
                credit_type_code=credit_type.code,
                credit_type_name=credit_type.name,
                credits_count=int(row.credits_count) if row is not None else 0,
                updated_at=row.updated_at if row is not None else None,
            )
        )
    return items


@router.post("/{client_id}/manual-credits/{credit_type_id}", response_model=AdminClientManualCreditOut)
def upsert_admin_client_manual_credit(
    client_id: UUID,
    credit_type_id: UUID,
    payload: AdminClientManualCreditUpdateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientManualCreditOut:
    _require_client(db, client_id)
    credit_type = db.scalar(select(CreditType).where(CreditType.id == credit_type_id))
    if credit_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit type not found")

    row = db.scalar(
        select(ClientManualCreditBalance)
        .where(
            ClientManualCreditBalance.user_id == client_id,
            ClientManualCreditBalance.credit_type_id == credit_type_id,
        )
        .with_for_update()
    )
    previous = int(row.credits_count) if row is not None else 0
    next_value = int(payload.credits_count)
    now = _utcnow()

    if row is None:
        row = ClientManualCreditBalance(
            user_id=client_id,
            credit_type_id=credit_type_id,
            credits_count=next_value,
            updated_at=now,
        )
    else:
        row.credits_count = next_value
        row.updated_at = now
    db.add(row)

    _create_client_note(
        db,
        client_id=client_id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=(
            f"Credit manuel '{credit_type.name}' modifie: {previous} -> {next_value}."
        ),
    )

    db.commit()
    db.refresh(row)

    return AdminClientManualCreditOut(
        id=row.id,
        credit_type_id=credit_type.id,
        credit_type_code=credit_type.code,
        credit_type_name=credit_type.name,
        credits_count=int(row.credits_count),
        updated_at=row.updated_at,
    )


@router.get("/{client_id}/notes", response_model=list[AdminClientNoteOut])
def list_admin_client_notes(
    client_id: UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientNoteOut]:
    _require_client(db, client_id)
    author_alias = aliased(User)
    rows = db.execute(
        select(ClientNoteEntry, author_alias)
        .outerjoin(author_alias, author_alias.id == ClientNoteEntry.author_user_id)
        .where(ClientNoteEntry.user_id == client_id)
        .order_by(ClientNoteEntry.created_at.desc())
        .limit(limit)
    ).all()
    return [_client_note_out(note, author=author) for note, author in rows]


@router.post("/{client_id}/notes", response_model=AdminClientNoteOut, status_code=status.HTTP_201_CREATED)
def create_admin_client_note(
    client_id: UUID,
    payload: AdminClientNoteCreateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientNoteOut:
    _require_client(db, client_id)
    note = _create_client_note(
        db,
        client_id=client_id,
        message=payload.message,
        entry_type="MANUAL",
        author_user_id=actor.id,
    )
    db.commit()
    db.refresh(note)
    return _client_note_out(note, author=actor)


@router.get("/{client_id}/bookings", response_model=list[AdminClientBookingOut])
def list_admin_client_bookings(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientBookingOut]:
    _require_client(db, client_id)

    rows = db.execute(
        select(Booking, CourseSession, CourseType, Location, Plan)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id)
        .outerjoin(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(Booking.user_id == client_id)
        .order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())
    ).all()

    return [
        AdminClientBookingOut(
            id=booking.id,
            session_id=session_obj.id,
            session_title=session_obj.title,
            session_status=session_obj.status,
            session_start_at_utc=session_obj.start_at_utc,
            session_end_at_utc=session_obj.end_at_utc,
            course_type_name=course_type.name,
            location_name=location.name,
            client_plan_subscription_id=booking.client_plan_subscription_id,
            plan_name=plan.name if plan is not None else None,
            status=booking.status.value,
            booked_at=booking.booked_at,
            cancelled_at=booking.cancelled_at,
            cancellation_reason=booking.cancellation_reason,
            price_excl_vat_snapshot=booking.price_excl_vat_snapshot,
            vat_rate_snapshot=booking.vat_rate_snapshot,
            vat_amount_snapshot=booking.vat_amount_snapshot,
            total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
            currency_snapshot=booking.currency_snapshot,
        )
        for booking, session_obj, course_type, location, plan in rows
    ]


@router.get("/{client_id}/messages", response_model=list[AdminClientMessageOut])
def list_admin_client_messages(
    client_id: UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientMessageOut]:
    client = _require_client(db, client_id)

    rows = db.execute(
        select(EmailReminder, Booking, CourseSession, CourseType, Location)
        .join(Booking, Booking.id == EmailReminder.booking_id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(Booking.user_id == client_id)
        .order_by(EmailReminder.created_at.desc())
        .limit(limit)
    ).all()

    items: list[AdminClientMessageOut] = []
    for reminder, booking, session_obj, course_type, location in rows:
        start_human = _format_session_datetime(session_obj, client.timezone, location)
        subject_preview = f"Rappel cours: {course_type.name} - {start_human}"

        items.append(
            AdminClientMessageOut(
                id=reminder.id,
                booking_id=booking.id,
                session_id=session_obj.id,
                session_title=session_obj.title,
                scheduled_for_utc=reminder.scheduled_for_utc,
                sent_at=reminder.sent_at,
                status=reminder.status,
                provider_message_id=reminder.provider_message_id,
                error_message=reminder.error_message,
                subject_preview=subject_preview,
            )
        )

    return items


def _build_admin_client_payments(db: Session, *, client_id: UUID) -> list[AdminClientPaymentOut]:
    client = _require_client(db, client_id)
    billing_profile = resolve_billing_profile(db, client)

    rows_subs = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(ClientPlanSubscription.user_id == client_id)
    ).all()

    rows_bookings = db.execute(
        select(Booking, CourseSession, CourseType, Location, Plan)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id)
        .outerjoin(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(Booking.user_id == client_id)
    ).all()

    manual_rows = db.scalars(
        select(ClientManualTransaction).where(ClientManualTransaction.user_id == client_id)
    ).all()
    manual_student_ids = {row.student_user_id for row in manual_rows if row.student_user_id is not None}
    manual_students_by_id: dict[UUID, User] = {}
    if manual_student_ids:
        manual_students_by_id = {
            user.id: user for user in db.scalars(select(User).where(User.id.in_(manual_student_ids))).all()
        }

    refunds = db.scalars(
        select(ClientPaymentRefund).where(ClientPaymentRefund.user_id == client_id)
    ).all()
    refund_by_key = {(row.source.strip().upper(), row.source_payment_id): row for row in refunds}

    items: list[AdminClientPaymentOut] = []

    for sub, plan in rows_subs:
        if plan.kind == PlanKind.FORFAIT:
            continue

        pricing = _estimate_subscription_pricing(
            db,
            plan=plan,
            residence_country=billing_profile.residence_country or "FR",
            preferred_currency=billing_profile.preferred_currency or "EUR",
            on_date=sub.started_at,
        )

        if pricing is not None:
            price_excl_vat, vat_rate, vat_amount, total_incl_vat, currency_code = pricing
        else:
            price_excl_vat = Decimal("0.00")
            vat_rate = Decimal("0.00")
            vat_amount = Decimal("0.00")
            total_incl_vat = Decimal("0.00")
            currency_code = (plan.currency_code or billing_profile.preferred_currency or "EUR").upper()

        items.append(
            AdminClientPaymentOut(
                id=sub.id,
                source="PLAN_PURCHASE",
                occurred_at=sub.started_at,
                label=plan.name,
                status=_subscription_payment_status(sub),
                amount_excl_vat=price_excl_vat,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                total_incl_vat=total_incl_vat,
                currency=currency_code,
                reference=plan.code,
            )
        )

    for booking, session_obj, course_type, location, plan in rows_bookings:
        is_billable = True
        status_value = booking.status.value
        if plan is not None and plan.kind == PlanKind.FORFAIT:
            is_billable = (
                session_obj.status != SessionStatus.CANCELLED
                and booking.status not in {BookingStatus.WAITLISTED, BookingStatus.CANCELLED, BookingStatus.EXCUSED_ABSENCE}
            )
            if not is_billable:
                status_value = "NOT_BILLABLE"
        elif booking.status == BookingStatus.EXCUSED_ABSENCE:
            is_billable = False
        items.append(
            AdminClientPaymentOut(
                id=booking.id,
                source="BOOKING",
                occurred_at=session_obj.start_at_utc,
                label=f"{course_type.name} - {location.name}",
                status=status_value,
                amount_excl_vat=Decimal("0.00") if not is_billable else booking.price_excl_vat_snapshot,
                vat_rate=Decimal("0.00") if not is_billable else booking.vat_rate_snapshot,
                vat_amount=Decimal("0.00") if not is_billable else booking.vat_amount_snapshot,
                total_incl_vat=Decimal("0.00") if not is_billable else booking.total_incl_vat_snapshot,
                currency=booking.currency_snapshot,
                reference=str(session_obj.id),
            )
        )

    for row in manual_rows:
        student = manual_students_by_id.get(row.student_user_id) if row.student_user_id is not None else None
        label = row.label
        if student is not None and student.id != client_id:
            label = f"{label} - {_display_name(student.first_name, student.last_name, student.email)}"

        reference_parts: list[str] = []
        if row.category:
            reference_parts.append(row.category)
        if row.reference:
            reference_parts.append(row.reference)
        reference = " | ".join(reference_parts) or None

        items.append(
            AdminClientPaymentOut(
                id=row.id,
                source="MANUAL",
                occurred_at=row.occurred_at,
                label=label,
                status=(row.status or "COMPLETED").strip().upper() or "COMPLETED",
                amount_excl_vat=_quantize_money(Decimal(row.amount_excl_vat)),
                vat_rate=Decimal(row.vat_rate),
                vat_amount=_quantize_money(Decimal(row.vat_amount)),
                total_incl_vat=_quantize_money(Decimal(row.total_incl_vat)),
                currency=_normalize_currency(row.currency, fallback=billing_profile.preferred_currency or "EUR"),
                reference=reference,
            )
        )

    for item in items:
        refund = refund_by_key.get((item.source.strip().upper(), item.id))
        if refund is not None:
            item.status = "REFUNDED"
            item.refunded_at = refund.refunded_at
            item.refund_reason = refund.reason
        item.invoice_number = _invoice_number_for_payment(item.id, item.occurred_at)
        item.invoice_status = _invoice_status_from_payment_status(item.status)

    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items


@router.get("/{client_id}/payments", response_model=list[AdminClientPaymentOut])
def list_admin_client_payments(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminClientPaymentOut]:
    return _build_admin_client_payments(db, client_id=client_id)


@router.post("/{client_id}/manual-transactions", response_model=AdminClientPaymentOut, status_code=status.HTTP_201_CREATED)
def create_admin_client_manual_transaction(
    client_id: UUID,
    payload: AdminClientManualTransactionCreateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientPaymentOut:
    client = _require_client(db, client_id)
    transaction_type = payload.transaction_type.value.strip().upper()
    sign = MANUAL_TRANSACTION_SIGN_BY_TYPE.get(transaction_type)
    if sign is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported transaction type")

    student_id = payload.student_id
    if student_id is not None:
        allowed_student_ids = _manual_transaction_allowed_student_ids(db, client=client)
        if student_id not in allowed_student_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Selected student is not linked to this account",
            )

    total_abs = _quantize_money(Decimal(payload.amount_incl_vat))
    if total_abs <= Decimal("0.00"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Amount must be greater than zero")

    vat_rate = Decimal(payload.vat_rate).quantize(Decimal("0.001"))
    ratio = Decimal("1.000") + (vat_rate / Decimal("100"))
    if ratio <= Decimal("0.000"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid VAT rate")

    amount_excl_abs = _quantize_money(total_abs / ratio)
    vat_amount_abs = _quantize_money(total_abs - amount_excl_abs)

    label = _manual_transaction_label(transaction_type, _normalize_optional(payload.label))
    description = _normalize_optional(payload.description)
    category = _normalize_optional(payload.category)
    if category:
        allowed_categories = _configured_product_categories(db)
        if allowed_categories and category.casefold() not in {item.casefold() for item in allowed_categories}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unknown category. Update products categories in admin config first.",
            )
    reference = _normalize_optional(payload.reference)
    currency = _normalize_currency(payload.currency, fallback=client.preferred_currency or "EUR")
    occurred_at = payload.occurred_at or _utcnow()
    status_value = MANUAL_TRANSACTION_STATUS_BY_TYPE.get(transaction_type, "COMPLETED")

    row = ClientManualTransaction(
        user_id=client.id,
        student_user_id=student_id,
        actor_user_id=actor.id,
        transaction_type=transaction_type,
        status=status_value,
        label=label,
        description=description,
        category=category,
        occurred_at=occurred_at,
        amount_excl_vat=_quantize_money(amount_excl_abs * sign),
        vat_rate=vat_rate,
        vat_amount=_quantize_money(vat_amount_abs * sign),
        total_incl_vat=_quantize_money(total_abs * sign),
        currency=currency,
        reference=reference,
    )
    db.add(row)

    direction_label = "debiteur" if sign > 0 else "crediteur"
    _create_client_note(
        db,
        client_id=client.id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=(
            f"Transaction manuelle ajoutee ({label}) : {row.total_incl_vat:.2f} {currency} "
            f"[{direction_label}]"
            + (f". Categorie: {category}." if category else ".")
        ),
    )

    db.commit()

    created = next(
        (
            item
            for item in _build_admin_client_payments(db, client_id=client.id)
            if item.id == row.id and item.source.strip().upper() == "MANUAL"
        ),
        None,
    )
    if created is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to load created transaction")
    return created


@router.get("/{client_id}/payments/invoice-range")
def download_admin_client_range_invoice(
    client_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    include_pending: bool = Query(default=True),
    include_cancelled: bool = Query(default=False),
    note: str | None = Query(default=None, max_length=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    client = _require_client(db, client_id)
    if end_date < start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid date range")

    start_at = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_at_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    all_payments = _build_admin_client_payments(db, client_id=client_id)
    payments = [row for row in all_payments if start_at <= row.occurred_at < end_at_exclusive]

    if not include_pending:
        payments = [row for row in payments if _invoice_status_from_payment_status(row.status) != "PENDING"]
    if not include_cancelled:
        payments = [row for row in payments if _invoice_status_from_payment_status(row.status) != "CANCELLED"]

    if not payments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transactions for this period")

    payments.sort(key=lambda row: row.occurred_at)
    totals_by_currency: dict[str, dict[str, Decimal]] = {}
    for row in payments:
        currency = _normalize_currency(row.currency, fallback="EUR")
        current = totals_by_currency.setdefault(
            currency,
            {"amount_excl_vat": Decimal("0.00"), "vat_amount": Decimal("0.00"), "total_incl_vat": Decimal("0.00")},
        )
        current["amount_excl_vat"] = _quantize_money(current["amount_excl_vat"] + Decimal(row.amount_excl_vat))
        current["vat_amount"] = _quantize_money(current["vat_amount"] + Decimal(row.vat_amount))
        current["total_incl_vat"] = _quantize_money(current["total_incl_vat"] + Decimal(row.total_incl_vat))

    issued_at = _utcnow()
    compact = str(client.id).replace("-", "").upper()
    invoice_number = f"FAC-RANGE-{issued_at.strftime('%Y%m%d%H%M%S')}-{compact[:6]}"
    client_label = _display_name(client.first_name, client.last_name, client.email)
    company_name = _get_setting_value(db, "config_account_club_name", "Piano Academie")
    company_email = _get_setting_value(db, "config_account_contact_email", "") or "-"
    company_address = " ".join(
        part
        for part in [
            _get_setting_value(db, "config_account_address_line", ""),
            _get_setting_value(db, "config_account_postal_code", ""),
            _get_setting_value(db, "config_account_city", ""),
            _get_setting_value(db, "config_account_country", ""),
        ]
        if part
    ).strip() or "-"

    lines = [
        "Piano Academie - Facture periode",
        f"Numero: {invoice_number}",
        f"Date d'emission: {issued_at.strftime('%d/%m/%Y %H:%M')}",
        f"Client: {client_label} ({client.id})",
        f"Periode: {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}",
        f"Filtres: inclure en attente={include_pending} | inclure annule={include_cancelled}",
        "",
        f"Transactions ({len(payments)}):",
    ]
    for row in payments:
        payment_status = row.status or "-"
        lines.append(
            " - "
            + f"{row.occurred_at.strftime('%d/%m/%Y %H:%M')} | {_payment_source_label(row.source)} | {row.label} | "
            + f"Statut={payment_status} | "
            + f"Total={_quantize_money(Decimal(row.total_incl_vat))} {row.currency} | Ref={row.reference or '-'}"
        )

    lines.append("")
    lines.append("Totaux:")
    for currency_code in sorted(totals_by_currency.keys()):
        values = totals_by_currency[currency_code]
        lines.append(
            " - "
            + f"{currency_code} | HT={values['amount_excl_vat']} | TVA={values['vat_amount']} | TTC={values['total_incl_vat']}"
        )

    normalized_note = _normalize_optional(note)
    if normalized_note:
        lines.extend(["", f"Note: {normalized_note}"])

    lines.extend(
        [
            "",
            company_name,
            f"Contact: {company_email}",
            company_address,
            "",
        ]
    )

    content = "\n".join(lines)
    file_name = f"{invoice_number}.txt".replace('"', "")
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{client_id}/payments/{source}/{payment_id}/refund", response_model=AdminClientPaymentRefundOut)
def refund_admin_client_payment(
    client_id: UUID,
    source: str,
    payment_id: UUID,
    payload: AdminClientPaymentRefundRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminClientPaymentRefundOut:
    _require_client(db, client_id)
    source_code = source.strip().upper()
    if source_code not in {"PLAN_PURCHASE", "BOOKING"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported payment source")

    if source_code == "PLAN_PURCHASE":
        exists = db.scalar(
            select(ClientPlanSubscription.id).where(
                ClientPlanSubscription.id == payment_id,
                ClientPlanSubscription.user_id == client_id,
            )
        )
    else:
        exists = db.scalar(
            select(Booking.id).where(
                Booking.id == payment_id,
                Booking.user_id == client_id,
            )
        )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    row = db.scalar(
        select(ClientPaymentRefund)
        .where(
            ClientPaymentRefund.user_id == client_id,
            ClientPaymentRefund.source == source_code,
            ClientPaymentRefund.source_payment_id == payment_id,
        )
        .with_for_update()
    )
    now = _utcnow()
    reason = _normalize_optional(payload.reason)
    if row is None:
        row = ClientPaymentRefund(
            user_id=client_id,
            source=source_code,
            source_payment_id=payment_id,
            actor_user_id=actor.id,
            refunded_at=now,
            updated_at=now,
            reason=reason,
        )
    else:
        row.actor_user_id = actor.id
        row.refunded_at = now
        row.updated_at = now
        row.reason = reason
    db.add(row)

    _create_client_note(
        db,
        client_id=client_id,
        author_user_id=actor.id,
        entry_type="AUTO",
        message=(
            f"Remboursement enregistre ({_payment_source_label(source_code)}) "
            f"sur le paiement {payment_id}."
            + (f" Motif: {reason}." if reason else "")
        ),
    )

    db.commit()
    db.refresh(row)

    return AdminClientPaymentRefundOut(
        client_id=client_id,
        source=source_code,
        payment_id=payment_id,
        refunded_at=row.refunded_at,
        reason=row.reason,
    )


@router.get("/{client_id}/payments/{source}/{payment_id}/invoice")
def download_admin_client_payment_invoice(
    client_id: UUID,
    source: str,
    payment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    payment_user = _require_client(db, client_id)
    source_code = source.strip().upper()
    if source_code not in {"PLAN_PURCHASE", "BOOKING", "MANUAL"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported payment source")

    payment = next(
        (
            row
            for row in _build_admin_client_payments(db, client_id=client_id)
            if row.id == payment_id and row.source.strip().upper() == source_code
        ),
        None,
    )
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    invoice_number = payment.invoice_number or _invoice_number_for_payment(payment.id, payment.occurred_at)
    client_label = _display_name(payment_user.first_name, payment_user.last_name, payment_user.email)
    content = render_invoice_text(
        db,
        invoice_number=invoice_number,
        issued_at=payment.occurred_at,
        client_id=str(client_id),
        client_name=client_label,
        payment_type=_payment_source_label(payment.source),
        label=payment.label,
        payment_status=payment.status,
        amount_excl_vat=payment.amount_excl_vat,
        vat_amount=payment.vat_amount,
        total_incl_vat=payment.total_incl_vat,
        currency=payment.currency,
        reference=payment.reference,
        refunded_at=payment.refunded_at,
        refund_reason=payment.refund_reason,
    )

    file_name = f"{invoice_number}.txt".replace('"', "")
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{client_id}/plans/{plan_id}/purchase", response_model=ClientSubscriptionOut, status_code=status.HTTP_201_CREATED)
def admin_purchase_plan_for_client(
    client_id: UUID,
    plan_id: UUID,
    payload: AdminClientPlanPurchaseRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ClientSubscriptionOut:
    client = _require_client(db, client_id)
    if not client.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client is inactive")

    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    now = _utcnow()
    _lock_user_purchase_scope(db, client.id)

    if plan.kind == PlanKind.SUBSCRIPTION and _has_same_subscription_in_current_month(
        db,
        user_id=client.id,
        plan_id=plan.id,
        now=now,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This subscription is already purchased for the current month",
        )

    if plan.kind == PlanKind.PACK and _has_active_pack_with_remaining_credits(db, user_id=client.id, now=now):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active pack with remaining credits already exists",
        )

    credits_initial: int | None = None
    credits_remaining: int | None = None
    ends_at = None
    payload = payload or AdminClientPlanPurchaseRequest()
    requested_method = _normalize_optional(payload.payment_method_code)
    method_code = (requested_method or _default_subscription_billing_method(plan) or "").strip().upper() or None

    if plan.kind == PlanKind.PACK:
        credits_initial = _effective_pack_credits_for_plan(db, plan=plan)
        credits_remaining = credits_initial
        ends_at = add_months_utc(now, int(plan.pack_validity_months or 12))
    elif plan.kind == PlanKind.SUBSCRIPTION:
        ends_at = add_months_utc(now, 1)

    should_start_pending = _is_online_collection_method(method_code) and plan.kind != PlanKind.FORFAIT
    subscription = ClientPlanSubscription(
        user_id=client.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING if should_start_pending else SubscriptionStatus.ACTIVE,
        started_at=now,
        ends_at=ends_at,
        credits_initial=credits_initial,
        credits_remaining=credits_remaining,
        auto_renew=(plan.kind == PlanKind.SUBSCRIPTION and not should_start_pending),
        billing_method_code=method_code,
        next_payment_at=ends_at if plan.kind == PlanKind.SUBSCRIPTION else None,
    )

    db.add(subscription)
    db.flush()

    checkout_url: str | None = None
    if should_start_pending and method_code is not None:
        billing_profile = resolve_billing_profile(db, client)
        pricing = _estimate_subscription_pricing(
            db,
            plan=plan,
            residence_country=billing_profile.residence_country or "FR",
            preferred_currency=billing_profile.preferred_currency or "EUR",
            on_date=subscription.started_at,
        )
        amount_due = pricing[3] if pricing is not None else Decimal("0.00")
        currency_code = pricing[4] if pricing is not None else (plan.currency_code or billing_profile.preferred_currency or "EUR").upper()
        website = _get_setting_value(db, "config_account_website", "")
        checkout_url = _create_checkout_for_subscription(
            db,
            client=client,
            subscription=subscription,
            plan=plan,
            method_code=method_code,
            amount_due=amount_due,
            currency_code=currency_code,
            raw_website=website,
            force_pending=True,
        )

    db.commit()
    db.refresh(subscription)

    return ClientSubscriptionOut(
        id=subscription.id,
        status=subscription.status,
        started_at=subscription.started_at,
        ends_at=subscription.ends_at,
        next_payment_at=subscription.next_payment_at,
        credits_initial=subscription.credits_initial,
        credits_remaining=subscription.credits_remaining,
        auto_renew=subscription.auto_renew,
        billing_method_code=subscription.billing_method_code,
        suspension_starts_at=subscription.suspension_starts_at,
        suspension_ends_at=subscription.suspension_ends_at,
        cancellation_requested_at=subscription.cancellation_requested_at,
        cancellation_effective_at=subscription.cancellation_effective_at,
        plan=PlanMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
        ),
        checkout_url=checkout_url,
        payment_reference=subscription.payment_provider_subscription_ref,
    )
