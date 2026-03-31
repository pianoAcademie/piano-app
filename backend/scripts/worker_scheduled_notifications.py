from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.jobs.application.session_jobs import run_session_auto_completion_job
from app.services.jobs.application.notification_jobs import run_scheduled_notification_dispatch_job
from app.services.quotes.lifecycle_jobs import run_quote_daily_lifecycle_job
from app.services.session_automation import run_auto_cancel_empty_sessions_job, run_expire_pending_payment_bookings_job


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    while True:
        db = SessionLocal()
        try:
            run_scheduled_notification_dispatch_job(
                db,
                now=utcnow(),
                limit=500,
            )
            run_quote_daily_lifecycle_job(
                db,
                now=utcnow(),
                limit=500,
            )
            run_expire_pending_payment_bookings_job(
                db,
                now=utcnow(),
                limit=500,
            )
            run_auto_cancel_empty_sessions_job(
                db,
                now=utcnow(),
                limit=500,
            )
            run_session_auto_completion_job(
                db,
                now=utcnow(),
                limit=500,
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        time.sleep(5)


if __name__ == "__main__":
    main()
