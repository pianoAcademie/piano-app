from __future__ import annotations

import csv
from decimal import Decimal
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import Numeric, case, cast, extract, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.ops import CommunicationChannel as CommunicationChannelModel, CommunicationLog, LegalEntity
from app.models.payout import ProfessorSessionPayout
from app.models.user import User, UserRole
from app.schemas.report import (
    AttendanceReportRow,
    CommunicationChannel,
    CommunicationFiltersOut,
    CommunicationPeriod,
    CommunicationReportPageOut,
    CommunicationProfessorFilterOut,
    CommunicationReportRow,
    CommunicationResendRequest,
    CommunicationTypeFilterOut,
    ProfessorStatementRow,
    ReservationReportRow,
)
from app.services.communication_journal import COMMUNICATION_TYPE_LABELS, KNOWN_COMMUNICATION_TYPES, communication_type_label
from app.services.email_delivery import email_delivery_disabled_reason, send_email
from app.services.messaging_templates import resolve_sender_profile

router = APIRouter(prefix="/admin/reports")
INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::"
COMMUNICATION_ARCHIVE_RETENTION_DAYS = 365


def _professor_name(prof: Professor) -> str:
    return f"{prof.first_name} {prof.last_name}".strip()


def _client_name(user: User) -> str:
    value = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return value or user.email


def _service_address(user: User) -> str:
    parts = [
        (user.address_line or "").strip(),
        (user.postal_code or "").strip(),
        (user.city or "").strip(),
        (user.address_country or "").strip().upper(),
    ]
    return " ".join(part for part in parts if part).strip()


def _invoice_fields_from_note_message(message: str | None) -> tuple[str | None, str | None]:
    raw = (message or "").strip()
    if not raw:
        return None, None
    prefix_index = raw.find(INVOICE_RANGE_NOTE_PREFIX)
    if prefix_index >= 0:
        payload = raw[prefix_index + len(INVOICE_RANGE_NOTE_PREFIX) :].strip()
        if payload:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    invoice_number = str(parsed.get("invoice_number") or "").strip() or None
                    invoice_status = str(parsed.get("invoice_status") or "").strip().upper() or None
                    return invoice_number, invoice_status
            except json.JSONDecodeError:
                pass
    # Fallback for legacy note text if JSON payload is not present.
    match = re.search(r"\bFacture\s+([A-Za-z0-9._/-]+)", raw)
    invoice_number = match.group(1).strip() if match is not None else None
    return invoice_number, None


def _ensure_date_range(from_: datetime | None, to: datetime | None) -> None:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before 'to'",
        )


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _communication_period_bounds(
    period: CommunicationPeriod,
    now_utc: datetime,
) -> tuple[datetime, datetime] | None:
    today_start, today_end = _day_bounds(now_utc.date())
    if period == CommunicationPeriod.ALL:
        return None
    if period == CommunicationPeriod.TODAY:
        return today_start, today_end
    if period == CommunicationPeriod.WEEK:
        return now_utc - timedelta(days=7), now_utc
    if period == CommunicationPeriod.MONTH:
        return now_utc - timedelta(days=30), now_utc
    if period == CommunicationPeriod.SEMESTER:
        return now_utc - timedelta(days=183), now_utc
    if period == CommunicationPeriod.YEAR:
        return now_utc - timedelta(days=365), now_utc
    return today_start, today_end


def _archive_communications_older_than_one_year(db: Session, now_utc: datetime) -> None:
    archive_before = now_utc - timedelta(days=COMMUNICATION_ARCHIVE_RETENTION_DAYS)
    db.execute(
        update(CommunicationLog)
        .where(
            CommunicationLog.archived_at.is_(None),
            CommunicationLog.occurred_at < archive_before,
        )
        .values(archived_at=now_utc, updated_at=now_utc)
    )
    db.commit()


def _parse_communication_log_id(raw_value: str) -> UUID:
    raw = str(raw_value or "").strip()
    if raw.startswith("communication-log-"):
        raw = raw[len("communication-log-") :]
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Identifiant de communication invalide",
        ) from exc


