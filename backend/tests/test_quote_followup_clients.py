from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _create_quote_client, _resolve_followup_clients, _resolve_parent_contact_data
from app.models.family import ClientFamilyLink
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
            "app.api.routes.quotes._find_adult_user_by_email_for_update",
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

    def test_parent_contact_prefers_quote_normalized_parent_fields(self) -> None:
        quote = SimpleNamespace(
            meta={
                "typeform_intake": {
                    "normalized_payload": {
                        "parent_first_name": "Julie",
                        "parent_last_name": "Germain",
                        "parent_email": "julie.germain@example.com",
                        "parent_phone": "06 11 22 33 44",
                    }
                }
            }
        )
        quote_prospect = SimpleNamespace(
            meta={
                "parent_referent": {
                    "first_name": "Maxime",
                    "last_name": "Germain",
                    "email": "maxime.germain@example.com",
                    "phone": "06 00 00 00 00",
                }
            }
        )

        parent_contact = _resolve_parent_contact_data(
            quote=quote,
            quote_prospect=quote_prospect,
            parent_prospect=None,
        )

        self.assertEqual(parent_contact["first_name"], "Julie")
        self.assertEqual(parent_contact["last_name"], "Germain")
        self.assertEqual(parent_contact["email"], "julie.germain@example.com")
        self.assertEqual(parent_contact["phone"], "06 11 22 33 44")

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
            "app.api.routes.quotes._find_adult_user_by_email_for_update",
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

    def test_existing_child_creates_missing_parent_from_quote_context(self) -> None:
        db = _FakeSession()
        child_id = uuid4()
        parent_id = uuid4()
        quote = SimpleNamespace(prospect_id=uuid4(), client_id=child_id, meta={})
        followup = SimpleNamespace(target_client_id=child_id)
        quote_prospect = SimpleNamespace(
            id=uuid4(),
            email="jeanne.in.tokyo@gmail.com",
            first_name="Elise",
            last_name="Hu",
            phone="+33763744649",
            linked_client_id=child_id,
            status="new",
            updated_at=None,
            meta={"prospect_type": "child"},
        )
        parent_prospect = SimpleNamespace(
            id=uuid4(),
            email="jeanne.in.tokyo@gmail.com",
            first_name="Jeanne",
            last_name="Hu",
            phone="+33763744649",
            linked_client_id=None,
            status="new",
            updated_at=None,
            meta={},
        )
        child = SimpleNamespace(
            id=child_id,
            email="jeanne.in.tokyo@gmail.com",
            client_kind=ClientKind.CHILD,
            client_status=ClientStatus.PENDING,
            is_active=True,
            updated_at=None,
            birth_date=None,
        )
        created_parent = SimpleNamespace(
            id=parent_id,
            email="jeanne.in.tokyo@gmail.com",
            client_kind=ClientKind.ADULT,
            client_status=ClientStatus.RESPONSABLE,
            is_active=True,
            updated_at=None,
        )
        created_user_ids: list[object] = []
        created_family_link_ids: list[object] = []
        user_snapshots: dict[str, dict[str, object]] = {}
        create_calls: list[dict[str, object]] = []

        def create_quote_client_side_effect(*args, **kwargs):
            create_calls.append(kwargs)
            return created_parent

        def load_user_for_update_side_effect(_db, user_id):
            if user_id == child_id:
                return child
            return None

        with patch(
            "app.api.routes.quotes._load_prospect_for_update",
            return_value=quote_prospect,
        ), patch(
            "app.api.routes.quotes._resolve_quote_parent_prospect",
            return_value=parent_prospect,
        ), patch(
            "app.api.routes.quotes._quote_child_birth_date",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._quote_parent_address_fields",
            return_value={
                "address_line": "9 place Falguiere",
                "postal_code": "75015",
                "city": "Paris",
                "country_code": "FR",
            },
        ), patch(
            "app.api.routes.quotes._load_user_for_update",
            side_effect=load_user_for_update_side_effect,
        ), patch(
            "app.api.routes.quotes._find_adult_user_by_email_for_update",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.resolve_billing_profile",
            return_value=None,
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
                        "mode": "existing",
                        "selectedClientId": str(child_id),
                    },
                },
                user_snapshots=user_snapshots,
                prospect_snapshots={},
                created_user_ids=created_user_ids,
                created_family_link_ids=created_family_link_ids,
            )

        self.assertEqual(student_result.id, child_id)
        self.assertEqual(billing_result.id, parent_id)
        self.assertEqual(quote.client_id, child_id)
        self.assertEqual(followup.target_client_id, child_id)
        self.assertNotEqual(child.email, "jeanne.in.tokyo@gmail.com")
        self.assertEqual(user_snapshots[str(child_id)]["email"], "jeanne.in.tokyo@gmail.com")
        self.assertEqual(parent_prospect.linked_client_id, parent_id)
        self.assertEqual(parent_prospect.status, "converted")
        self.assertEqual(created_user_ids, [parent_id])
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0]["email"], "jeanne.in.tokyo@gmail.com")
        self.assertEqual(create_calls[0]["first_name"], "Jeanne")
        self.assertEqual(create_calls[0]["last_name"], "Hu")
        self.assertEqual(create_calls[0]["postal_code"], "75015")
        self.assertTrue(any(isinstance(value, ClientFamilyLink) for value in db.added))

    def test_child_existing_parent_rejects_adult_with_child_identity(self) -> None:
        db = _FakeSession()
        parent_id = uuid4()
        quote = SimpleNamespace(prospect_id=uuid4(), client_id=None)
        followup = SimpleNamespace(target_client_id=None)
        quote_prospect = SimpleNamespace(
            id=uuid4(),
            email="adele.de.masson@hotmail.fr",
            first_name="Thalie",
            last_name="MAKHOUL de Masson d'Autume",
            phone="+33767188976",
            linked_client_id=None,
            status="new",
            updated_at=None,
            meta={"prospect_type": "child"},
        )
        selected_adult = SimpleNamespace(
            id=parent_id,
            email="adele.de.masson@hotmail.fr",
            first_name="Thalie",
            last_name="MAKHOUL de Masson d'Autume",
            client_kind=ClientKind.ADULT,
            client_status=ClientStatus.RESPONSABLE,
        )

        def load_user_for_update_side_effect(_db, user_id):
            if user_id == parent_id:
                return selected_adult
            return None

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
            return_value={},
        ), patch(
            "app.api.routes.quotes._quote_child_birth_date",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._load_user_for_update",
            side_effect=load_user_for_update_side_effect,
        ), patch(
            "app.api.routes.quotes._resolve_parent_contact_data",
            return_value={
                "email": "adele.de.masson@hotmail.fr",
                "first_name": None,
                "last_name": None,
                "phone": "+33767188976",
            },
        ):
            with self.assertRaises(HTTPException) as raised:
                _resolve_followup_clients(
                    db,
                    quote=quote,
                    followup=followup,
                    transformation_payload={
                        "clientResolution": {
                            "mode": "new_child_existing_parent",
                            "selectedParentClientId": str(parent_id),
                        },
                    },
                    user_snapshots={},
                    prospect_snapshots={},
                    created_user_ids=[],
                    created_family_link_ids=[],
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("reprend le nom", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
