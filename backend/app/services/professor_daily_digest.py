from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.product_catalog import CatalogProduct, ProductRequest
from app.models.user import User
from app.services.email_branding import render_branded_email
from app.services.email_delivery import send_email
from app.services.session_teachers import effective_teacher_filter_for_professor
from app.services.product_catalog import READY_FOR_DELIVERY_STATUSES, reconcile_waiting_product_requests

logger = logging.getLogger(__name__)
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")


@dataclass(frozen=True)
class ProfessorDailyDigestResult:
    checked: int
    sent: int
    skipped_not_due: int
    skipped_no_courses: int
    failed: int


def _parse_hhmm(value: str) -> time | None:
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
    return time(hour=hour, minute=minute)


def _attendance_label(status: BookingStatus) -> str:
    labels = {
        BookingStatus.BOOKED: "Prévu",
        BookingStatus.WAITLISTED: "Liste d’attente",
        BookingStatus.ATTENDED: "Présent",
        BookingStatus.NO_SHOW: "Absent non excusé",
        BookingStatus.EXCUSED_ABSENCE: "Absent excusé",
    }
    return labels.get(status, status.value)


def product_request_is_ready_for_notification(request_row: ProductRequest, product: CatalogProduct) -> bool:
    if request_row.status not in READY_FOR_DELIVERY_STATUSES:
        return False
    if product.is_virtual:
        return True
    return int(request_row.stock_reserved_quantity or 0) >= int(request_row.quantity or 0)


def _build_digest_body(
    db: Session,
    *,
    professor: Professor,
    day_start_utc: datetime,
    day_end_utc: datetime,
    digest_date: date,
) -> tuple[str, str, int]:
    sessions = db.execute(
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            effective_teacher_filter_for_professor(professor_id=professor.id),
            CourseSession.start_at_utc >= day_start_utc,
            CourseSession.start_at_utc < day_end_utc,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .order_by(CourseSession.start_at_utc.asc())
    ).all()

    subject = f"Planning du jour - {digest_date.strftime('%d/%m/%Y')}"
    if not sessions:
        return (
            subject,
            render_branded_email(
                preview="Votre planning Piano Académie du jour.",
                eyebrow="ESPACE PROFESSEUR",
                title="Votre planning du jour",
                greeting=f"Bonjour {professor.first_name},",
                intro="Vous n’avez aucun cours programmé aujourd’hui.",
            ),
            0,
        )

    digest_rows: list[tuple[str, str]] = []
    session_count = len(sessions)

    roster_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.WAITLISTED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )

    for session_obj, course_type, location in sessions:
        local_start = session_obj.start_at_utc.astimezone(PARIS_TIMEZONE)
        local_end = session_obj.end_at_utc.astimezone(PARIS_TIMEZONE)
        roster_rows = db.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status.in_(roster_statuses),
            )
            .order_by(User.last_name.asc(), User.first_name.asc(), User.email.asc())
        ).all()

        roster = "Aucun élève inscrit"
        if roster_rows:
            roster_labels: list[str] = []
            for booking, user in roster_rows:
                display_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email
                roster_labels.append(f"{display_name} ({_attendance_label(booking.status)})")
            roster = ", ".join(roster_labels)

        delivery_rows = db.execute(
            select(ProductRequest, CatalogProduct, User)
            .join(CatalogProduct, CatalogProduct.id == ProductRequest.product_id)
            .join(User, User.id == ProductRequest.student_user_id)
            .where(
                ProductRequest.assigned_session_id == session_obj.id,
                ProductRequest.assigned_professor_id == professor.id,
                ProductRequest.status.in_(READY_FOR_DELIVERY_STATUSES),
            )
            .order_by(User.last_name.asc(), User.first_name.asc(), CatalogProduct.title.asc())
        ).all()
        delivery_labels: list[str] = []
        for request_row, product, student in delivery_rows:
            if not product_request_is_ready_for_notification(request_row, product):
                continue
            student_name = f"{(student.first_name or '').strip()} {(student.last_name or '').strip()}".strip() or student.email
            delivery_labels.append(f"{product.title} x{int(request_row.quantity or 0)} pour {student_name}")
        delivery_note = ""
        if delivery_labels:
            delivery_note = " | À remettre (stock présent et réservé) : " + "; ".join(delivery_labels)
        digest_rows.append(
            (
                f"{local_start.strftime('%H:%M')}–{local_end.strftime('%H:%M')}",
                f"{session_obj.title} · {course_type.name} · {location.name} · {roster}{delivery_note}",
            )
        )

    return (
        subject,
        render_branded_email(
            preview=f"Votre planning du {digest_date.strftime('%d/%m/%Y')}.",
            eyebrow="ESPACE PROFESSEUR",
            title="Votre planning du jour",
            greeting=f"Bonjour {professor.first_name},",
            intro=f"Voici vos {session_count} cours programmés aujourd’hui.",
            rows=digest_rows,
        ),
        session_count,
    )


def _mark_ready_requests_notified(
    db: Session,
    *,
    professor_id,
    day_start_utc: datetime,
    day_end_utc: datetime,
    notified_at: datetime,
) -> None:
    ready_requests = db.scalars(
        select(ProductRequest)
        .join(CourseSession, CourseSession.id == ProductRequest.assigned_session_id)
        .where(
            ProductRequest.assigned_professor_id == professor_id,
            ProductRequest.status.in_(READY_FOR_DELIVERY_STATUSES),
            CourseSession.start_at_utc >= day_start_utc,
            CourseSession.start_at_utc < day_end_utc,
        )
    ).all()
    for request_row in ready_requests:
        request_row.professor_notified_at = notified_at
        request_row.updated_at = notified_at
        db.add(request_row)


def run_send_professor_daily_digest_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 300,
) -> ProfessorDailyDigestResult:
    reconcile_waiting_product_requests(db, now=now)
    paris_now = now.astimezone(PARIS_TIMEZONE)
    today_paris: date = paris_now.date()
    day_start_paris = datetime.combine(today_paris, time.min, tzinfo=PARIS_TIMEZONE)
    day_end_paris = datetime.combine(today_paris + timedelta(days=1), time.min, tzinfo=PARIS_TIMEZONE)
    day_start_utc = day_start_paris.astimezone(timezone.utc)
    day_end_utc = day_end_paris.astimezone(timezone.utc)

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
        if professor.last_daily_schedule_sent_on == today_paris:
            skipped_not_due += 1
            continue

        due_time = _parse_hhmm(professor.daily_schedule_email_time)
        if due_time is None:
            skipped_not_due += 1
            continue

        due_at_paris = datetime.combine(today_paris, due_time, tzinfo=PARIS_TIMEZONE)
        if paris_now < due_at_paris:
            skipped_not_due += 1
            continue

        try:
            subject, body, session_count = _build_digest_body(
                db,
                professor=professor,
                day_start_utc=day_start_utc,
                day_end_utc=day_end_utc,
                digest_date=today_paris,
            )
            if professor.daily_schedule_skip_if_no_course and session_count == 0:
                professor.last_daily_schedule_sent_on = today_paris
                skipped_no_courses += 1
                continue

            message_id = send_email(
                to_email=professor.email,
                subject=subject,
                body=body,
                body_format="HTML",
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
            professor.last_daily_schedule_sent_on = today_paris
            _mark_ready_requests_notified(
                db,
                professor_id=professor.id,
                day_start_utc=day_start_utc,
                day_end_utc=day_end_utc,
                notified_at=now,
            )
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
