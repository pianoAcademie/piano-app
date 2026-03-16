from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Location
from app.models.quote import Prospect, Quote, QuoteEmailOutbox, QuoteEvent, QuoteLine
from app.services.email_delivery import email_delivery_disabled_reason
from app.services.messaging_templates import load_messaging_settings
from app.services.notifications.infrastructure.repository import append_job_run_log, finish_job_run, start_job_run
from app.services.quotes.email_templates import (
    USAGE_CONTEXT_QUOTE_CANCEL,
    USAGE_CONTEXT_QUOTE_REMINDER,
    send_quote_templated_email,
    send_quote_templated_sms,
)
from app.services.quotes.recipient_resolution import resolve_quote_recipient_phone
from app.services.providers.sms import sms_delivery_disabled_reason

JOB_NAME = "quote_daily_lifecycle_job"
DEFAULT_QUOTE_TIMEZONE = "Europe/Paris"
REMINDER_ELIGIBLE_STATUSES = {"sent", "change_requested"}
EXPIRABLE_STATUSES = {"sent", "change_requested"}
ARCHIVABLE_QUOTE_STATUSES = {"created", "sent", "approved", "expired", "change_requested"}


@dataclass(frozen=True)
class QuoteDailyLifecycleSettings:
    reminder_enabled: bool
    reminder_lead_hours: int
    daily_job_local_time: time
    auto_cancel_enabled: bool
    auto_cancel_delay_hours: int
    cancel_notification_enabled: bool
    delivery_enabled: bool
    sms_delivery_enabled: bool
    quote_reminder_template_ref: str | None
    quote_cancel_template_ref: str | None
    quote_reminder_sms_template_ref: str | None
    quote_cancel_sms_template_ref: str | None
    quote_reminder_sms_enabled: bool
    quote_cancel_sms_notification_enabled: bool


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
    return datetime.now(UTC)


def _load_quote_lifecycle_settings(db: Session) -> QuoteDailyLifecycleSettings:
    payload, _ = load_messaging_settings(db)
    raw_time = str(payload.get("quote_daily_job_local_time") or "07:00").strip()
    try:
        parsed_local_time = time.fromisoformat(raw_time)
    except ValueError:
        parsed_local_time = time(hour=7, minute=0)
    return QuoteDailyLifecycleSettings(
        reminder_enabled=bool(payload.get("quote_reminder_enabled", True)),
        reminder_lead_hours=max(int(payload.get("quote_reminder_lead_hours") or 24), 1),
        daily_job_local_time=parsed_local_time.replace(second=0, microsecond=0),
        auto_cancel_enabled=bool(payload.get("quote_auto_cancel_enabled", True)),
        auto_cancel_delay_hours=max(int(payload.get("quote_auto_cancel_delay_hours") or 24), 0),
        cancel_notification_enabled=bool(payload.get("quote_cancel_notification_enabled", True)),
        delivery_enabled=email_delivery_disabled_reason() is None,
        sms_delivery_enabled=sms_delivery_disabled_reason(db) is None,
        quote_reminder_template_ref=str(payload.get("quote_reminder_template_ref") or "").strip() or None,
        quote_cancel_template_ref=str(payload.get("quote_cancel_template_ref") or "").strip() or None,
        quote_reminder_sms_template_ref=str(payload.get("quote_reminder_sms_template_ref") or "").strip() or None,
        quote_cancel_sms_template_ref=str(payload.get("quote_cancel_sms_template_ref") or "").strip() or None,
        quote_reminder_sms_enabled=bool(payload.get("quote_reminder_sms_enabled", False)),
        quote_cancel_sms_notification_enabled=bool(payload.get("quote_cancel_sms_notification_enabled", False)),
    )


def _quote_timezone_name(db: Session, quote: Quote) -> str:
    if quote.location_id is not None:
        location = db.scalar(select(Location).where(Location.id == quote.location_id))
        if location is not None and str(location.timezone or "").strip():
            return str(location.timezone).strip()
    return DEFAULT_QUOTE_TIMEZONE


def _quote_timezone(db: Session, quote: Quote) -> ZoneInfo:
    timezone_name = _quote_timezone_name(db, quote)
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo(DEFAULT_QUOTE_TIMEZONE)


def _trigger_due(
    *,
    now: datetime,
    zone: ZoneInfo,
    reference_at: datetime,
    local_time: time,
) -> bool:
    localized_reference = reference_at.astimezone(zone)
    trigger_at = datetime.combine(localized_reference.date(), local_time, tzinfo=zone)
    return now.astimezone(zone) >= trigger_at


