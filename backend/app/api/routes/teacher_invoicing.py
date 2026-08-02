from __future__ import annotations

import base64
import csv
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import BookingStatus, CourseType, DeliveryMode, Location, Professor
from app.models.ops import AppSetting, LegalEntity
from app.models.teacher_invoicing import (
    TeacherInvoice,
    TeacherInvoiceAuditEvent,
    TeacherInvoiceLine,
    TeacherMonthlyStatement,
    TeacherStatementMessage,
)
from app.models.user import User, UserRole
from app.schemas.professor import (
    TeacherApproveStatementsOut,
    TeacherStatementDisputeLinesRequest,
    TeacherInvoiceLineOut,
    TeacherInvoiceOut,
    TeacherStatementDisputeRequest,
    TeacherStatementMissingServiceRequest,
    TeacherStatementMissingSessionOut,
    TeacherStatementOut,
)
from app.services.email_delivery import send_email
from app.services.i18n import normalize_language
from app.services.messaging_templates import resolve_sender_profile
from app.services.teacher_invoice_documents import (
    get_teacher_invoice_template,
    render_teacher_invoice_html,
    render_teacher_invoice_pdf_from_html,
)
from app.services.teacher_invoicing import (
    ComputedStatement,
    PARIS_TIMEZONE,
    compute_teacher_monthly_statements,
    invoice_period_label,
    statement_to_snapshot_payload,
)
from app.services.payouts import resolve_hourly_rate_for_missing_service

router = APIRouter(prefix="/teacher")

TEACHER_I18N = {
    "fr": {
        "delivery_online": "En ligne",
        "delivery_onsite": "Presentiel",
        "delivery_any": "Tous modes",
        "professor_not_found": "Profil professeur introuvable",
        "siret_pending": "en cours d'immatriculation",
        "payment_instructions": "Paiement par virement bancaire sous 30 jours.",
        "late_payment_penalty_text": "Penalites de retard conformement aux CGV.",
        "dispute_subject": "Litige releve professeur {name} - {period}",
        "attendance_incomplete": "Presences incompletes. Completez les seances manquantes avant validation.",
        "statement_blocked": "Le releve est bloque par un litige ouvert ou un signalement de prestation manquante.",
        "statement_not_approved": "Releve non approuve: validez d abord le releve avant generation de facture.",
        "company_fallback": "Societe",
        "entity_fallback": "Entite",
        "statement_not_found_period": "Aucun releve trouve pour cette periode",
        "selected_lines_none": "- (aucune ligne precisee)",
        "selected_lines_issue": "Probleme sur prestations selectionnees\nLignes:\n{selected_lines}\n\nCommentaire professeur:\n{comment}",
        "service_type_not_found": "Type de prestation introuvable",
        "location_not_found": "Lieu introuvable",
        "service_type_required": "Type de prestation et duree obligatoires",
        "service_fallback": "Prestation",
        "missing_service_message": "Signalement prestation manquante\nDate: {service_date}\nPrestation: {service_label}\nEleve/Groupe: {student_or_group}\nDuree (min): {duration_minutes}\nModalite/Lieu: {modality_label}\nEleves presents: {attendee_count}\nTaux estime HT: {estimated_rate}\n\nCommentaire professeur:\n{comment}",
        "external_invoice_must_be_approved": "Le releve doit etre approuve avant envoi d une facture externe",
        "payor_invalid": "Entite payeur invalide",
        "statement_not_found_payor": "Releve introuvable pour l entite payeur selectionnee",
        "external_invoice_default_name": "facture.pdf",
        "file_must_be_pdf": "Le fichier doit etre un PDF",
        "file_empty": "Fichier PDF vide",
        "file_too_large": "Fichier PDF trop volumineux (max 10 Mo)",
        "external_invoice_subject": "Facture externe professeur - {period}",
        "external_invoice_body": "Facture externe transmise par {teacher_name}\nPeriode: {period}\nEntite payeur: {payor_name}\nTotal TTC releve: {total_ttc} {currency}\nNote: {note}",
        "csv_file_name": "releve_prestations_{year}_{month}.csv",
        "csv_header_entity": "entite",
        "csv_header_period": "periode",
        "csv_header_service": "prestation",
        "csv_header_date": "date",
        "csv_header_time": "horaire",
        "csv_header_student_group": "eleve_ou_groupe",
        "csv_header_location_mode": "lieu_modalite",
        "csv_header_attendance": "presences_eleves",
        "csv_header_duration": "duree_minutes",
        "csv_header_rate_ht": "taux_ht",
        "csv_header_amount_ht": "montant_ht",
        "csv_header_vat": "tva",
        "csv_header_total_ttc": "total_ttc",
        "csv_header_currency": "devise",
        "attendance_booked": "A renseigner",
        "attendance_attended": "Present(e)",
        "attendance_no_show": "Absent(e) non excuse(e)",
        "attendance_excused": "Absent(e) excuse(e)",
        "teacher_invoice_not_found": "Facture professeur introuvable",
        "teacher_invoice_subject": "Facture professeur {invoice_number}",
        "teacher_invoice_body": "Facture professeur {invoice_number}\nPeriode: {period}\nTotal TTC: {total_ttc}\nProfesseur: {teacher_name}",
    },
    "en": {
        "delivery_online": "Online",
        "delivery_onsite": "On-site",
        "delivery_any": "All modes",
        "professor_not_found": "Professor profile not found",
        "siret_pending": "registration pending",
        "payment_instructions": "Payment by bank transfer within 30 days.",
        "late_payment_penalty_text": "Late-payment penalties apply according to the terms and conditions.",
        "dispute_subject": "Teacher statement dispute {name} - {period}",
        "attendance_incomplete": "Attendance is incomplete. Complete missing sessions before approval.",
        "statement_blocked": "The statement is blocked by an open dispute or a missing-service report.",
        "statement_not_approved": "Statement not approved: validate the statement before generating an invoice.",
        "company_fallback": "Company",
        "entity_fallback": "Entity",
        "statement_not_found_period": "No statement found for this period",
        "selected_lines_none": "- (no lines selected)",
        "selected_lines_issue": "Issue on selected services\nLines:\n{selected_lines}\n\nTeacher comment:\n{comment}",
        "service_type_not_found": "Service type not found",
        "location_not_found": "Location not found",
        "service_type_required": "Service type and duration are required",
        "service_fallback": "Service",
        "missing_service_message": "Missing service report\nDate: {service_date}\nService: {service_label}\nStudent/Group: {student_or_group}\nDuration (min): {duration_minutes}\nMode/Location: {modality_label}\nStudents present: {attendee_count}\nEstimated net rate: {estimated_rate}\n\nTeacher comment:\n{comment}",
        "external_invoice_must_be_approved": "The statement must be approved before sending an external invoice",
        "payor_invalid": "Invalid payor legal entity",
        "statement_not_found_payor": "Statement not found for the selected payor",
        "external_invoice_default_name": "invoice.pdf",
        "file_must_be_pdf": "The file must be a PDF",
        "file_empty": "Empty PDF file",
        "file_too_large": "PDF file is too large (max 10 MB)",
        "external_invoice_subject": "Teacher external invoice - {period}",
        "external_invoice_body": "External invoice sent by {teacher_name}\nPeriod: {period}\nPayor entity: {payor_name}\nStatement gross total: {total_ttc} {currency}\nNote: {note}",
        "csv_file_name": "teacher_statement_{year}_{month}.csv",
        "csv_header_entity": "entity",
        "csv_header_period": "period",
        "csv_header_service": "service",
        "csv_header_date": "date",
        "csv_header_time": "time",
        "csv_header_student_group": "student_or_group",
        "csv_header_location_mode": "location_mode",
        "csv_header_attendance": "student_attendance",
        "csv_header_duration": "duration_minutes",
        "csv_header_rate_ht": "net_rate",
        "csv_header_amount_ht": "net_amount",
        "csv_header_vat": "vat",
        "csv_header_total_ttc": "gross_total",
        "csv_header_currency": "currency",
        "attendance_booked": "To complete",
        "attendance_attended": "Present",
        "attendance_no_show": "Unexcused absence",
        "attendance_excused": "Excused absence",
        "teacher_invoice_not_found": "Teacher invoice not found",
        "teacher_invoice_subject": "Teacher invoice {invoice_number}",
        "teacher_invoice_body": "Teacher invoice {invoice_number}\nPeriod: {period}\nGross total: {total_ttc}\nTeacher: {teacher_name}",
    },
}


def _teacher_language(current_user: User | None = None, *, language: str | None = None) -> str:
    if language is not None:
        return normalize_language(language)
    return normalize_language(current_user.preferred_language if current_user is not None else None)


def _teacher_text(key: str, *, language: str | None = None, current_user: User | None = None, **values: object) -> str:
    normalized_language = _teacher_language(current_user, language=language)
    template = TEACHER_I18N.get(normalized_language, TEACHER_I18N["fr"]).get(key, key)
    return template.format(**values)


def _teacher_csv_headers(language: str | None) -> list[str]:
    return [
        _teacher_text("csv_header_entity", language=language),
        _teacher_text("csv_header_period", language=language),
        _teacher_text("csv_header_service", language=language),
        _teacher_text("csv_header_date", language=language),
        _teacher_text("csv_header_time", language=language),
        _teacher_text("csv_header_student_group", language=language),
        _teacher_text("csv_header_location_mode", language=language),
        _teacher_text("csv_header_attendance", language=language),
        _teacher_text("csv_header_duration", language=language),
        _teacher_text("csv_header_rate_ht", language=language),
        _teacher_text("csv_header_amount_ht", language=language),
        _teacher_text("csv_header_vat", language=language),
        _teacher_text("csv_header_total_ttc", language=language),
        _teacher_text("csv_header_currency", language=language),
    ]


def _attendance_status_label(value: str, *, language: str | None = None) -> str:
    normalized = (value or "").strip().upper()
    key_by_status = {
        BookingStatus.BOOKED.value: "attendance_booked",
        BookingStatus.ATTENDED.value: "attendance_attended",
        BookingStatus.NO_SHOW.value: "attendance_no_show",
        BookingStatus.EXCUSED_ABSENCE.value: "attendance_excused",
    }
    key = key_by_status.get(normalized)
    return _teacher_text(key, language=language) if key is not None else normalized or "-"


def _session_attendance_csv_label(item: dict[str, Any], *, language: str | None = None) -> str:
    raw_attendance = item.get("attendance")
    if not isinstance(raw_attendance, list) or not raw_attendance:
        return "-"
    labels: list[str] = []
    for raw_row in raw_attendance:
        if not isinstance(raw_row, dict):
            continue
        student_name = str(raw_row.get("student_name") or "-").strip() or "-"
        status_label = _attendance_status_label(str(raw_row.get("status") or ""), language=language)
        labels.append(f"{student_name}: {status_label}")
    return " | ".join(labels) or "-"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _format_money(value: Decimal | None) -> str:
    return f"{_quantize(value or Decimal('0'))}"


def _delivery_mode_label(mode: DeliveryMode, *, language: str | None = None) -> str:
    if mode == DeliveryMode.ONLINE:
        return _teacher_text("delivery_online", language=language)
    if mode == DeliveryMode.ONSITE:
        return _teacher_text("delivery_onsite", language=language)
    return _teacher_text("delivery_any", language=language)


def _teacher_invoice_lines_payload(lines: list[TeacherInvoiceLine]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for line in lines:
        ref = "-"
        if line.course_type_id:
            ref = str(line.course_type_id).split("-")[0].upper()
        payload.append(
            {
                "ref": ref,
                "label": (line.course_type_label or "").strip() or "-",
                "unit_price_ht": _format_money(line.unit_rate_ht),
                "quantity": _format_money(line.hours),
                "total_ht": _format_money(line.amount_ht),
            }
        )
    return payload


def _resolve_professor_profile(db: Session, *, current_user: User) -> Professor:
    professor = db.scalar(select(Professor).where(Professor.email == current_user.email))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("professor_not_found", current_user=current_user))
    return professor


def _statement_status_from_computed(computed: ComputedStatement) -> str:
    return "to_verify" if computed.attendance_complete else "awaiting_attendance"


def _sync_monthly_statements(
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
    now = _utcnow()
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


def _missing_sessions_from_computed(rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]]) -> list[TeacherStatementMissingSessionOut]:
    missing: list[TeacherStatementMissingSessionOut] = []
    for _, computed in rows:
        for item in computed.missing_sessions:
            missing.append(
                TeacherStatementMissingSessionOut(
                    session_id=item.session_id,
                    title=item.title,
                    start_at_utc=item.start_at_utc,
                    end_at_utc=item.end_at_utc,
                    pending_students_count=item.pending_students_count,
                    total_students_count=item.total_students_count,
                )
            )
    return missing


def _statement_out(row: TeacherMonthlyStatement, computed: ComputedStatement) -> TeacherStatementOut:
    return TeacherStatementOut(
        statement_id=row.id,
        payor_legal_entity_id=computed.payor_legal_entity_id,
        payor_legal_entity_name=computed.payor_legal_entity_name,
        year=computed.year,
        month=computed.month,
        status=row.status,
        attendance_complete=computed.attendance_complete,
        currency=computed.currency,
        totals_ht=computed.totals_ht,
        totals_vat=computed.totals_vat,
        totals_ttc=computed.totals_ttc,
        dispute_message_last=row.dispute_message_last,
        lines=[
            {
                "course_type_id": line.course_type_id,
                "course_type_label": line.course_type_label,
                "hours": line.hours,
                "unit_rate_ht": line.unit_rate_ht,
                "amount_ht": line.amount_ht,
                "amount_ttc": line.amount_ttc,
                "meta": line.meta,
            }
            for line in computed.lines
        ],
        missing_sessions=[
            {
                "session_id": item.session_id,
                "title": item.title,
                "start_at_utc": item.start_at_utc,
                "end_at_utc": item.end_at_utc,
                "pending_students_count": item.pending_students_count,
                "total_students_count": item.total_students_count,
            }
            for item in computed.missing_sessions
        ],
    )


def _render_statement_csv(
    rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]],
    *,
    year: int,
    month: int,
    language: str,
) -> str:
    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(_teacher_csv_headers(language))
    period_label = invoice_period_label(year=year, month=month, language=language)
    total_hours = Decimal("0.00")
    total_ht = Decimal("0.00")
    total_vat = Decimal("0.00")
    total_ttc = Decimal("0.00")

    for _, computed in rows:
        total_hours += sum((line.hours for line in computed.lines), Decimal("0.00"))
        total_ht += computed.totals_ht
        total_vat += computed.totals_vat
        total_ttc += computed.totals_ttc
        for line in computed.lines:
            session_items = line.meta.get("session_items") if isinstance(line.meta, dict) else None
            if isinstance(session_items, list) and session_items:
                for item in session_items:
                    start_iso = str(item.get("start_at_utc") or "")
                    end_iso = str(item.get("end_at_utc") or "")
                    start_dt = datetime.fromisoformat(start_iso) if start_iso else None
                    end_dt = datetime.fromisoformat(end_iso) if end_iso else None
                    schedule_label = "-"
                    if start_dt is not None and end_dt is not None:
                        local_start = start_dt.astimezone(PARIS_TIMEZONE)
                        local_end = end_dt.astimezone(PARIS_TIMEZONE)
                        schedule_label = f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}"
                    raw_modality = str(item.get("modality") or "").strip().upper()
                    if raw_modality in {"EN_LIGNE", "ONLINE"}:
                        modality_label = _teacher_text("delivery_online", language=language)
                    elif raw_modality in {"PRESENTIEL", "ONSITE"}:
                        modality_label = _teacher_text("delivery_onsite", language=language)
                    else:
                        modality_label = raw_modality or "-"
                    writer.writerow(
                        [
                            computed.payor_legal_entity_name,
                            period_label,
                            str(item.get("title") or line.course_type_label),
                            str(item.get("date") or ""),
                            schedule_label,
                            str(item.get("student_or_group") or ""),
                            f"{item.get('location_name') or '-'} / {modality_label}",
                            _session_attendance_csv_label(item, language=language),
                            str(item.get("duration_minutes") or ""),
                            str(item.get("unit_rate_ht") or line.unit_rate_ht),
                            str(item.get("amount_ht") or line.amount_ht),
                            str(
                                item.get("vat_amount")
                                or _quantize(
                                    Decimal(item.get("amount_ttc") or "0")
                                    - Decimal(item.get("amount_ht") or "0")
                                )
                            ),
                            str(item.get("amount_ttc") or line.amount_ttc),
                            computed.currency,
                        ]
                    )
            else:
                writer.writerow(
                    [
                        computed.payor_legal_entity_name,
                        period_label,
                        line.course_type_label,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        f"{line.unit_rate_ht}",
                        f"{line.amount_ht}",
                        f"{_quantize(line.amount_ttc - line.amount_ht)}",
                        f"{line.amount_ttc}",
                        computed.currency,
                    ]
                )

    writer.writerow([])
    writer.writerow(
        [
            "RECAPITULATIF" if normalize_language(language) == "fr" else "SUMMARY",
            period_label,
            "TOTAL",
            "",
            "",
            "",
            "",
            "",
            f"{_quantize(total_hours)} h",
            "",
            f"{_quantize(total_ht)}",
            f"{_quantize(total_vat)}",
            f"{_quantize(total_ttc)}",
            rows[0][1].currency if rows else "EUR",
        ]
    )
    return output.getvalue()


def _invoice_lines_for_invoice_ids(db: Session, *, invoice_ids: list[UUID]) -> dict[UUID, list[TeacherInvoiceLine]]:
    if not invoice_ids:
        return {}
    rows = db.scalars(
        select(TeacherInvoiceLine)
        .where(TeacherInvoiceLine.invoice_id.in_(invoice_ids))
        .order_by(TeacherInvoiceLine.created_at.asc(), TeacherInvoiceLine.id.asc())
    ).all()
    grouped: dict[UUID, list[TeacherInvoiceLine]] = {invoice_id: [] for invoice_id in invoice_ids}
    for row in rows:
        grouped.setdefault(row.invoice_id, []).append(row)
    return grouped


def _invoice_out(
    invoice: TeacherInvoice,
    *,
    payor_name: str,
    lines: list[TeacherInvoiceLine],
) -> TeacherInvoiceOut:
    return TeacherInvoiceOut(
        id=invoice.id,
        statement_id=invoice.statement_id,
        payor_legal_entity_id=invoice.payor_legal_entity_id,
        payor_legal_entity_name=payor_name,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        is_vat_applicable=invoice.is_vat_applicable,
        vat_rate=invoice.vat_rate,
        totals_ht=invoice.totals_ht,
        totals_vat=invoice.totals_vat,
        totals_ttc=invoice.totals_ttc,
        teacher_siret_display=invoice.teacher_siret_display,
        teacher_iban=invoice.teacher_iban,
        status=invoice.status,
        sent_to_accounting_at=invoice.sent_to_accounting_at,
        cancelled_at=invoice.cancelled_at,
        created_at=invoice.created_at,
        lines=[
            TeacherInvoiceLineOut(
                id=line.id,
                course_type_id=line.course_type_id,
                course_type_label=line.course_type_label,
                hours=line.hours,
                unit_rate_ht=line.unit_rate_ht,
                amount_ht=line.amount_ht,
                amount_ttc=line.amount_ttc,
                meta=line.meta if isinstance(line.meta, dict) else {},
            )
            for line in lines
        ],
    )


def _log_audit(
    db: Session,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    teacher_id: UUID | None = None,
    statement_id: UUID | None = None,
    invoice_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        TeacherInvoiceAuditEvent(
            event_type=event_type,
            actor_user_id=actor_user_id,
            teacher_id=teacher_id,
            statement_id=statement_id,
            invoice_id=invoice_id,
            payload=payload or {},
        )
    )


def _invoice_pdf_bytes(
    db: Session,
    *,
    invoice: TeacherInvoice,
    payor: LegalEntity,
    professor: Professor,
    language: str | None = None,
) -> bytes:
    if invoice.pdf_storage_key:
        try:
            return base64.b64decode(invoice.pdf_storage_key.encode("ascii"))
        except Exception:
            pass

    normalized_language = _teacher_language(language=language)
    html_template, _, _ = get_teacher_invoice_template(db, language=normalized_language)
    invoice_lines = db.scalars(
        select(TeacherInvoiceLine)
        .where(TeacherInvoiceLine.invoice_id == invoice.id)
        .order_by(TeacherInvoiceLine.created_at.asc(), TeacherInvoiceLine.id.asc())
    ).all()
    rendered_html = render_teacher_invoice_html(
        html_template=html_template,
        context={
            "teacher_full_name": f"{professor.first_name} {professor.last_name}".strip(),
            "teacher_company_name": (professor.teacher_company_name or "").strip() or f"{professor.first_name} {professor.last_name}".strip(),
            "teacher_company_address": (professor.teacher_company_address or "").strip() or "-",
            "teacher_email": professor.email,
            "teacher_phone": (professor.phone or "").strip() or "-",
            "teacher_siret_display": (invoice.teacher_siret_display or "").strip() or _teacher_text("siret_pending", language=normalized_language),
            "teacher_iban": (invoice.teacher_iban or "").strip() or "-",
            "payor_company_name": (payor.name or "").strip() or "-",
            "payor_company_address": (payor.address_text or "").strip() or "-",
            "payor_company_siret": (payor.siret or "").strip() or "-",
            "payor_company_vat": (payor.vat_number or "").strip() or "-",
            "invoice_number_display": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "invoice_period_label": invoice_period_label(year=invoice.invoice_date.year, month=invoice.invoice_date.month, language=normalized_language),
            "lines_by_course_type": _teacher_invoice_lines_payload(invoice_lines),
            "totals_ht": _format_money(invoice.totals_ht),
            "totals_vat": _format_money(invoice.totals_vat),
            "totals_ttc": _format_money(invoice.totals_ttc),
            "payment_instructions": _teacher_text("payment_instructions", language=normalized_language),
            "late_payment_penalty_text": _teacher_text("late_payment_penalty_text", language=normalized_language),
            "comptability_email": "-",
        },
    )
    return render_teacher_invoice_pdf_from_html(rendered_html)


def _resolve_accounting_email(db: Session, *, payor: LegalEntity) -> str:
    by_entity = (payor.accounting_email or "").strip()
    if by_entity:
        return by_entity
    setting = db.scalar(select(AppSetting.value).where(AppSetting.key == "comptability_email"))
    if setting is not None and setting.strip():
        return setting.strip()
    return "comptabilite@piano-academie.com"


def _send_statement_dispute_email(
    db: Session,
    *,
    rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]],
    professor: Professor,
    current_user: User,
    year: int,
    month: int,
    message: str,
) -> None:
    language = _teacher_language(current_user)
    payor_entity = db.scalar(select(LegalEntity).where(LegalEntity.id == rows[0][1].payor_legal_entity_id))
    if payor_entity is None:
        return
    to_email = _resolve_accounting_email(db, payor=payor_entity)
    sender = resolve_sender_profile(db, sender_kind="TEACHER")
    try:
        send_email(
            to_email=to_email,
            subject=_teacher_text(
                "dispute_subject",
                language=language,
                name=f"{professor.first_name} {professor.last_name}".strip(),
                period=invoice_period_label(year=year, month=month, language=language),
            ),
            body=message,
            context="TEACHER_STATEMENT_DISPUTE",
            from_email=sender.from_email,
            from_name=sender.from_name,
            reply_to=sender.reply_to,
            subject_prefix=sender.subject_prefix,
            sender_user_id=current_user.id,
            professor_id=professor.id,
        )
    except Exception:
        # The dispute is already persisted; email failure must not block professor workflow.
        return


def _mark_statements_with_message(
    db: Session,
    *,
    rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]],
    professor: Professor,
    current_user: User,
    status_value: str,
    message: str,
    source: str,
    message_type: str,
    message_meta: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
) -> list[TeacherStatementOut]:
    now = _utcnow()
    cleaned_message = message.strip()
    for statement, _ in rows:
        statement.status = status_value
        statement.dispute_message_last = cleaned_message
        statement.updated_at = now
        db.add(statement)
        db.add(
            TeacherStatementMessage(
                statement_id=statement.id,
                teacher_id=professor.id,
                message=cleaned_message,
                source=source,
                message_type=message_type,
                status="a_traiter",
                meta=message_meta,
                related_entity_type="teacher_monthly_statement",
                related_entity_id=statement.id,
                updated_at=now,
            )
        )
        _log_audit(
            db,
            event_type=event_type,
            actor_user_id=current_user.id,
            teacher_id=professor.id,
            statement_id=statement.id,
            payload=payload,
        )
    db.commit()
    return [_statement_out(statement, computed) for statement, computed in rows]

def _assert_no_missing_sessions(rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]], *, language: str | None = None) -> None:
    missing_sessions = _missing_sessions_from_computed(rows)
    if missing_sessions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": _teacher_text("attendance_incomplete", language=language),
                "missing_sessions": [row.model_dump(mode="json") for row in missing_sessions],
            },
        )


def _assert_statements_approvable(rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]], *, language: str | None = None) -> None:
    blocked_statuses = {"in_dispute", "awaiting_admin_feedback"}
    blocked = [statement.status for statement, _ in rows if statement.status in blocked_statuses]
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": _teacher_text("statement_blocked", language=language),
                "blocked_statuses": sorted(set(blocked)),
            },
        )


def _generate_invoices_for_period(
    db: Session,
    *,
    current_user: User,
    professor: Professor,
    rows: list[tuple[TeacherMonthlyStatement, ComputedStatement]],
    year: int,
    month: int,
    require_validated_status: bool,
) -> TeacherApproveStatementsOut:
    language = _teacher_language(current_user)
    _assert_no_missing_sessions(rows, language=language)

    locked_professor = db.scalar(select(Professor).where(Professor.id == professor.id).with_for_update())
    if locked_professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("professor_not_found", language=language))
    counter = max(1, int(locked_professor.teacher_invoice_counter or 1))
    now = _utcnow()
    invoice_date = now.date()
    generated: list[TeacherInvoice] = []

    for statement, computed in sorted(rows, key=lambda row: row[1].payor_legal_entity_name.casefold()):
        existing_invoice = db.scalar(
            select(TeacherInvoice)
            .where(TeacherInvoice.statement_id == statement.id)
            .order_by(TeacherInvoice.created_at.desc())
            .limit(1)
        )
        if existing_invoice is not None:
            generated.append(existing_invoice)
            continue

        if require_validated_status and statement.status not in {"validated", "invoice_generated", "approved"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_teacher_text("statement_not_approved", language=language),
            )

        payor = db.scalar(select(LegalEntity).where(LegalEntity.id == computed.payor_legal_entity_id))
        if payor is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("payor_invalid", language=language))

        invoice_number = f"PROF-{str(locked_professor.id).split('-')[0].upper()}-{counter:06d}"
        counter += 1
        due_date = invoice_date + timedelta(days=30)
        teacher_siret_display = (locked_professor.teacher_siret or "").strip() or _teacher_text("siret_pending", language=language)
        teacher_iban = (
            (locked_professor.teacher_iban or "").strip()
            or (locked_professor.iban or "").strip()
            or "-"
        )

        invoice = TeacherInvoice(
            teacher_id=locked_professor.id,
            statement_id=statement.id,
            payor_legal_entity_id=payor.id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            is_vat_applicable=bool(locked_professor.teacher_is_vat_applicable),
            vat_rate=(locked_professor.teacher_vat_rate if locked_professor.teacher_is_vat_applicable else None),
            totals_ht=_quantize(computed.totals_ht),
            totals_vat=_quantize(computed.totals_vat),
            totals_ttc=_quantize(computed.totals_ttc),
            recipient_company_name=(payor.name or "").strip() or _teacher_text("company_fallback", language=language),
            recipient_company_address=(payor.address_text or "").strip() or "-",
            recipient_company_siret=(payor.siret or "").strip() or None,
            recipient_company_vat=(payor.vat_number or "").strip() or None,
            teacher_siret_display=teacher_siret_display,
            teacher_iban=teacher_iban,
            status="generated",
            updated_at=now,
        )
        db.add(invoice)
        db.flush()

        for line in computed.lines:
            db.add(
                TeacherInvoiceLine(
                    invoice_id=invoice.id,
                    course_type_id=line.course_type_id,
                    course_type_label=line.course_type_label,
                    hours=_quantize(line.hours),
                    unit_rate_ht=_quantize(line.unit_rate_ht),
                    amount_ht=_quantize(line.amount_ht),
                    amount_ttc=_quantize(line.amount_ttc),
                    meta=line.meta,
                )
            )
        db.flush()
        invoice_lines = db.scalars(
            select(TeacherInvoiceLine)
            .where(TeacherInvoiceLine.invoice_id == invoice.id)
            .order_by(TeacherInvoiceLine.created_at.asc(), TeacherInvoiceLine.id.asc())
        ).all()

        html_template, _, _ = get_teacher_invoice_template(db, language=language)
        rendered_html = render_teacher_invoice_html(
            html_template=html_template,
            context={
                "teacher_full_name": f"{locked_professor.first_name} {locked_professor.last_name}".strip(),
                "teacher_company_name": (locked_professor.teacher_company_name or "").strip() or f"{locked_professor.first_name} {locked_professor.last_name}".strip(),
                "teacher_company_address": (locked_professor.teacher_company_address or "").strip() or "-",
                "teacher_email": locked_professor.email,
                "teacher_phone": (locked_professor.phone or "").strip() or "-",
                "teacher_siret_display": teacher_siret_display,
                "teacher_iban": teacher_iban,
                "payor_company_name": (payor.name or "").strip() or "-",
                "payor_company_address": (payor.address_text or "").strip() or "-",
                "payor_company_siret": (payor.siret or "").strip() or "-",
                "payor_company_vat": (payor.vat_number or "").strip() or "-",
                "invoice_number_display": invoice_number,
                "invoice_date": invoice_date.isoformat(),
                "due_date": due_date.isoformat(),
                "invoice_period_label": invoice_period_label(year=year, month=month, language=language),
                "lines_by_course_type": _teacher_invoice_lines_payload(invoice_lines),
                "totals_ht": _format_money(computed.totals_ht),
                "totals_vat": _format_money(computed.totals_vat),
                "totals_ttc": _format_money(computed.totals_ttc),
                "payment_instructions": _teacher_text("payment_instructions", language=language),
                "late_payment_penalty_text": _teacher_text("late_payment_penalty_text", language=language),
                "comptability_email": _resolve_accounting_email(db, payor=payor),
            },
        )
        pdf_content = render_teacher_invoice_pdf_from_html(rendered_html)
        invoice.pdf_storage_key = base64.b64encode(pdf_content).decode("ascii")
        db.add(invoice)

        statement.status = "invoice_generated"
        statement.updated_at = now
        db.add(statement)

        _log_audit(
            db,
            event_type="teacher_invoice_generated",
            actor_user_id=current_user.id,
            teacher_id=locked_professor.id,
            statement_id=statement.id,
            invoice_id=invoice.id,
            payload={"invoice_number": invoice_number},
        )
        generated.append(invoice)

    locked_professor.teacher_invoice_counter = counter
    locked_professor.updated_at = now
    db.add(locked_professor)
    db.commit()

    payor_by_id = {
        row.id: row
        for row in db.scalars(
            select(LegalEntity).where(LegalEntity.id.in_([inv.payor_legal_entity_id for inv in generated]))
        ).all()
    }
    lines_by_invoice_id = _invoice_lines_for_invoice_ids(db, invoice_ids=[inv.id for inv in generated])
    return TeacherApproveStatementsOut(
        generated_invoices=[
            _invoice_out(
                invoice,
                payor_name=(
                    payor_by_id.get(invoice.payor_legal_entity_id).name
                    if payor_by_id.get(invoice.payor_legal_entity_id)
                    else _teacher_text("entity_fallback", language=language)
                ),
                lines=lines_by_invoice_id.get(invoice.id, []),
            )
            for invoice in generated
        ],
        blocked_missing_sessions=[],
    )


@router.get("/admin/statements/{professor_id}/{year}/{month}", response_model=list[TeacherStatementOut])
def get_admin_teacher_statement_month(
    professor_id: UUID,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[TeacherStatementOut]:
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Periode invalide")
    professor = db.scalar(select(Professor).where(Professor.id == professor_id))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professeur introuvable")
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    db.commit()
    return [_statement_out(statement, computed) for statement, computed in rows]


@router.get("/admin/statements/{professor_id}/{year}/{month}/export.csv")
def export_admin_teacher_statement_month_csv(
    professor_id: UUID,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Periode invalide")
    professor = db.scalar(select(Professor).where(Professor.id == professor_id))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professeur introuvable")
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_teacher_text("statement_not_found_period", current_user=current_user),
        )
    language = _teacher_language(current_user)
    content = _render_statement_csv(rows, year=year, month=month, language=language)
    db.commit()
    file_name = f"releve_heures_{year}_{month:02d}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/statements", response_model=list[TeacherStatementOut])
def list_teacher_statements(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    now = _utcnow()
    resolved_year = year or now.year
    resolved_month = month or now.month
    rows = _sync_monthly_statements(db, professor=professor, year=resolved_year, month=resolved_month)
    db.commit()
    return [_statement_out(statement, computed) for statement, computed in rows]


@router.get("/statements/{year}/{month}", response_model=list[TeacherStatementOut])
def get_teacher_statement_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    db.commit()
    return [_statement_out(statement, computed) for statement, computed in rows]


@router.post("/statements/{year}/{month}/dispute", response_model=list[TeacherStatementOut])
def dispute_teacher_statement_month(
    year: int,
    month: int,
    payload: TeacherStatementDisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    message = payload.message.strip()
    out = _mark_statements_with_message(
        db,
        rows=rows,
        professor=professor,
        current_user=current_user,
        status_value="in_dispute",
        message=message,
        source="releves_professeur",
        message_type="erreur_releve",
        message_meta={
            "scope": "month",
            "year": year,
            "month": month,
            "message": message,
        },
        event_type="teacher_statement_disputed",
        payload={"message": message},
    )
    _send_statement_dispute_email(
        db,
        rows=rows,
        professor=professor,
        current_user=current_user,
        year=year,
        month=month,
        message=message,
    )
    return out


@router.post("/statements/{year}/{month}/dispute-lines", response_model=list[TeacherStatementOut])
def dispute_teacher_statement_selected_lines(
    year: int,
    month: int,
    payload: TeacherStatementDisputeLinesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    selected_lines = [row.strip() for row in payload.selected_lines if row.strip()]
    language = _teacher_language(current_user)
    selected_lines_text = "\n".join(f"- {label}" for label in selected_lines) if selected_lines else _teacher_text("selected_lines_none", language=language)
    message = _teacher_text(
        "selected_lines_issue",
        language=language,
        selected_lines=selected_lines_text,
        comment=payload.message.strip(),
    )
    out = _mark_statements_with_message(
        db,
        rows=rows,
        professor=professor,
        current_user=current_user,
        status_value="in_dispute",
        message=message,
        source="releves_professeur",
        message_type="erreur_lignes_releve",
        message_meta={
            "scope": "selected_lines",
            "year": year,
            "month": month,
            "selected_lines": selected_lines,
            "comment": payload.message.strip(),
        },
        event_type="teacher_statement_disputed_lines",
        payload={"selected_lines": selected_lines, "message": payload.message.strip()},
    )
    _send_statement_dispute_email(
        db,
        rows=rows,
        professor=professor,
        current_user=current_user,
        year=year,
        month=month,
        message=message,
    )
    return out


@router.post("/statements/{year}/{month}/report-missing-service", response_model=list[TeacherStatementOut])
def report_teacher_statement_missing_service(
    year: int,
    month: int,
    payload: TeacherStatementMissingServiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    language = _teacher_language(current_user)
    attendee_count = int(payload.attendee_count or 0)
    service_label: str
    duration_minutes: int
    modality_label: str
    estimated_rate_text: str
    estimated_rate_currency: str | None = None
    course_type_id: str | None = None
    location_id: str | None = None
    location_name: str | None = None

    if payload.course_type_id is not None and payload.location_id is not None:
        course_type = db.scalar(select(CourseType).where(CourseType.id == payload.course_type_id))
        if course_type is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("service_type_not_found", language=language))
        location = db.scalar(select(Location).where(Location.id == payload.location_id))
        if location is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("location_not_found", language=language))

        service_label = (course_type.name or "").strip() or _teacher_text("service_fallback", language=language)
        duration_minutes = int(course_type.duration_minutes or 0) or int(payload.duration_minutes or 60)
        modality_label = f"{location.name} / {_delivery_mode_label(course_type.mode, language=language)}"
        resolved_rate = resolve_hourly_rate_for_missing_service(
            db,
            professor_id=professor.id,
            course_type_id=course_type.id,
            location_id=location.id,
            on_date=payload.service_date,
            attendees_count=attendee_count,
        )
        estimated_rate_text = "-" if resolved_rate is None else _format_money(resolved_rate.hourly_rate)
        estimated_rate_currency = resolved_rate.currency_code if resolved_rate is not None else None
        course_type_id = str(course_type.id)
        location_id = str(location.id)
        location_name = location.name
    else:
        if payload.service_label is None or payload.duration_minutes is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_teacher_text("service_type_required", language=language),
            )
        service_label = payload.service_label.strip()
        duration_minutes = int(payload.duration_minutes)
        modality_label = (payload.modality or "-").strip()
        estimated_rate_text = "-" if payload.estimated_rate_ht is None else f"{_quantize(payload.estimated_rate_ht)}"

    message = _teacher_text(
        "missing_service_message",
        language=language,
        service_date=payload.service_date.isoformat(),
        service_label=service_label,
        student_or_group=(payload.student_or_group or "-").strip(),
        duration_minutes=duration_minutes,
        modality_label=modality_label,
        attendee_count=attendee_count,
        estimated_rate=f"{estimated_rate_text}{f' {estimated_rate_currency}' if estimated_rate_currency else ''}",
        comment=payload.comment.strip(),
    )
    out = _mark_statements_with_message(
        db,
        rows=rows,
        professor=professor,
        current_user=current_user,
        status_value="awaiting_admin_feedback",
        message=message,
        source="releves_professeur",
        message_type="prestation_manquante",
        message_meta={
            "scope": "missing_service",
            "year": year,
            "month": month,
            "service_date": payload.service_date.isoformat(),
            "service_label": service_label,
            "course_type_id": course_type_id,
            "location_id": location_id,
            "location_name": location_name,
            "student_or_group": (payload.student_or_group or "").strip(),
            "duration_minutes": duration_minutes,
            "modality": modality_label,
            "attendee_count": attendee_count,
            "estimated_rate_ht": estimated_rate_text,
            "estimated_rate_currency": estimated_rate_currency,
            "comment": payload.comment.strip(),
        },
        event_type="teacher_statement_missing_service_reported",
        payload={
            "service_date": payload.service_date.isoformat(),
            "service_label": service_label,
            "course_type_id": course_type_id,
            "student_or_group": (payload.student_or_group or "").strip(),
            "duration_minutes": duration_minutes,
            "modality": modality_label,
            "location_id": location_id,
            "location_name": location_name,
            "attendee_count": attendee_count,
            "estimated_rate_ht": estimated_rate_text,
            "estimated_rate_currency": estimated_rate_currency,
            "comment": payload.comment.strip(),
        },
    )
    _send_statement_dispute_email(
        db,
        rows=rows,
        professor=professor,
        current_user=current_user,
        year=year,
        month=month,
        message=message,
    )
    return out


@router.post("/statements/{year}/{month}/send-external-invoice", response_model=list[TeacherStatementOut])
async def send_teacher_external_invoice(
    year: int,
    month: int,
    payor_legal_entity_id: str = Form(...),
    note: str | None = Form(default=None),
    invoice_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    language = _teacher_language(current_user)

    try:
        payor_id = UUID(payor_legal_entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("payor_invalid", language=language)) from exc

    statement_row = next((item for item in rows if item[0].payor_legal_entity_id == payor_id), None)
    if statement_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_payor", language=language))
    statement, computed = statement_row
    if statement.status not in {"validated", "approved", "exported", "invoice_generated", "closed"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_teacher_text("external_invoice_must_be_approved", language=language),
        )

    file_name = (invoice_file.filename or _teacher_text("external_invoice_default_name", language=language)).strip()
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("file_must_be_pdf", language=language))
    file_content = await invoice_file.read()
    if not file_content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("file_empty", language=language))
    max_size = 10 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("file_too_large", language=language))

    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == computed.payor_legal_entity_id))
    if payor is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("payor_invalid", language=language))

    destination_email = _resolve_accounting_email(db, payor=payor)
    sender = resolve_sender_profile(db, sender_kind="TEACHER")
    note_text = (note or "").strip()
    send_email(
        to_email=destination_email,
        subject=_teacher_text(
            "external_invoice_subject",
            language=language,
            period=invoice_period_label(year=year, month=month, language=language),
        ),
        body=_teacher_text(
            "external_invoice_body",
            language=language,
            teacher_name=f"{professor.first_name} {professor.last_name}".strip(),
            period=invoice_period_label(year=year, month=month, language=language),
            payor_name=computed.payor_legal_entity_name,
            total_ttc=computed.totals_ttc,
            currency=computed.currency,
            note=note_text or "-",
        ),
        context="TEACHER_EXTERNAL_INVOICE_TO_ACCOUNTING",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        attachments=[(file_name, file_content, "application/pdf")],
        sender_user_id=current_user.id,
        professor_id=professor.id,
    )

    now = _utcnow()
    statement.status = "exported"
    statement.updated_at = now
    db.add(statement)
    _log_audit(
        db,
        event_type="teacher_statement_external_invoice_sent",
        actor_user_id=current_user.id,
        teacher_id=professor.id,
        statement_id=statement.id,
        payload={
            "payor_legal_entity_id": str(computed.payor_legal_entity_id),
            "payor_legal_entity_name": computed.payor_legal_entity_name,
            "destination_email": destination_email,
            "file_name": file_name,
            "file_size_bytes": len(file_content),
            "note": note_text,
        },
    )
    db.commit()
    return [_statement_out(row, computed_row) for row, computed_row in rows]


@router.post("/statements/{year}/{month}/approve-only", response_model=list[TeacherStatementOut])
def approve_teacher_statement_month_only(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherStatementOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    language = _teacher_language(current_user)
    _assert_no_missing_sessions(rows, language=language)
    _assert_statements_approvable(rows, language=language)
    now = _utcnow()
    for statement, _ in rows:
        if statement.status not in {"invoice_generated", "closed"}:
            statement.status = "validated"
            statement.updated_at = now
            db.add(statement)
            _log_audit(
                db,
                event_type="teacher_statement_validated",
                actor_user_id=current_user.id,
                teacher_id=professor.id,
                statement_id=statement.id,
            )
    db.commit()
    return [_statement_out(statement, computed) for statement, computed in rows]


@router.post("/statements/{year}/{month}/generate-invoices", response_model=TeacherApproveStatementsOut)
def generate_teacher_statement_invoices(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherApproveStatementsOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    _assert_statements_approvable(rows, language=_teacher_language(current_user))
    return _generate_invoices_for_period(
        db,
        current_user=current_user,
        professor=professor,
        rows=rows,
        year=year,
        month=month,
        require_validated_status=True,
    )


@router.post("/statements/{year}/{month}/approve", response_model=TeacherApproveStatementsOut)
def approve_teacher_statement_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherApproveStatementsOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    _assert_statements_approvable(rows, language=_teacher_language(current_user))
    return _generate_invoices_for_period(
        db,
        current_user=current_user,
        professor=professor,
        rows=rows,
        year=year,
        month=month,
        require_validated_status=True,
    )


@router.get("/statements/{year}/{month}/export.csv")
def export_teacher_statement_month_csv(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> Response:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = _sync_monthly_statements(db, professor=professor, year=year, month=month)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("statement_not_found_period", current_user=current_user))
    language = _teacher_language(current_user)

    content = _render_statement_csv(rows, year=year, month=month, language=language)
    now = _utcnow()
    for statement, _ in rows:
        if statement.status not in {"invoice_generated", "closed"}:
            statement.status = "exported"
            statement.updated_at = now
            db.add(statement)
            _log_audit(
                db,
                event_type="teacher_statement_exported",
                actor_user_id=current_user.id,
                teacher_id=professor.id,
                statement_id=statement.id,
                payload={"format": "csv", "period": f"{year}-{month:02d}"},
            )

    db.commit()
    file_name = _teacher_text("csv_file_name", language=language, year=year, month=f"{month:02d}")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/invoices", response_model=list[TeacherInvoiceOut])
def list_teacher_invoices(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[TeacherInvoiceOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    stmt = select(TeacherInvoice).where(TeacherInvoice.teacher_id == professor.id).order_by(TeacherInvoice.invoice_date.desc(), TeacherInvoice.created_at.desc())
    if year is not None:
        stmt = stmt.where(func.extract("year", TeacherInvoice.invoice_date) == year)
    if month is not None:
        stmt = stmt.where(func.extract("month", TeacherInvoice.invoice_date) == month)
    invoices = db.scalars(stmt).all()
    lines_by_invoice_id = _invoice_lines_for_invoice_ids(db, invoice_ids=[row.id for row in invoices])
    payor_by_id = {row.id: row for row in db.scalars(select(LegalEntity).where(LegalEntity.id.in_([inv.payor_legal_entity_id for inv in invoices]))).all()}
    language = _teacher_language(current_user)
    return [
        _invoice_out(
            invoice,
            payor_name=(
                payor_by_id.get(invoice.payor_legal_entity_id).name
                if payor_by_id.get(invoice.payor_legal_entity_id)
                else _teacher_text("entity_fallback", language=language)
            ),
            lines=lines_by_invoice_id.get(invoice.id, []),
        )
        for invoice in invoices
    ]


def _load_teacher_invoice_or_404(
    db: Session,
    *,
    invoice_id: UUID,
    teacher_id: UUID,
    lock: bool = False,
    language: str | None = None,
) -> TeacherInvoice:
    stmt = select(TeacherInvoice).where(TeacherInvoice.id == invoice_id, TeacherInvoice.teacher_id == teacher_id)
    if lock:
        stmt = stmt.with_for_update()
    invoice = db.scalar(stmt)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_teacher_text("teacher_invoice_not_found", language=language))
    return invoice


@router.get("/invoices/{invoice_id}", response_model=TeacherInvoiceOut)
def get_teacher_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherInvoiceOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    language = _teacher_language(current_user)
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id, language=language)
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    lines = db.scalars(select(TeacherInvoiceLine).where(TeacherInvoiceLine.invoice_id == invoice.id).order_by(TeacherInvoiceLine.created_at.asc())).all()
    return _invoice_out(
        invoice,
        payor_name=(payor.name if payor is not None else _teacher_text("entity_fallback", language=language)),
        lines=lines,
    )


@router.get("/invoices/{invoice_id}/pdf")
def download_teacher_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> Response:
    professor = _resolve_professor_profile(db, current_user=current_user)
    language = _teacher_language(current_user)
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id, language=language)
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    if payor is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("payor_invalid", language=language))
    pdf_content = _invoice_pdf_bytes(db, invoice=invoice, payor=payor, professor=professor, language=language)
    file_name = f"{invoice.invoice_number}.pdf".replace('"', "")
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )


def _update_invoice_status(
    db: Session,
    *,
    invoice_id: UUID,
    current_user: User,
    target_status: str,
    cancel: bool,
) -> TeacherInvoiceOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    language = _teacher_language(current_user)
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id, lock=True, language=language)
    now = _utcnow()
    invoice.status = target_status
    invoice.cancelled_at = now if cancel else None
    invoice.updated_at = now
    db.add(invoice)
    _log_audit(
        db,
        event_type="teacher_invoice_cancelled" if cancel else "teacher_invoice_uncancelled",
        actor_user_id=current_user.id,
        teacher_id=professor.id,
        statement_id=invoice.statement_id,
        invoice_id=invoice.id,
    )
    db.commit()
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    lines = db.scalars(select(TeacherInvoiceLine).where(TeacherInvoiceLine.invoice_id == invoice.id).order_by(TeacherInvoiceLine.created_at.asc())).all()
    return _invoice_out(invoice, payor_name=(payor.name if payor is not None else _teacher_text("entity_fallback", language=language)), lines=lines)


@router.post("/invoices/{invoice_id}/cancel", response_model=TeacherInvoiceOut)
def cancel_teacher_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherInvoiceOut:
    return _update_invoice_status(
        db,
        invoice_id=invoice_id,
        current_user=current_user,
        target_status="cancelled",
        cancel=True,
    )


@router.post("/invoices/{invoice_id}/uncancel", response_model=TeacherInvoiceOut)
def uncancel_teacher_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherInvoiceOut:
    return _update_invoice_status(
        db,
        invoice_id=invoice_id,
        current_user=current_user,
        target_status="generated",
        cancel=False,
    )


@router.post("/invoices/{invoice_id}/send-to-accounting", response_model=TeacherInvoiceOut)
def send_teacher_invoice_to_accounting(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherInvoiceOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    language = _teacher_language(current_user)
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id, lock=True, language=language)
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    if payor is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_teacher_text("payor_invalid", language=language))
    destination_email = _resolve_accounting_email(db, payor=payor)
    pdf_content = _invoice_pdf_bytes(db, invoice=invoice, payor=payor, professor=professor, language=language)
    sender = resolve_sender_profile(db, sender_kind="TEACHER")
    send_email(
        to_email=destination_email,
        subject=_teacher_text("teacher_invoice_subject", language=language, invoice_number=invoice.invoice_number),
        body=_teacher_text(
            "teacher_invoice_body",
            language=language,
            invoice_number=invoice.invoice_number,
            period=invoice_period_label(year=invoice.invoice_date.year, month=invoice.invoice_date.month, language=language),
            total_ttc=invoice.totals_ttc,
            teacher_name=f"{professor.first_name} {professor.last_name}".strip(),
        ),
        context="TEACHER_INVOICE_TO_ACCOUNTING",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        attachments=[(f"{invoice.invoice_number}.pdf", pdf_content, "application/pdf")],
        sender_user_id=current_user.id,
        professor_id=professor.id,
    )
    now = _utcnow()
    invoice.sent_to_accounting_at = now
    invoice.status = "sent_to_accounting"
    invoice.updated_at = now
    db.add(invoice)
    _log_audit(
        db,
        event_type="teacher_invoice_sent_to_accounting",
        actor_user_id=current_user.id,
        teacher_id=professor.id,
        statement_id=invoice.statement_id,
        invoice_id=invoice.id,
        payload={"destination_email": destination_email},
    )
    db.commit()
    lines = db.scalars(select(TeacherInvoiceLine).where(TeacherInvoiceLine.invoice_id == invoice.id).order_by(TeacherInvoiceLine.created_at.asc())).all()
    return _invoice_out(invoice, payor_name=payor.name or _teacher_text("entity_fallback", language=language), lines=lines)
