from __future__ import annotations

import csv
from decimal import Decimal
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import Numeric, case, cast, extract, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.ops import CommunicationLog, LegalEntity
from app.models.payout import ProfessorSessionPayout
from app.models.user import User, UserRole
from app.schemas.report import (
    AttendanceReportRow,
    CommunicationChannel,
    CommunicationFiltersOut,
    CommunicationProfessorFilterOut,
    CommunicationReportRow,
    CommunicationTypeFilterOut,
    ProfessorStatementRow,
    ReservationReportRow,
)
from app.services.communication_journal import COMMUNICATION_TYPE_LABELS, KNOWN_COMMUNICATION_TYPES, communication_type_label

router = APIRouter(prefix="/admin/reports")
INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::"


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


@router.get("/communications", response_model=list[CommunicationReportRow])
def report_communications(
    channel: CommunicationChannel = Query(default=CommunicationChannel.EMAIL),
    limit: int = Query(default=300, ge=1, le=2000),
    q: str | None = Query(default=None),
    communication_type: str | None = Query(default=None),
    occurred_on: date | None = Query(default=None),
    professor_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[CommunicationReportRow]:
    normalized_type = (communication_type or "").strip().upper()
    search = (q or "").strip()
    day = occurred_on or _utc_today()
    day_start, day_end = _day_bounds(day)

    stmt = (
        select(CommunicationLog)
        .where(
            CommunicationLog.channel == channel.value,
            CommunicationLog.occurred_at >= day_start,
            CommunicationLog.occurred_at < day_end,
        )
        .order_by(CommunicationLog.occurred_at.desc())
        .limit(limit)
    )

    if normalized_type and normalized_type != "ALL":
        stmt = stmt.where(func.upper(CommunicationLog.communication_type) == normalized_type)
    if professor_id is not None:
        stmt = stmt.where(CommunicationLog.professor_id == professor_id)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(CommunicationLog.subject).like(pattern),
                func.lower(CommunicationLog.sender_label).like(pattern),
                func.lower(CommunicationLog.recipient).like(pattern),
                func.lower(CommunicationLog.content).like(pattern),
                func.lower(CommunicationLog.source).like(pattern),
            )
        )

    rows = db.scalars(stmt).all()
    return [_communication_row_out(row) for row in rows]


@router.get("/communications/filters", response_model=CommunicationFiltersOut)
def report_communication_filters(
    channel: CommunicationChannel = Query(default=CommunicationChannel.EMAIL),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationFiltersOut:
    type_codes: set[str] = set()
    for code in KNOWN_COMMUNICATION_TYPES:
        type_codes.add(code)
    db_type_rows = db.scalars(
        select(CommunicationLog.communication_type)
        .where(CommunicationLog.channel == channel.value)
        .distinct()
    ).all()
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
