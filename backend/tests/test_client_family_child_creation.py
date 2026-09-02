from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.clients import create_client_family_child
from app.models.family import ClientFamilyLink
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.schemas.user import ClientFamilyChildCreateRequest


class _FakeSession:
    def __init__(self, course_session: object) -> None:
        self.course_session = course_session
        self.scalar_calls = 0
        self.added: list[object] = []
        self.commit_calls = 0

    def scalar(self, _query: object) -> object | None:
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.course_session
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if isinstance(value, User) and value.id is None:
                value.id = uuid4()

    def commit(self) -> None:
        self.commit_calls += 1

    def refresh(self, _value: object) -> None:
        return None


def _adult_user() -> User:
    return User(
        id=uuid4(),
        email="parent@example.com",
        hashed_password="hashed-password",
        role=UserRole.CLIENT,
        first_name="Marie",
        last_name="Fournier",
        address_line="1 rue de Paris",
        postal_code="75001",
        city="Paris",
        address_country="FR",
        residence_country="FR",
        preferred_language="fr",
        preferred_currency="EUR",
        timezone="Europe/Paris",
        client_kind=ClientKind.ADULT,
        client_status=ClientStatus.RESPONSABLE,
        is_active=True,
    )


class ClientFamilyChildCreationTests(unittest.TestCase):
    def test_existing_parent_can_add_new_child_from_trial_checkout(self) -> None:
        parent = _adult_user()
        db = _FakeSession(
            SimpleNamespace(id=uuid4(), child_bookings_enabled=True)
        )
        payload = ClientFamilyChildCreateRequest(
            first_name="Senna",
            last_name="Fournier",
            birth_date="2018-05-12",
            trial_session_id=db.course_session.id,
        )

        result = create_client_family_child(payload, db=db, current_user=parent)

        child = next(value for value in db.added if isinstance(value, User))
        link = next(value for value in db.added if isinstance(value, ClientFamilyLink))
        self.assertEqual(result.id, child.id)
        self.assertEqual(result.first_name, "Senna")
        self.assertEqual(child.client_status, ClientStatus.TRIAL)
        self.assertEqual(child.client_kind, ClientKind.CHILD)
        self.assertFalse(child.lesson_reminder_sms_opt_in)
        self.assertEqual(link.adult_user_id, parent.id)
        self.assertEqual(link.child_user_id, child.id)
        self.assertTrue(link.is_billing_recipient)
        self.assertEqual(db.commit_calls, 1)

    def test_child_account_cannot_add_another_child(self) -> None:
        child = _adult_user()
        child.client_kind = ClientKind.CHILD
        db = _FakeSession(SimpleNamespace(id=uuid4(), child_bookings_enabled=True))
        payload = ClientFamilyChildCreateRequest(
            first_name="Other",
            last_name="Child",
            birth_date="2019-01-01",
        )

        with self.assertRaises(HTTPException) as raised:
            create_client_family_child(payload, db=db, current_user=child)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(db.added, [])


if __name__ == "__main__":
    unittest.main()