def _communication_row_out(row: CommunicationLog) -> CommunicationReportRow:
    return CommunicationReportRow(
        id=f"communication-log-{row.id}",
        channel=CommunicationChannel(row.channel.value),
        source=row.source,
        communication_type=row.communication_type,
        communication_type_label=communication_type_label(row.communication_type),
        sender_category=row.sender_category.value,
        sender_label=row.sender_label,
        sender_user_id=row.sender_user_id,
        professor_id=row.professor_id,
        occurred_at=row.occurred_at,
        subject=row.subject,
        recipient=row.recipient,
        recipient_user_id=row.recipient_user_id,
        delivery_status=row.delivery_status.value,
        provider_message_id=row.provider_message_id,
        provider=row.provider,
        content=row.content,
        content_format=row.content_format.value,
        error_message=row.error_message,
    )


@router.post("/communications/{communication_id}/resend", response_model=CommunicationReportRow)
def resend_communication(
    communication_id: str = Path(...),
    payload: CommunicationResendRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationReportRow:
    normalized_communication_id = _parse_communication_log_id(communication_id)
    row = db.scalar(select(CommunicationLog).where(CommunicationLog.id == normalized_communication_id).limit(1))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Communication introuvable")
    if row.channel != CommunicationChannelModel.EMAIL:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seules les communications email peuvent etre renvoyees")

    delivery_error = email_delivery_disabled_reason()
    if delivery_error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=delivery_error)

    recipient = str((payload.recipient_email if payload is not None else None) or row.recipient or "").strip().lower()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Destinataire email introuvable")
    sender_category = getattr(row.sender_category, "value", str(row.sender_category or "")).strip().upper()
    sender = resolve_sender_profile(db, sender_kind="TEACHER" if sender_category == "PROFESSOR" else "STUDIO")

    message_id = send_email(
        to_email=recipient,
        subject=row.subject,
        body=row.content,
        body_format=row.content_format.value if hasattr(row.content_format, "value") else str(row.content_format),
        context=f"{row.source}_RESEND",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        sender_user_id=row.sender_user_id,
        sender_label=row.sender_label,
        sender_category=row.sender_category,
        professor_id=row.professor_id,
        recipient_user_id=row.recipient_user_id if recipient == str(row.recipient or "").strip().lower() else None,
        communication_type=row.communication_type,
    )
    resent_row = db.scalar(
        select(CommunicationLog)
        .where(
            CommunicationLog.provider_message_id == message_id,
            CommunicationLog.channel == CommunicationChannelModel.EMAIL,
        )
        .order_by(CommunicationLog.occurred_at.desc())
        .limit(1)
    )
    if resent_row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Renvoi journalise introuvable")
    return _communication_row_out(resent_row)


@router.get("/reservations", response_model=list[ReservationReportRow])
def report_reservations(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    professor_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[ReservationReportRow]:
    _ensure_date_range(from_, to)

    stmt = (
        select(CourseSession, CourseType, Location, Professor, Booking, User)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Professor, Professor.id == CourseSession.professor_id)
        .join(Booking, Booking.session_id == CourseSession.id)
        .join(User, User.id == Booking.user_id)
    )

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)
    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if professor_id is not None:
        stmt = stmt.where(CourseSession.professor_id == professor_id)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())).all()

    return [
        ReservationReportRow(
            session_id=session.id,
            start_at_utc=session.start_at_utc,
            end_at_utc=session.end_at_utc,
            session_status=session.status,
            course_type_id=course_type.id,
            course_type_code=course_type.code,
            course_type_name=course_type.name,
            location_id=location.id,
            location_name=location.name,
            professor_id=professor.id,
            professor_name=_professor_name(professor),
            booking_id=booking.id,
            client_email=user.email,
            booking_status=booking.status,
            total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
            currency_snapshot=booking.currency_snapshot,
        )
        for session, course_type, location, professor, booking, user in rows
    ]


@router.get("/attendance", response_model=list[AttendanceReportRow])
def report_attendance(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    professor_id: UUID | None = None,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AttendanceReportRow]:
    _ensure_date_range(from_, to)

    stmt = (
        select(CourseSession, CourseType, Location, Professor, Booking, User)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Professor, Professor.id == CourseSession.professor_id)
        .join(Booking, Booking.session_id == CourseSession.id)
        .join(User, User.id == Booking.user_id)
    )

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)
    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if professor_id is not None:
        stmt = stmt.where(CourseSession.professor_id == professor_id)

    stmt = stmt.where(Booking.status != BookingStatus.WAITLISTED)
    if not include_cancelled:
        stmt = stmt.where(Booking.status != BookingStatus.CANCELLED)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())).all()

    return [
        AttendanceReportRow(
            session_id=session.id,
            start_at_utc=session.start_at_utc,
            course_type_name=course_type.name,
            location_name=location.name,
            professor_name=_professor_name(professor),
            booking_id=booking.id,
            client_email=user.email,
            attendance_status=booking.status.value,
        )
        for session, course_type, location, professor, booking, user in rows
    ]


