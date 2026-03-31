from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.catalog import BookingStatus, SessionStatus
from app.services.jobs.application.session_jobs import run_session_auto_completion_job


class _ExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, execute_results: list[list[object]], scalar_results: list[object] | None = None) -> None:
        self._execute_results = list(execute_results)
        self._scalar_results = list(scalar_results or [])

    def execute(self, _query: object) -> _ExecuteResult:
        if not self._execute_results:
            raise AssertionError("Unexpected execute call")
        return _ExecuteResult(self._execute_results.pop(0))

    def scalar(self, _query: object) -> object | None:
        if not self._scalar_results:
            return None
        return self._scalar_results.pop(0)


@contextmanager
def _acquired_lock(*_args: object, **_kwargs: object):
    yield True


class SessionAutoCompletionJobTests(unittest.TestCase):
    def test_due_scheduled_session_is_completed_and_invoiced(self) -> None:
        now = datetime(2026, 9, 23, 12, 5, tzinfo=timezone.utc)
        session_obj = SimpleNamespace(
            id=uuid4(),
            status=SessionStatus.SCHEDULED,
            start_at_utc=now - timedelta(hours=2),
            end_at_utc=now - timedelta(hours=1),
            updated_at=None,
        )
        course_type = SimpleNamespace(id=uuid4())
        location = SimpleNamespace(id=uuid4())
        owner = SimpleNamespace(id=uuid4())
        booking = SimpleNamespace(
            id=uuid4(),
            session_id=session_obj.id,
            status=BookingStatus.BOOKED,
            booked_at=now - timedelta(days=1),
        )
        note = SimpleNamespace(id=uuid4(), user_id=owner.id)
        fake_db = _FakeSession(
            execute_results=[
                [(session_obj, course_type, location)],
                [(booking, owner)],
            ],
            scalar_results=[owner],
        )

        with patch("app.services.jobs.application.session_jobs.redis_lock", _acquired_lock), patch(
            "app.services.jobs.application.session_jobs.get_job_cursor",
            return_value=None,
        ), patch(
            "app.services.jobs.application.session_jobs.start_job_run",
            return_value=SimpleNamespace(id=uuid4()),
        ), patch(
            "app.services.jobs.application.session_jobs.finish_job_run",
        ) as finish_job_run, patch(
            "app.services.jobs.application.session_jobs.upsert_job_cursor",
        ) as upsert_job_cursor, patch(
            "app.services.jobs.application.session_jobs.generate_final_invoice_for_booking",
            return_value=(note, {"invoice_number": "PA26-0187"}, True),
        ) as generate_final_invoice, patch(
            "app.services.jobs.application.session_jobs.send_final_invoice_email",
        ) as send_final_invoice_email:
            result = run_session_auto_completion_job(fake_db, now=now, limit=10)

        self.assertEqual(session_obj.status, SessionStatus.COMPLETED)
        self.assertEqual(session_obj.updated_at, now)
        self.assertEqual(result.checked, 1)
        self.assertEqual(result.completed, 1)
        self.assertEqual(result.invoices_generated, 1)
        self.assertEqual(result.failed, 0)
        generate_final_invoice.assert_called_once()
        send_final_invoice_email.assert_called_once()
        upsert_job_cursor.assert_called_once()
        finish_job_run.assert_called_once()

    def test_job_is_throttled_when_recently_processed(self) -> None:
        now = datetime(2026, 9, 23, 12, 5, tzinfo=timezone.utc)
        recent_cursor = SimpleNamespace(last_processed_at=now - timedelta(minutes=1))

        with patch(
            "app.services.jobs.application.session_jobs.get_job_cursor",
            return_value=recent_cursor,
        ), patch(
            "app.services.jobs.application.session_jobs.start_job_run",
        ) as start_job_run:
            result = run_session_auto_completion_job(_FakeSession(execute_results=[]), now=now, limit=10)

        self.assertEqual(result.checked, 0)
        self.assertEqual(result.completed, 0)
        self.assertIsNone(result.job_run_id)
        start_job_run.assert_not_called()

    def test_due_empty_scheduled_session_is_cancelled_instead_of_completed(self) -> None:
        now = datetime(2026, 9, 23, 12, 5, tzinfo=timezone.utc)
        session_obj = SimpleNamespace(
            id=uuid4(),
            status=SessionStatus.SCHEDULED,
            start_at_utc=now - timedelta(hours=2),
            end_at_utc=now - timedelta(hours=1),
            updated_at=None,
            cancel_reason=None,
        )
        course_type = SimpleNamespace(id=uuid4())
        location = SimpleNamespace(id=uuid4())
        fake_db = _FakeSession(
            execute_results=[
                [(session_obj, course_type, location)],
                [],
            ],
            scalar_results=[],
        )

        with patch("app.services.jobs.application.session_jobs.redis_lock", _acquired_lock), patch(
            "app.services.jobs.application.session_jobs.get_job_cursor",
            return_value=None,
        ), patch(
            "app.services.jobs.application.session_jobs.start_job_run",
            return_value=SimpleNamespace(id=uuid4()),
        ), patch(
            "app.services.jobs.application.session_jobs.finish_job_run",
        ) as finish_job_run, patch(
            "app.services.jobs.application.session_jobs.upsert_job_cursor",
        ) as upsert_job_cursor, patch(
            "app.services.jobs.application.session_jobs.generate_final_invoice_for_booking",
        ) as generate_final_invoice, patch(
            "app.services.jobs.application.session_jobs.send_final_invoice_email",
        ) as send_final_invoice_email:
            result = run_session_auto_completion_job(fake_db, now=now, limit=10)

        self.assertEqual(session_obj.status, SessionStatus.CANCELLED)
        self.assertEqual(session_obj.cancel_reason, "AUTO_NO_BOOKINGS")
        self.assertEqual(session_obj.updated_at, now)
        self.assertEqual(result.checked, 1)
        self.assertEqual(result.completed, 0)
        self.assertEqual(result.invoices_generated, 0)
        self.assertEqual(result.failed, 0)
        generate_final_invoice.assert_not_called()
        send_final_invoice_email.assert_not_called()
        upsert_job_cursor.assert_called_once()
        finish_job_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
