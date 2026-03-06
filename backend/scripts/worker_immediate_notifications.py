from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal
from app.services.notifications.application.dispatcher import dispatch_notification
from app.services.notifications.domain.constants import QUEUE_NOTIFICATIONS_IMMEDIATE
from app.services.notifications.infrastructure.repository import get_notification_for_dispatch
from app.services.shared.queue.redis_queue import queue_pop


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    while True:
        payload = queue_pop(QUEUE_NOTIFICATIONS_IMMEDIATE, timeout_seconds=3)
        if payload is None:
            continue
        raw_notification_id = str(payload.get("notification_id") or "").strip()
        if not raw_notification_id:
            continue
        try:
            notification_id = UUID(raw_notification_id)
        except ValueError:
            continue

        db = SessionLocal()
        try:
            notification = get_notification_for_dispatch(db, notification_id=notification_id)
            if notification is not None:
                dispatch_notification(
                    db,
                    notification=notification,
                    now=utcnow(),
                )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


if __name__ == "__main__":
    main()
