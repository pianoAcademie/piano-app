from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry, PaymentReceipt
from app.models.ops import AppSetting
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.family_billing import resolve_billing_profile
from app.services.invoice_documents import render_payment_receipt_pdf, reserve_next_invoice_number
from app.services.invoice_number_service import InvoiceNumberService
from app.services.messaging_templates import resolve_frontend_base_url, resolve_predefined_template, resolve_sender_profile

logger = logging.getLogger(__name__)

INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::"
PAYMENT_RECEIPT_NUMBER_FORMAT_SETTING_KEY = "config_payment_receipt_number_format_v1"
PAYMENT_RECEIPT_NUMBER_NEXT_SETTING_KEY = "config_payment_receipt_number_next_v1"
DEFAULT_PAYMENT_RECEIPT_NUMBER_FORMAT = "PAY-%YYYY%-%NNNN%"
DEFAULT_PAYMENT_RECEIPT_NUMBER_NEXT = 1
PAYMENT_RECEIPT_PUBLIC_PAYMENT_TOKEN_SCOPE = "PAYMENT_RECEIPT_PUBLIC_PAY"
PAYMENT_RECEIPT_CLIENT_TEMPLATE_CODE = "PAYMENT_RECEIPT"
PAYMENT_RECEIPT_ADMIN_TEMPLATE_CODE = "PAYMENT_RECEIPT_ADMIN"
PAYMENT_RECEIPT_CONTEXT = "CLIENT_PAYMENT_RECEIPT"
PAYMENT_RECEIPT_ADMIN_CONTEXT = "ADMIN_PAYMENT_RECEIPT"
PAYMENT_RECEIPT_NOTE_TEXT = (
    "Ce document confirme la reception de votre paiement. Le document commercial final de la prestation sera emis a sa realisation."
)
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
FINAL_INVOICE_ELIGIBLE_BOOKING_STATUSES = (
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
)


@dataclass(frozen=True)
class BookingReceiptSnapshot:
    customer_id: UUID
    customer_first_name: str | None
    customer_last_name: str | None
    customer_email: str | None
    customer_name: str
    customer_billing_address: str
    student_id: UUID | None
    student_name: str
    booking_id: UUID
    session_id: UUID
    session_status: str
    service_date: date | None
    reservation_label: str
    activity_name: str
    location_label: str
    session_time_label: str
    amount_total: Decimal
    currency: str
    legal_entity_id: UUID | None


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _setting_value(db: Session, key: str, default: str) -> str:
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        return default
    value = str(row.value or "").strip()
    return value or default


def _normalize_receipt_number_format(value: str | None) -> str:
    candidate = (value or "").strip().upper()
    if not candidate:
        return DEFAULT_PAYMENT_RECEIPT_NUMBER_FORMAT
    return candidate[:120]


def _normalize_receipt_number_next(value: str | int | None) -> int:
    if value is None:
        return DEFAULT_PAYMENT_RECEIPT_NUMBER_NEXT
    try:
        number = int(str(value).strip())
    except ValueError:
        return DEFAULT_PAYMENT_RECEIPT_NUMBER_NEXT
    if number < 1:
        return DEFAULT_PAYMENT_RECEIPT_NUMBER_NEXT
    return min(number, 999_999_999)


def _format_receipt_number(pattern: str, *, paid_at: datetime, next_number: int) -> str:
    rendered = _normalize_receipt_number_format(pattern)
    rendered = rendered.replace("%YYYY%", paid_at.strftime("%Y"))
    rendered = rendered.replace("%YY%", paid_at.strftime("%y"))
    rendered = rendered.replace("%MM%", paid_at.strftime("%m"))
    rendered = rendered.replace("%DD%", paid_at.strftime("%d"))

    def _replace_sequence_token(match: re.Match[str]) -> str:
        token = match.group(0)
        width = max(len(token) - 2, 1)
        return str(next_number).zfill(width)

    rendered = re.sub(r"%N+%", _replace_sequence_token, rendered)
    if "%N" in rendered:
        rendered = rendered.replace("%N", str(next_number))
    return rendered


