from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from app.models.catalog import BookingStatus
from app.services.i18n import normalize_language
from app.services.invoice_documents import CompanyIdentity
from app.services.teacher_invoicing import ComputedStatement

PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
NAVY = colors.HexColor("#1C263D")
GOLD = colors.HexColor("#D29A3A")
PALE_GOLD = colors.HexColor("#FBF4E7")
PALE_BLUE = colors.HexColor("#F4F7FB")
LINE = colors.HexColor("#D8DFEA")
TEXT = colors.HexColor("#1B2638")
MUTED = colors.HexColor("#607089")

TEXTS = {
    "fr": {
        "document_title": "RELEVE MENSUEL DE PRESTATIONS",
        "not_invoice": "Document de contrôle des prestations - ne vaut pas facture.",
        "period": "Période",
        "generated": "Généré le",
        "teacher": "Professeur",
        "official_info": "Informations officielles Piano Académie",
        "legal_form": "Forme juridique",
        "capital": "Capital social",
        "vat": "TVA intracommunautaire",
        "phone": "Telephone",
        "summary": "Recapitulatif",
        "courses": "Cours effectués",
        "hours": "Total des heures",
        "total_ht": "Montant total HT",
        "attendance": "Présences",
        "attendance_complete": "Complètes",
        "attendance_incomplete": "À compléter",
        "details": "Détail des cours effectués",
        "date_time": "Date et horaire",
        "course_location": "Cours et lieu",
        "duration": "Durée",
        "students": "Présence des élèves",
        "rate": "Taux horaire HT",
        "amount": "Montant HT",
        "no_students": "Aucun élève inscrit",
        "booked": "À renseigner",
        "attended": "Présent(e)",
        "no_show": "Absent(e) non excusé(e)",
        "excused": "Absent(e) excusé(e)",
        "entity": "Entite payeuse",
        "page": "Page",
        "no_course": "Aucun cours terminé sur cette période.",
    },
    "en": {
        "document_title": "MONTHLY SERVICE STATEMENT",
        "not_invoice": "Service review document - this is not an invoice.",
        "period": "Period",
        "generated": "Generated on",
        "teacher": "Teacher",
        "official_info": "Official Piano Academie information",
        "legal_form": "Legal form",
        "capital": "Share capital",
        "vat": "VAT number",
        "phone": "Phone",
        "summary": "Summary",
        "courses": "Lessons completed",
        "hours": "Total hours",
        "total_ht": "Total excl. tax",
        "attendance": "Attendance",
        "attendance_complete": "Complete",
        "attendance_incomplete": "To complete",
        "details": "Completed lesson details",
        "date_time": "Date and time",
        "course_location": "Lesson and location",
        "duration": "Duration",
        "students": "Student attendance",
        "rate": "Hourly rate excl. tax",
        "amount": "Amount excl. tax",
        "no_students": "No students enrolled",
        "booked": "To enter",
        "attended": "Present",
        "no_show": "Unexcused absence",
        "excused": "Excused absence",
        "entity": "Payor entity",
        "page": "Page",
        "no_course": "No completed lesson for this period.",
    },
}

MONTH_LABELS = {
    "fr": ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
}


def _text(language: str, key: str) -> str:
    return TEXTS.get(language, TEXTS["fr"]).get(key, key)


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _money(value: object, currency: str, language: str) -> str:
    rendered = f"{_decimal(value):,.2f}"
    if language == "fr":
        rendered = rendered.replace(",", " ").replace(".", ",")
    return f"{rendered} {currency}"


def _hours(value: Decimal, language: str) -> str:
    rendered = f"{value.quantize(Decimal('0.01'))}"
    if language == "fr":
        rendered = rendered.replace(".", ",")
    return f"{rendered} h"


