from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Numeric, case, cast, extract, func, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.client_record import ClientNoteEntry
from app.models.ops import EmailReminder, MessageFormat, ProfessorSessionMessage, ReminderStatus
from app.models.payout import ProfessorSessionPayout
from app.models.user import User, UserRole
from app.schemas.report import (
    AttendanceReportRow,
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationReportRow,
    CommunicationSenderCategory,
    ProfessorStatementRow,
    ReservationReportRow,
)

router = APIRouter(prefix="/admin/reports")


def _professor_name(prof: Professor) -> str:
    return f"{prof.first_name} {prof.last_name}".strip()


def _ensure_date_range(from_: datetime | None, to: datetime | None) -> None:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before 'to'",
        )


def _display_name(user: User | None) -> str:
    if user is None:
        return "Systeme"
    label = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return label or user.email


def _sender_category(user: User | None) -> CommunicationSenderCategory:
    if user is None:
        return CommunicationSenderCategory.SYSTEM
    if user.role == UserRole.PROF:
        return CommunicationSenderCategory.PROFESSOR
    return CommunicationSenderCategory.OTHER_USER


def _extract_contact(text: str) -> str:
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    if email_match:
        return email_match.group(0).lower()
    phone_match = re.search(r"\+?[0-9][0-9 .()-]{6,}[0-9]", text or "")
    if phone_match:
        return phone_match.group(0).strip()
    return "-"


def _reminder_status_to_delivery(status_value: ReminderStatus) -> CommunicationDeliveryStatus:
    if status_value == ReminderStatus.SENT:
        return CommunicationDeliveryStatus.DELIVERED
    if status_value == ReminderStatus.FAILED:
        return CommunicationDeliveryStatus.FAILED
    if status_value == ReminderStatus.SKIPPED:
        return CommunicationDeliveryStatus.SKIPPED
    if status_value == ReminderStatus.PENDING:
        return CommunicationDeliveryStatus.PENDING
    return CommunicationDeliveryStatus.UNKNOWN


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


@router.get("/communications", response_model=list[CommunicationReportRow])
def report_communications(
    channel: CommunicationChannel = Query(default=CommunicationChannel.EMAIL),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[CommunicationReportRow]:
    rows: list[CommunicationReportRow] = []

    if channel == CommunicationChannel.EMAIL:
        prof_rows = db.execute(
            select(ProfessorSessionMessage, Professor, CourseSession.title)
            .join(Professor, Professor.id == ProfessorSessionMessage.professor_id)
            .join(CourseSession, CourseSession.id == ProfessorSessionMessage.session_id)
            .order_by(ProfessorSessionMessage.sent_at.desc())
            .limit(limit)
        ).all()
        for message_row, professor, session_title in prof_rows:
            sender_name = f"{(professor.first_name or '').strip()} {(professor.last_name or '').strip()}".strip() or professor.email
            rows.append(
                CommunicationReportRow(
                    id=f"prof-message-{message_row.id}",
                    channel=CommunicationChannel.EMAIL,
                    source="PROFESSOR_SESSION_MESSAGE",
                    sender_category=CommunicationSenderCategory.PROFESSOR,
                    sender_label=sender_name,
                    occurred_at=message_row.sent_at,
                    subject=message_row.subject,
                    recipient=f"{message_row.recipient_count} destinataire(s) - {session_title}",
                    delivery_status=CommunicationDeliveryStatus.SENT,
                    provider_message_id=None,
                    content=message_row.body,
                    content_format="HTML" if message_row.body_format == MessageFormat.HTML else "TEXT",
                )
            )

        reminder_rows = db.execute(
            select(EmailReminder, User.email, CourseSession.title)
            .join(Booking, Booking.id == EmailReminder.booking_id)
            .join(User, User.id == Booking.user_id)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .order_by(func.coalesce(EmailReminder.sent_at, EmailReminder.created_at).desc())
            .limit(limit)
        ).all()
        for reminder, recipient_email, session_title in reminder_rows:
            occurred_at = reminder.sent_at or reminder.created_at
            rows.append(
                CommunicationReportRow(
                    id=f"email-reminder-{reminder.id}",
                    channel=CommunicationChannel.EMAIL,
                    source="SYSTEM_EMAIL_REMINDER",
                    sender_category=CommunicationSenderCategory.SYSTEM,
                    sender_label="Systeme",
                    occurred_at=occurred_at,
                    subject=f"Rappel de cours - {session_title}",
                    recipient=(recipient_email or "-").strip().lower() or "-",
                    delivery_status=_reminder_status_to_delivery(reminder.status),
                    provider_message_id=reminder.provider_message_id,
                    content=(
                        reminder.error_message.strip()
                        if reminder.error_message and reminder.error_message.strip()
                        else "Rappel de cours genere automatiquement par le systeme."
                    ),
                    content_format="TEXT",
                )
            )

        author_user = aliased(User)
        note_rows = db.execute(
            select(ClientNoteEntry, author_user)
            .outerjoin(author_user, author_user.id == ClientNoteEntry.author_user_id)
            .where(ClientNoteEntry.entry_type == "EMAIL")
            .order_by(ClientNoteEntry.created_at.desc())
            .limit(limit)
        ).all()
        for note, author in note_rows:
            rows.append(
                CommunicationReportRow(
                    id=f"client-note-email-{note.id}",
                    channel=CommunicationChannel.EMAIL,
                    source="CLIENT_NOTE_EMAIL",
                    sender_category=_sender_category(author),
                    sender_label=_display_name(author),
                    occurred_at=note.created_at,
                    subject="Operation email",
                    recipient=_extract_contact(note.message),
                    delivery_status=CommunicationDeliveryStatus.SENT,
                    provider_message_id=None,
                    content=note.message,
                    content_format="TEXT",
                )
            )

    if channel == CommunicationChannel.SMS:
        author_user = aliased(User)
        note_rows = db.execute(
            select(ClientNoteEntry, author_user)
            .outerjoin(author_user, author_user.id == ClientNoteEntry.author_user_id)
            .where(ClientNoteEntry.entry_type == "SMS")
            .order_by(ClientNoteEntry.created_at.desc())
            .limit(limit)
        ).all()
        for note, author in note_rows:
            rows.append(
                CommunicationReportRow(
                    id=f"client-note-sms-{note.id}",
                    channel=CommunicationChannel.SMS,
                    source="CLIENT_NOTE_SMS",
                    sender_category=_sender_category(author),
                    sender_label=_display_name(author),
                    occurred_at=note.created_at,
                    subject="Operation SMS",
                    recipient=_extract_contact(note.message),
                    delivery_status=CommunicationDeliveryStatus.UNKNOWN,
                    provider_message_id=None,
                    content=note.message,
                    content_format="TEXT",
                )
            )

    rows.sort(key=lambda row: row.occurred_at, reverse=True)
    return rows[:limit]
