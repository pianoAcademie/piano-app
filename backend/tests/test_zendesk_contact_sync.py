from __future__ import annotations

from datetime import UTC, datetime
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.services.zendesk_contact_sync import (
    ZendeskClient,
    ZendeskContactCandidate,
    build_zendesk_user_payload,
    find_shared_phones,
    is_mergeable_talk_placeholder_user,
    normalize_email,
    normalize_phone,
    run_zendesk_contact_sync_job,
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

    def test_only_phone_only_talk_placeholder_is_mergeable(self) -> None:
        phone = "+33613554319"
        self.assertTrue(
            is_mergeable_talk_placeholder_user(
                {
                    "role": "end-user",
                    "name": "Appelant +33 6 13 55 43 19",
                    "phone": phone,
                    "email": None,
                    "external_id": None,
                },
                phone=phone,
            )
        )
        self.assertFalse(
            is_mergeable_talk_placeholder_user(
                {
                    "role": "end-user",
                    "name": "Régine Onomo",
                    "phone": phone,
                    "email": "regine@example.test",
                    "external_id": None,
                },
                phone=phone,
            )
        )

    def test_phone_identity_merges_unique_talk_placeholder_into_app_user(self) -> None:
        phone = "+33613554319"
        calls: list[tuple[str, str, dict]] = []
        client = object.__new__(ZendeskClient)

        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == "/users/200/identities.json":
                return {"identities": [{"type": "email", "value": "regine@example.test"}]}
            if path == "/users/search.json":
                return {
                    "users": [
                        {
                            "id": 100,
                            "role": "end-user",
                            "name": "Appelant +33 6 13 55 43 19",
                            "phone": phone,
                            "email": None,
                            "external_id": None,
                        },
                        {
                            "id": 200,
                            "role": "end-user",
                            "name": "Régine Onomo",
                            "phone": phone,
                            "email": "regine@example.test",
                            "external_id": "piano-client:regine",
                        },
                    ]
                }
            if path == "/users/100/identities.json":
                return {"identities": [{"type": "phone_number", "value": phone, "primary": True}]}
            if path == "/users/100/merge":
                return {"job_status": {"status": "completed"}}
            self.fail(f"Requête Zendesk inattendue : {method} {path}")

        client._request = fake_request
        merged, unresolved = client.ensure_identities(user_id=200, emails=(), phones=(phone,))

        self.assertEqual(merged, 1)
        self.assertEqual(unresolved, ())
        self.assertIn(("PUT", "/users/100/merge", {"json": {"user": {"id": 200}}}), calls)

    def test_apply_releases_database_transaction_before_zendesk_calls(self) -> None:
        class FakeDb:
            def __init__(self) -> None:
                self.commits = 0

            def commit(self) -> None:
                self.commits += 1

            def rollback(self) -> None:
                pass

            def get(self, _model, _identifier):
                return job_run

        @contextmanager
        def acquired_lock(*_args, **_kwargs):
            yield True

        db = FakeDb()
        job_run = SimpleNamespace(id=uuid4())

        class FakeZendeskClient:
            def __enter__(self):
                self.assert_database_was_released()
                return self

            def __exit__(self, *_args):
                pass

            def assert_database_was_released(self) -> None:
                self_outer.assertEqual(db.commits, 1)

            def check_connection(self) -> None:
                pass

            def ensure_user_fields(self) -> None:
                pass

            def create_or_update_user(self, _payload) -> int:
                return 123

            def ensure_identities(self, **_kwargs):
                return 0, ()

        self_outer = self
        with (
            patch("app.services.zendesk_contact_sync.get_job_cursor", return_value=None),
            patch("app.services.zendesk_contact_sync.redis_lock", acquired_lock),
            patch("app.services.zendesk_contact_sync.start_job_run", return_value=job_run),
            patch("app.services.zendesk_contact_sync.build_zendesk_contact_candidates", return_value=[_candidate()]),
            patch("app.services.zendesk_contact_sync.find_shared_phones", return_value={}),
            patch("app.services.zendesk_contact_sync.ZendeskClient", FakeZendeskClient),
            patch("app.services.zendesk_contact_sync.upsert_job_cursor"),
            patch("app.services.zendesk_contact_sync.finish_job_run"),
        ):
            result = run_zendesk_contact_sync_job(
                db,
                now=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
                dry_run=False,
                full=True,
                check_connection=True,
            )

        self.assertEqual(result.created_or_updated, 1)


if __name__ == "__main__":
    unittest.main()
