from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.session_teachers import effective_teacher_filter_for_professor

logger = logging.getLogger(__name__)
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
REMINDER_LOCAL_TIME = time(hour=6)


@dataclass(frozen=True)
class PendingAttendanceSession:
    session_id: UUID
    title: str
    course_type_name: str
    location_name: str
    start_at_utc: datetime
    end_at_utc: datetime
    student_names: tuple[str, ...]


@dataclass(frozen=True)
class ProfessorAttendanceReminderResult:
    checked: int
    sent: int
    skipped_not_due: int
    skipped_complete: int
    failed: int


def _professor_language(db: Session, *, professor: Professor) -> str:
    language = db.scalar(
        select(User.preferred_language)
        .where(func.lower(User.email) == professor.email.strip().lower())
        .limit(1)
    )
    return "en" if str(language or "").strip().lower().startswith("en") else "fr"


def _month_label(value: date, *, language: str) -> str:
    labels = {
        "fr": (
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ),
        "en": (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
    }
    return f"{labels[language][value.month - 1]} {value.year}"


def _session_date_label(value: datetime, *, language: str) -> str:
    local_value = value.astimezone(PARIS_TIMEZONE)
    if language == "en":
        weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        months = (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )
        return f"{weekdays[local_value.weekday()]}, {months[local_value.month - 1]} {local_value.day}, {local_value.year}"
    weekdays = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
    months = (
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    )
    return f"{weekdays[local_value.weekday()]} {local_value.day} {months[local_value.month - 1]} {local_value.year}"


def _pending_attendance_sessions(
    db: Session,
    *,
    professor: Professor,
    month_start_utc: datetime,
    now: datetime,
) -> list[PendingAttendanceSession]:
    rows = db.execute(
        select(CourseSession, CourseType, Location, User)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Booking, Booking.session_id == CourseSession.id)
        .join(User, User.id == Booking.user_id)
        .where(
            effective_teacher_filter_for_professor(professor_id=professor.id),
            CourseSession.start_at_utc >= month_start_utc,
            CourseSession.end_at_utc <= now,
            CourseSession.status != SessionStatus.CANCELLED,
            Booking.status == BookingStatus.BOOKED,
        )
        .order_by(
            CourseSession.start_at_utc.asc(),
            User.last_name.asc(),
            User.first_name.asc(),
            User.email.asc(),
        )
    ).all()

    grouped: OrderedDict[UUID, dict[str, object]] = OrderedDict()
    for session_obj, course_type, location, student in rows:
        bucket = grouped.setdefault(
            session_obj.id,
            {
                "session": session_obj,
                "course_type": course_type,
                "location": location,
                "student_names": [],
            },
        )
        display_name = f"{(student.first_name or '').strip()} {(student.last_name or '').strip()}".strip()
        student_names = bucket["student_names"]
        if isinstance(student_names, list):
            student_names.append(display_name or student.email)

    return [
        PendingAttendanceSession(
            session_id=session_id,
            title=str(bucket["session"].title),
            course_type_name=str(bucket["course_type"].name),
            location_name=str(bucket["location"].name),
            start_at_utc=bucket["session"].start_at_utc,
            end_at_utc=bucket["session"].end_at_utc,
            student_names=tuple(str(name) for name in bucket["student_names"]),
        )
        for session_id, bucket in grouped.items()
    ]


