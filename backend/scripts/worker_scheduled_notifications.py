from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.jobs.application.session_jobs import run_session_auto_completion_job
from app.services.jobs.application.notification_jobs import (
    run_reminder_generation_job,
    run_scheduled_notification_dispatch_job,
)
from app.services.invoice_reminders import run_invoice_due_reminder_job
from app.services.bank_transfer_orders import run_bank_transfer_order_expiration_job, run_bank_transfer_review_digest_job
from app.services.quotes.lifecycle_jobs import run_quote_daily_lifecycle_job
from app.services.professor_daily_digest import run_send_professor_daily_digest_job
from app.services.professor_attendance_reminders import run_send_professor_attendance_reminder_job
from app.services.session_automation import run_auto_cancel_empty_sessions_job, run_expire_pending_payment_bookings_job
from app.services.notifications.application.orchestrator import enqueue_notifications
from app.services.subscription_payment_reminders import run_subscription_payment_action_reminder_job
from app.services.teacher_statement_notifications import run_teacher_statement_accounting_digest_job
from app.services.zendesk_contact_sync import (
    DEFAULT_LIMIT as ZENDESK_SYNC_LIMIT,
    run_zendesk_contact_sync_job,
    zendesk_credentials_complete,
    zendesk_full_sync_due,
    zendesk_sync_due,
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    last_reminder_generation_at: datetime | None = None
    last_professor_digest_at: datetime | None = None
    last_professor_attendance_reminder_at: datetime | None = None
    last_subscription_payment_reminder_at: datetime | None = None
    last_teacher_statement_accounting_digest_at: datetime | None = None
    while True:
        db = SessionLocal()
        try:
            cycle_now = utcnow()
            jobs = []
            if (
                last_reminder_generation_at is None
                or cycle_now - last_reminder_generation_at >= timedelta(minutes=1)
            ):
                jobs.append(("reminder_generation", run_reminder_generation_job))
                last_reminder_generation_at = cycle_now
            if last_professor_digest_at is None or cycle_now - last_professor_digest_at >= timedelta(minutes=1):
                jobs.append(("professor_daily_digest", run_send_professor_daily_digest_job))
                last_professor_digest_at = cycle_now
            if (
                last_professor_attendance_reminder_at is None
                or cycle_now - last_professor_attendance_reminder_at >= timedelta(minutes=1)
            ):
                jobs.append(("professor_attendance_reminder", run_send_professor_attendance_reminder_job))
                last_professor_attendance_reminder_at = cycle_now
            if (
                last_subscription_payment_reminder_at is None
                or cycle_now - last_subscription_payment_reminder_at >= timedelta(minutes=30)
            ):
                jobs.append(("subscription_payment_action_reminders", run_subscription_payment_action_reminder_job))
                last_subscription_payment_reminder_at = cycle_now
            if (
                last_teacher_statement_accounting_digest_at is None
                or cycle_now - last_teacher_statement_accounting_digest_at >= timedelta(hours=1)
            ):
                jobs.append(("teacher_statement_accounting_digest", run_teacher_statement_accounting_digest_job))
                last_teacher_statement_accounting_digest_at = cycle_now
            if zendesk_credentials_complete() and zendesk_sync_due(db, now=cycle_now):
                run_full_zendesk_sync = zendesk_full_sync_due(db, now=cycle_now)
                jobs.append(
                    (
                        "zendesk_contact_sync",
                        lambda active_db, *, now, limit: run_zendesk_contact_sync_job(
                            active_db,
                            now=now,
                            limit=max(limit, ZENDESK_SYNC_LIMIT),
                            full=run_full_zendesk_sync,
                        ),
                    )
                )
            jobs.extend((
                ("scheduled_notification_dispatch", run_scheduled_notification_dispatch_job),
                ("invoice_due_reminders", run_invoice_due_reminder_job),
                ("quote_daily_lifecycle", run_quote_daily_lifecycle_job),
                ("expire_bank_transfer_orders", run_bank_transfer_order_expiration_job),
                ("bank_transfer_review_digest", run_bank_transfer_review_digest_job),
                ("expire_pending_payment_bookings", run_expire_pending_payment_bookings_job),
                ("auto_cancel_empty_sessions", run_auto_cancel_empty_sessions_job),
                ("session_auto_completion", run_session_auto_completion_job),
            ))
            for job_name, job_fn in jobs:
                try:
                    job_result = job_fn(
                        db,
                        now=utcnow(),
                        limit=500,
                    )
                    db.commit()
                    if job_name == "auto_cancel_empty_sessions":
                        enqueue_notifications(list(job_result.notifications))
                except Exception:
                    db.rollback()
                    logger.exception("Scheduled worker job failed", extra={"job_name": job_name})
        finally:
            db.close()
        time.sleep(5)


if __name__ == "__main__":
    main()
