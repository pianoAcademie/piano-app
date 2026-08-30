from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO
from uuid import UUID
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import CourseSession, Professor, SessionStatus
from app.models.ops import AppSetting
from app.models.teacher_invoicing import (
    TeacherInvoice,
    TeacherInvoiceAuditEvent,
    TeacherMonthlyStatement,
)
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.teacher_invoicing import (
    ComputedStatement,
    compute_teacher_monthly_statements,
    invoice_period_label,
    month_bounds_utc,
    statement_to_snapshot_payload,
)

logger = logging.getLogger(__name__)

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
ACCOUNTING_EMAIL = "comptabilite@piano-academie.com"
LAST_COURSE_DELAY = timedelta(hours=2)
ACCOUNTING_SEND_HOUR = 7
ACCOUNTING_DIGEST_SETTING_PREFIX = "teacher_statement_accounting_digest_v1"
NOTIFICATIONS_ENABLED_SETTING_KEY = "teacher_statement_notifications_enabled_v1"
NOTIFICATION_ROLLOUT_START = date(2026, 8, 1)
EXCLUDED_TECHNICAL_PROFESSOR_EMAILS = frozenset(
    {
        "apple-review-professor-20260814@piano-academie.com",
    }
)

EVENT_BLOCKED_EMAIL_SENT = "teacher_statement_blocked_email_sent"
EVENT_AVAILABLE_EMAIL_SENT = "teacher_statement_available_email_sent"


@dataclass(frozen=True)
class TeacherPeriodCandidate:
    professor: Professor
    year: int
    month: int
    last_course_end_at_utc: datetime


@dataclass(frozen=True)
class TeacherStatementNotificationResult:
    checked: int
    available_sent: int
    blocked_sent: int
    accounting_sent: int
    skipped_not_due: int
    skipped_already_sent: int
    failed: int
    dry_run: bool


def _quantized_text(value: Decimal | float | int) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def teacher_statement_professor_is_eligible(professor: Professor) -> bool:
    return professor.email.strip().lower() not in EXCLUDED_TECHNICAL_PROFESSOR_EMAILS


