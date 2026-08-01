from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.user import User
from app.services.email_delivery import send_email

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfessorDailyDigestResult:
    checked: int
    sent: int
    skipped_not_due: int
    skipped_no_courses: int
    failed: int


def _parse_hhmm_utc(value: str) -> time | None:
    raw = (value or "").strip()
    if len(raw) != 5 or raw[2] != ":":
        return None
    try:
        hour = int(raw[:2])
        minute = int(raw[3:])
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return time(hour=hour, minute=minute, tzinfo=timezone.utc)


def _attendance_label(status: BookingStatus) -> str:
    labels = {
        BookingStatus.BOOKED: "PREVU",
        BookingStatus.WAITLISTED: "LISTE_ATTENTE",
        BookingStatus.ATTENDED: "PRESENT",
        BookingStatus.NO_SHOW: "ABSENT_NON_EXCUSE",
        BookingStatus.EXCUSED_ABSENCE: "ABSENT_EXCUSE",
    }
    return labels.get(status, status.value)


def _build_digest_body(
    db: Session,
    *,
    professor: Professor,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> tuple[str, str, int]:
    sessions = db.execute(
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            CourseSession.professor_id == professor.id,
            CourseSession.start_at_utc >= day_start_utc,
            CourseSession.start_at_utc < day_end_utc,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .order_by(CourseSession.start_at_utc.asc())
    ).all()

    subject = f"Planning du jour - {day_start_utc.strftime('%d/%m/%Y')}"
    if not sessions:
        return subject, "Bonjour,\n\nAucun cours programme aujourd'hui.\n", 0

    lines: list[str] = ["Bonjour,", "", "Voici vos cours du jour:", ""]
    session_count = len(sessions)

    roster_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.WAITLISTED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )

    for session_obj, course_type, location in sessions:
        lines.append(
            f"- {session_obj.start_at_utc.strftime('%H:%M')} - {session_obj.end_at_utc.strftime('%H:%M')} | {session_obj.title} | {course_type.name} | {location.name}"
        )

        roster_rows = db.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status.in_(roster_statuses),
            )
            .order_by(User.last_name.asc(), User.first_name.asc(), User.email.asc())
        ).all()

        if not roster_rows:
            lines.append("  * Aucun eleve inscrit")
            continue

        for booking, user in roster_rows:
            display_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email
            lines.append(f"  * {display_name} - {_attendance_label(booking.status)}")
        lines.append("")

    return subject, "\n".join(lines), session_count


def run_send_professor_daily_digest_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 300,
) -> ProfessorDailyDigestResult:
    utc_now = now.astimezone(timezone.utc)
    today_utc: date = utc_now.date()
    day_start_utc = datetime.combine(today_utc, time(hour=0, minute=0, tzinfo=timezone.utc))
    day_end_utc = day_start_utc + timedelta(days=1)

    professors = db.scalars(
        select(Professor)
        .where(
            Professor.active.is_(True),
            Professor.daily_schedule_email_enabled.is_(True),
        )
        .order_by(Professor.last_name.asc(), Professor.first_name.asc())
        .limit(limit)
        .with_for_update()
    ).all()

    sent = 0
    skipped_not_due = 0
    skipped_no_courses = 0
    failed = 0

    for professor in professors:
        if professor.last_daily_schedule_sent_on == today_utc:
            skipped_not_due += 1
            continue

        due_time = _parse_hhmm_utc(professor.daily_schedule_email_time)
        if due_time is None:
            skipped_not_due += 1
            continue

        due_at_utc = datetime.combine(today_utc, due_time)
        if utc_now < due_at_utc:
            skipped_not_due += 1
            continue

        try:
            subject, body, session_count = _build_digest_body(
                db,
                professor=professor,
                day_start_utc=day_start_utc,
                day_end_utc=day_end_utc,
            )
            if professor.daily_schedule_skip_if_no_course and session_count == 0:
                professor.last_daily_schedule_sent_on = today_utc
                skipped_no_courses += 1
                continue

            message_id = send_email(
                to_email=professor.email,
                subject=subject,
                body=body,
                body_format="TEXT",
                context="PROFESSOR_DAILY_DIGEST",
            )
            if not message_id:
                raise RuntimeError("email provider returned empty message id")
            logger.info(
                "Professor daily digest sent | id=%s | to=%s | subject=%s",
                message_id,
                professor.email,
                subject,
            )
            professor.last_daily_schedule_sent_on = today_utc
            sent += 1
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.exception("Professor daily digest failed | professor_id=%s | error=%s", professor.id, exc)
            failed += 1

    return ProfessorDailyDigestResult(
        checked=len(professors),
        sent=sent,
        skipped_not_due=skipped_not_due,
        skipped_no_courses=skipped_no_courses,
        failed=failed,
    )
