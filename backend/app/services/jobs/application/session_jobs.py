from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.user import User, UserRole
from app.services.notifications.domain.constants import SOURCE_SCHEDULER
from app.services.notifications.infrastructure.repository import (
    append_job_run_log,
    finish_job_run,
    get_job_cursor,
    start_job_run,
    upsert_job_cursor,
)
from app.services.payment_receipts import (
    FINAL_INVOICE_ELIGIBLE_BOOKING_STATUSES,
    generate_final_invoice_for_booking,
    send_final_invoice_email,
)
from app.services.shared.locks.redis_lock import redis_lock

JOB_NAME = "session_auto_completion_job"
JOB_LOCK_KEY = "lock:job:session_auto_completion"
JOB_MIN_INTERVAL = timedelta(minutes=5)
AUTO_EMPTY_SESSION_CANCEL_REASON = "AUTO_NO_BOOKINGS"


@dataclass(frozen=True)
class SessionAutoCompletionJobResult:
    checked: int
    completed: int
    invoices_generated: int
    skipped: int
    failed: int
    job_run_id: UUID | None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def run_session_auto_completion_job(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> SessionAutoCompletionJobResult:
    ts = now or _utcnow()
    cursor = get_job_cursor(db, job_name=JOB_NAME)
    if (
        cursor is not None
        and cursor.last_processed_at is not None
        and ts - cursor.last_processed_at < JOB_MIN_INTERVAL
    ):
        return SessionAutoCompletionJobResult(
            checked=0,
            completed=0,
            invoices_generated=0,
            skipped=0,
            failed=0,
            job_run_id=None,
        )

    with redis_lock(JOB_LOCK_KEY, ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError(f"{JOB_NAME} lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_NAME,
            job_key=JOB_NAME,
            triggered_by=SOURCE_SCHEDULER,
            started_at=ts,
            metadata_json={"limit": limit, "min_interval_seconds": int(JOB_MIN_INTERVAL.total_seconds())},
        )
        checked = 0
        completed = 0
        invoices_generated = 0
        skipped = 0
        failed = 0

        try:
            session_rows = db.execute(
                select(CourseSession, CourseType, Location)
                .join(CourseType, CourseType.id == CourseSession.course_type_id)
                .join(Location, Location.id == CourseSession.location_id)
                .where(
                    CourseSession.status == SessionStatus.SCHEDULED,
                    CourseSession.end_at_utc <= ts,
                )
                .order_by(CourseSession.end_at_utc.asc(), CourseSession.start_at_utc.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            checked = len(session_rows)

            session_context: dict[UUID, tuple[CourseSession, CourseType, Location]] = {
                session_obj.id: (session_obj, course_type, location)
                for session_obj, course_type, location in session_rows
            }

            booking_rows: list[tuple[Booking, User]] = []
            if session_context:
                booking_rows = db.execute(
                    select(Booking, User)
                    .join(User, User.id == Booking.user_id)
                    .where(
                        Booking.session_id.in_(list(session_context.keys())),
                        Booking.status.in_(FINAL_INVOICE_ELIGIBLE_BOOKING_STATUSES),
                    )
                    .order_by(Booking.booked_at.asc())
                ).all()

            sessions_with_billable_bookings = {booking.session_id for booking, _owner in booking_rows}

            for session_id, (session_obj, _course_type, _location) in session_context.items():
                session_obj.updated_at = ts
                if session_id not in sessions_with_billable_bookings:
                    session_obj.status = SessionStatus.CANCELLED
                    session_obj.cancel_reason = AUTO_EMPTY_SESSION_CANCEL_REASON
                    continue
                session_obj.status = SessionStatus.COMPLETED
                completed += 1

            if session_context:
                for booking, owner in booking_rows:
                    session_obj, course_type, location = session_context[booking.session_id]
                    try:
                        note, metadata, created = generate_final_invoice_for_booking(
                            db,
                            booking=booking,
                            session_obj=session_obj,
                            course_type=course_type,
                            location=location,
                            owner=owner,
                            author_user_id=None,
                        )
                    except ValueError:
                        skipped += 1
                        continue
                    except Exception as exc:
                        failed += 1
                        append_job_run_log(
                            db,
                            job_run_id=job_run.id,
                            level="ERROR",
                            message=f"Final invoice generation failed for booking {booking.id}",
                            context_json={"booking_id": str(booking.id), "error": str(exc)},
                        )
                        continue

                    if not created:
                        continue
                    invoices_generated += 1

                    invoice_customer = db.scalar(
                        select(User).where(User.id == note.user_id, User.role == UserRole.CLIENT)
                    )
                    if invoice_customer is None:
                        continue
                    try:
                        send_final_invoice_email(
                            db,
                            customer=invoice_customer,
                            note_id=note.id,
                            metadata=metadata,
                        )
                    except Exception as exc:
                        failed += 1
                        append_job_run_log(
                            db,
                            job_run_id=job_run.id,
                            level="ERROR",
                            message=f"Final invoice email failed for booking {booking.id}",
                            context_json={"booking_id": str(booking.id), "note_id": str(note.id), "error": str(exc)},
                        )

            upsert_job_cursor(db, job_name=JOB_NAME, last_processed_at=ts, updated_at=ts)
            finish_job_run(
                db,
                job_run=job_run,
                status="warning" if failed > 0 else "success",
                finished_at=ts,
                items_scanned=checked,
                items_processed=completed,
                items_sent=invoices_generated,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"{completed} sessions auto-completed, {invoices_generated} final invoices generated",
            )
            return SessionAutoCompletionJobResult(
                checked=checked,
                completed=completed,
                invoices_generated=invoices_generated,
                skipped=skipped,
                failed=failed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=ts,
                items_scanned=checked,
                items_processed=completed,
                items_sent=invoices_generated,
                items_skipped=skipped,
                items_failed=failed + 1,
                summary_text=None,
                error_text=str(exc),
            )
            raise
