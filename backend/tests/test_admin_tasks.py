from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from pydantic import ValidationError

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_tasks import _effective_status, _send_assignment_email, _source_description
from app.schemas.admin_task import (
    AdminTaskCommentCreateRequest,
    AdminTaskCreateRequest,
    AdminTaskUpdateRequest,
)


class AdminTaskSchemaTests(unittest.TestCase):
    def test_naive_due_date_is_interpreted_in_paris_timezone(self) -> None:
        payload = AdminTaskCreateRequest(
            task_type="CLIENT_CALL",
            description="Rappeler la famille",
            due_at=datetime(2026, 9, 2, 14, 30),
        )

        self.assertIsNotNone(payload.due_at)
        self.assertEqual(payload.due_at.utcoffset(), timedelta(hours=2))

    def test_description_is_trimmed_and_required(self) -> None:
        payload = AdminTaskCreateRequest(task_type="SLOT_CHOICE", description="  Choisir le créneau  ")
        self.assertEqual(payload.description, "Choisir le créneau")

        with self.assertRaises(ValidationError):
            AdminTaskCreateRequest(task_type="SLOT_CHOICE", description="   ")

    def test_client_and_prospect_cannot_both_be_selected(self) -> None:
        with self.assertRaises(ValidationError):
            AdminTaskCreateRequest(
                task_type="CLIENT_CALL",
                description="Rappeler",
                client_id=uuid4(),
                prospect_id=uuid4(),
            )

    def test_comment_can_be_cleared_on_update(self) -> None:
        payload = AdminTaskUpdateRequest(comment="  ")

        self.assertIn("comment", payload.model_fields_set)
        self.assertIsNone(payload.comment)

    def test_follow_up_comment_is_trimmed_and_required(self) -> None:
        payload = AdminTaskCommentCreateRequest(body="  Retour de la famille attendu  ")

        self.assertEqual(payload.body, "Retour de la famille attendu")
        with self.assertRaises(ValidationError):
            AdminTaskCommentCreateRequest(body="   ")


class AdminTaskStatusTests(unittest.TestCase):
    def test_open_task_past_due_is_exposed_as_overdue(self) -> None:
        task = SimpleNamespace(status="ASSIGNED", due_at=datetime.now(timezone.utc) - timedelta(minutes=1))

        self.assertEqual(_effective_status(task), "OVERDUE")

    def test_completed_task_never_becomes_overdue(self) -> None:
        task = SimpleNamespace(status="COMPLETED", due_at=datetime.now(timezone.utc) - timedelta(days=10))

        self.assertEqual(_effective_status(task), "COMPLETED")

    def test_waiting_client_status_is_preserved_before_due_date(self) -> None:
        task = SimpleNamespace(status="WAITING_CLIENT", due_at=datetime.now(timezone.utc) + timedelta(days=1))

        self.assertEqual(_effective_status(task), "WAITING_CLIENT")

    def test_contacted_without_response_status_is_preserved_before_due_date(self) -> None:
        task = SimpleNamespace(status="CONTACTED_NO_RESPONSE", due_at=datetime.now(timezone.utc) + timedelta(days=1))

        self.assertEqual(_effective_status(task), "CONTACTED_NO_RESPONSE")

    def test_planning_task_type_is_accepted(self) -> None:
        payload = AdminTaskCreateRequest(task_type="PLANNING", description="Mettre à jour la série")

        self.assertEqual(payload.task_type, "PLANNING")


class AdminTaskSourcePrefillTests(unittest.TestCase):
    def test_quote_description_contains_reference_and_direct_link(self) -> None:
        quote_id = uuid4()
        quote = SimpleNamespace(id=quote_id, quote_number="DV-20260825-1234")

        description = _source_description(None, quote, "https://app.piano-academie.com/")

        self.assertEqual(
            description,
            f"Devis DV-20260825-1234\nhttps://app.piano-academie.com/admin/quotes/{quote_id}",
        )

    def test_intake_description_contains_reference_and_direct_link(self) -> None:
        intake_id = uuid4()
        intake = SimpleNamespace(id=intake_id, source_response_id="response-abc")

        description = _source_description(intake, None, "https://app.piano-academie.com")

        self.assertEqual(
            description,
            f"Intake response-abc\nhttps://app.piano-academie.com/admin/intakes/{intake_id}",
        )


class AdminTaskAssignmentEmailTests(unittest.TestCase):
    @patch("app.api.routes.admin_tasks.resolve_frontend_base_url", return_value="https://app.piano-academie.com")
    @patch("app.api.routes.admin_tasks.send_email", return_value="mail-test")
    def test_assignment_email_uses_own_journal_session(self, send_email_mock, _base_url_mock) -> None:
        task_id = uuid4()
        assignee_id = uuid4()
        sender_id = uuid4()
        task = SimpleNamespace(
            id=task_id,
            task_type="CLIENT_CALL",
            due_at=None,
            description="Rappeler la famille",
        )
        assignee = SimpleNamespace(
            id=assignee_id,
            first_name="Estela",
            last_name="Oliviero",
            contact_email=None,
            email="estela.oliviero@piano-academie.com",
        )
        sender = SimpleNamespace(
            id=sender_id,
            first_name="",
            last_name="",
            contact_email="admin@piano-academie.com",
            email="admin@piano-academie.com",
        )

        result = _send_assignment_email(SimpleNamespace(), task, assignee, sender)

        self.assertEqual(result, "mail-test")
        kwargs = send_email_mock.call_args.kwargs
        self.assertNotIn("db", kwargs)
        self.assertEqual(kwargs["recipient_user_id"], assignee_id)
        self.assertEqual(kwargs["context"], "ADMIN_TASK_ASSIGNED")


if __name__ == "__main__":
    unittest.main()
