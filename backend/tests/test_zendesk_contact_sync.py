from __future__ import annotations

from datetime import UTC, datetime
import unittest
from uuid import uuid4

from app.services.zendesk_contact_sync import (
    ZendeskContactCandidate,
    build_zendesk_user_payload,
    find_shared_phones,
    normalize_email,
    normalize_phone,
)


def _candidate(**overrides):
    values = {
        "source_type": "client",
        "source_id": uuid4(),
        "external_id": f"piano-client:{uuid4()}",
        "name": "Marie Dupont",
        "email": "marie@example.test",
        "alternate_emails": ("famille@example.test",),
        "phones": ("+33612345678", "+33142345678"),
        "status": "RESPONSABLE",
        "children": ("Alice Dupont", "Louis Dupont"),
        "schedule": (
            "Alice Dupont — mercredi 17:00-18:00 — Rue de la Pompe — Piano collectif",
            "Louis Dupont — vendredi 18:00-19:00 — Rue de Richelieu — Piano collectif",
        ),
        "locations": ("Rue de la Pompe", "Rue de Richelieu"),
        "adult_is_student": True,
        "adult_plans": ("Forfait annuel adulte (active)",),
        "profile_url": "https://app.piano-academie.com/admin/clients/example",
    }
    values.update(overrides)
    return ZendeskContactCandidate(**values)


class ZendeskContactSyncTests(unittest.TestCase):
    def test_french_phone_numbers_are_normalized_for_talk_matching(self) -> None:
        self.assertEqual(normalize_phone("06 12 34 56 78"), "+33612345678")
        self.assertEqual(normalize_phone("0033 (0)6 12 34 56 78"), "+33612345678")
        self.assertEqual(normalize_phone("+33 6 12 34 56 78"), "+33612345678")
        self.assertIsNone(normalize_phone("020 7946 0958", default_country_code="GB"))
        self.assertIsNone(normalize_phone("123"))

    def test_email_normalization_is_case_insensitive(self) -> None:
        self.assertEqual(normalize_email("  Marie@Example.COM "), "marie@example.com")
        self.assertIsNone(normalize_email("   "))

    def test_payload_contains_family_context_without_creating_child_users(self) -> None:
        candidate = _candidate()
        payload = build_zendesk_user_payload(
            candidate,
            synced_at=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
        )["user"]

        self.assertEqual(payload["external_id"], candidate.external_id)
        self.assertEqual(payload["role"], "end-user")
        self.assertEqual(payload["phone"], "+33612345678")
        self.assertIn("Alice Dupont", payload["user_fields"]["piano_app_children"])
        self.assertIn("mercredi 17:00-18:00", payload["user_fields"]["piano_app_schedule"])
        self.assertIn("Rue de la Pompe", payload["user_fields"]["piano_app_locations"])
        self.assertIs(payload["user_fields"]["piano_app_adult_student"], True)
        self.assertEqual(
            payload["user_fields"]["piano_app_adult_plans"],
            "Forfait annuel adulte (active)",
        )

    def test_shared_phone_is_excluded_from_the_two_users(self) -> None:
        first = _candidate(external_id="piano-client:first", phones=("+33612345678",))
        second = _candidate(external_id="piano-client:second", phones=("+33612345678",))
        conflicts = find_shared_phones((first, second))

        self.assertEqual(
            conflicts,
            {"+33612345678": ("piano-client:first", "piano-client:second")},
        )
        payload = build_zendesk_user_payload(
            first,
            synced_at=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
            excluded_phones=set(conflicts),
        )["user"]
        self.assertIsNone(payload["phone"])

    def test_long_schedule_is_truncated_to_a_zendesk_textarea_field(self) -> None:
        candidate = _candidate(schedule=tuple(f"Enfant — lundi 17:00 — Lieu {index}" for index in range(300)))
        payload = build_zendesk_user_payload(
            candidate,
            synced_at=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
        )["user"]
        self.assertLessEqual(len(payload["user_fields"]["piano_app_schedule"]), 5_000)
        self.assertTrue(payload["user_fields"]["piano_app_schedule"].endswith("…"))


if __name__ == "__main__":
    unittest.main()