@router.get("/professor-statements", response_model=list[ProfessorStatementRow])
def report_professor_statements(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    professor_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[ProfessorStatementRow]:
    _ensure_date_range(from_, to)

    duration_hours_expr = cast(
        extract("epoch", CourseSession.end_at_utc - CourseSession.start_at_utc) / 3600.0,
        Numeric(10, 2),
    )

    booked_case = case(
        (
            Booking.status.in_(
                [
                    BookingStatus.BOOKED,
                    BookingStatus.ATTENDED,
                    BookingStatus.NO_SHOW,
                    BookingStatus.EXCUSED_ABSENCE,
                ]
            ),
            1,
        ),
        else_=0,
    )
    attended_case = case((Booking.status == BookingStatus.ATTENDED, 1), else_=0)
    no_show_case = case((Booking.status == BookingStatus.NO_SHOW, 1), else_=0)
    excused_case = case((Booking.status == BookingStatus.EXCUSED_ABSENCE, 1), else_=0)

    stmt = (
        select(
            CourseSession.id.label("session_id"),
            Professor.id.label("professor_id"),
            Professor.first_name.label("prof_first_name"),
            Professor.last_name.label("prof_last_name"),
            CourseSession.start_at_utc,
            CourseSession.end_at_utc,
            CourseSession.status,
            CourseType.name.label("course_type_name"),
            Location.name.label("location_name"),
            duration_hours_expr.label("duration_hours"),
            func.coalesce(func.sum(booked_case), 0).label("booked_students"),
            func.coalesce(func.sum(attended_case), 0).label("attended_students"),
            func.coalesce(func.sum(no_show_case), 0).label("no_show_students"),
            func.coalesce(func.sum(excused_case), 0).label("excused_absence_students"),
            ProfessorSessionPayout.hourly_rate_snapshot.label("hourly_rate_snapshot"),
            ProfessorSessionPayout.amount_snapshot.label("amount_snapshot"),
            ProfessorSessionPayout.currency_snapshot.label("currency_snapshot"),
            ProfessorSessionPayout.payout_status.label("payout_status"),
        )
        .join(Professor, Professor.id == CourseSession.professor_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Booking, Booking.session_id == CourseSession.id)
        .outerjoin(ProfessorSessionPayout, ProfessorSessionPayout.session_id == CourseSession.id)
        .where(CourseSession.status != SessionStatus.CANCELLED)
        .group_by(
            CourseSession.id,
            Professor.id,
            Professor.first_name,
            Professor.last_name,
            CourseSession.start_at_utc,
            CourseSession.end_at_utc,
            CourseSession.status,
            CourseType.name,
            Location.name,
            duration_hours_expr,
            ProfessorSessionPayout.hourly_rate_snapshot,
            ProfessorSessionPayout.amount_snapshot,
            ProfessorSessionPayout.currency_snapshot,
            ProfessorSessionPayout.payout_status,
        )
    )

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)
    if professor_id is not None:
        stmt = stmt.where(CourseSession.professor_id == professor_id)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc())).all()

    result: list[ProfessorStatementRow] = []
    for row in rows:
        result.append(
            ProfessorStatementRow(
                session_id=row.session_id,
                professor_id=row.professor_id,
                professor_name=f"{row.prof_first_name} {row.prof_last_name}".strip(),
                start_at_utc=row.start_at_utc,
                end_at_utc=row.end_at_utc,
                session_status=row.status,
                course_type_name=row.course_type_name,
                location_name=row.location_name,
                duration_hours=float(row.duration_hours or 0),
                booked_students=int(row.booked_students or 0),
                attended_students=int(row.attended_students or 0),
                no_show_students=int(row.no_show_students or 0),
                excused_absence_students=int(row.excused_absence_students or 0),
                hourly_rate_snapshot=row.hourly_rate_snapshot,
                amount_snapshot=row.amount_snapshot,
                currency_snapshot=row.currency_snapshot,
                payout_status=(row.payout_status.value if row.payout_status is not None else None),
            )
        )

    return result