def reserve_next_payment_receipt_number(db: Session, *, paid_at: datetime | None = None) -> str:
    effective_paid_at = paid_at or _utcnow()
    now = _utcnow()
    format_row = db.scalar(
        select(AppSetting).where(AppSetting.key == PAYMENT_RECEIPT_NUMBER_FORMAT_SETTING_KEY).with_for_update()
    )
    next_row = db.scalar(
        select(AppSetting).where(AppSetting.key == PAYMENT_RECEIPT_NUMBER_NEXT_SETTING_KEY).with_for_update()
    )
    pattern = _normalize_receipt_number_format(format_row.value if format_row else None)
    next_number = _normalize_receipt_number_next(next_row.value if next_row else None)
    receipt_number = _format_receipt_number(pattern, paid_at=effective_paid_at, next_number=next_number)
    if format_row is None:
        db.add(AppSetting(key=PAYMENT_RECEIPT_NUMBER_FORMAT_SETTING_KEY, value=pattern, updated_at=now))
    else:
        format_row.value = pattern
        format_row.updated_at = now
    next_value = str(next_number + 1)
    if next_row is None:
        db.add(AppSetting(key=PAYMENT_RECEIPT_NUMBER_NEXT_SETTING_KEY, value=next_value, updated_at=now))
    else:
        next_row.value = next_value
        next_row.updated_at = now
    return receipt_number


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _display_name(first_name: str | None, last_name: str | None, email: str | None) -> str:
    value = " ".join(part for part in [(first_name or "").strip(), (last_name or "").strip()] if part).strip()
    return value or (email or "").strip() or "-"


def _country_display_name(raw: str | None) -> str:
    code = (raw or "").strip().upper()
    mapping = {
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
    return mapping.get(code, code or "France")


def _billing_address_label(user: User) -> str:
    parts = [(user.address_line or "").strip(), (user.postal_code or "").strip(), (user.city or "").strip()]
    label = " ".join(part for part in parts if part).strip()
    country = _country_display_name(user.address_country or user.residence_country)
    return f"{label} ({country})".strip() if label else country


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        logger.warning("Unable to render payment receipt template, returning raw template")
        return normalized.strip()


def _frontend_url(path: str) -> str:
    candidate = resolve_frontend_base_url()
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _session_zone(session_obj: CourseSession) -> ZoneInfo | timezone:
    timezone_name = (session_obj.timezone or "").strip() or "Europe/Paris"
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _session_local_date(session_obj: CourseSession) -> date:
    zone = _session_zone(session_obj)
    return session_obj.start_at_utc.astimezone(zone).date()


def _session_local_time_label(session_obj: CourseSession) -> str:
    zone = _session_zone(session_obj)
    start_local = session_obj.start_at_utc.astimezone(zone)
    end_local = session_obj.end_at_utc.astimezone(zone)
    return f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}"


def should_defer_booking_invoice(session_obj: CourseSession, *, now: datetime | None = None) -> bool:
    if session_obj.status == SessionStatus.COMPLETED:
        return False
    effective_now = now or _utcnow()
    return _session_local_date(session_obj) > effective_now.astimezone(_session_zone(session_obj)).date()


