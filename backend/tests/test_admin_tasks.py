from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_tasks import _effective_status
from app.schemas.admin_task import AdminTaskCreateRequest, AdminTaskUpdateRequest


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


class AdminTaskStatusTests(unittest.TestCase):
    def test_open_task_past_due_is_exposed_as_overdue(self) -> None:
        task = SimpleNamespace(status="ASSIGNED", due_at=datetime.now(timezone.utc) - timedelta(minutes=1))

        self.assertEqual(_effective_status(task), "OVERDUE")

    def test_completed_task_never_becomes_overdue(self) -> None:
        task = SimpleNamespace(status="COMPLETED", due_at=datetime.now(timezone.utc) - timedelta(days=10))

        self.assertEqual(_effective_status(task), "COMPLETED")


if __name__ == "__main__":
    unittest.main()