def _build_reminder_email(
    db: Session,
    *,
    professor: Professor,
    sessions: list[PendingAttendanceSession],
    month: date,
    language: str,
) -> tuple[str, str]:
    language = "en" if language == "en" else "fr"
    month_label = _month_label(month, language=language)
    pending_students = sum(len(session.student_names) for session in sessions)
    base_url = resolve_frontend_base_url(db).rstrip("/")
    portal_url = f"{base_url}/prof?tab=overview"
    first_name = (professor.first_name or "").strip()

    if language == "en":
        subject = f"Attendance to complete – {month_label}"
        greeting = f"Hello {escape(first_name)}," if first_name else "Hello,"
        intro = (
            f"There are <strong>{len(sessions)} lesson(s)</strong> and "
            f"<strong>{pending_students} student attendance record(s)</strong> still to complete for {escape(month_label)}."
        )
        student_label = "Attendance to complete"
        action_label = "Complete attendance"
        footer = "This reminder is sent only while attendance is missing."
    else:
        subject = f"Présences à compléter – {month_label}"
        greeting = f"Bonjour {escape(first_name)}," if first_name else "Bonjour,"
        intro = (
            f"Il reste <strong>{len(sessions)} cours</strong> et "
            f"<strong>{pending_students} présence(s) élève</strong> à renseigner pour {escape(month_label)}."
        )
        student_label = "Présences à renseigner"
        action_label = "Saisir les présences"
        footer = "Ce rappel est envoyé uniquement lorsqu'il reste des présences à saisir."

    session_blocks: list[str] = []
    for session in sessions:
        local_start = session.start_at_utc.astimezone(PARIS_TIMEZONE)
        local_end = session.end_at_utc.astimezone(PARIS_TIMEZONE)
        day_key = local_start.date().isoformat()
        session_url = (
            f"{base_url}/prof?tab=planning&amp;agenda_view=day"
            f"&amp;agenda_date={day_key}&amp;session_id={session.session_id}&amp;attendance_filter=missing"
        )
        student_names = ", ".join(escape(name) for name in session.student_names)
        session_blocks.append(
            "<li style=\"margin:0 0 18px 0;\">"
            f"<strong>{escape(_session_date_label(session.start_at_utc, language=language))} · "
            f"{local_start.strftime('%H:%M')}–{local_end.strftime('%H:%M')}</strong><br>"
            f"{escape(session.title)} · {escape(session.course_type_name)} · {escape(session.location_name)}<br>"
            f"<span>{escape(student_label)} : {student_names}</span><br>"
            f"<a href=\"{session_url}\">{escape(action_label)}</a>"
            "</li>"
        )

    body = (
        "<div style=\"font-family:Arial,sans-serif;color:#172033;line-height:1.55;\">"
        f"<p>{greeting}</p>"
        f"<p>{intro}</p>"
        f"<ul style=\"padding-left:22px;\">{''.join(session_blocks)}</ul>"
        f"<p><a href=\"{escape(portal_url)}\" style=\"display:inline-block;padding:10px 16px;"
        "background:#c98224;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;\">"
        f"{escape(action_label)}</a></p>"
        f"<p style=\"color:#667085;font-size:13px;\">{escape(footer)}</p>"
        "</div>"
    )
    return subject, body


def run_send_professor_attendance_reminder_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 300,
) -> ProfessorAttendanceReminderResult:
    paris_now = now.astimezone(PARIS_TIMEZONE)
    today_paris = paris_now.date()
    due_at_paris = datetime.combine(today_paris, REMINDER_LOCAL_TIME, tzinfo=PARIS_TIMEZONE)
    month_start_paris = datetime(today_paris.year, today_paris.month, 1, tzinfo=PARIS_TIMEZONE)
    month_start_utc = month_start_paris.astimezone(timezone.utc)

    professors = db.scalars(
        select(Professor)
        .where(Professor.active.is_(True))
        .order_by(Professor.last_name.asc(), Professor.first_name.asc())
        .limit(limit)
        .with_for_update()
    ).all()

    sent = 0
    skipped_not_due = 0
    skipped_complete = 0
    failed = 0

    for professor in professors:
        if professor.last_attendance_reminder_sent_on == today_paris or paris_now < due_at_paris:
            skipped_not_due += 1
            continue

        try:
            sessions = _pending_attendance_sessions(
                db,
                professor=professor,
                month_start_utc=month_start_utc,
                now=now,
            )
            if not sessions:
                professor.last_attendance_reminder_sent_on = today_paris
                skipped_complete += 1
                continue

            language = _professor_language(db, professor=professor)
            subject, body = _build_reminder_email(
                db,
                professor=professor,
                sessions=sessions,
                month=today_paris,
                language=language,
            )
            message_id = send_email(
                to_email=professor.email,
                subject=subject,
                body=body,
                body_format="HTML",
                context="PROFESSOR_ATTENDANCE_REMINDER",
            )
            if not message_id:
                raise RuntimeError("email provider returned empty message id")
            professor.last_attendance_reminder_sent_on = today_paris
            sent += 1
            logger.info(
                "Professor attendance reminder sent | id=%s | professor_id=%s | sessions=%s",
                message_id,
                professor.id,
                len(sessions),
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.exception("Professor attendance reminder failed | professor_id=%s | error=%s", professor.id, exc)
            failed += 1

    return ProfessorAttendanceReminderResult(
        checked=len(professors),
        sent=sent,
        skipped_not_due=skipped_not_due,
        skipped_complete=skipped_complete,
        failed=failed,
    )