def build_booking_receipt_snapshot(
    db: Session,
    *,
    booking: Booking,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
    owner: User,
) -> BookingReceiptSnapshot:
    billing_profile = resolve_billing_profile(db, owner)
    customer_name = _display_name(billing_profile.first_name, billing_profile.last_name, billing_profile.email)
    student_name = _display_name(owner.first_name, owner.last_name, owner.email)
    is_distinct_student = owner.id != billing_profile.id
    reservation_label = f"{course_type.name} - {location.name}"
    if is_distinct_student:
        reservation_label = f"{reservation_label} - {student_name}"
    return BookingReceiptSnapshot(
        customer_id=billing_profile.id,
        customer_first_name=billing_profile.first_name,
        customer_last_name=billing_profile.last_name,
        customer_email=_normalize_optional(billing_profile.email),
        customer_name=customer_name,
        customer_billing_address=_billing_address_label(billing_profile),
        student_id=owner.id if is_distinct_student else None,
        student_name=student_name,
        booking_id=booking.id,
        session_id=session_obj.id,
        session_status=session_obj.status.value if hasattr(session_obj.status, "value") else str(session_obj.status),
        service_date=_session_local_date(session_obj),
        reservation_label=reservation_label,
        activity_name=course_type.name,
        location_label=(location.name or "").strip(),
        session_time_label=_session_local_time_label(session_obj),
        amount_total=_quantize_money(Decimal(booking.total_incl_vat_snapshot)),
        currency=((booking.currency_snapshot or "EUR").strip().upper() or "EUR"),
        legal_entity_id=session_obj.snapshot_seller_legal_entity_id or course_type.seller_legal_entity_id,
    )


def _payment_key(*, source: str, payment_id: UUID) -> str:
    return f"{source.strip().upper()}:{payment_id}"


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


def _parse_invoice_range_note_entry(note: ClientNoteEntry) -> dict[str, object] | None:
    message = note.message or ""
    if INVOICE_RANGE_NOTE_PREFIX not in message:
        return None
    payload = message.split(INVOICE_RANGE_NOTE_PREFIX, 1)[1].strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if str(parsed.get("kind") or "").strip().upper() != "INVOICE_RANGE":
        return None
    return parsed


def _invoice_note_for_booking(db: Session, *, booking_id: UUID) -> tuple[ClientNoteEntry, dict[str, object]] | None:
    note_ids = db.scalars(
        select(ClientInvoiceLine.note_id)
        .where(
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
        note = db.scalar(select(ClientNoteEntry).where(ClientNoteEntry.id == note_id))
        if note is None:
            continue
        metadata = _parse_invoice_range_note_entry(note)
        if metadata is None:
            continue
        if str(metadata.get("invoice_status") or "").strip().upper() == "CANCELLED":
            continue
        return note, metadata
    return None


def completed_payment_receipt_totals(db: Session, *, booking_id: UUID) -> tuple[Decimal, str, list[UUID]]:
    rows = db.scalars(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.booking_id == booking_id,
            PaymentReceipt.status == "COMPLETED",
        )
        .order_by(PaymentReceipt.paid_at.asc().nullslast(), PaymentReceipt.created_at.asc(), PaymentReceipt.id.asc())
    ).all()
    total = Decimal("0.00")
    currency = "EUR"
    manual_ids: list[UUID] = []
    for row in rows:
        total += _quantize_money(Decimal(row.amount_paid or 0))
        currency = ((row.currency or "EUR").strip().upper() or "EUR")
        if row.manual_transaction_id is not None:
            manual_ids.append(row.manual_transaction_id)
    return _quantize_money(total), currency, manual_ids


def remaining_booking_amount_due(db: Session, *, booking: Booking) -> Decimal:
    paid_total, _, _ = completed_payment_receipt_totals(db, booking_id=booking.id)
    total = _quantize_money(Decimal(booking.total_incl_vat_snapshot))
    return _quantize_money(max(total - paid_total, Decimal("0.00")))


def get_or_create_pending_booking_payment_receipt(
    db: Session,
    *,
    booking: Booking,
    snapshot: BookingReceiptSnapshot,
) -> PaymentReceipt:
    pending = db.scalar(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.booking_id == booking.id,
            PaymentReceipt.status == "PENDING",
            PaymentReceipt.final_invoice_note_id.is_(None),
        )
        .order_by(PaymentReceipt.created_at.desc(), PaymentReceipt.id.desc())
        .with_for_update()
        .limit(1)
    )
    amount_due = remaining_booking_amount_due(db, booking=booking)
    metadata = {
        "booking_id": str(snapshot.booking_id),
        "session_id": str(snapshot.session_id),
        "booking_status": booking.status.value if hasattr(booking.status, "value") else str(booking.status),
        "session_status": snapshot.session_status,
        "activity_name": snapshot.activity_name,
        "student_name": snapshot.student_name,
        "session_time_label": snapshot.session_time_label,
    }
    if pending is None:
        pending = PaymentReceipt(
            customer_id=snapshot.customer_id,
            student_id=snapshot.student_id,
            booking_id=snapshot.booking_id,
            legal_entity_id=snapshot.legal_entity_id,
            currency=snapshot.currency,
            amount_paid=amount_due,
            reservation_label=snapshot.reservation_label,
            scheduled_service_date=snapshot.service_date,
            location_label=snapshot.location_label,
            receipt_metadata=metadata,
        )
        db.add(pending)
        db.flush()
        return pending

    pending.customer_id = snapshot.customer_id
    pending.student_id = snapshot.student_id
    pending.legal_entity_id = snapshot.legal_entity_id
    pending.currency = snapshot.currency
    pending.amount_paid = amount_due
    pending.reservation_label = snapshot.reservation_label
    pending.scheduled_service_date = snapshot.service_date
    pending.location_label = snapshot.location_label
    pending.receipt_metadata = metadata
    pending.updated_at = _utcnow()
    db.add(pending)
    db.flush()
    return pending