def _date_time_labels(start_raw: object, end_raw: object, language: str) -> tuple[str, str]:
    try:
        start = datetime.fromisoformat(str(start_raw)).astimezone(PARIS_TIMEZONE)
        end = datetime.fromisoformat(str(end_raw)).astimezone(PARIS_TIMEZONE)
    except (TypeError, ValueError):
        return "-", "-"
    date_label = start.strftime("%d/%m/%Y")
    time_label = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
    return date_label, time_label


def _attendance_label(status: object, language: str) -> str:
    normalized = str(status or "").strip().upper()
    key_by_status = {
        BookingStatus.BOOKED.value: "booked",
        BookingStatus.ATTENDED.value: "attended",
        BookingStatus.NO_SHOW.value: "no_show",
        BookingStatus.EXCUSED_ABSENCE.value: "excused",
    }
    key = key_by_status.get(normalized)
    return _text(language, key) if key else normalized or "-"


def _flatten_sessions(rows: list[ComputedStatement], language: str) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for statement in rows:
        for line in statement.lines:
            raw_items = line.meta.get("session_items") if isinstance(line.meta, dict) else None
            items = raw_items if isinstance(raw_items, list) else []
            if not items:
                sessions.append(
                    {
                        "sort": "",
                        "date": "-",
                        "time": "-",
                        "title": line.course_type_label,
                        "location": "-",
                        "duration": _hours(line.hours, language),
                        "attendance": _text(language, "no_students"),
                        "rate": _money(line.unit_rate_ht, statement.currency, language),
                        "amount": _money(line.amount_ht, statement.currency, language),
                        "entity": statement.payor_legal_entity_name,
                    }
                )
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                date_label, time_label = _date_time_labels(item.get("start_at_utc"), item.get("end_at_utc"), language)
                raw_attendance = item.get("attendance")
                attendance_rows = raw_attendance if isinstance(raw_attendance, list) else []
                attendance_labels = []
                for attendance in attendance_rows:
                    if not isinstance(attendance, dict):
                        continue
                    name = str(attendance.get("student_name") or "-").strip() or "-"
                    attendance_labels.append(f"{name}: {_attendance_label(attendance.get('status'), language)}")
                duration_minutes = max(0, int(item.get("duration_minutes") or 0))
                sessions.append(
                    {
                        "sort": str(item.get("start_at_utc") or ""),
                        "date": date_label,
                        "time": time_label,
                        "title": str(item.get("title") or line.course_type_label).strip() or line.course_type_label,
                        "location": str(item.get("location_name") or "-").strip() or "-",
                        "duration": f"{duration_minutes} min",
                        "attendance": "\n".join(attendance_labels) or _text(language, "no_students"),
                        "rate": _money(item.get("unit_rate_ht", line.unit_rate_ht), statement.currency, language),
                        "amount": _money(item.get("amount_ht", line.amount_ht), statement.currency, language),
                        "entity": statement.payor_legal_entity_name,
                    }
                )
    return sorted(sessions, key=lambda row: row["sort"])


def _identity_lines(identity: CompanyIdentity, language: str) -> list[str]:
    lines = [f"<b>{escape(identity.company_name)}</b>"]
    legal_parts = []
    if identity.company_legal_form:
        legal_parts.append(f"{_text(language, 'legal_form')}: {escape(identity.company_legal_form)}")
    if identity.company_share_capital:
        legal_parts.append(f"{_text(language, 'capital')}: {escape(identity.company_share_capital)}")
    if legal_parts:
        lines.append(" | ".join(legal_parts))
    lines.append(f"SIREN: {escape(identity.company_siren)} | SIRET: {escape(identity.company_siret)}")
    lines.append(f"{_text(language, 'vat')}: {escape(identity.company_vat_number)}")
    lines.append(escape(identity.company_address))
    lines.append(f"{_text(language, 'phone')}: {escape(identity.company_phone)} | Email: {escape(identity.company_email)}")
    return lines