@router.get("/sap/{year}/csv")
def report_sap_csv(
    year: int = Path(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    services_entity_id = db.scalar(
        select(LegalEntity.id).where(func.upper(func.trim(LegalEntity.name)) == "PIANO ACADEMIE SERVICES").limit(1)
    )
    if services_entity_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legal entity 'PIANO ACADEMIE SERVICES' not found",
        )

    period_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    rows = db.execute(
        select(ClientInvoiceLine, ClientNoteEntry, User)
        .join(ClientNoteEntry, ClientNoteEntry.id == ClientInvoiceLine.note_id)
        .join(User, User.id == ClientInvoiceLine.user_id)
        .where(
            ClientInvoiceLine.seller_legal_entity_id == services_entity_id,
            ClientInvoiceLine.occurred_at >= period_start,
            ClientInvoiceLine.occurred_at < period_end,
        )
        .order_by(
            func.lower(func.coalesce(User.last_name, "")),
            func.lower(func.coalesce(User.first_name, "")),
            func.lower(User.email),
            ClientInvoiceLine.occurred_at.asc(),
            ClientInvoiceLine.id.asc(),
        )
    ).all()

    grouped: dict[str, dict[str, object]] = {}
    for line, note, client in rows:
        client_id = str(client.id)
        bucket = grouped.setdefault(
            client_id,
            {
                "client_id": client_id,
                "client_name": _client_name(client),
                "client_email": client.email,
                "service_address": _service_address(client),
                "total_paid_ttc": Decimal("0.00"),
                "details": [],
            },
        )
        invoice_number, payment_status = _invoice_fields_from_note_message(note.message)
        line_total = Decimal(line.total_incl_vat or 0).quantize(Decimal("0.01"))
        bucket["total_paid_ttc"] = (Decimal(bucket["total_paid_ttc"]) + line_total).quantize(Decimal("0.01"))
        details_bucket = bucket["details"]
        if not isinstance(details_bucket, list):
            details_bucket = []
            bucket["details"] = details_bucket
        details_bucket.append(
            {
                "line_occurred_at": line.occurred_at,
                "invoice_number": invoice_number or "",
                "label": line.label or "",
                "total_incl_vat": line_total,
                "currency": (line.currency or "").upper(),
                "note_id": str(line.note_id),
                "payment_status": payment_status or "",
            }
        )

    output_rows: list[dict[str, str]] = []
    sorted_clients = sorted(
        grouped.values(),
        key=lambda row: (
            str(row["client_name"]).casefold(),
            str(row["client_email"]).casefold(),
        ),
    )
    for bucket in sorted_clients:
        details_raw = bucket.get("details")
        details = details_raw if isinstance(details_raw, list) else []
        details.sort(
            key=lambda row: (
                row.get("line_occurred_at")
                if isinstance(row, dict) and isinstance(row.get("line_occurred_at"), datetime)
                else period_start
            )
        )
        statuses = sorted({str(row["payment_status"]).strip().upper() for row in details if str(row["payment_status"]).strip()})
        summary_status = statuses[0] if len(statuses) == 1 else ("MIXED" if statuses else "")
        total_paid = Decimal(bucket["total_paid_ttc"]).quantize(Decimal("0.01"))

        output_rows.append(
            {
                "row_type": "SUMMARY",
                "year": str(year),
                "client_id": str(bucket["client_id"]),
                "client_name": str(bucket["client_name"]),
                "client_email": str(bucket["client_email"]),
                "total_paid_ttc": f"{total_paid:.2f}",
                "line_occurred_at": "",
                "invoice_number": "",
                "label": "TOTAL_CLIENT",
                "total_incl_vat": "",
                "currency": "",
                "service_address": str(bucket["service_address"]),
                "note_id": "",
                "payment_status": summary_status,
            }
        )
        for detail in details:
            detail_occurred_at = detail.get("line_occurred_at")
            detail_total = detail.get("total_incl_vat")
            try:
                detail_total_decimal = Decimal(str(detail_total)).quantize(Decimal("0.01"))
            except Exception:
                detail_total_decimal = Decimal("0.00")
            output_rows.append(
                {
                    "row_type": "DETAIL",
                    "year": str(year),
                    "client_id": str(bucket["client_id"]),
                    "client_name": str(bucket["client_name"]),
                    "client_email": str(bucket["client_email"]),
                    "total_paid_ttc": f"{total_paid:.2f}",
                    "line_occurred_at": (detail_occurred_at.isoformat() if isinstance(detail_occurred_at, datetime) else ""),
                    "invoice_number": str(detail["invoice_number"]),
                    "label": str(detail["label"]),
                    "total_incl_vat": f"{detail_total_decimal:.2f}",
                    "currency": str(detail["currency"]),
                    "service_address": str(bucket["service_address"]),
                    "note_id": str(detail["note_id"]),
                    "payment_status": str(detail["payment_status"]),
                }
            )

    csv_columns = [
        "row_type",
        "year",
        "client_id",
        "client_name",
        "client_email",
        "total_paid_ttc",
        "line_occurred_at",
        "invoice_number",
        "label",
        "total_incl_vat",
        "currency",
        "service_address",
        "note_id",
        "payment_status",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=csv_columns)
    writer.writeheader()
    writer.writerows(output_rows)

    file_name = f"sap_services_export_{year}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/communications", response_model=CommunicationReportPageOut)