def _load_lines_for_quotes(db: Session, quote_ids: list[UUID]) -> dict[UUID, list[QuoteLine]]:
    if not quote_ids:
        return {}
    rows = db.scalars(
        select(QuoteLine)
        .where(QuoteLine.quote_id.in_(quote_ids))
        .order_by(QuoteLine.quote_id.asc(), QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
    ).all()
    out: dict[UUID, list[QuoteLine]] = {quote_id: [] for quote_id in quote_ids}
    for row in rows:
        out.setdefault(row.quote_id, []).append(row)
    return out


def _queue_email_if_new(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    kind: str,
    usage_context: str,
    recipient_email: str,
    template_ref: str | None,
    now: datetime,
    delivery_enabled: bool,
) -> bool:
    if not delivery_enabled:
        return False
    normalized_recipient = recipient_email.strip().lower()
    message_key = f"{kind}:{quote.id}:{normalized_recipient}"
    existing = db.scalar(select(QuoteEmailOutbox).where(QuoteEmailOutbox.message_key == message_key))
    if existing is not None:
        return False

    row = QuoteEmailOutbox(
        quote_id=quote.id,
        kind=kind,
        message_key=message_key,
        recipient_email=normalized_recipient,
        subject=f"Devis {quote.quote_number}",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()

    rendered, message_id = send_quote_templated_email(
        db,
        quote=quote,
        lines=lines,
        recipient_email=normalized_recipient,
        usage_context=usage_context,
        template_ref=template_ref,
        email_context=f"QUOTE_{kind.upper()}",
    )
    row.subject = rendered.subject
    row.provider_message_id = message_id
    row.status = "sent" if message_id else "failed"
    row.sent_at = now if message_id else None
    row.updated_at = now
    db.add(row)
    return bool(message_id)


def _send_sms_if_enabled(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    kind: str,
    usage_context: str,
    recipient_phone: str,
    template_ref: str | None,
    now: datetime,
    delivery_enabled: bool,
) -> bool:
    if not delivery_enabled:
        return False
    rendered, provider_result = send_quote_templated_sms(
        db,
        quote=quote,
        lines=lines,
        recipient_phone=recipient_phone,
        usage_context=usage_context,
        template_ref=template_ref,
        sms_context=f"QUOTE_{kind.upper()}",
    )
    if not provider_result.ok:
        return False
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_sms_sent",
            actor_type="system",
            payload={
                "kind": kind,
                "usage_context": usage_context,
                "recipient_phone": recipient_phone,
                "template_ref": rendered.template_ref,
                "provider": provider_result.provider_name,
                "provider_status": provider_result.provider_status,
                "provider_message_id": provider_result.provider_message_id,
            },
            created_at=now,
        )
    )
    return True


