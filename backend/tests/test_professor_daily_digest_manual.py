from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.routes.admin_collaborators import router
from app.models.ops import CommunicationDeliveryStatus, CommunicationSenderCategory
from app.models.user import UserRole
from app.schemas.admin import AdminCollaboratorDailyScheduleRequest
from app.services.professor_daily_digest_manual import MANUAL_DIGEST_SOURCE, send_manual_daily_schedule

MODULE = "app.services.professor_daily_digest_manual"


class ManualDailyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 31, 8, tzinfo=timezone.utc)
        self.professor = SimpleNamespace(
            id=uuid4(), email="teacher@example.test", active=True, first_name="Alice",
            last_daily_schedule_sent_on=date(2026, 8, 31),
            daily_schedule_email_enabled=False, daily_schedule_email_time="07:00",
            daily_schedule_skip_if_no_course=False,
        )
        self.actor = SimpleNamespace(id=uuid4(), first_name="Admin", last_name="", email="admin@example.test", role=UserRole.ADMIN)
        self.payload = AdminCollaboratorDailyScheduleRequest(
            confirmed=True, request_id=uuid4(), digest_date=date(2026, 8, 31), recipient=self.professor.email,
        )
        self.db = MagicMock()
        self.db.scalar.return_value = None
        self.build = self.enterContext(patch(f"{MODULE}._build_digest_body", return_value=("Planning", "<h1>Fresh</h1>", 1)))
        self.send = self.enterContext(patch(f"{MODULE}.send_email", return_value="mail-test"))

    def run_send(self):
        return send_manual_daily_schedule(
            self.db, professor=self.professor, actor=self.actor, payload=self.payload, now=self.now,
        )

    def test_resends_even_when_already_sent_and_automatic_disabled_without_changing_settings(self):
        before = vars(self.professor).copy()
        result = self.run_send()
        self.assertEqual(result.status, "sent")
        self.assertEqual(before, vars(self.professor))
        self.send.assert_called_once()
        call = self.send.call_args.kwargs
        self.assertEqual(call["to_email"], "teacher@example.test")
        self.assertEqual(call["body"], "<h1>Fresh</h1>")
        self.assertEqual(call["body_format"], "HTML")
        self.assertEqual(call["professor_id"], self.professor.id)
        self.assertEqual(call["sender_user_id"], self.actor.id)
        self.assertEqual(call["sender_category"], CommunicationSenderCategory.OTHER_USER)
        self.assertEqual(call["context"], MANUAL_DIGEST_SOURCE + str(self.payload.request_id))
        self.assertIs(call["db"], self.db)
        self.db.commit.assert_called_once()

    def test_date_boundaries_use_paris_including_dst(self):
        cases = [
            (datetime(2026, 8, 30, 22, 30, tzinfo=timezone.utc), date(2026, 8, 31), datetime(2026, 8, 30, 22, tzinfo=timezone.utc), 24),
            (datetime(2027, 1, 9, 23, 30, tzinfo=timezone.utc), date(2027, 1, 10), datetime(2027, 1, 9, 23, tzinfo=timezone.utc), 24),
            (datetime(2026, 3, 29, 12, tzinfo=timezone.utc), date(2026, 3, 29), datetime(2026, 3, 28, 23, tzinfo=timezone.utc), 23),
            (datetime(2026, 10, 25, 12, tzinfo=timezone.utc), date(2026, 10, 25), datetime(2026, 10, 24, 22, tzinfo=timezone.utc), 25),
        ]
        for now, day, start, hours in cases:
            with self.subTest(day=day):
                self.now = now
                self.payload.digest_date = day
                self.run_send()
                args = self.build.call_args.kwargs
                self.assertEqual(args["digest_date"], day)
                self.assertEqual(args["day_start_utc"], start)
                self.assertEqual(args["day_end_utc"], start + timedelta(hours=hours))

    def test_empty_day_never_sends_even_if_automatic_empty_day_option_is_enabled(self):
        self.build.return_value = ("Planning", "No classes", 0)
        self.assertEqual(self.run_send().status, "no_courses")
        self.send.assert_not_called()
        self.db.commit.assert_not_called()

    def test_no_false_success_for_delivery_failure_or_log_mode(self):
        self.send.return_value = None
        with self.assertRaises(HTTPException) as error:
            self.run_send()
        self.assertEqual(error.exception.status_code, 502)
        self.db.commit.assert_called_once()  # keep the delivery failure journal

    def test_replayed_request_does_not_send_twice(self):
        for status in (CommunicationDeliveryStatus.SENT, CommunicationDeliveryStatus.DELIVERED):
            self.db.scalar.return_value = SimpleNamespace(delivery_status=status, provider_message_id="old-mail")
            self.assertEqual(self.run_send().status, "already_sent")
        self.send.assert_not_called()
        self.build.assert_not_called()
        query = self.db.scalar.call_args.args[0]
        self.assertIn(str(self.professor.id), str(query.compile().params))
        self.assertIn(str(self.payload.request_id), str(query.compile().params))

    def test_replayed_failed_or_bounced_request_requires_new_confirmation(self):
        self.db.scalar.return_value = SimpleNamespace(delivery_status=CommunicationDeliveryStatus.FAILED)
        with self.assertRaises(HTTPException) as error:
            self.run_send()
        self.assertEqual(error.exception.status_code, 409)
        self.send.assert_not_called()

    def test_two_tabs_or_new_request_id_are_rate_limited(self):
        self.db.scalar.side_effect = [None, uuid4()]
        with self.assertRaises(HTTPException) as error:
            self.run_send()
        self.assertEqual(error.exception.status_code, 429)
        self.send.assert_not_called()
        query = self.db.scalar.call_args.args[0]
        self.assertIn(self.now - timedelta(seconds=60), query.compile().params.values())

    def test_stale_confirmation_email_date_and_inactive_professor_are_rejected(self):
        for change in ("date", "email", "active"):
            with self.subTest(change=change):
                self.payload.digest_date = date(2026, 8, 31)
                self.payload.recipient = "teacher@example.test"
                self.professor.active = True
                if change == "date":
                    self.payload.digest_date = date(2026, 8, 30)
                elif change == "email":
                    self.payload.recipient = "other@example.test"
                else:
                    self.professor.active = False
                with self.assertRaises(HTTPException) as error:
                    self.run_send()
                self.assertEqual(error.exception.status_code, 409)
        self.send.assert_not_called()
        self.build.assert_not_called()
        self.db.scalar.assert_not_called()

    def api(self, *, authenticated=True):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        if authenticated:
            app.dependency_overrides[get_current_user] = lambda: self.actor
        return TestClient(app)

    def test_api_accepts_admin_and_locks_professor_before_sending(self):
        with patch("app.api.routes.admin_collaborators._utcnow", return_value=self.now):
            self.db.scalar.side_effect = [self.professor, None, None]
            response = self.api().post(
                f"/admin/collaborators/{self.professor.id}/send-daily-schedule",
                json=self.payload.model_dump(mode="json"),
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "sent")
        self.assertIn("FOR UPDATE", str(self.db.scalar.call_args_list[0].args[0]))

    def test_api_requires_admin(self):
        for role in (UserRole.PROF, UserRole.CLIENT):
            self.actor.role = role
            response = self.api().post(
                f"/admin/collaborators/{self.professor.id}/send-daily-schedule",
                json=self.payload.model_dump(mode="json"),
            )
            self.assertEqual(response.status_code, 403)
        self.send.assert_not_called()
        self.db.scalar.assert_not_called()

    def test_api_requires_authentication(self):
        response = self.api(authenticated=False).post(
            f"/admin/collaborators/{self.professor.id}/send-daily-schedule",
            json=self.payload.model_dump(mode="json"),
        )
        self.assertEqual(response.status_code, 401)
        self.send.assert_not_called()

    def test_api_requires_explicit_confirmation_uuid_and_today(self):
        body = self.payload.model_dump(mode="json")
        for field, value in (("confirmed", False), ("request_id", "bad"), ("digest_date", "bad")):
            response = self.api().post(
                f"/admin/collaborators/{self.professor.id}/send-daily-schedule",
                json={**body, field: value},
            )
            self.assertEqual(response.status_code, 422, response.text)
        response = self.api().post(f"/admin/collaborators/{self.professor.id}/send-daily-schedule", json={})
        self.assertEqual(response.status_code, 422)
        self.send.assert_not_called()

    def test_unknown_professor_and_get_cannot_send(self):
        response = self.api().post(
            f"/admin/collaborators/{uuid4()}/send-daily-schedule",
            json=self.payload.model_dump(mode="json"),
        )
        self.assertEqual(response.status_code, 404)
        response = self.api().get(f"/admin/collaborators/{self.professor.id}/send-daily-schedule")
        self.assertEqual(response.status_code, 405)
        self.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