def teacher_statement_notifications_enabled(db: Session) -> bool:
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == NOTIFICATIONS_ENABLED_SETTING_KEY))
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def set_teacher_statement_notifications_enabled(db: Session, *, enabled: bool, now: datetime) -> None:
    row = db.scalar(select(AppSetting).where(AppSetting.key == NOTIFICATIONS_ENABLED_SETTING_KEY).with_for_update())
    value = "true" if enabled else "false"
    if row is None:
        db.add(AppSetting(key=NOTIFICATIONS_ENABLED_SETTING_KEY, value=value, updated_at=now))
    else:
        row.value = value
        row.updated_at = now
        db.add(row)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _previous_month(value: date) -> date:
    return (value.replace(day=1) - timedelta(days=1)).replace(day=1)


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _easter_sunday(year: int) -> date:
    """Gregorian Easter date, used only to exclude French movable public holidays."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    month_adjustment = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * month_adjustment) // 451
    month = (h + month_adjustment - 7 * m + 114) // 31
    day = ((h + month_adjustment - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _french_public_holidays(year: int) -> set[date]:
    easter = _easter_sunday(year)
    return {
        date(year, 1, 1),
        easter + timedelta(days=1),
        date(year, 5, 1),
        date(year, 5, 8),
        easter + timedelta(days=39),
        easter + timedelta(days=50),
        date(year, 7, 14),
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 11, 11),
        date(year, 12, 25),
    }


def is_french_business_day(value: date) -> bool:
    return value.weekday() < 5 and value not in _french_public_holidays(value.year)


def add_french_business_days(value: date, days: int) -> date:
    if days < 0:
        raise ValueError("days must be positive")
    result = value
    remaining = days
    while remaining:
        result += timedelta(days=1)
        if is_french_business_day(result):
            remaining -= 1
    return result


def invoice_deadline(*, period_year: int, period_month: int, notification_date: date) -> date:
    period_start = date(period_year, period_month, 1)
    regular_deadline = _next_month(period_start)
    fair_deadline = add_french_business_days(notification_date, 2)
    return max(regular_deadline, fair_deadline)


def expected_payment_date(deadline: date) -> date:
    return add_french_business_days(deadline, 3)


def _professor_language(db: Session, *, professor: Professor) -> str:
    language = db.scalar(
        select(User.preferred_language)
        .where(func.lower(User.email) == professor.email.strip().lower())
        .limit(1)
    )
    return "en" if str(language or "").strip().lower().startswith("en") else "fr"


def _statement_status_from_computed(computed: ComputedStatement) -> str:
    return "to_verify" if computed.attendance_complete else "awaiting_attendance"


def sync_teacher_monthly_statements(
    db: Session,
    *,
    professor: Professor,
    year: int,
    month: int,
) -> list[tuple[TeacherMonthlyStatement, ComputedStatement]]:
    computed_rows = compute_teacher_monthly_statements(db, professor=professor, year=year, month=month)
    if not computed_rows:
        return []

    existing_rows = db.scalars(
        select(TeacherMonthlyStatement).where(
            TeacherMonthlyStatement.teacher_id == professor.id,
            TeacherMonthlyStatement.year == year,
            TeacherMonthlyStatement.month == month,
        )
    ).all()
    existing_by_payor = {row.payor_legal_entity_id: row for row in existing_rows}
    now = datetime.now(tz=UTC)
    synced: list[tuple[TeacherMonthlyStatement, ComputedStatement]] = []

    for computed in computed_rows:
        row = existing_by_payor.get(computed.payor_legal_entity_id)
        if row is None:
            row = TeacherMonthlyStatement(
                teacher_id=professor.id,
                payor_legal_entity_id=computed.payor_legal_entity_id,
                year=year,
                month=month,
                status=_statement_status_from_computed(computed),
                attendance_complete=computed.attendance_complete,
                totals_snapshot=statement_to_snapshot_payload(computed),
                updated_at=now,
            )
            db.add(row)
        else:
            if row.status not in {"validated", "invoice_generated", "closed", "in_dispute", "awaiting_admin_feedback"}:
                row.status = _statement_status_from_computed(computed)
            row.attendance_complete = computed.attendance_complete
            row.totals_snapshot = statement_to_snapshot_payload(computed)
            row.updated_at = now
            db.add(row)
        synced.append((row, computed))

    db.flush()
    return synced


def _period_candidates(
    db: Session,
    *,
    period: date,
    limit: int,
) -> list[TeacherPeriodCandidate]:
    period_start_utc, period_end_utc = month_bounds_utc(year=period.year, month=period.month)
    effective_teacher_id = func.coalesce(CourseSession.substitute_teacher_id, CourseSession.professor_id)
    last_sessions = (
        select(
            effective_teacher_id.label("teacher_id"),
            func.max(CourseSession.end_at_utc).label("last_course_end_at_utc"),
        )
        .where(
            CourseSession.start_at_utc >= period_start_utc,
            CourseSession.start_at_utc < period_end_utc,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .group_by(effective_teacher_id)
        .subquery()
    )
    rows = db.execute(
        select(Professor, last_sessions.c.last_course_end_at_utc)
        .join(last_sessions, last_sessions.c.teacher_id == Professor.id)
        .where(func.lower(func.trim(Professor.email)).notin_(EXCLUDED_TECHNICAL_PROFESSOR_EMAILS))
        .order_by(Professor.last_name.asc(), Professor.first_name.asc())
        .limit(limit)
    ).all()
    return [
        TeacherPeriodCandidate(
            professor=professor,
            year=period.year,
            month=period.month,
            last_course_end_at_utc=last_course_end_at_utc,
        )
        for professor, last_course_end_at_utc in rows
    ]


def _period_event_exists(
    db: Session,
    *,
    professor_id: UUID,
    year: int,
    month: int,
    event_type: str,
) -> bool:
    events = db.scalars(
        select(TeacherInvoiceAuditEvent).where(
            TeacherInvoiceAuditEvent.teacher_id == professor_id,
            TeacherInvoiceAuditEvent.event_type == event_type,
        )
    ).all()
    period_key = f"{year:04d}-{month:02d}"
    return any(str((event.payload or {}).get("period") or "") == period_key for event in events)


def _record_period_event(
    db: Session,
    *,
    professor_id: UUID,
    statement_ids: Iterable[UUID],
    year: int,
    month: int,
    event_type: str,
    provider_message_id: str,
) -> None:
    period_key = f"{year:04d}-{month:02d}"
    for statement_id in statement_ids:
        db.add(
            TeacherInvoiceAuditEvent(
                event_type=event_type,
                teacher_id=professor_id,
                statement_id=statement_id,
                payload={"period": period_key, "provider_message_id": provider_message_id},
            )
        )


def _format_date(value: date, *, language: str) -> str:
    if language == "en":
        return value.strftime("%Y-%m-%d")
    return value.strftime("%d/%m/%Y")


def _email_shell(*, title: str, greeting: str, content: str, footer: str) -> str:
    return (
        "<div style=\"margin:0;background:#f3f5f8;padding:24px;font-family:Arial,sans-serif;color:#172033;\">"
        "<div style=\"max-width:680px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;\">"
        "<div style=\"background:#172033;padding:28px 34px;color:#fff;\">"
        "<div style=\"color:#f2c879;font-weight:700;font-size:14px;\">PIANO ACADÉMIE · ESPACE PROFESSEUR</div>"
        f"<h1 style=\"margin:8px 0 0;font-size:28px;\">{escape(title)}</h1></div>"
        "<div style=\"padding:30px 34px;line-height:1.6;\">"
        f"<p style=\"font-size:17px;\">{greeting}</p>{content}"
        f"<p style=\"margin-top:28px;color:#667085;font-size:13px;\">{escape(footer)}</p>"
        "</div></div></div>"
    )


def build_blocked_email(
    db: Session,
    *,
    professor: Professor,
    statements: list[ComputedStatement],
    year: int,
    month: int,
    language: str,
) -> tuple[str, str]:
    period = invoice_period_label(year=year, month=month, language=language)
    missing = [item for statement in statements for item in statement.missing_sessions]
    portal_url = f"{resolve_frontend_base_url(db).rstrip('/')}/prof?tab=planning"
    first_name = escape((professor.first_name or "").strip())
    if language == "en":
        subject = f"Action required – your {period} statement is blocked"
        title = "Attendance must be completed"
        greeting = f"Hello {first_name}," if first_name else "Hello,"
        intro = (
            f"<p>Your service statement for <strong>{escape(period)}</strong> cannot be validated because "
            "some attendance records are missing.</p>"
        )
        action = "Complete attendance"
        footer = "The statement will be unlocked automatically once all attendance has been entered."
    else:
        subject = f"Action requise – votre relevé de {period} est bloqué"
        title = "Présences à compléter"
        greeting = f"Bonjour {first_name}," if first_name else "Bonjour,"
        intro = (
            f"<p>Votre relevé de prestations pour <strong>{escape(period)}</strong> ne peut pas être validé, "
            "car certaines présences ne sont pas renseignées.</p>"
        )
        action = "Compléter les présences"
        footer = "Le relevé sera automatiquement débloqué lorsque toutes les présences auront été renseignées."

    items = []
    for row in missing:
        local_start = row.start_at_utc.astimezone(PARIS_TIMEZONE)
        items.append(
            "<li style=\"margin-bottom:8px;\">"
            f"<strong>{escape(row.title)}</strong> · {local_start.strftime('%d/%m/%Y %H:%M')} · "
            f"{row.pending_students_count} présence(s) à compléter</li>"
        )
    content = (
        intro
        + f"<ul style=\"padding-left:22px;\">{''.join(items)}</ul>"
        + f"<p><a href=\"{escape(portal_url)}\" style=\"display:inline-block;padding:11px 18px;"
        "background:#c98224;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;\">"
        f"{escape(action)}</a></p>"
    )
    return subject, _email_shell(title=title, greeting=greeting, content=content, footer=footer)


def build_available_email(
    db: Session,
    *,
    professor: Professor,
    statements: list[ComputedStatement],
    year: int,
    month: int,
    notification_date: date,
    language: str,
) -> tuple[str, str]:
    period = invoice_period_label(year=year, month=month, language=language)
    deadline = invoice_deadline(period_year=year, period_month=month, notification_date=notification_date)
    payment_date = expected_payment_date(deadline)
    portal_url = f"{resolve_frontend_base_url(db).rstrip('/')}/prof/statements?year={year}&month={month}"
    first_name = escape((professor.first_name or "").strip())
    has_home_courses = any("PIANO ACADEMIE SERVICES" in statement.payor_legal_entity_name.upper() for statement in statements)
    vat_applicable = bool(professor.teacher_is_vat_applicable)
    vat_rate = _quantized_text(professor.teacher_vat_rate or 0)

    if language == "en":
        subject = f"Your service statement is available – {period}"
        title = "Your monthly statement is available"
        greeting = f"Hello {first_name}," if first_name else "Hello,"
        steps = (
            "<ol><li>Review the lessons in your statement.</li><li>Report any discrepancy before approval.</li>"
            "<li>Approve the statement.</li><li>Generate an invoice using the Piano Academie template, or upload your own invoice.</li></ol>"
        )
        tax_text = (
            f"Your invoice must show the net amount, VAT at {escape(vat_rate)}%, and the gross amount payable."
            if vat_applicable
            else "Your invoice must show the net amount, the wording “VAT not applicable”, and the amount payable."
        )
        home_text = (
            "<p><strong>Home lessons:</strong> a separate invoice addressed to Piano Academie Services is required. "
            "Your professor portal separates the corresponding amount.</p>"
            if has_home_courses
            else ""
        )
        action = "Open my professor portal"
        footer = "If attendance is missing, the statement cannot be approved."
        intro = f"Your service statement for <strong>{escape(period)}</strong> is available in your professor portal."
        deadline_label = "Invoice due by"
        payment_label = "Expected payment"
    else:
        subject = f"Votre relevé de prestations est disponible – {period}"
        title = "Votre relevé mensuel est disponible"
        greeting = f"Bonjour {first_name}," if first_name else "Bonjour,"
        steps = (
            "<ol><li>Consultez et vérifiez les cours figurant sur votre relevé.</li>"
            "<li>En cas d'anomalie, utilisez « Signaler un problème » avant la validation.</li>"
            "<li>Validez votre relevé.</li>"
            "<li>Générez votre facture avec le modèle Piano Académie ou déposez votre propre facture.</li></ol>"
        )
        tax_text = (
            f"Votre facture doit faire apparaître le montant HT, la TVA au taux configuré de {escape(vat_rate)} %, "
            "puis le montant TTC et le net à payer."
            if vat_applicable
            else "Votre facture doit faire apparaître le total HT, la mention « TVA non applicable, article 293 B du CGI », puis le net à payer."
        )
        home_text = (
            "<p><strong>Cours à domicile :</strong> une facture distincte adressée à Piano Académie Services est nécessaire. "
            "Votre espace professeur présente séparément le montant correspondant.</p>"
            if has_home_courses
            else ""
        )
        action = "Accéder à mon espace professeur"
        footer = "Un relevé comportant des présences non renseignées ne peut pas être validé."
        intro = f"Votre relevé de prestations pour <strong>{escape(period)}</strong> est disponible dans votre espace professeur."
        deadline_label = "Facture attendue au plus tard le"
        payment_label = "Paiement prévisionnel"

    content = (
        f"<p>{intro}</p>"
        + steps
        + f"<p>{tax_text}</p>"
        + home_text
        + f"<p>{escape(deadline_label)} <strong>{_format_date(deadline, language=language)}</strong>.<br>"
        f"{escape(payment_label)} : <strong>{_format_date(payment_date, language=language)}</strong>.</p>"
        + f"<p><a href=\"{escape(portal_url)}\" style=\"display:inline-block;padding:11px 18px;"
        "background:#c98224;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;\">"
        f"{escape(action)}</a></p>"
    )
    return subject, _email_shell(title=title, greeting=greeting, content=content, footer=footer)


def build_missing_service_resolved_email(
    db: Session,
    *,
    professor: Professor,
    statements: list[ComputedStatement],
    matched_session: dict[str, object],
    year: int,
    month: int,
    attendee_count: int,
    language: str,
) -> tuple[str, str]:
    period = invoice_period_label(year=year, month=month, language=language)
    portal_url = f"{resolve_frontend_base_url(db).rstrip('/')}/prof/statements?year={year}&month={month}"
    first_name = escape((professor.first_name or "").strip())
    service_date_raw = str(matched_session.get("date") or "")
    try:
        service_date = date.fromisoformat(service_date_raw)
        service_date_label = _format_date(service_date, language=language)
    except ValueError:
        service_date_label = service_date_raw or "-"
    title_text = escape(str(matched_session.get("title") or "Cours"))
    location_text = escape(str(matched_session.get("location_name") or "-"))
    rate_text = escape(str(matched_session.get("unit_rate_ht") or "0.00"))
    currency = escape(statements[0].currency if statements else "EUR")
    total_ht = sum((statement.totals_ht for statement in statements), Decimal("0.00"))
    total_text = escape(_quantized_text(total_ht))
    attendee_text = str(max(0, attendee_count))

    if language == "en":
        subject = f"Your missing service has been added – {period}"
        title = "Your statement has been corrected"
        greeting = f"Hello {first_name}," if first_name else "Hello,"
        content = (
            "<p>Your report has been reviewed and the service below now appears in your statement:</p>"
            f"<div style=\"background:#f5f7fa;border-radius:10px;padding:16px 18px;margin:18px 0;\">"
            f"<strong>{title_text}</strong><br>{escape(service_date_label)} · {location_text}<br>"
            f"{attendee_text} student(s) present · <strong>{rate_text} {currency} net</strong></div>"
            f"<p>Your {escape(period)} statement now totals <strong>{total_text} {currency} net</strong>.</p>"
            f"<p><a href=\"{escape(portal_url)}\" style=\"display:inline-block;padding:11px 18px;"
            "background:#c98224;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;\">"
            "Review my statement</a></p>"
        )
        footer = "You can report another discrepancy directly from your professor portal."
    else:
        subject = f"Votre prestation manquante a été ajoutée – {period}"
        title = "Votre relevé a été corrigé"
        greeting = f"Bonjour {first_name}," if first_name else "Bonjour,"
        content = (
            "<p>Votre signalement a été vérifié et la prestation suivante figure désormais dans votre relevé :</p>"
            f"<div style=\"background:#f5f7fa;border-radius:10px;padding:16px 18px;margin:18px 0;\">"
            f"<strong>{title_text}</strong><br>{escape(service_date_label)} · {location_text}<br>"
            f"{attendee_text} élève(s) présent(s) · <strong>{rate_text} {currency} HT</strong></div>"
            f"<p>Votre relevé de {escape(period)} présente désormais un total de "
            f"<strong>{total_text} {currency} HT</strong>.</p>"
            f"<p><a href=\"{escape(portal_url)}\" style=\"display:inline-block;padding:11px 18px;"
            "background:#c98224;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;\">"
            "Consulter mon relevé</a></p>"
        )
        footer = "Vous pouvez signaler toute autre anomalie directement depuis votre espace professeur."
    return subject, _email_shell(title=title, greeting=greeting, content=content, footer=footer)


def _invoice_status(db: Session, statement_id: UUID) -> str:
    invoice = db.scalar(
        select(TeacherInvoice)
        .where(TeacherInvoice.statement_id == statement_id)
        .order_by(TeacherInvoice.created_at.desc())
        .limit(1)
    )
    if invoice is None:
        return "Attendue"
    if invoice.sent_to_accounting_at is not None:
        return "Transmise à la comptabilité"
    return "Générée ou déposée"


def render_accounting_digest_pdf(
    *,
    year: int,
    month: int,
    rows: list[tuple[Professor, TeacherMonthlyStatement, ComputedStatement, str]],
    generated_at: datetime,
) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Relevés professeurs {year:04d}-{month:02d}",
        author="Piano Académie",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DigestSmall", parent=styles["BodyText"], fontSize=7.2, leading=9))
    styles.add(ParagraphStyle(name="DigestRight", parent=styles["DigestSmall"], alignment=TA_RIGHT))
    story: list[object] = [
        Paragraph("RELEVÉS DES PROFESSEURS", styles["Title"]),
        Paragraph(
            f"Période : {escape(invoice_period_label(year=year, month=month, language='fr'))} · "
            f"Généré le {generated_at.astimezone(PARIS_TIMEZONE).strftime('%d/%m/%Y %H:%M')}",
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
    ]

    header = ["Professeur", "Entité", "HT", "TVA", "Montant à payer", "Présences", "Relevé", "Facture"]
    data: list[list[object]] = [[Paragraph(f"<b>{escape(value)}</b>", styles["DigestSmall"]) for value in header]]
    for professor, statement, computed, invoice_status in rows:
        vat_display = _quantized_text(computed.totals_vat) if bool(professor.teacher_is_vat_applicable) else "Non applicable"
        amount_payable = computed.totals_ttc if bool(professor.teacher_is_vat_applicable) else computed.totals_ht
        data.append(
            [
                Paragraph(escape(f"{professor.first_name} {professor.last_name}".strip()), styles["DigestSmall"]),
                Paragraph(escape(computed.payor_legal_entity_name), styles["DigestSmall"]),
                Paragraph(_quantized_text(computed.totals_ht), styles["DigestRight"]),
                Paragraph(escape(vat_display), styles["DigestRight"]),
                Paragraph(f"<b>{_quantized_text(amount_payable)} {escape(computed.currency)}</b>", styles["DigestRight"]),
                Paragraph("Complètes" if computed.attendance_complete else "À compléter", styles["DigestSmall"]),
                Paragraph(escape(statement.status), styles["DigestSmall"]),
                Paragraph(escape(invoice_status), styles["DigestSmall"]),
            ]
        )

    table = Table(data, colWidths=[39 * mm, 42 * mm, 24 * mm, 28 * mm, 34 * mm, 29 * mm, 29 * mm, 42 * mm], repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8DFEA")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8DFEA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for index, (_, _, computed, _) in enumerate(rows, start=1):
        if not computed.attendance_complete:
            commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#FFF3D6")))
        elif index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#F4F7FB")))
    table.setStyle(TableStyle(commands))
    story.extend(
        [
            table,
            Spacer(1, 4 * mm),
            Paragraph(
                "Les relevés avec des présences à compléter sont bloqués et exclus des montants validés pour paiement. "
                "Pour les professeurs sans TVA, le montant à payer est égal au HT. Pour les professeurs assujettis, "
                "le montant à payer correspond au TTC.",
                styles["BodyText"],
            ),
        ]
    )
    doc.build(story)
    return output.getvalue()


def _digest_fingerprint(rows: list[tuple[Professor, TeacherMonthlyStatement, ComputedStatement, str]]) -> str:
    payload = [
        {
            "statement_id": str(statement.id),
            "status": statement.status,
            "attendance_complete": computed.attendance_complete,
            "ht": _quantized_text(computed.totals_ht),
            "vat": _quantized_text(computed.totals_vat),
            "payable": _quantized_text(computed.totals_ttc if professor.teacher_is_vat_applicable else computed.totals_ht),
            "invoice_status": invoice_status,
        }
        for professor, statement, computed, invoice_status in rows
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _send_accounting_digest_if_due(
    db: Session,
    *,
    now: datetime,
    rows: list[tuple[Professor, TeacherMonthlyStatement, ComputedStatement, str]],
    year: int,
    month: int,
    dry_run: bool,
) -> int:
    paris_now = now.astimezone(PARIS_TIMEZONE)
    if paris_now.hour < ACCOUNTING_SEND_HOUR or not rows:
        return 0
    period_key = f"{year:04d}-{month:02d}"
    setting_key = f"{ACCOUNTING_DIGEST_SETTING_PREFIX}:{period_key}"
    fingerprint = _digest_fingerprint(rows)
    setting = db.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    previous: dict[str, str] = {}
    if setting is not None:
        try:
            previous = json.loads(setting.value)
        except (TypeError, ValueError):
            previous = {}
    if previous.get("fingerprint") == fingerprint or previous.get("sent_on") == paris_now.date().isoformat():
        return 0
    if dry_run:
        return 1

    pdf = render_accounting_digest_pdf(year=year, month=month, rows=rows, generated_at=now)
    is_update = bool(previous)
    subject_prefix = "Mise à jour – " if is_update else ""
    subject = f"{subject_prefix}Relevés des professeurs – {invoice_period_label(year=year, month=month, language='fr')}"
    body = (
        "Bonjour,<br><br>Vous trouverez en pièce jointe le récapitulatif des relevés des professeurs. "
        "Les relevés comportant des présences non renseignées sont identifiés comme bloqués et ne doivent pas être validés pour paiement.<br><br>"
        "Le montant à payer est égal au HT lorsque la TVA n'est pas applicable. Pour un professeur assujetti à la TVA, il correspond au TTC.<br><br>"
        "Bien cordialement,<br>Piano Académie"
    )
    message_id = send_email(
        to_email=ACCOUNTING_EMAIL,
        subject=subject,
        body=body,
        body_format="HTML",
        context="TEACHER_STATEMENT_ACCOUNTING_DIGEST",
        attachments=[(f"releves_professeurs_{period_key}.pdf", pdf, "application/pdf")],
    )
    if not message_id:
        raise RuntimeError("accounting digest email provider returned no message id")
    value = json.dumps(
        {"fingerprint": fingerprint, "sent_on": paris_now.date().isoformat(), "provider_message_id": message_id},
        sort_keys=True,
    )
    if setting is None:
        db.add(AppSetting(key=setting_key, value=value, updated_at=now))
    else:
        setting.value = value
        setting.updated_at = now
        db.add(setting)
    return 1


def run_teacher_statement_notification_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
    dry_run: bool = True,
) -> TeacherStatementNotificationResult:
    paris_now = now.astimezone(PARIS_TIMEZONE)
    periods = {
        period
        for period in {_month_start(paris_now.date()), _previous_month(paris_now.date())}
        if period >= NOTIFICATION_ROLLOUT_START
    }
    checked = 0
    available_sent = 0
    blocked_sent = 0
    accounting_sent = 0
    skipped_not_due = 0
    skipped_already_sent = 0
    failed = 0
    rows_by_period: dict[tuple[int, int], list[tuple[Professor, TeacherMonthlyStatement, ComputedStatement, str]]] = {}

    for period in sorted(periods):
        for candidate in _period_candidates(db, period=period, limit=limit):
            if not teacher_statement_professor_is_eligible(candidate.professor):
                continue
            checked += 1
            if candidate.last_course_end_at_utc + LAST_COURSE_DELAY > now:
                skipped_not_due += 1
                continue
            try:
                synced = sync_teacher_monthly_statements(
                    db,
                    professor=candidate.professor,
                    year=candidate.year,
                    month=candidate.month,
                )
                if not synced:
                    continue
                computed_rows = [computed for _, computed in synced]
                all_complete = all(row.attendance_complete for row in computed_rows)
                event_type = EVENT_AVAILABLE_EMAIL_SENT if all_complete else EVENT_BLOCKED_EMAIL_SENT
                already_sent = _period_event_exists(
                    db,
                    professor_id=candidate.professor.id,
                    year=candidate.year,
                    month=candidate.month,
                    event_type=event_type,
                )
                if already_sent:
                    skipped_already_sent += 1
                else:
                    language = _professor_language(db, professor=candidate.professor)
                    if all_complete:
                        subject, body = build_available_email(
                            db,
                            professor=candidate.professor,
                            statements=computed_rows,
                            year=candidate.year,
                            month=candidate.month,
                            notification_date=paris_now.date(),
                            language=language,
                        )
                    else:
                        subject, body = build_blocked_email(
                            db,
                            professor=candidate.professor,
                            statements=computed_rows,
                            year=candidate.year,
                            month=candidate.month,
                            language=language,
                        )
                    if dry_run:
                        message_id = "dry-run"
                    else:
                        message_id = send_email(
                            to_email=candidate.professor.email,
                            subject=subject,
                            body=body,
                            body_format="HTML",
                            context=(
                                "TEACHER_STATEMENT_AVAILABLE"
                                if all_complete
                                else "TEACHER_STATEMENT_BLOCKED_ATTENDANCE"
                            ),
                            professor_id=candidate.professor.id,
                        )
                        if not message_id:
                            raise RuntimeError("teacher statement email provider returned no message id")
                    if not dry_run:
                        _record_period_event(
                            db,
                            professor_id=candidate.professor.id,
                            statement_ids=[statement.id for statement, _ in synced],
                            year=candidate.year,
                            month=candidate.month,
                            event_type=event_type,
                            provider_message_id=message_id,
                        )
                    if all_complete:
                        available_sent += 1
                    else:
                        blocked_sent += 1

                period_rows = rows_by_period.setdefault((candidate.year, candidate.month), [])
                period_rows.extend(
                    (
                        candidate.professor,
                        statement,
                        computed,
                        _invoice_status(db, statement.id),
                    )
                    for statement, computed in synced
                )
            except Exception as exc:  # pragma: no cover - defensive production path
                logger.exception(
                    "Teacher statement notification failed | professor_id=%s | period=%s-%02d | error=%s",
                    candidate.professor.id,
                    candidate.year,
                    candidate.month,
                    exc,
                )
                failed += 1

    previous_period = _previous_month(paris_now.date())
    if paris_now.day >= 1 and previous_period >= NOTIFICATION_ROLLOUT_START:
        digest_rows = rows_by_period.get((previous_period.year, previous_period.month), [])
        digest_rows.sort(key=lambda row: (row[0].last_name.casefold(), row[0].first_name.casefold(), row[2].payor_legal_entity_name.casefold()))
        try:
            accounting_sent = _send_accounting_digest_if_due(
                db,
                now=now,
                rows=digest_rows,
                year=previous_period.year,
                month=previous_period.month,
                dry_run=dry_run,
            )
        except Exception as exc:  # pragma: no cover - defensive production path
            logger.exception("Teacher statement accounting digest failed | error=%s", exc)
            failed += 1

    return TeacherStatementNotificationResult(
        checked=checked,
        available_sent=available_sent,
        blocked_sent=blocked_sent,
        accounting_sent=accounting_sent,
        skipped_not_due=skipped_not_due,
        skipped_already_sent=skipped_already_sent,
        failed=failed,
        dry_run=dry_run,
    )


__all__ = [
    "TeacherStatementNotificationResult",
    "add_french_business_days",
    "build_available_email",
    "build_blocked_email",
    "build_missing_service_resolved_email",
    "expected_payment_date",
    "invoice_deadline",
    "is_french_business_day",
    "render_accounting_digest_pdf",
    "run_teacher_statement_notification_job",
    "set_teacher_statement_notifications_enabled",
    "teacher_statement_notifications_enabled",
    "teacher_statement_professor_is_eligible",
]
