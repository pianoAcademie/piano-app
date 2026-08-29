from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.notifications.domain.constants import (
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_PENDING,
)
from app.services.automation_triggers import (
    EVENT_PLAN_PURCHASE_CONFIRMED,
    EVENT_TRIAL_COURSE_ATTENDED,
    _automation_scheduled_for,
    _rule_matches,
    cancel_pending_trial_attended_triggers,
)
from app.services.messaging_templates import render_template_content


class AutomationTriggerTests(unittest.TestCase):
    def test_percent_and_standard_placeholders_are_supported(self) -> None:
        rendered = render_template_content(
            "Bonjour %firstname% {last_name} {{ student_name }}",
            {"firstname": "Marie", "last_name": "Dupont", "student_name": "Lina Dupont"},
        )
        self.assertEqual(rendered, "Bonjour Marie Dupont Lina Dupont")

    def test_purchase_rule_requires_matching_plan_and_public(self) -> None:
        plan_id = uuid4()
        client = SimpleNamespace(client_kind=SimpleNamespace(value="ADULT"))
        rule = {
            "active": True,
            "event_type": EVENT_PLAN_PURCHASE_CONFIRMED,
            "plan_id": str(plan_id),
            "course_type_id": None,
            "location_id": None,
            "client_kind": "ADULT",
        }
        self.assertTrue(
            _rule_matches(
                rule,
                event_type=EVENT_PLAN_PURCHASE_CONFIRMED,
                client=client,
                plan_id=plan_id,
            )
        )
        self.assertFalse(
            _rule_matches(
                rule,
                event_type=EVENT_PLAN_PURCHASE_CONFIRMED,
                client=client,
                plan_id=uuid4(),
            )
        )

    def test_inactive_rule_never_matches(self) -> None:
        rule = {"active": False, "event_type": EVENT_PLAN_PURCHASE_CONFIRMED}
        client = SimpleNamespace(client_kind=SimpleNamespace(value="ADULT"))
        self.assertFalse(
            _rule_matches(rule, event_type=EVENT_PLAN_PURCHASE_CONFIRMED, client=client)
        )

    def test_trial_followup_waits_until_four_hours_after_course_end(self) -> None:
        course_end = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
        attendance_recorded = datetime(2026, 8, 29, 13, 0, tzinfo=UTC)

        scheduled_for = _automation_scheduled_for(
            event_type=EVENT_TRIAL_COURSE_ATTENDED,
            occurred_at=attendance_recorded,
            delay=timedelta(hours=4),
            session_obj=SimpleNamespace(end_at_utc=course_end),
        )

        self.assertEqual(scheduled_for, datetime(2026, 8, 29, 16, 0, tzinfo=UTC))

    def test_trial_followup_is_due_immediately_when_attendance_is_late(self) -> None:
        course_end = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
        attendance_recorded = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)

        scheduled_for = _automation_scheduled_for(
            event_type=EVENT_TRIAL_COURSE_ATTENDED,
            occurred_at=attendance_recorded,
            delay=timedelta(hours=4),
            session_obj=SimpleNamespace(end_at_utc=course_end),
        )

        self.assertEqual(scheduled_for, attendance_recorded)

    def test_non_trial_delay_still_starts_at_event_time(self) -> None:
        occurred_at = datetime(2026, 8, 29, 13, 0, tzinfo=UTC)

        scheduled_for = _automation_scheduled_for(
            event_type=EVENT_PLAN_PURCHASE_CONFIRMED,
            occurred_at=occurred_at,
            delay=timedelta(hours=4),
            session_obj=None,
        )

        self.assertEqual(scheduled_for, datetime(2026, 8, 29, 17, 0, tzinfo=UTC))

    def test_attendance_correction_cancels_only_pending_trial_followup(self) -> None:
        now = datetime(2026, 8, 29, 14, 0, tzinfo=UTC)
        matching = SimpleNamespace(
            payload_snapshot={"automation_event_type": EVENT_TRIAL_COURSE_ATTENDED},
            status=NOTIFICATION_STATUS_PENDING,
            skipped_at=None,
            failure_reason=None,
            updated_at=None,
        )
        unrelated = SimpleNamespace(
            payload_snapshot={"automation_event_type": EVENT_PLAN_PURCHASE_CONFIRMED},
            status=NOTIFICATION_STATUS_PENDING,
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [matching, unrelated]

        cancelled = cancel_pending_trial_attended_triggers(
            db,
            booking_id=uuid4(),
            now=now,
        )

        self.assertEqual(cancelled, 1)
        self.assertEqual(matching.status, NOTIFICATION_STATUS_CANCELLED)
        self.assertEqual(matching.skipped_at, now)
        self.assertEqual(unrelated.status, NOTIFICATION_STATUS_PENDING)
        db.add.assert_called_once_with(matching)


if __name__ == "__main__":
    unittest.main()
