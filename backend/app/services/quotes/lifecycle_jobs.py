from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Location
from app.models.quote import Prospect, Quote, QuoteEmailOutbox, QuoteEvent, QuoteLine
from app.models.user import User
from app.services.email_delivery import email_delivery_disabled_reason
from app.services.email_delivery import send_email
from app.services.messaging_templates import load_messaging_settings
from app.services.notifications.application.recipients import resolve_admin_quote_expiry_digest_recipients
from app.services.notifications.infrastructure.repository import append_job_run_log, finish_job_run, get_job_cursor, start_job_run, upsert_job_cursor
from app.services.quotes.email_templates import (
    USAGE_CONTEXT_QUOTE_CANCEL,
    USAGE_CONTEXT_QUOTE_REMINDER,
    send_quote_templated_email,
    send_quote_templated_sms,
)
from app.services.quotes.recipient_resolution import resolve_quote_recipient_phone
from app.services.providers.sms import sms_delivery_disabled_reason

JOB_NAME = "quote_daily_lifecycle_job"
QUOTE_EXPIRY_DIGEST_CURSOR = "quote_expiring_today_admin_digest"
QUOTE_EXPIRY_DIGEST_UTC_TIME = time(hour=5, minute=0)
DEFAULT_QUOTE_TIMEZONE = "Europe/Paris"
REMINDER_ELIGIBLE_STATUSES = {"sent", "change_requested"}
EXPIRABLE_STATUSES = {"sent", "change_requested"}
ARCHIVABLE_QUOTE_STATUSES = {"created", "sent", "approved", "expired", "change_requested"}


