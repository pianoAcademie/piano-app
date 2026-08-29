from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.product_catalog import ProductRequestStatus
from app.models.catalog import BookingStatus
from app.services.professor_daily_digest import (
    _build_digest_body,
    product_request_is_ready_for_notification,
    run_send_professor_daily_digest_job,
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


class _DigestSession:
    def __init__(self, result_sets: list[list[object]]) -> None:
        self._result_sets = list(result_sets)
        self.statements: list[str] = []

    def execute(self, query: object) -> _FakeScalarResult:
        self.statements.append(str(query))
        return _FakeScalarResult(self._result_sets.pop(0))


def _professor() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email="professor@example.test",
        daily_schedule_email_time="07:00",
        daily_schedule_skip_if_no_course=True,
        last_daily_schedule_sent_on=None,
    )


class ProfessorDailyDigestTests(unittest.TestCase):
    def test_trial_session_roster_uses_trial_label_for_legacy_booking(self) -> None:
        professor = SimpleNamespace(id=uuid4(), first_name="Mi-Young")
        session_obj = SimpleNamespace(
            id=uuid4(),
            title="Cours d'essai",
            start_at_utc=datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        )
        course_type = SimpleNamespace(name="Cours d'essai collectif", code="TRIAL_GROUP")
        location = SimpleNamespace(name="Rue Scheffer")
        booking = SimpleNamespace(status=BookingStatus.BOOKED, is_trial_course=False)
        student = SimpleNamespace(first_name="Hanna", last_name="TAIEB", email="hanna@example.test")
        db = _DigestSession(
            [
                [(session_obj, course_type, location)],
                [(booking, student)],
                [],
            ]
        )

        _, body, session_count = _build_digest_body(
            db,  # type: ignore[arg-type]
            professor=professor,  # type: ignore[arg-type]
            day_start_utc=datetime(2026, 8, 28, 22, 0, tzinfo=timezone.utc),
            day_end_utc=datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc),
            digest_date=datetime(2026, 8, 29, tzinfo=timezone.utc).date(),
        )

        self.assertEqual(session_count, 1)
        self.assertIn("Hanna TAIEB (Essai)", body)
        self.assertNotIn("Hanna TAIEB (Prévu)", body)

    def test_masterclass_is_listed_in_each_associated_professor_digest(self) -> None:
        professor_id = uuid4()
        professor = SimpleNamespace(id=professor_id, first_name="Alice")
        session_obj = SimpleNamespace(
            id=uuid4(),
            title="Masterclass jazz",
            start_at_utc=datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc),
        )
        course_type = SimpleNamespace(name="Masterclass")
        location = SimpleNamespace(name="Rue de Richelieu")
        db = _DigestSession([[(session_obj, course_type, location)], [], []])

        _, body, session_count = _build_digest_body(
            db,  # type: ignore[arg-type]
            professor=professor,  # type: ignore[arg-type]
            day_start_utc=datetime(2026, 8, 21, 22, 0, tzinfo=timezone.utc),
            day_end_utc=datetime(2026, 8, 22, 22, 0, tzinfo=timezone.utc),
            digest_date=datetime(2026, 8, 22, tzinfo=timezone.utc).date(),
        )

        self.assertEqual(session_count, 1)
        self.assertIn("Masterclass jazz", body)
        self.assertIn("course_session_professors", db.statements[0])
        self.assertIn("course_session_professors.professor_id", db.statements[0])

    def test_product_delivery_notification_requires_ready_status_and_reserved_stock(self) -> None:
        product = SimpleNamespace(is_virtual=False)
        waiting = SimpleNamespace(
            status=ProductRequestStatus.WAITING_STOCK,
            stock_reserved_quantity=0,
            quantity=1,
        )
        ready_without_stock = SimpleNamespace(
            status=ProductRequestStatus.TO_DELIVER,
            stock_reserved_quantity=0,
            quantity=1,
        )
        ready = SimpleNamespace(
            status=ProductRequestStatus.TO_DELIVER,
            stock_reserved_quantity=1,
            quantity=1,
        )

        self.assertFalse(product_request_is_ready_for_notification(waiting, product))
        self.assertFalse(product_request_is_ready_for_notification(ready_without_stock, product))
        self.assertTrue(product_request_is_ready_for_notification(ready, product))

    def test_summer_digest_is_due_at_seven_in_paris(self) -> None:
        professor = _professor()
        db = _FakeSession([professor])

        with patch(
            "app.services.professor_daily_digest._build_digest_body",
            return_value=("Planning", "Body", 1),
        ) as build_body, patch(
            "app.services.professor_daily_digest.reconcile_waiting_product_requests",
        ), patch(
            "app.services.professor_daily_digest._mark_ready_requests_notified",
        ), patch(
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
            "app.services.professor_daily_digest.reconcile_waiting_product_requests",
        ), patch(
            "app.services.professor_daily_digest._mark_ready_requests_notified",
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
