from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.admin_clients import (
    INVOICE_RANGE_NOTE_PREFIX,
    _invoice_range_pending_check_coverage,
    _parse_invoice_range_note_entry,
    send_admin_client_range_invoice_email,
)
from app.models.client_record import ClientNoteEntry
from app.models.user import User, UserRole
from app.schemas.admin import AdminRangeInvoiceEmailRequest

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")


@dataclass(frozen=True)
class InvoiceReminderJobResult:
    checked: int
    sent: int
    skipped: int
    failed: int


def _local_today(now: datetime) -> date:
    aware_now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return aware_now.astimezone(PARIS_TZ).date()


def _invoice_amount_due_positive(metadata: dict[str, object]) -> bool:
    raw_totals = metadata.get("total_to_pay_by_currency") or metadata.get("totals_by_currency") or {}
    if not isinstance(raw_totals, dict):
        return False
    for raw_amount in raw_totals.values():
        try:
            if Decimal(str(raw_amount)) > Decimal("0.00"):
                return True
        except (InvalidOperation, ValueError):
            continue
    return False


def _invoice_is_covered_by_received_checks(db: Session, metadata: dict[str, object]) -> bool:
    status_value, _, _ = _invoice_range_pending_check_coverage(db, metadata=metadata)
    return status_value == "COVERED"


def invoice_is_due_for_j_minus_one_reminder(
    metadata: dict[str, object],
    *,
    target_due_date: date,
    db: Session | None = None,
) -> bool:
    if bool(metadata.get("no_due_date")):
        return False
    if str(metadata.get("invoice_status") or "ISSUED").strip().upper() != "ISSUED":
        return False
    if metadata.get("reminded_at"):
        return False
    try:
        due_date = date.fromisoformat(str(metadata.get("due_date") or ""))
    except ValueError:
        return False
    if due_date != target_due_date:
        return False
    if db is not None and _invoice_is_covered_by_received_checks(db, metadata):
        return False
    return _invoice_amount_due_positive(metadata)


def run_invoice_due_reminder_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 200,
) -> InvoiceReminderJobResult:
    target_due_date = _local_today(now) + timedelta(days=1)
    notes = db.scalars(
        select(ClientNoteEntry)
        .where(
            ClientNoteEntry.message.contains(INVOICE_RANGE_NOTE_PREFIX),
            ClientNoteEntry.message.contains(target_due_date.isoformat()),
        )
        .order_by(ClientNoteEntry.created_at.asc(), ClientNoteEntry.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).all()
    actor = db.scalar(
        select(User)
        .where(User.role == UserRole.ADMIN)
        .order_by(User.created_at.asc())
        .limit(1)
    )

    checked = 0
    sent = 0
    skipped = 0
    failed = 0

    if actor is None:
        return InvoiceReminderJobResult(checked=len(notes), sent=0, skipped=0, failed=len(notes))

    for note in notes:
        checked += 1
        metadata = _parse_invoice_range_note_entry(note)
        if metadata is None or not invoice_is_due_for_j_minus_one_reminder(
            metadata,
            target_due_date=target_due_date,
            db=db,
        ):
            skipped += 1
            continue
        try:
            send_admin_client_range_invoice_email(
                client_id=UUID(str(note.user_id)),
                note_id=UUID(str(note.id)),
                payload=AdminRangeInvoiceEmailRequest(
                    kind="REMINDER",
                    to_emails=None,
                    subject=None,
                    body=None,
                    body_format="TEXT",
                    include_change_summary=False,
                ),
                db=db,
                actor=actor,
            )
            sent += 1
        except HTTPException as exc:
            db.rollback()
            failed += 1
            logger.exception(
                "Invoice reminder failed | note_id=%s | detail=%s",
                note.id,
                exc.detail,
            )
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("Unexpected invoice reminder error | note_id=%s", note.id)

    return InvoiceReminderJobResult(checked=checked, sent=sent, skipped=skipped, failed=failed)
