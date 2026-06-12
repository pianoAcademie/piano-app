from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import html
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client_record import BankTransferOrder, ClientNoteEntry
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_messaging_delivery_config
from app.services.notifications.application.recipients import resolve_admin_bank_transfer_review_recipients
from app.services.notifications.infrastructure.repository import get_job_cursor, upsert_job_cursor


BANK_TRANSFER_ORDER_STATUS_PENDING = "pending_bank_transfer"
BANK_TRANSFER_ORDER_STATUS_EXPIRED = "expired"
BANK_TRANSFER_REVIEW_DIGEST_CURSOR = "bank_transfer_review_daily_digest"
BANK_TRANSFER_REVIEW_DIGEST_LOCAL_TIME = time(8, 0)
PARIS_TZ = ZoneInfo("Europe/Paris")
UTC = timezone.utc


@dataclass(frozen=True)
class BankTransferExpirationJobResult:
    checked: int
    expired: int


@dataclass(frozen=True)
class BankTransferReviewDigestJobResult:
    checked: int
    sent: int
    skipped: int
    failed: int


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _local_digest_date(now: datetime) -> date:
    return _aware_utc(now).astimezone(PARIS_TZ).date()


def _is_due_for_digest(now: datetime) -> bool:
    local_now = _aware_utc(now).astimezone(PARIS_TZ)
    return local_now.time().replace(second=0, microsecond=0) >= BANK_TRANSFER_REVIEW_DIGEST_LOCAL_TIME


def _digest_already_processed(db: Session, *, digest_date: date) -> bool:
    cursor = get_job_cursor(db, job_name=BANK_TRANSFER_REVIEW_DIGEST_CURSOR)
    if cursor is None or cursor.last_processed_at is None:
        return False
    return _aware_utc(cursor.last_processed_at).astimezone(PARIS_TZ).date() >= digest_date


def _mark_digest_processed(db: Session, *, digest_date: date, now: datetime) -> None:
    processed_at = datetime.combine(digest_date, BANK_TRANSFER_REVIEW_DIGEST_LOCAL_TIME, tzinfo=PARIS_TZ).astimezone(UTC)
    upsert_job_cursor(db, job_name=BANK_TRANSFER_REVIEW_DIGEST_CURSOR, last_processed_at=processed_at, updated_at=_aware_utc(now))


def _format_amount(value: object, currency: str) -> str:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return f"{value} {currency}".strip()
    return f"{amount:.2f} {currency}".strip()


def _format_local_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return _aware_utc(value).astimezone(PARIS_TZ).strftime("%d/%m/%Y %H:%M")


def _display_name(user: User) -> str:
    name = " ".join(part.strip() for part in (user.first_name or "", user.last_name or "") if part and part.strip())
    return name or user.email


def _invoice_number(note: ClientNoteEntry | None) -> str:
    if note is None:
        return "-"
    message = note.message or ""
    marker = "Facture "
    if marker in message:
        tail = message.split(marker, 1)[1].strip()
        return tail.split(" ", 1)[0].strip() or "-"
    return "-"


def _review_digest_status_label(status: str | None) -> str:
    if status == BANK_TRANSFER_ORDER_STATUS_PENDING:
        return "A verifier"
    if status == BANK_TRANSFER_ORDER_STATUS_EXPIRED:
        return "Expire - relancer"
    return str(status or "")


def _review_digest_row_html(rows: list[tuple[BankTransferOrder, User, ClientNoteEntry | None]], *, empty_message: str) -> str:
    if not rows:
        return f"<tr><td colspan='7' style='padding:10px;color:#6b7280;'>{html.escape(empty_message)}</td></tr>"
    return "".join(
        "<tr>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;'>{html.escape(order.order_reference)}</td>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;'>{html.escape(_invoice_number(note))}</td>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;'>{html.escape(_display_name(customer))}<br>"
        f"<span style='color:#6b7280;'>{html.escape(customer.email)}</span></td>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;text-align:right;'>{html.escape(_format_amount(order.amount_incl_vat, order.currency))}</td>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;'>{html.escape(_format_local_datetime(order.created_at))}</td>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;'>{html.escape(_format_local_datetime(order.expires_at))}</td>"
        f"<td style='padding:8px 10px;border-top:1px solid #e5e7eb;'>{html.escape(_review_digest_status_label(order.status))}</td>"
        "</tr>"
        for order, customer, note in rows
    )


def _review_digest_table_html(rows: list[tuple[BankTransferOrder, User, ClientNoteEntry | None]], *, empty_message: str) -> str:
    rows_html = _review_digest_row_html(rows, empty_message=empty_message)
    return (
        "<table style='border-collapse:collapse;width:100%;font-size:13px;'>"
        "<thead><tr style='background:#f3f4f6;'>"
        "<th style='text-align:left;padding:8px 10px;'>Reference</th>"
        "<th style='text-align:left;padding:8px 10px;'>Facture</th>"
        "<th style='text-align:left;padding:8px 10px;'>Client</th>"
        "<th style='text-align:right;padding:8px 10px;'>Montant</th>"
        "<th style='text-align:left;padding:8px 10px;'>Cree le</th>"
        "<th style='text-align:left;padding:8px 10px;'>Expire le</th>"
        "<th style='text-align:left;padding:8px 10px;'>Statut</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def _latest_review_digest_rows(
    rows: list[tuple[BankTransferOrder, User, ClientNoteEntry | None]],
    *,
    limit: int,
) -> list[tuple[BankTransferOrder, User, ClientNoteEntry | None]]:
    latest_by_invoice: dict[object, tuple[BankTransferOrder, User, ClientNoteEntry | None]] = {}
    for row in rows:
        order = row[0]
        key: object
        if order.invoice_note_id is not None:
            key = ("invoice", order.customer_id, order.invoice_note_id)
        else:
            key = ("order", order.id)
        current = latest_by_invoice.get(key)
        if current is None or order.created_at > current[0].created_at:
            latest_by_invoice[key] = row
    return sorted(
        latest_by_invoice.values(),
        key=lambda row: (
            0 if row[0].status == BANK_TRANSFER_ORDER_STATUS_PENDING else 1,
            row[0].created_at,
            str(row[0].id),
        ),
    )[:limit]


