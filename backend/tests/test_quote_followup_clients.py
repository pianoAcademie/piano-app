from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _create_quote_client, _resolve_followup_clients
from app.models.user import ClientKind, ClientStatus


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def add_all(self, values: list[object]) -> None:
        self.added.extend(values)

    def flush(self) -> None:
        self.flush_count += 1


class QuoteFollowupClientsTests(unittest.TestCase):
    def test_create_quote_client_accepts_address_fields(self) -> None:
        db = _FakeSession()

        client = _create_quote_client(
            db,
            email="child@example.com",
            first_name="Raphael",
            last_name="Boisnard",
            phone="+33638151506",
            birth_date=None,
            address_line="12 rue d'Assas",
            postal_code="75006",
            city="Paris",
            address_country="FR",
            client_kind=ClientKind.CHILD,
            status=ClientStatus.ACTIVE,
        )

        self.assertEqual(client.address_line, "12 rue d'Assas")
        self.assertEqual(client.postal_code, "75006")
        self.assertEqual(client.city, "Paris")
        self.assertEqual(client.address_country, "FR")
        self.assertEqual(db.flush_count, 1)

    def test_new_parent_child_uses_child_phone_without_name_error(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(prospect_id=uuid4(), client_id=None)
        followup = SimpleNamespace(target_client_id=None)
        quote_prospect = SimpleNamespace(
            id=uuid4(),
            email="child@example.com",
            first_name="Raphael",
            last_name="Boisnard",
            phone="06 12 34 56 78",
            linked_client_id=None,
            status="new",
            updated_at=None,
        )
        billing = SimpleNamespace(id=uuid4())
        student = SimpleNamespace(id=uuid4())
        created_user_ids: list[object] = []
        created_family_link_ids: list[object] = []
        create_calls: list[dict[str, object]] = []

        def create_quote_client_side_effect(*args, **kwargs):
            create_calls.append(kwargs)
            if len(create_calls) == 1:
                return billing
            return student

        with patch(
            "app.api.routes.quotes._load_prospect_for_update",
            return_value=quote_prospect,
        ), patch(
            "app.api.routes.quotes._resolve_quote_parent_prospect",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._remember_prospect_snapshot",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._quote_parent_address_fields",
            return_value={
                "address_line": "12 rue d'Assas",
                "postal_code": "75006",
                "city": "Paris",
                "country_code": "FR",
            },
        ), patch(
            "app.api.routes.quotes._quote_child_birth_date",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._load_user_for_update",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._find_user_by_email_for_update",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._resolve_parent_contact_data",
            return_value={
                "email": "parent@example.com",
                "first_name": "Emilie",
                "last_name": "Boisnard",
                "phone": "07 98 76 54 32",
            },
        ), patch(
            "app.api.routes.quotes._create_quote_client",
            side_effect=create_quote_client_side_effect,
        ), patch(
            "app.api.routes.quotes._find_family_link_for_update",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.refresh_responsable_status",
            return_value=None,
        ):
            student_result, billing_result = _resolve_followup_clients(
                db,
                quote=quote,
                followup=followup,
                transformation_payload={"clientResolution": {"mode": "new_parent_child"}},
                user_snapshots={},
                prospect_snapshots={},
                created_user_ids=created_user_ids,
                created_family_link_ids=created_family_link_ids,
            )

        self.assertEqual(student_result.id, student.id)
        self.assertEqual(billing_result.id, billing.id)
        self.assertEqual(followup.target_client_id, student.id)
        self.assertEqual(quote.client_id, student.id)
        self.assertEqual(len(create_calls), 2)
        self.assertEqual(create_calls[1]["phone"], "06 12 34 56 78")
        self.assertEqual(create_calls[1]["address_line"], "12 rue d'Assas")
        self.assertEqual(created_user_ids, [billing.id, student.id])

    def test_new_parent_child_ignores_pending_adult_placeholder_for_child(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(prospect_id=uuid4(), client_id=uuid4())
        followup = SimpleNamespace(target_client_id=None)
        quote_prospect = SimpleNamespace(
            id=uuid4(),
            email="parent@example.com",
            first_name="Raphael",
            last_name="Boisnard",
            phone="+33638151506",
            linked_client_id=quote.client_id,
            status="converted",
            updated_at=None,
        )
        billing = SimpleNamespace(id=quote.client_id, client_kind=ClientKind.ADULT)
        student = SimpleNamespace(id=uuid4())
        created_user_ids: list[object] = []
        created_family_link_ids: list[object] = []
        create_calls: list[dict[str, object]] = []

        def load_user_for_update_side_effect(_db, user_id):
            if user_id == billing.id:
                return billing
            return None

        def find_user_by_email_side_effect(_db, email):
            if email == "parent@example.com":
                return billing
            return None

        def create_quote_client_side_effect(*args, **kwargs):
            create_calls.append(kwargs)
            return student

        with patch(
            "app.api.routes.quotes._load_prospect_for_update",
            return_value=quote_prospect,
        ), patch(
            "app.api.routes.quotes._resolve_quote_parent_prospect",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._remember_prospect_snapshot",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._remember_user_snapshot",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._apply_quote_client_contact_defaults",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._quote_parent_address_fields",
            return_value={
                "address_line": "12 rue d'Assas",
                "postal_code": "75006",
                "city": "Paris",
                "country_code": "FR",
            },
        ), patch(
            "app.api.routes.quotes._quote_child_birth_date",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._load_user_for_update",
            side_effect=load_user_for_update_side_effect,
        ), patch(
            "app.api.routes.quotes._find_user_by_email_for_update",
            side_effect=find_user_by_email_side_effect,
        ), patch(
            "app.api.routes.quotes._resolve_parent_contact_data",
            return_value={
                "email": "parent@example.com",
                "first_name": "Emilie",
                "last_name": "Boisnard",
                "phone": "+33638151506",
            },
        ), patch(
            "app.api.routes.quotes._create_quote_client",
            side_effect=create_quote_client_side_effect,
        ), patch(
            "app.api.routes.quotes._find_family_link_for_update",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.refresh_responsable_status",
            return_value=None,
        ):
            student_result, billing_result = _resolve_followup_clients(
                db,
                quote=quote,
                followup=followup,
                transformation_payload={
                    "clientResolution": {
                        "mode": "new_parent_child",
                        "selectedClientId": str(billing.id),
                    },
                },
                user_snapshots={},
                prospect_snapshots={},
                created_user_ids=created_user_ids,
                created_family_link_ids=created_family_link_ids,
            )

        self.assertEqual(student_result.id, student.id)
        self.assertEqual(billing_result.id, billing.id)
        self.assertEqual(followup.target_client_id, student.id)
        self.assertEqual(quote.client_id, student.id)
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0]["phone"], "+33638151506")


if __name__ == "__main__":
    unittest.main()
