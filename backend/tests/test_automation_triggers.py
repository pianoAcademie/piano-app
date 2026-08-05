from __future__ import annotations

from types import SimpleNamespace
import unittest
from uuid import uuid4

from app.services.automation_triggers import (
    EVENT_PLAN_PURCHASE_CONFIRMED,
    _rule_matches,
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


if __name__ == "__main__":
    unittest.main()