def render_teacher_statement_pdf(
    *,
    professor_name: str,
    year: int,
    month: int,
    statements: list[ComputedStatement],
    identities: dict[object, CompanyIdentity],
    language: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    normalized_language = normalize_language(language)
    t = lambda key: _text(normalized_language, key)
    generated = (generated_at or datetime.now(UTC)).astimezone(PARIS_TIMEZONE)
    period_label = f"{MONTH_LABELS[normalized_language][month - 1]} {year}"
    sessions = _flatten_sessions(statements, normalized_language)
    total_hours = sum((line.hours for statement in statements for line in statement.lines), Decimal("0.00"))
    totals_by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for statement in statements:
        totals_by_currency[statement.currency] += statement.totals_ht
    attendance_complete = bool(statements) and all(statement.attendance_complete for statement in statements)

    identity_list: list[CompanyIdentity] = []
    seen_identity_ids: set[object] = set()
    for statement in statements:
        if statement.payor_legal_entity_id in seen_identity_ids:
            continue
        seen_identity_ids.add(statement.payor_legal_entity_id)
        identity = identities.get(statement.payor_legal_entity_id)
        if identity is not None:
            identity_list.append(identity)
    primary_identity = identity_list[0] if identity_list else None

    output = BytesIO()
    doc = BaseDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=29 * mm,
        bottomMargin=18 * mm,
        title=f"{t('document_title')} - {professor_name} - {period_label}",
        author=primary_identity.company_name if primary_identity else "Piano Academie",
        subject=t("not_invoice"),
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PAHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=5, spaceAfter=7))
    styles.add(ParagraphStyle(name="PABody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=TEXT))
    styles.add(ParagraphStyle(name="PASmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.2, leading=9, textColor=MUTED))
    styles.add(ParagraphStyle(name="PATable", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.2, leading=9, textColor=TEXT))
    styles.add(ParagraphStyle(name="PATableRight", parent=styles["PATable"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="PATableCenter", parent=styles["PATable"], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="PANote", parent=styles["BodyText"], fontName="Helvetica-Oblique", fontSize=8, leading=10, textColor=MUTED, alignment=TA_LEFT))

    logo_reader = None
    if primary_identity and primary_identity.company_logo_jpeg:
        try:
            logo_reader = ImageReader(BytesIO(primary_identity.company_logo_jpeg))
        except Exception:
            logo_reader = None

    def draw_page(canvas: Any, document: Any) -> None:
        width, height = landscape(A4)
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 23 * mm, width, 23 * mm, stroke=0, fill=1)
        title_x = 12 * mm
        if logo_reader is not None:
            canvas.drawImage(logo_reader, 12 * mm, height - 19.5 * mm, width=23 * mm, height=15 * mm, preserveAspectRatio=True, anchor="sw", mask="auto")
            title_x = 39 * mm
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(title_x, height - 10.5 * mm, t("document_title"))
        canvas.setFillColor(colors.HexColor("#F2C879"))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(title_x, height - 16.5 * mm, f"{professor_name} | {period_label}")
        canvas.setStrokeColor(LINE)
        canvas.line(12 * mm, 12 * mm, width - 12 * mm, 12 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.8)
        footer_name = primary_identity.company_name if primary_identity else "Piano Academie"
        footer_siret = f" | SIRET: {primary_identity.company_siret}" if primary_identity else ""
        canvas.drawString(12 * mm, 7.5 * mm, f"{footer_name}{footer_siret}")
        canvas.drawRightString(width - 12 * mm, 7.5 * mm, f"{t('page')} {document.page}")
        canvas.restoreState()

    content_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="teacher-statement-content",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates(PageTemplate(id="teacher-statement", frames=[content_frame], onPage=draw_page))

    story: list[Any] = []
    intro = Table(
        [
            [Paragraph(f"<b>{t('teacher')}</b><br/>{escape(professor_name)}", styles["PABody"]), Paragraph(f"<b>{t('period')}</b><br/>{escape(period_label)}", styles["PABody"]), Paragraph(f"<b>{t('generated')}</b><br/>{generated.strftime('%d/%m/%Y %H:%M')}", styles["PABody"])],
        ],
        colWidths=[100 * mm, 70 * mm, 70 * mm],
    )
    intro.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE_GOLD), ("BOX", (0, 0), (-1, -1), 0.6, GOLD), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E8D4AE")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([intro, Spacer(1, 4 * mm), Paragraph(t("official_info"), styles["PAHeading"])])

    if identity_list:
        identity_cells = [Paragraph("<br/>".join(_identity_lines(identity, normalized_language)), styles["PASmall"]) for identity in identity_list]
        identity_table = Table([identity_cells], colWidths=[(246 * mm) / len(identity_cells)] * len(identity_cells))
        identity_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE), ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(identity_table)
    story.extend([Spacer(1, 3 * mm), Paragraph(t("not_invoice"), styles["PANote"]), Spacer(1, 3 * mm), Paragraph(t("summary"), styles["PAHeading"])])

    totals_label = " | ".join(_money(value, currency, normalized_language) for currency, value in sorted(totals_by_currency.items())) or _money(0, "EUR", normalized_language)
    summary_data = [[
        Paragraph(f"<font color='#607089'>{t('courses')}</font><br/><b><font size='14'>{len(sessions)}</font></b>", styles["PABody"]),
        Paragraph(f"<font color='#607089'>{t('hours')}</font><br/><b><font size='14'>{_hours(total_hours, normalized_language)}</font></b>", styles["PABody"]),
        Paragraph(f"<font color='#607089'>{t('total_ht')}</font><br/><b><font size='14'>{totals_label}</font></b>", styles["PABody"]),
        Paragraph(f"<font color='#607089'>{t('attendance')}</font><br/><b><font color='{'#237A4B' if attendance_complete else '#9A6500'}'>{t('attendance_complete') if attendance_complete else t('attendance_incomplete')}</font></b>", styles["PABody"]),
    ]]
    summary = Table(summary_data, colWidths=[61.5 * mm] * 4)
    summary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([summary, Spacer(1, 4 * mm), Paragraph(t("details"), styles["PAHeading"])])

    if not sessions:
        story.append(Paragraph(t("no_course"), styles["PABody"]))
    else:
        header_style = ParagraphStyle(name="PAHeader", parent=styles["PATable"], fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_LEFT)
        table_data: list[list[Any]] = [[
            Paragraph(t("date_time"), header_style),
            Paragraph(t("course_location"), header_style),
            Paragraph(t("duration"), header_style),
            Paragraph(t("students"), header_style),
            Paragraph(t("rate"), header_style),
            Paragraph(t("amount"), header_style),
        ]]
        for session in sessions:
            date_cell = Paragraph(f"<b>{escape(session['date'])}</b><br/>{escape(session['time'])}", styles["PATable"])
            course_cell = Paragraph(f"<b>{escape(session['title'])}</b><br/>{escape(session['location'])}<br/><font color='#607089'>{t('entity')}: {escape(session['entity'])}</font>", styles["PATable"])
            attendance_cell = Paragraph("<br/>".join(escape(value) for value in session["attendance"].split("\n")), styles["PATable"])
            table_data.append([
                date_cell,
                course_cell,
                Paragraph(escape(session["duration"]), styles["PATableCenter"]),
                attendance_cell,
                Paragraph(escape(session["rate"]), styles["PATableRight"]),
                Paragraph(f"<b>{escape(session['amount'])}</b>", styles["PATableRight"]),
            ])
        detail_table = Table(table_data, colWidths=[28 * mm, 59 * mm, 18 * mm, 77 * mm, 31 * mm, 31 * mm], repeatRows=1, splitByRow=1)
        table_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for row_index in range(1, len(table_data)):
            if row_index % 2 == 0:
                table_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), PALE_BLUE))
        detail_table.setStyle(TableStyle(table_commands))
        story.append(detail_table)

    doc.build(story)
    return output.getvalue()