def _build_review_digest_body(rows: list[tuple[BankTransferOrder, User, ClientNoteEntry | None]], *, now: datetime) -> str:
    generated_at = _format_local_datetime(_aware_utc(now))
    pending_rows = [row for row in rows if row[0].status == BANK_TRANSFER_ORDER_STATUS_PENDING]
    expired_rows = [row for row in rows if row[0].status == BANK_TRANSFER_ORDER_STATUS_EXPIRED]
    pending_table = _review_digest_table_html(pending_rows, empty_message="Aucun virement bancaire en attente.")
    expired_table = _review_digest_table_html(expired_rows, empty_message="Aucun virement bancaire expire a relancer.")
    return (
        "<div style='font-family:Arial,sans-serif;color:#111827;font-size:14px;line-height:1.45;'>"
        "<h1 style='font-size:18px;margin:0 0 12px;'>Virements bancaires a verifier</h1>"
        f"<p style='margin:0 0 14px;'>Generation : {html.escape(generated_at)}.</p>"
        "<p style='margin:0 0 14px;'>Ces commandes ont ete choisies en paiement par virement. "
        "Les virements en attente doivent etre verifies sur le compte bancaire ; les demandes expirees doivent etre relancees si le paiement n'a pas ete retrouve. "
        "Une fois le virement retrouve sur le compte, utilisez l'action admin <strong>V€</strong> sur la facture pour la marquer payee.</p>"
        "<h2 style='font-size:16px;margin:18px 0 8px;'>A verifier</h2>"
        f"{pending_table}"
        "<h2 style='font-size:16px;margin:18px 0 8px;'>Expires a relancer</h2>"
        f"{expired_table}"
        "</div>"
    )


def run_bank_transfer_order_expiration_job(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> BankTransferExpirationJobResult:
    current = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(BankTransferOrder)
        .where(
            BankTransferOrder.status == BANK_TRANSFER_ORDER_STATUS_PENDING,
            BankTransferOrder.expires_at <= current,
        )
        .order_by(BankTransferOrder.expires_at.asc())
        .limit(limit)
    ).all()
    for row in rows:
        row.status = BANK_TRANSFER_ORDER_STATUS_EXPIRED
        row.expired_at = current
        row.updated_at = current
        db.add(row)
    return BankTransferExpirationJobResult(checked=len(rows), expired=len(rows))


def run_bank_transfer_review_digest_job(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> BankTransferReviewDigestJobResult:
    current = now or datetime.now(UTC)
    digest_date = _local_digest_date(current)
    if not _is_due_for_digest(current) or _digest_already_processed(db, digest_date=digest_date):
        return BankTransferReviewDigestJobResult(checked=0, sent=0, skipped=1, failed=0)

    raw_rows = db.execute(
        select(BankTransferOrder, User, ClientNoteEntry)
        .join(User, User.id == BankTransferOrder.customer_id)
        .outerjoin(ClientNoteEntry, ClientNoteEntry.id == BankTransferOrder.invoice_note_id)
        .where(BankTransferOrder.status.in_([BANK_TRANSFER_ORDER_STATUS_PENDING, BANK_TRANSFER_ORDER_STATUS_EXPIRED]))
        .order_by(BankTransferOrder.created_at.desc(), BankTransferOrder.id.desc())
        .limit(max(limit * 3, limit))
    ).all()
    rows = _latest_review_digest_rows(
        [(order, customer, note) for order, customer, note in raw_rows],
        limit=limit,
    )
    recipients = [recipient.email for recipient in resolve_admin_bank_transfer_review_recipients(db) if recipient.email]
    if not rows or not recipients:
        _mark_digest_processed(db, digest_date=digest_date, now=current)
        return BankTransferReviewDigestJobResult(checked=len(rows), sent=0, skipped=1, failed=0)

    delivery_config = resolve_messaging_delivery_config(db)
    body = _build_review_digest_body(rows, now=current)
    subject = f"Virements bancaires a verifier - {digest_date.strftime('%d/%m/%Y')}"
    sent = 0
    failed = 0
    for recipient_email in recipients:
        message_id = send_email(
            to_email=recipient_email,
            subject=subject,
            body=body,
            body_format="HTML",
            context="BANK_TRANSFER_REVIEW_DIGEST",
            from_email=delivery_config.from_email,
            sender_label="Systeme",
            communication_type="ADMIN_NOTIFICATION",
        )
        if message_id:
            sent += 1
        else:
            failed += 1
    _mark_digest_processed(db, digest_date=digest_date, now=current)
    return BankTransferReviewDigestJobResult(checked=len(rows), sent=sent, skipped=0, failed=failed)