def create_payment_receipt_public_token(*, client_id: UUID, receipt_id: UUID) -> str:
    payload = {
        "scope": PAYMENT_RECEIPT_PUBLIC_PAYMENT_TOKEN_SCOPE,
        "client_id": str(client_id),
        "receipt_id": str(receipt_id),
        "exp": int((_utcnow() + timedelta(days=365)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def assert_payment_receipt_public_token(*, token: str, client_id: UUID, receipt_id: UUID) -> None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except PyJWTError as exc:
        raise ValueError("Lien de paiement invalide ou expire") from exc
    if str(payload.get("scope") or "") != PAYMENT_RECEIPT_PUBLIC_PAYMENT_TOKEN_SCOPE:
        raise ValueError("Lien de paiement invalide")
    if str(payload.get("client_id") or "") != str(client_id):
        raise ValueError("Lien de paiement invalide")
    if str(payload.get("receipt_id") or "") != str(receipt_id):
        raise ValueError("Lien de paiement invalide")


def payment_receipt_public_payment_url(*, client_id: UUID, receipt_id: UUID) -> str:
    token = create_payment_receipt_public_token(client_id=client_id, receipt_id=receipt_id)
    return f"{_frontend_url(f'/api/v1/public/payments/bookings/{client_id}/{receipt_id}')}?token={token}"


def payment_receipt_checkout_urls(*, client_id: UUID, receipt_id: UUID) -> tuple[str, str, str]:
    token = create_payment_receipt_public_token(client_id=client_id, receipt_id=receipt_id)
    query = f"token={token}"
    success_url = _frontend_url(f"/api/v1/public/payments/bookings/{client_id}/{receipt_id}/return?{query}&state=success")
    cancel_url = _frontend_url(f"/api/v1/public/payments/bookings/{client_id}/{receipt_id}/return?{query}&state=cancel")
    webhook_url = _frontend_url(
        f"/api/v1/public/payments/bookings/{client_id}/{receipt_id}/webhook?{query}"
    )
    return success_url, cancel_url, webhook_url


def _build_manual_reference(*, payment_method_code: str, custom_reference: str | None) -> str:
    method = payment_method_code.strip().upper() or "CARD_ONLINE"
    reference = (custom_reference or "").strip()
    return f"{method}|{reference}" if reference else method


def mark_payment_receipt_completed(
    db: Session,
    *,
    receipt: PaymentReceipt,
    provider_reference: str,
    payment_provider: str | None,
    payment_method: str | None = "CARD_ONLINE",
    paid_at: datetime | None = None,
) -> tuple[PaymentReceipt, ClientManualTransaction, bool]:
    effective_paid_at = paid_at or _utcnow()
    if receipt.manual_transaction_id is not None:
        transaction = db.scalar(
            select(ClientManualTransaction).where(ClientManualTransaction.id == receipt.manual_transaction_id)
        )
        if transaction is not None:
            if receipt.receipt_number is None:
                receipt.receipt_number = reserve_next_payment_receipt_number(db, paid_at=effective_paid_at)
            receipt.status = "COMPLETED"
            receipt.paid_at = effective_paid_at
            receipt.payment_method = payment_method
            receipt.payment_provider = payment_provider
            receipt.payment_transaction_reference = provider_reference
            receipt.updated_at = _utcnow()
            db.add(receipt)
            return receipt, transaction, False

    signed_total = _quantize_money(Decimal("0.00") - Decimal(receipt.amount_paid or 0))
    transaction = ClientManualTransaction(
        user_id=receipt.customer_id,
        student_user_id=receipt.student_id,
        actor_user_id=None,
        transaction_type="PAYMENT",
        status="COMPLETED",
        label=f"Paiement recu - {receipt.reservation_label}",
        description=f"Justificatif de paiement {provider_reference}",
        category="BOOKING_PAYMENT_RECEIPT",
        occurred_at=effective_paid_at,
        amount_excl_vat=signed_total,
        vat_rate=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total_incl_vat=signed_total,
        currency=((receipt.currency or "EUR").strip().upper() or "EUR"),
        reference=_build_manual_reference(
            payment_method_code=payment_method or "CARD_ONLINE",
            custom_reference=f"PSP:{provider_reference}",
        ),
        legal_entity_id=receipt.legal_entity_id,
    )
    db.add(transaction)
    db.flush()

    receipt.receipt_number = receipt.receipt_number or reserve_next_payment_receipt_number(db, paid_at=effective_paid_at)
    receipt.status = "COMPLETED"
    receipt.paid_at = effective_paid_at
    receipt.payment_method = payment_method
    receipt.payment_provider = payment_provider
    receipt.payment_transaction_reference = provider_reference
    receipt.manual_transaction_id = transaction.id
    receipt.updated_at = _utcnow()
    db.add(receipt)
    db.flush()
    return receipt, transaction, True


def render_payment_receipt_attachment(
    db: Session,
    *,
    receipt: PaymentReceipt,
    snapshot: BookingReceiptSnapshot,
) -> tuple[str, bytes]:
    if receipt.receipt_number is None:
        raise ValueError("Payment receipt number missing")
    content = render_payment_receipt_pdf(
        db,
        receipt_number=receipt.receipt_number,
        paid_at=receipt.paid_at or receipt.created_at,
        client_name=snapshot.customer_name,
        client_billing_address=snapshot.customer_billing_address,
        amount_paid=_quantize_money(Decimal(receipt.amount_paid)),
        currency=receipt.currency,
        payment_method=receipt.payment_method,
        payment_provider=receipt.payment_provider,
        payment_transaction_reference=receipt.payment_transaction_reference,
        reservation_label=receipt.reservation_label,
        scheduled_service_date=receipt.scheduled_service_date,
        location_label=receipt.location_label,
        student_name=snapshot.student_name if snapshot.student_name != snapshot.customer_name else None,
        note=PAYMENT_RECEIPT_NOTE_TEXT,
        legal_entity_id=receipt.legal_entity_id,
    )
    return f"{receipt.receipt_number}.pdf", content


def _receipt_email_context(
    *,
    receipt: PaymentReceipt,
    snapshot: BookingReceiptSnapshot,
) -> dict[str, str]:
    paid_at = receipt.paid_at or receipt.created_at
    account_url = _frontend_url("/client?tab=finance&finance_view=transactions")
    return {
        "first_name": (snapshot.customer_first_name or "").strip() or snapshot.customer_name,
        "last_name": (snapshot.customer_last_name or "").strip(),
        "full_name": snapshot.customer_name,
        "client_name": snapshot.customer_name,
        "student_name": snapshot.student_name,
        "receipt_number": receipt.receipt_number or "-",
        "amount_paid": f"{_quantize_money(Decimal(receipt.amount_paid)):.2f}",
        "currency": receipt.currency,
        "payment_date": paid_at.strftime("%d/%m/%Y %H:%M"),
        "paid_at": paid_at.strftime("%d/%m/%Y %H:%M"),
        "payment_method": _normalize_optional(receipt.payment_method) or "-",
        "payment_provider": _normalize_optional(receipt.payment_provider) or "-",
        "payment_reference": _normalize_optional(receipt.payment_transaction_reference) or "-",
        "reservation_label": receipt.reservation_label,
        "scheduled_service_date": receipt.scheduled_service_date.strftime("%d/%m/%Y") if receipt.scheduled_service_date else "-",
        "location_label": _normalize_optional(receipt.location_label) or "-",
        "account_url": account_url,
        "transactions_url": account_url,
        "payment_document_notice": PAYMENT_RECEIPT_NOTE_TEXT,
    }


def _send_template_email_with_optional_attachment(
    db: Session,
    *,
    template_code: str,
    to_email: str,
    context: dict[str, str],
    delivery_context: str,
    attachment: tuple[str, bytes] | None = None,
) -> str | None:
    try:
        template = resolve_predefined_template(db, code=template_code)
    except KeyError:
        logger.warning("Unknown predefined template for payment receipt notifications: %s", template_code)
        return None
    if not bool(template.get("active", True)):
        return None
    subject_template = str(template.get("subject") or "").strip()
    body_template = str(template.get("body") or "").strip()
    if not subject_template or not body_template:
        return None
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    attachments = None
    if attachment is not None:
        attachments = [(attachment[0], attachment[1], "application/pdf")]
    return send_email(
        to_email=to_email,
        subject=_render_template(subject_template, context),
        body=_render_template(body_template, context),
        body_format="HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT",
        context=delivery_context,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        attachments=attachments,
    )


def send_payment_receipt_notifications(
    db: Session,
    *,
    receipt: PaymentReceipt,
    snapshot: BookingReceiptSnapshot,
    send_admin_copy: bool = True,
) -> bool:
    recipient_email = snapshot.customer_email
    if recipient_email is None:
        return False
    attachment = render_payment_receipt_attachment(db, receipt=receipt, snapshot=snapshot)
    context = _receipt_email_context(receipt=receipt, snapshot=snapshot)
    sent_any = False
    if _send_template_email_with_optional_attachment(
        db,
        template_code=PAYMENT_RECEIPT_CLIENT_TEMPLATE_CODE,
        to_email=recipient_email,
        context=context,
        delivery_context=PAYMENT_RECEIPT_CONTEXT,
        attachment=attachment,
    ):
        sent_any = True

    if send_admin_copy:
        try:
            template = resolve_predefined_template(db, code=PAYMENT_RECEIPT_ADMIN_TEMPLATE_CODE)
        except KeyError:
            template = None
        if template is not None and bool(template.get("active", True)):
            from app.services.notifications.application.recipients import resolve_admin_booking_notification_recipients

            for admin_recipient in resolve_admin_booking_notification_recipients(db, is_cancellation=False):
                admin_email = _normalize_optional(admin_recipient.email)
                if admin_email is None:
                    continue
                if _send_template_email_with_optional_attachment(
                    db,
                    template_code=PAYMENT_RECEIPT_ADMIN_TEMPLATE_CODE,
                    to_email=admin_email,
                    context=context,
                    delivery_context=PAYMENT_RECEIPT_ADMIN_CONTEXT,
                    attachment=attachment,
                ):
                    sent_any = True
    return sent_any


def build_final_invoice_metadata(
    *,
    booking: Booking,
    snapshot: BookingReceiptSnapshot,
    issued_at: datetime,
    invoice_number: str,
    reconciled_manual_payment_ids: list[UUID],
    total_paid: Decimal,
) -> dict[str, object]:
    total_amount = _quantize_money(Decimal(booking.total_incl_vat_snapshot))
    total_to_pay = _quantize_money(max(total_amount - total_paid, Decimal("0.00")))
    metadata: dict[str, object] = {
        "kind": "INVOICE_RANGE",
        "invoice_number": invoice_number,
        "issued_date": issued_at.date().isoformat(),
        "due_date": issued_at.date().isoformat(),
        "no_due_date": False,
        "start_date": snapshot.service_date.isoformat() if snapshot.service_date is not None else issued_at.date().isoformat(),
        "end_date": snapshot.service_date.isoformat() if snapshot.service_date is not None else issued_at.date().isoformat(),
        "layout": "DETAILED",
        "billing_entity": "PIANO_ACADEMIE",
        "seller_legal_entity_id": str(snapshot.legal_entity_id) if snapshot.legal_entity_id is not None else None,
        "generation_mode": "SERVICE_COMPLETED",
        "group_adjustments_by_type": False,
        "include_discount_adjustments": False,
        "include_supplement_adjustments": False,
        "include_pending": True,
        "include_cancelled": False,
        "included_payment_keys": [_payment_key(source="BOOKING", payment_id=booking.id)],
        "totals_by_currency": {snapshot.currency: f"{total_amount:.2f}"},
        "applied_payment_totals_by_currency": {snapshot.currency: f"{total_paid:.2f}"},
        "total_to_pay_by_currency": {snapshot.currency: f"{total_to_pay:.2f}"},
        "invoice_status": "PAID" if total_to_pay <= Decimal("0.00") else "ISSUED",
        "public_note": snapshot.reservation_label,
        "reconciled_manual_payment_ids": [str(value) for value in reconciled_manual_payment_ids],
        "service_realized_date": snapshot.service_date.isoformat() if snapshot.service_date is not None else None,
    }
    return metadata


def generate_final_invoice_for_booking(
    db: Session,
    *,
    booking: Booking,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
    owner: User,
    author_user_id: UUID | None,
    issued_at: datetime | None = None,
) -> tuple[ClientNoteEntry, dict[str, object], bool]:
    existing = _invoice_note_for_booking(db, booking_id=booking.id)
    if existing is not None:
        note, metadata = existing
        return note, metadata, False
    if booking.status == BookingStatus.CANCELLED:
        raise ValueError("Cancelled bookings cannot generate a final invoice")
    if booking.status == BookingStatus.EXCUSED_ABSENCE:
        raise ValueError("Excused absences cannot generate a final invoice")
    if booking.status not in FINAL_INVOICE_ELIGIBLE_BOOKING_STATUSES:
        raise ValueError("Booking status is not eligible for final invoicing")
    if session_obj.status != SessionStatus.COMPLETED:
        raise ValueError("Final invoice can only be generated once the service is completed")

    snapshot = build_booking_receipt_snapshot(
        db,
        booking=booking,
        session_obj=session_obj,
        course_type=course_type,
        location=location,
        owner=owner,
    )
    effective_issued_at = issued_at or _utcnow()
    if snapshot.legal_entity_id is None:
        invoice_number = reserve_next_invoice_number(db, issued_at=effective_issued_at)
    else:
        invoice_number = InvoiceNumberService.allocate_invoice_number(
            db,
            legal_entity_id=snapshot.legal_entity_id,
            issued_at=effective_issued_at,
        )
    total_paid, _, reconciled_manual_payment_ids = completed_payment_receipt_totals(db, booking_id=booking.id)
    metadata = build_final_invoice_metadata(
        booking=booking,
        snapshot=snapshot,
        issued_at=effective_issued_at,
        invoice_number=invoice_number,
        reconciled_manual_payment_ids=reconciled_manual_payment_ids,
        total_paid=total_paid,
    )
    note = ClientNoteEntry(
        user_id=snapshot.customer_id,
        author_user_id=author_user_id,
        entry_type="AUTO",
        message=_build_invoice_range_note_message(metadata),
    )
    db.add(note)
    db.flush()
    invoice_line = ClientInvoiceLine(
        note_id=note.id,
        user_id=snapshot.customer_id,
        source="BOOKING",
        source_payment_id=booking.id,
        occurred_at=session_obj.start_at_utc,
        label=snapshot.reservation_label,
        amount_excl_vat=_quantize_money(Decimal(booking.price_excl_vat_snapshot)),
        vat_rate=Decimal(booking.vat_rate_snapshot).quantize(Decimal("0.001")),
        vat_amount=_quantize_money(Decimal(booking.vat_amount_snapshot)),
        total_incl_vat=_quantize_money(Decimal(booking.total_incl_vat_snapshot)),
        currency=snapshot.currency,
        billing_entity="PIANO_ACADEMIE",
        seller_legal_entity_id=snapshot.legal_entity_id,
    )
    db.add(invoice_line)
    now = _utcnow()
    for receipt in db.scalars(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.booking_id == booking.id,
            PaymentReceipt.status == "COMPLETED",
        )
        .with_for_update()
    ).all():
        receipt.final_invoice_note_id = note.id
        receipt.final_invoice_generated_at = now
        receipt.updated_at = now
        db.add(receipt)
    return note, metadata, True


def send_final_invoice_email(
    db: Session,
    *,
    customer: User,
    note_id: UUID,
    metadata: dict[str, object],
) -> str | None:
    recipient_email = _normalize_optional(customer.email)
    if recipient_email is None:
        return None
    billing_profile = resolve_billing_profile(db, customer)
    invoice_number = str(metadata.get("invoice_number") or "").strip() or str(note_id)
    invoice_url = _frontend_url(f"/client/invoices/invoice-range:{note_id}/download")
    context = {
        "first_name": (billing_profile.first_name or "").strip() or recipient_email,
        "last_name": (billing_profile.last_name or "").strip(),
        "full_name": _display_name(billing_profile.first_name, billing_profile.last_name, billing_profile.email),
        "client_name": _display_name(billing_profile.first_name, billing_profile.last_name, billing_profile.email),
        "invoice_number": invoice_number,
        "invoice_url": invoice_url,
        "payment_url": invoice_url,
        "amount_due": str(
            (
                metadata.get("total_to_pay_by_currency")
                or {}
            ).get(next(iter((metadata.get("total_to_pay_by_currency") or {"EUR": "0.00"}).keys())), "0.00")
        ),
        "total_incl_vat": str(
            (
                metadata.get("totals_by_currency")
                or {}
            ).get(next(iter((metadata.get("totals_by_currency") or {"EUR": "0.00"}).keys())), "0.00")
        ),
        "currency": next(iter((metadata.get("totals_by_currency") or {"EUR": "0.00"}).keys())),
        "due_date": str(metadata.get("due_date") or ""),
        "issued_date": str(metadata.get("issued_date") or ""),
    }
    try:
        template = resolve_predefined_template(db, code="INVOICE")
    except KeyError:
        return None
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    return send_email(
        to_email=recipient_email,
        subject=_render_template(str(template.get("subject") or "").strip(), context),
        body=_render_template(str(template.get("body") or "").strip(), context),
        body_format="HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT",
        context="CLIENT_FINAL_INVOICE",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )
