from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Professor
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
    TeacherInvoiceLineOut,
    TeacherInvoiceOut,
    TeacherStatementDisputeRequest,
    TeacherStatementMissingSessionOut,
    TeacherStatementOut,
)
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_sender_profile
from app.services.teacher_invoice_documents import (
    get_teacher_invoice_template,
    render_teacher_invoice_html,
    render_teacher_invoice_pdf_from_html,
)
from app.services.teacher_invoicing import (
    ComputedStatement,
    compute_teacher_monthly_statements,
    invoice_period_label,
    statement_to_snapshot_payload,
)

router = APIRouter(prefix="/teacher")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _resolve_professor_profile(db: Session, *, current_user: User) -> Professor:
    professor = db.scalar(select(Professor).where(Professor.email == current_user.email))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor profile not found")
    return professor


def _statement_status_from_computed(computed: ComputedStatement) -> str:
    return "ready" if computed.attendance_complete else "awaiting_attendance"


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
            if row.status not in {"approved", "closed", "disputed"}:
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


def _invoice_pdf_bytes(db: Session, *, invoice: TeacherInvoice, payor: LegalEntity, professor: Professor) -> bytes:
    if invoice.pdf_storage_key:
        try:
            return base64.b64decode(invoice.pdf_storage_key.encode("ascii"))
        except Exception:
            pass

    html_template, _, _ = get_teacher_invoice_template(db)
    rendered_html = render_teacher_invoice_html(
        html_template=html_template,
        context={
            "teacher_full_name": f"{professor.first_name} {professor.last_name}".strip(),
            "teacher_company_name": (professor.teacher_company_name or "").strip() or f"{professor.first_name} {professor.last_name}".strip(),
            "teacher_company_address": (professor.teacher_company_address or "").strip() or "-",
            "teacher_email": professor.email,
            "teacher_phone": (professor.phone or "").strip() or "-",
            "teacher_siret_display": (invoice.teacher_siret_display or "").strip() or "en cours d'immatriculation",
            "teacher_iban": (invoice.teacher_iban or "").strip() or "-",
            "payor_company_name": (payor.name or "").strip() or "-",
            "payor_company_address": (payor.address_text or "").strip() or "-",
            "payor_company_siret": (payor.siret or "").strip() or "-",
            "payor_company_vat": (payor.vat_number or "").strip() or "-",
            "invoice_number_display": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "invoice_period_label": invoice_period_label(year=invoice.invoice_date.year, month=invoice.invoice_date.month),
            "lines_by_course_type": "-",
            "totals_ht": f"{invoice.totals_ht}",
            "totals_vat": f"{invoice.totals_vat}",
            "totals_ttc": f"{invoice.totals_ttc}",
            "payment_instructions": "Paiement par virement bancaire sous 30 jours.",
            "late_payment_penalty_text": "Penalites de retard conformement aux CGV.",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No statement found for this period")
    now = _utcnow()
    for statement, _ in rows:
        statement.status = "disputed"
        statement.dispute_message_last = payload.message.strip()
        statement.updated_at = now
        db.add(statement)
        db.add(
            TeacherStatementMessage(
                statement_id=statement.id,
                teacher_id=professor.id,
                message=payload.message.strip(),
                status="open",
            )
        )
        _log_audit(
            db,
            event_type="teacher_statement_disputed",
            actor_user_id=current_user.id,
            teacher_id=professor.id,
            statement_id=statement.id,
            payload={"message": payload.message.strip()},
        )

    payor_entity = db.scalar(select(LegalEntity).where(LegalEntity.id == rows[0][1].payor_legal_entity_id))
    if payor_entity is not None:
        to_email = _resolve_accounting_email(db, payor=payor_entity)
        sender = resolve_sender_profile(db, sender_kind="TEACHER")
        send_email(
            to_email=to_email,
            subject=f"Litige releve professeur {professor.first_name} {professor.last_name} - {month:02d}/{year}",
            body=payload.message.strip(),
            context="TEACHER_STATEMENT_DISPUTE",
            from_email=sender.from_email,
            from_name=sender.from_name,
            reply_to=sender.reply_to,
            subject_prefix=sender.subject_prefix,
            sender_user_id=current_user.id,
            professor_id=professor.id,
        )

    db.commit()
    return [_statement_out(statement, computed) for statement, computed in rows]


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No statement found for this period")

    missing_sessions = _missing_sessions_from_computed(rows)
    if missing_sessions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Attendance incomplete. Complete missing sessions before approval.",
                "missing_sessions": [row.model_dump(mode="json") for row in missing_sessions],
            },
        )

    locked_professor = db.scalar(select(Professor).where(Professor.id == professor.id).with_for_update())
    if locked_professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor profile not found")
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

        payor = db.scalar(select(LegalEntity).where(LegalEntity.id == computed.payor_legal_entity_id))
        if payor is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payor legal entity not found")

        invoice_number = f"PROF-{str(locked_professor.id).split('-')[0].upper()}-{counter:06d}"
        counter += 1
        due_date = invoice_date + timedelta(days=30)
        teacher_siret_display = (locked_professor.teacher_siret or "").strip() or "en cours d'immatriculation"
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
            recipient_company_name=(payor.name or "").strip() or "Societe",
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

        html_template, _, _ = get_teacher_invoice_template(db)
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
                "invoice_period_label": invoice_period_label(year=year, month=month),
                "lines_by_course_type": " | ".join(
                    f"{line.course_type_label}: {line.hours}h x {line.unit_rate_ht} = {line.amount_ht} HT"
                    for line in computed.lines
                ),
                "totals_ht": f"{_quantize(computed.totals_ht)}",
                "totals_vat": f"{_quantize(computed.totals_vat)}",
                "totals_ttc": f"{_quantize(computed.totals_ttc)}",
                "payment_instructions": "Paiement par virement bancaire sous 30 jours.",
                "late_payment_penalty_text": "Penalites de retard conformement aux CGV.",
                "comptability_email": _resolve_accounting_email(db, payor=payor),
            },
        )
        pdf_content = render_teacher_invoice_pdf_from_html(rendered_html)
        invoice.pdf_storage_key = base64.b64encode(pdf_content).decode("ascii")
        db.add(invoice)

        statement.status = "approved"
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

    payor_by_id = {row.id: row for row in db.scalars(select(LegalEntity).where(LegalEntity.id.in_([inv.payor_legal_entity_id for inv in generated]))).all()}
    lines_by_invoice_id = _invoice_lines_for_invoice_ids(db, invoice_ids=[inv.id for inv in generated])
    return TeacherApproveStatementsOut(
        generated_invoices=[
            _invoice_out(
                invoice,
                payor_name=(payor_by_id.get(invoice.payor_legal_entity_id).name if payor_by_id.get(invoice.payor_legal_entity_id) else "Entite"),
                lines=lines_by_invoice_id.get(invoice.id, []),
            )
            for invoice in generated
        ],
        blocked_missing_sessions=[],
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
    return [
        _invoice_out(
            invoice,
            payor_name=(payor_by_id.get(invoice.payor_legal_entity_id).name if payor_by_id.get(invoice.payor_legal_entity_id) else "Entite"),
            lines=lines_by_invoice_id.get(invoice.id, []),
        )
        for invoice in invoices
    ]


def _load_teacher_invoice_or_404(db: Session, *, invoice_id: UUID, teacher_id: UUID, lock: bool = False) -> TeacherInvoice:
    stmt = select(TeacherInvoice).where(TeacherInvoice.id == invoice_id, TeacherInvoice.teacher_id == teacher_id)
    if lock:
        stmt = stmt.with_for_update()
    invoice = db.scalar(stmt)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher invoice not found")
    return invoice


@router.get("/invoices/{invoice_id}", response_model=TeacherInvoiceOut)
def get_teacher_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> TeacherInvoiceOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id)
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    lines = db.scalars(select(TeacherInvoiceLine).where(TeacherInvoiceLine.invoice_id == invoice.id).order_by(TeacherInvoiceLine.created_at.asc())).all()
    return _invoice_out(
        invoice,
        payor_name=(payor.name if payor is not None else "Entite"),
        lines=lines,
    )


@router.get("/invoices/{invoice_id}/pdf")
def download_teacher_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> Response:
    professor = _resolve_professor_profile(db, current_user=current_user)
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id)
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    if payor is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payor legal entity not found")
    pdf_content = _invoice_pdf_bytes(db, invoice=invoice, payor=payor, professor=professor)
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
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id, lock=True)
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
    return _invoice_out(invoice, payor_name=(payor.name if payor is not None else "Entite"), lines=lines)


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
    invoice = _load_teacher_invoice_or_404(db, invoice_id=invoice_id, teacher_id=professor.id, lock=True)
    payor = db.scalar(select(LegalEntity).where(LegalEntity.id == invoice.payor_legal_entity_id))
    if payor is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payor legal entity not found")
    destination_email = _resolve_accounting_email(db, payor=payor)
    pdf_content = _invoice_pdf_bytes(db, invoice=invoice, payor=payor, professor=professor)
    sender = resolve_sender_profile(db, sender_kind="TEACHER")
    send_email(
        to_email=destination_email,
        subject=f"Facture professeur {invoice.invoice_number}",
        body=(
            f"Facture professeur {invoice.invoice_number}\n"
            f"Periode: {invoice_period_label(year=invoice.invoice_date.year, month=invoice.invoice_date.month)}\n"
            f"Total TTC: {invoice.totals_ttc}\n"
            f"Professeur: {professor.first_name} {professor.last_name}"
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
    return _invoice_out(invoice, payor_name=payor.name, lines=lines)