def run_quote_daily_lifecycle_job(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 2000,
) -> QuoteDailyJobResult:
    ts = now or _utcnow()
    settings = _load_quote_lifecycle_settings(db)
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
        metadata_json={
            "limit": limit,
            "quote_reminder_enabled": settings.reminder_enabled,
            "quote_auto_cancel_enabled": settings.auto_cancel_enabled,
            "quote_daily_job_local_time": settings.daily_job_local_time.strftime("%H:%M"),
        },
    )
    try:
        if settings.reminder_enabled:
            reminder_quotes = db.scalars(
                select(Quote)
                .where(
                    Quote.status.in_(sorted(REMINDER_ELIGIBLE_STATUSES)),
                    Quote.expires_at.is_not(None),
                    Quote.reminder_sent_at.is_(None),
                )
                .order_by(Quote.expires_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            quote_lines_by_id = _load_lines_for_quotes(db, [quote.id for quote in reminder_quotes])
            for quote in reminder_quotes:
                checked += 1
                if quote.expires_at is None or quote.expires_at <= ts:
                    continue
                zone = _quote_timezone(db, quote)
                reminder_reference = quote.expires_at - timedelta(hours=settings.reminder_lead_hours)
                if not _trigger_due(
                    now=ts,
                    zone=zone,
                    reference_at=reminder_reference,
                    local_time=settings.daily_job_local_time,
                ):
                    continue
                recipient = (
                    str((quote.meta or {}).get("recipient_email") or "").strip().lower()
                    or str((quote.meta or {}).get("prospect_email") or "").strip().lower()
                )
                recipient_phone = resolve_quote_recipient_phone(db, quote)
                if not recipient and not recipient_phone:
                    failed += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="warning",
                        message="Reminder skipped: missing recipient",
                        context_json={"quote_id": str(quote.id)},
                    )
                    continue
                email_sent = False
                sms_sent = False
                try:
                    if recipient:
                        email_sent = _queue_email_if_new(
                            db,
                            quote=quote,
                            lines=quote_lines_by_id.get(quote.id, []),
                            kind="reminder",
                            usage_context=USAGE_CONTEXT_QUOTE_REMINDER,
                            recipient_email=recipient,
                            template_ref=settings.quote_reminder_template_ref,
                            now=ts,
                            delivery_enabled=settings.delivery_enabled,
                        )
                    if recipient_phone and settings.quote_reminder_sms_enabled:
                        sms_sent = _send_sms_if_enabled(
                            db,
                            quote=quote,
                            lines=quote_lines_by_id.get(quote.id, []),
                            kind="reminder",
                            usage_context=USAGE_CONTEXT_QUOTE_REMINDER,
                            recipient_phone=recipient_phone,
                            template_ref=settings.quote_reminder_sms_template_ref,
                            now=ts,
                            delivery_enabled=settings.sms_delivery_enabled,
                        )
                except Exception as exc:
                    failed += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="error",
                        message="Reminder send failed",
                        context_json={"quote_id": str(quote.id), "error": str(exc)},
                    )
                    continue
                if email_sent or sms_sent:
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
                            created_at=ts,
                        )
                    )

        expiring_quotes = db.scalars(
            select(Quote)
            .where(
                Quote.status.in_(sorted(EXPIRABLE_STATUSES)),
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
            quote.expired_at = quote.expired_at or ts
            quote.updated_at = ts
            db.add(quote)
            db.add(
                QuoteEvent(
                    quote_id=quote.id,
                    event_type="quote_expired",
                    actor_type="system",
                    payload={},
                    created_at=ts,
                )
            )
            expired += 1

        if settings.auto_cancel_enabled:
            cancellable_quotes = db.scalars(
                select(Quote)
                .where(
                    Quote.status == "expired",
                    Quote.cancelled_at.is_(None),
                    Quote.expires_at.is_not(None),
                )
                .order_by(Quote.expires_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            quote_lines_by_id = _load_lines_for_quotes(db, [quote.id for quote in cancellable_quotes])
            for quote in cancellable_quotes:
                checked += 1
                if quote.expires_at is None:
                    continue
                zone = _quote_timezone(db, quote)
                cancel_reference = quote.expires_at + timedelta(hours=settings.auto_cancel_delay_hours)
                if not _trigger_due(
                    now=ts,
                    zone=zone,
                    reference_at=cancel_reference,
                    local_time=settings.daily_job_local_time,
                ):
                    continue
                quote.status = "cancelled"
                quote.cancelled_at = ts
                quote.updated_at = ts
                db.add(quote)
                db.add(
                    QuoteEvent(
                        quote_id=quote.id,
                        event_type="quote_cancelled",
                        actor_type="system",
                        payload={"automatic": True},
                        created_at=ts,
                    )
                )
                cancelled += 1

                if not settings.cancel_notification_enabled:
                    recipient = ""
                else:
                    recipient = (
                        str((quote.meta or {}).get("recipient_email") or "").strip().lower()
                        or str((quote.meta or {}).get("prospect_email") or "").strip().lower()
                    )
                recipient_phone = resolve_quote_recipient_phone(db, quote)
                if not recipient and not recipient_phone:
                    continue
                try:
                    if recipient and settings.cancel_notification_enabled:
                        _queue_email_if_new(
                            db,
                            quote=quote,
                            lines=quote_lines_by_id.get(quote.id, []),
                            kind="cancel",
                            usage_context=USAGE_CONTEXT_QUOTE_CANCEL,
                            recipient_email=recipient,
                            template_ref=settings.quote_cancel_template_ref,
                            now=ts,
                            delivery_enabled=settings.delivery_enabled,
                        )
                    if recipient_phone and settings.quote_cancel_sms_notification_enabled:
                        _send_sms_if_enabled(
                            db,
                            quote=quote,
                            lines=quote_lines_by_id.get(quote.id, []),
                            kind="cancel",
                            usage_context=USAGE_CONTEXT_QUOTE_CANCEL,
                            recipient_phone=recipient_phone,
                            template_ref=settings.quote_cancel_sms_template_ref,
                            now=ts,
                            delivery_enabled=settings.sms_delivery_enabled,
                        )
                except Exception as exc:
                    failed += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="error",
                        message="Automatic cancel notification failed",
                        context_json={"quote_id": str(quote.id), "error": str(exc)},
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
                    Quote.status.in_(sorted(ARCHIVABLE_QUOTE_STATUSES)),
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