def report_communications(
    channel: CommunicationChannel | None = Query(default=None),
    period: CommunicationPeriod = Query(default=CommunicationPeriod.TODAY),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=25, le=100),
    q: str | None = Query(default=None),
    communication_type: str | None = Query(default=None),
    occurred_on: date | None = Query(default=None),
    professor_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationReportPageOut:
    if per_page not in (25, 50, 100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="per_page must be one of: 25, 50, 100",
        )

    now_utc = datetime.now(timezone.utc)
    _archive_communications_older_than_one_year(db, now_utc)

    normalized_type = (communication_type or "").strip().upper()
    search = (q or "").strip()
    period_bounds = _communication_period_bounds(period, now_utc)
    if occurred_on is not None:
        period_bounds = _day_bounds(occurred_on)

    filters: list = []
    if channel is not None:
        filters.append(CommunicationLog.channel == channel.value)
    if period_bounds is not None:
        start_at, end_at = period_bounds
        filters.append(CommunicationLog.occurred_at >= start_at)
        filters.append(CommunicationLog.occurred_at < end_at)

    if normalized_type and normalized_type != "ALL":
        filters.append(func.upper(CommunicationLog.communication_type) == normalized_type)
    if professor_id is not None:
        filters.append(CommunicationLog.professor_id == professor_id)
    if search:
        pattern = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(CommunicationLog.subject).like(pattern),
                func.lower(CommunicationLog.sender_label).like(pattern),
                func.lower(CommunicationLog.recipient).like(pattern),
                func.lower(CommunicationLog.content).like(pattern),
                func.lower(CommunicationLog.source).like(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(CommunicationLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(db.scalar(count_stmt) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = min(page, total_pages)
    offset = (current_page - 1) * per_page

    data_stmt = select(CommunicationLog)
    if filters:
        data_stmt = data_stmt.where(*filters)
    data_stmt = data_stmt.order_by(CommunicationLog.occurred_at.desc()).offset(offset).limit(per_page)
    rows = db.scalars(data_stmt).all()

    return CommunicationReportPageOut(
        items=[_communication_row_out(row) for row in rows],
        page=current_page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.get("/communications/filters", response_model=CommunicationFiltersOut)
def report_communication_filters(
    channel: CommunicationChannel | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationFiltersOut:
    type_codes: set[str] = set()
    for code in KNOWN_COMMUNICATION_TYPES:
        type_codes.add(code)
    db_type_stmt = select(CommunicationLog.communication_type).distinct()
    if channel is not None:
        db_type_stmt = db_type_stmt.where(CommunicationLog.channel == channel.value)
    db_type_rows = db.scalars(db_type_stmt).all()
    for code in db_type_rows:
        normalized = (code or "").strip().upper()
        if normalized:
            type_codes.add(normalized)
    communication_types = [
        CommunicationTypeFilterOut(code=code, label=communication_type_label(code))
        for code in sorted(type_codes, key=lambda item: COMMUNICATION_TYPE_LABELS.get(item, item))
    ]

    professors = db.scalars(
        select(Professor)
        .where(Professor.active.is_(True))
        .order_by(Professor.first_name.asc(), Professor.last_name.asc())
    ).all()
    professor_options = [
        CommunicationProfessorFilterOut(
            id=professor.id,
            label=f"{(professor.first_name or '').strip()} {(professor.last_name or '').strip()}".strip() or professor.email,
        )
        for professor in professors
    ]

    return CommunicationFiltersOut(
        communication_types=communication_types,
        professors=professor_options,
    )
