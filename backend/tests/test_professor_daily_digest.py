from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.professor_daily_digest import run_send_professor_daily_digest_job


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
        email="professor@example.test",
        daily_schedule_email_time="07:00",
        daily_schedule_skip_if_no_course=True,
        last_daily_schedule_sent_on=None,
    )


class ProfessorDailyDigestTests(unittest.TestCase):
    def test_summer_digest_is_due_at_seven_in_paris(self) -> None:
        professor = _professor()
        db = _FakeSession([professor])

        with patch(
            "app.services.professor_daily_digest._build_digest_body",
            return_value=("Planning", "Body", 1),
        ) as build_body, patch(
            "app.services.professor_daily_digest.send_email",
            return_value="message-id",
        ) as send_email:
            before = run_send_professor_daily_digest_job(
                db,
                now=datetime(2026, 8, 2, 4, 59, tzinfo=timezone.utc),
            )
            at_seven = run_send_professor_daily_digest_job(
                db,
                now=datetime(2026, 8, 2, 5, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(before.sent, 0)
        self.assertEqual(at_seven.sent, 1)
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.kwargs["body_format"], "HTML")
        self.assertEqual(
            build_body.call_args.kwargs["day_start_utc"],
            datetime(2026, 8, 1, 22, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            build_body.call_args.kwargs["day_end_utc"],
            datetime(2026, 8, 2, 22, 0, tzinfo=timezone.utc),
        )

    def test_winter_digest_is_due_at_seven_in_paris(self) -> None:
        professor = _professor()
        db = _FakeSession([professor])

        with patch(
            "app.services.professor_daily_digest._build_digest_body",
            return_value=("Planning", "Body", 1),
        ), patch(
            "app.services.professor_daily_digest.send_email",
            return_value="message-id",
        ) as send_email:
            result = run_send_professor_daily_digest_job(
                db,
                now=datetime(2027, 1, 10, 6, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(result.sent, 1)
        send_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