@dataclass(frozen=True)
class QuoteDailyLifecycleSettings:
    reminder_enabled: bool
    reminder_lead_hours_values: tuple[int, ...]
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
    expiry_digest_sent: int
    expired: int
    cancelled: int
    archived_prospects: int
    failed: int
    job_run_id: UUID


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json_object(value: object | None) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _load_quote_lifecycle_settings(db: Session) -> QuoteDailyLifecycleSettings:
    payload, _ = load_messaging_settings(db)
    raw_time = str(payload.get("quote_daily_job_local_time") or "07:00").strip()
    try:
        parsed_local_time = time.fromisoformat(raw_time)
    except ValueError:
        parsed_local_time = time(hour=7, minute=0)
    return QuoteDailyLifecycleSettings(
        reminder_enabled=bool(payload.get("quote_reminder_enabled", True)),
        reminder_lead_hours_values=tuple(
            sorted(
                {
                    max(int(item), 1)
                    for item in (payload.get("quote_reminder_lead_hours_values") or [payload.get("quote_reminder_lead_hours") or 24])
                    if str(item or "").strip()
                },
                reverse=True,
            )
            or (24,)
        ),
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


def _trigger_due_today(
    *,
    now: datetime,
    zone: ZoneInfo,
    reference_at: datetime,
    local_time: time,
) -> bool:
    localized_reference = reference_at.astimezone(zone)
    trigger_at = datetime.combine(localized_reference.date(), local_time, tzinfo=zone)
    localized_now = now.astimezone(zone)
    return localized_now.date() == trigger_at.date() and localized_now >= trigger_at


def _quote_reminder_offsets_sent(quote: Quote) -> set[int]:
    meta = quote.meta if isinstance(quote.meta, dict) else {}
    raw = meta.get("reminder_offsets_sent")
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for item in raw:
        try:
            parsed = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            out.add(parsed)
    return out


def _mark_quote_reminder_offset_sent(quote: Quote, *, offset_hours: int, now: datetime) -> None:
    meta = dict(quote.meta or {})
    sent_offsets = _quote_reminder_offsets_sent(quote)
    sent_offsets.add(offset_hours)
    meta["reminder_offsets_sent"] = sorted(sent_offsets, reverse=True)
    quote.meta = meta
    quote.reminder_sent_at = now
    quote.updated_at = now


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


def _quote_expiry_digest_date(now: datetime) -> date | None:
    today = now.astimezone(UTC).date()
    trigger_at = datetime.combine(today, QUOTE_EXPIRY_DIGEST_UTC_TIME, tzinfo=UTC)
    return today if now.astimezone(UTC) >= trigger_at else None


def _quote_expiry_digest_already_processed(db: Session, *, digest_date: date) -> bool:
    cursor = get_job_cursor(db, job_name=QUOTE_EXPIRY_DIGEST_CURSOR)
    if cursor is None or cursor.last_processed_at is None:
        return False
    return cursor.last_processed_at.astimezone(UTC).date() >= digest_date


def _mark_quote_expiry_digest_processed(db: Session, *, digest_date: date, now: datetime) -> None:
    processed_at = datetime.combine(digest_date, QUOTE_EXPIRY_DIGEST_UTC_TIME, tzinfo=UTC)
    upsert_job_cursor(db, job_name=QUOTE_EXPIRY_DIGEST_CURSOR, last_processed_at=processed_at, updated_at=now)


def _quote_meta_student_name(quote: Quote) -> str:
    quote_meta = _json_object(quote.meta)
    normalized = _json_object(_json_object(quote_meta.get("typeform_intake")).get("normalized_payload"))
    for first_key, last_key in (
        ("child_first_name", "child_last_name"),
        ("student_first_name", "student_last_name"),
        ("first_name", "last_name"),
    ):
        full_name = _join_name(normalized.get(first_key), normalized.get(last_key))
        if full_name:
            return full_name
    return ""


def _join_name(first_name: object | None, last_name: object | None) -> str:
    return f"{str(first_name or '').strip()} {str(last_name or '').strip()}".strip()


def _quote_student_name(quote: Quote, prospect: Prospect | None, client: User | None) -> str:
    meta_name = _quote_meta_student_name(quote)
    if meta_name:
        return meta_name
    if client is not None:
        client_name = _join_name(client.first_name, client.last_name)
        if client_name:
            return client_name
    if prospect is not None:
        prospect_name = _join_name(prospect.first_name, prospect.last_name)
        if prospect_name:
            return prospect_name
    return "Eleve non renseigne"


def _format_utc_day_label(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _quote_expiry_digest_rows(
    db: Session,
    *,
    digest_date: date,
    limit: int,
    statuses: set[str] | None = None,
) -> list[tuple[Quote, Prospect | None, User | None]]:
    day_start = datetime.combine(digest_date, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    stmt = (
        select(Quote, Prospect, User)
        .join(Prospect, Prospect.id == Quote.prospect_id, isouter=True)
        .join(User, User.id == Quote.client_id, isouter=True)
        .where(
            Quote.expires_at.is_not(None),
            Quote.expires_at >= day_start,
            Quote.expires_at < day_end,
        )
        .order_by(Quote.expires_at.asc(), Quote.quote_number.asc())
        .limit(limit)
    )
    if statuses is not None:
        stmt = stmt.where(Quote.status.in_(sorted(statuses)))
    return db.execute(stmt).all()


def _build_quote_expiry_digest_body(
    rows: list[tuple[Quote, Prospect | None, User | None]],
    *,
    digest_date: date,
    expired_yesterday_rows: list[tuple[Quote, Prospect | None, User | None]] | None = None,
) -> str:
    day_label = escape(_format_utc_day_label(digest_date))
    expired_yesterday_rows = expired_yesterday_rows or []

    def render_rows(section_rows: list[tuple[Quote, Prospect | None, User | None]]) -> str:
        rendered_rows: list[str] = []
        for quote, prospect, client in section_rows:
            student_name = escape(_quote_student_name(quote, prospect, client))
            quote_number = escape(str(quote.quote_number or "-"))
            expires_at = quote.expires_at.astimezone(UTC).strftime("%H:%M UTC") if quote.expires_at else "-"
            status = escape(str(quote.status or "-"))
            rendered_rows.append(
                "<tr>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{student_name}</td>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{quote_number}</td>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{escape(expires_at)}</td>"
                f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;'>{status}</td>"
                "</tr>"
            )
        return "".join(rendered_rows)

    today_rows_html = render_rows(rows)
    yesterday_rows_html = render_rows(expired_yesterday_rows)
    yesterday_section = ""
    if expired_yesterday_rows:
        yesterday_label = escape(_format_utc_day_label(digest_date - timedelta(days=1)))
        yesterday_section = (
            f"<h2 style='font-size:16px;margin:22px 0 8px;'>Devis expires hier ({yesterday_label})</h2>"
            "<table style='border-collapse:collapse;width:100%;max-width:760px;'>"
            "<thead><tr>"
            "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Eleve</th>"
            "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Devis</th>"
            "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Expiration</th>"
            "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Statut</th>"
            "</tr></thead>"
            f"<tbody>{yesterday_rows_html}</tbody>"
            "</table>"
        )
    return (
        "<div style='font-family:Arial,sans-serif;color:#1f2937;line-height:1.45;'>"
        f"<h1 style='font-size:18px;margin:0 0 12px;'>Devis expirant le {day_label}</h1>"
        "<p style='margin:0 0 14px;'>Voici la liste des devis qui expirent aujourd'hui, puis les devis qui ont expire hier.</p>"
        "<table style='border-collapse:collapse;width:100%;max-width:760px;'>"
        "<thead><tr>"
        "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Eleve</th>"
        "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Devis</th>"
        "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Expiration</th>"
        "<th align='left' style='padding:8px 10px;border-bottom:2px solid #d1d5db;'>Statut</th>"
        "</tr></thead>"
        f"<tbody>{today_rows_html}</tbody>"
        "</table>"
        f"{yesterday_section}"
        "</div>"
    )


def _send_quote_expiry_admin_digest(
    db: Session,
    *,
    digest_date: date,
    now: datetime,
    limit: int,
    delivery_enabled: bool,
    job_run_id: UUID,
) -> int:
    if _quote_expiry_digest_already_processed(db, digest_date=digest_date):
        return 0

    rows = _quote_expiry_digest_rows(db, digest_date=digest_date, limit=limit, statuses=EXPIRABLE_STATUSES)
    expired_yesterday_rows = _quote_expiry_digest_rows(
        db,
        digest_date=digest_date - timedelta(days=1),
        limit=limit,
        statuses=EXPIRABLE_STATUSES | {"expired", "cancelled"},
    )
    if not rows and not expired_yesterday_rows:
        _mark_quote_expiry_digest_processed(db, digest_date=digest_date, now=now)
        append_job_run_log(
            db,
            job_run_id=job_run_id,
            level="info",
            message="Quote expiry admin digest skipped: no quotes expiring today or expired yesterday",
            context_json={"digest_date": digest_date.isoformat()},
        )
        return 0

    recipients = resolve_admin_quote_expiry_digest_recipients(db)
    body = _build_quote_expiry_digest_body(rows, digest_date=digest_date, expired_yesterday_rows=expired_yesterday_rows)
    subject = f"Devis qui expirent aujourd'hui - {_format_utc_day_label(digest_date)}"
    sent = 0
    for recipient in recipients:
        if not recipient.email:
            continue
        if not delivery_enabled:
            continue
        message_id = send_email(
            to_email=recipient.email,
            subject=subject,
            body=body,
            body_format="HTML",
            context="QUOTE_EXPIRY_ADMIN_DIGEST",
        )
        if message_id:
            sent += 1

    _mark_quote_expiry_digest_processed(db, digest_date=digest_date, now=now)
    append_job_run_log(
        db,
        job_run_id=job_run_id,
        level="info",
        message="Quote expiry admin digest processed",
        context_json={
            "digest_date": digest_date.isoformat(),
            "quote_count": len(rows),
            "expired_yesterday_count": len(expired_yesterday_rows),
            "recipient_count": len([recipient for recipient in recipients if recipient.email]),
            "sent": sent,
        },
    )
    return sent


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
    dedupe_suffix: str | None = None,
) -> bool:
    if not delivery_enabled:
        return False
    normalized_recipient = recipient_email.strip().lower()
    message_key = f"{kind}:{quote.id}:{normalized_recipient}"
    if dedupe_suffix:
        message_key = f"{message_key}:{dedupe_suffix}"
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
    expiry_digest_sent = 0
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
        if settings.reminder_enabled and settings.reminder_lead_hours_values:
            max_reminder_lead_hours = max(settings.reminder_lead_hours_values)
            reminder_quotes = db.scalars(
                select(Quote)
                .where(
                    Quote.status.in_(sorted(REMINDER_ELIGIBLE_STATUSES)),
                    Quote.expires_at.is_not(None),
                    Quote.expires_at > ts,
                    Quote.expires_at <= ts + timedelta(hours=max_reminder_lead_hours + 24),
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
                already_sent_offsets = _quote_reminder_offsets_sent(quote)
                due_offsets = [
                    offset
                    for offset in settings.reminder_lead_hours_values
                    if offset not in already_sent_offsets
                    and _trigger_due_today(
                        now=ts,
                        zone=zone,
                        reference_at=quote.expires_at - timedelta(hours=offset),
                        local_time=settings.daily_job_local_time,
                    )
                ]
                if not due_offsets:
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
                for offset_hours in due_offsets:
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
                                dedupe_suffix=f"{offset_hours}h",
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
                            context_json={"quote_id": str(quote.id), "offset_hours": offset_hours, "error": str(exc)},
                        )
                        continue
                    if email_sent or sms_sent:
                        reminders_sent += 1
                        _mark_quote_reminder_offset_sent(quote, offset_hours=offset_hours, now=ts)
                        db.add(quote)
                        db.add(
                            QuoteEvent(
                                quote_id=quote.id,
                                event_type="quote_reminder_sent",
                                actor_type="system",
                                payload={"kind": "reminder", "offset_hours": offset_hours},
                                created_at=ts,
                            )
                        )

        digest_date = _quote_expiry_digest_date(ts)
        if digest_date is not None:
            try:
                expiry_digest_sent = _send_quote_expiry_admin_digest(
                    db,
                    digest_date=digest_date,
                    now=ts,
                    limit=limit,
                    delivery_enabled=settings.delivery_enabled,
                    job_run_id=job_run.id,
                )
            except Exception as exc:
                failed += 1
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="error",
                    message="Quote expiry admin digest failed",
                    context_json={"digest_date": digest_date.isoformat(), "error": str(exc)},
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
            items_sent=reminders_sent + expiry_digest_sent,
            items_skipped=max(checked - reminders_sent - expiry_digest_sent - failed, 0),
            items_failed=failed,
            summary_text=(
                f"reminders={reminders_sent} expiry_digest={expiry_digest_sent} expired={expired} "
                f"cancelled={cancelled} archived_marked={archived_prospects}"
            ),
        )
        return QuoteDailyJobResult(
            checked=checked,
            reminders_sent=reminders_sent,
            expiry_digest_sent=expiry_digest_sent,
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
            items_sent=reminders_sent + expiry_digest_sent,
            items_skipped=0,
            items_failed=max(failed, 1),
            error_text=str(exc),
        )
        raise
