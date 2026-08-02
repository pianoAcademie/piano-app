from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.professor_attendance_reminders import (
    PendingAttendanceSession,
    _build_reminder_email,
    run_send_professor_attendance_reminder_job,
)


class _FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(self, professors: list[object]) -> None:
        self._professors = professors

    def scalars(self, _query: object) -> _FakeScalarResult:
        return _FakeScalarResult(self._professors)


def _professor() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        first_name="Marie",
        last_name="Martin",
        email="professor@example.test",
        last_attendance_reminder_sent_on=None,
    )


def _pending_session() -> PendingAttendanceSession:
    return PendingAttendanceSession(
        session_id=uuid4(),
        title="Cours de piano collectif",
        course_type_name="Cours collectif",
        location_name="Rue de la Pompe",
        start_at_utc=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
        end_at_utc=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
        student_names=("Alice Martin", "Léo Bernard"),
    )


class ProfessorAttendanceReminderTests(unittest.TestCase):
    def test_summer_reminder_is_due_at_six_in_paris(self) -> None:
        professor = _professor()
        db = _FakeSession([professor])

        with patch(
            "app.services.professor_attendance_reminders._pending_attendance_sessions",
            return_value=[_pending_session()],
        ) as pending_sessions, patch(
            "app.services.professor_attendance_reminders._professor_language",
            return_value="fr",
        ), patch(
            "app.services.professor_attendance_reminders._build_reminder_email",
            return_value=("Présences", "Body"),
        ), patch(
            "app.services.professor_attendance_reminders.send_email",
            return_value="message-id",
        ) as send_email:
            before = run_send_professor_attendance_reminder_job(
                db,
                now=datetime(2026, 8, 2, 3, 59, tzinfo=timezone.utc),
            )
            at_six = run_send_professor_attendance_reminder_job(
                db,
                now=datetime(2026, 8, 2, 4, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(before.sent, 0)
        self.assertEqual(at_six.sent, 1)
        self.assertEqual(professor.last_attendance_reminder_sent_on, date(2026, 8, 2))
        send_email.assert_called_once()
        self.assertEqual(
            pending_sessions.call_args.kwargs["month_start_utc"],
            datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc),
        )

    def test_winter_reminder_is_due_at_six_in_paris(self) -> None:
        professor = _professor()
        db = _FakeSession([professor])

        with patch(
            "app.services.professor_attendance_reminders._pending_attendance_sessions",
            return_value=[_pending_session()],
        ), patch(
            "app.services.professor_attendance_reminders._professor_language",
            return_value="fr",
        ), patch(
            "app.services.professor_attendance_reminders._build_reminder_email",
            return_value=("Présences", "Body"),
        ), patch(
            "app.services.professor_attendance_reminders.send_email",
            return_value="message-id",
        ) as send_email:
            result = run_send_professor_attendance_reminder_job(
                db,
                now=datetime(2027, 1, 10, 5, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(result.sent, 1)
        send_email.assert_called_once()

    def test_no_email_is_sent_when_attendance_is_complete(self) -> None:
        professor = _professor()
        db = _FakeSession([professor])

        with patch(
            "app.services.professor_attendance_reminders._pending_attendance_sessions",
            return_value=[],
        ), patch(
            "app.services.professor_attendance_reminders.send_email",
        ) as send_email:
            result = run_send_professor_attendance_reminder_job(
                db,
                now=datetime(2026, 8, 2, 4, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(result.sent, 0)
        self.assertEqual(result.skipped_complete, 1)
        self.assertEqual(professor.last_attendance_reminder_sent_on, date(2026, 8, 2))
        send_email.assert_not_called()

    def test_email_lists_sessions_students_and_direct_attendance_link(self) -> None:
        professor = _professor()
        session = _pending_session()

        with patch(
            "app.services.professor_attendance_reminders.resolve_frontend_base_url",
            return_value="https://reservation.piano-academie.com",
        ):
            subject, body = _build_reminder_email(
                SimpleNamespace(),
                professor=professor,
                sessions=[session],
                month=date(2026, 8, 2),
                language="en",
            )

        self.assertEqual(subject, "Attendance to complete – August 2026")
        self.assertIn("Alice Martin", body)
        self.assertIn("Léo Bernard", body)
        self.assertIn("Rue de la Pompe", body)
        self.assertIn(f"session_id={session.session_id}", body)
        self.assertIn("attendance_filter=missing", body)


if __name__ == "__main__":
    unittest.main()
