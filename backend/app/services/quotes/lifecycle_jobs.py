from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.quote import Prospect, Quote, QuoteEmailOutbox, QuoteEvent
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_sender_profile
from app.services.notifications.infrastructure.repository import append_job_run_log, finish_job_run, start_job_run


JOB_NAME = "quote_daily_lifecycle_job"


@dataclass(frozen=True)
class QuoteDailyJobResult:
    checked: int
    reminders_sent: int
    expired: int
    cancelled: int
    archived_prospects: int
    failed: int
    job_run_id: UUID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _queue_email_if_new(
    db: Session,
    *,
    quote_id: UUID,
    kind: str,
    recipient_email: str,
    subject: str,
    body: str,
    now: datetime,
) -> bool:
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    message_key = f"{kind}:{quote_id}:{recipient_email.lower()}"
    existing = db.scalar(
        select(QuoteEmailOutbox).where(
            QuoteEmailOutbox.message_key == message_key,
        )
    )
    if existing is not None:
        return False
    row = QuoteEmailOutbox(
        quote_id=quote_id,
        kind=kind,
        message_key=message_key,
        recipient_email=recipient_email,
        subject=subject,
        status="queued",
    )
    db.add(row)
    db.flush()
    message_id = send_email(
        to_email=recipient_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context=f"QUOTE_{kind.upper()}",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )
    row.status = "sent" if message_id else "failed"
    row.provider_message_id = message_id
    row.sent_at = now if message_id else None
    row.updated_at = now
    db.add(row)
    return bool(message_id)


def run_quote_daily_lifecycle_job(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 2000,
) -> QuoteDailyJobResult:
    ts = now or _utcnow()
    reminders_sent = 0
    expired = 0
    cancelled = 0
    archived_prospects = 0
    failed = 0
    checked = 0

    job_run = start_job_run(
        db,
        job_name=JOB_NAME,
        job_key=JOB_NAME,
        triggered_by="scheduler",
        started_at=ts,
        metadata_json={"limit": limit},
    )
    try:
        reminder_window_start = ts + timedelta(hours=24)
        reminder_window_end = ts + timedelta(hours=25)

        reminder_quotes = db.scalars(
            select(Quote)
            .where(
                Quote.status == "sent",
                Quote.expires_at.is_not(None),
                Quote.expires_at >= reminder_window_start,
                Quote.expires_at <= reminder_window_end,
                Quote.reminder_sent_at.is_(None),
            )
            .order_by(Quote.expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()

        for quote in reminder_quotes:
            checked += 1
            recipient = (
                str((quote.meta or {}).get("recipient_email") or "").strip().lower()
                or str((quote.meta or {}).get("prospect_email") or "").strip().lower()
            )
            if not recipient:
                failed += 1
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="warning",
                    message="Reminder skipped: missing recipient",
                    context_json={"quote_id": str(quote.id)},
                )
                continue
            ok = _queue_email_if_new(
                db,
                quote_id=quote.id,
                kind="reminder",
                recipient_email=recipient,
                subject=f"Rappel devis {quote.quote_number}",
                body=(
                    f"Votre devis {quote.quote_number} expire le "
                    f"{quote.expires_at.strftime('%d/%m/%Y %H:%M') if quote.expires_at else '-'}."
                ),
                now=ts,
            )
            if ok:
                reminders_sent += 1
                quote.reminder_sent_at = ts
                quote.updated_at = ts
                db.add(quote)
                db.add(
                    QuoteEvent(
                        quote_id=quote.id,
                        event_type="quote_reminder_sent",
                        actor_type="system",
                        payload={"kind": "reminder"},
                    )
                )

        expiring_quotes = db.scalars(
            select(Quote)
            .where(
                Quote.status == "sent",
                Quote.expires_at.is_not(None),
                Quote.expires_at < ts,
            )
            .order_by(Quote.expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for quote in expiring_quotes:
            checked += 1
            quote.status = "expired"
            quote.expired_at = ts
            quote.updated_at = ts
            db.add(quote)
            db.add(
                QuoteEvent(
                    quote_id=quote.id,
                    event_type="quote_expired",
                    actor_type="system",
                    payload={},
                )
            )
            expired += 1

        cancellable_quotes = db.scalars(
            select(Quote)
            .where(
                Quote.status == "expired",
                Quote.expired_at.is_not(None),
                Quote.expired_at < (ts - timedelta(hours=24)),
            )
            .order_by(Quote.expired_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for quote in cancellable_quotes:
            checked += 1
            quote.status = "cancelled"
            quote.cancelled_at = ts
            quote.updated_at = ts
            db.add(quote)
            db.add(
                QuoteEvent(
                    quote_id=quote.id,
                    event_type="quote_cancelled",
                    actor_type="system",
                    payload={},
                )
            )
            cancelled += 1
            recipient = (
                str((quote.meta or {}).get("recipient_email") or "").strip().lower()
                or str((quote.meta or {}).get("prospect_email") or "").strip().lower()
            )
            if recipient:
                _queue_email_if_new(
                    db,
                    quote_id=quote.id,
                    kind="cancel",
                    recipient_email=recipient,
                    subject=f"Devis {quote.quote_number} annule",
                    body=f"Le devis {quote.quote_number} est annule car expire.",
                    now=ts,
                )

        archival_candidates = db.scalars(
            select(Prospect)
            .where(Prospect.status.in_(["active", "new", "lost"]))
            .order_by(Prospect.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for prospect in archival_candidates:
            checked += 1
            has_active_quote = db.scalar(
                select(Quote.id)
                .where(
                    Quote.prospect_id == prospect.id,
                    Quote.status.in_(["created", "sent", "approved", "expired", "change_requested"]),
                )
                .limit(1)
            )
            if has_active_quote is not None:
                continue
            has_non_converted_quote = db.scalar(
                select(Quote.id)
                .where(
                    Quote.prospect_id == prospect.id,
                    Quote.context_type == "acquisition",
                    Quote.status.in_(["cancelled", "rejected"]),
                )
                .limit(1)
            )
            if has_non_converted_quote is None:
                continue
            prospect.status = "archived"
            prospect.updated_at = ts
            db.add(prospect)
            archived_prospects += 1

        finish_job_run(
            db,
            job_run=job_run,
            status="success" if failed == 0 else "warning",
            finished_at=ts,
            items_scanned=checked,
            items_processed=checked,
            items_sent=reminders_sent,
            items_skipped=max(checked - reminders_sent - failed, 0),
            items_failed=failed,
            summary_text=(
                f"reminders={reminders_sent} expired={expired} "
                f"cancelled={cancelled} archived_marked={archived_prospects}"
            ),
        )
        return QuoteDailyJobResult(
            checked=checked,
            reminders_sent=reminders_sent,
            expired=expired,
            cancelled=cancelled,
            archived_prospects=archived_prospects,
            failed=failed,
            job_run_id=job_run.id,
        )
    except Exception as exc:
        finish_job_run(
            db,
            job_run=job_run,
            status="failed",
            finished_at=ts,
            items_scanned=checked,
            items_processed=checked,
            items_sent=reminders_sent,
            items_skipped=0,
            items_failed=max(failed, 1),
            error_text=str(exc),
        )
        raise
