from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.api.routes.clients import delete_client_account
from app.schemas.user import ClientAccountDeletionRequest
from app.services.security import hash_password


class _FakeDb:
    def __init__(self, active_commitment: object | None = None) -> None:
        self.active_commitment = active_commitment
        self.executed: list[object] = []
        self.added: list[object] = []
        self.committed = False

    def scalar(self, statement: object) -> object | None:
        del statement
        return self.active_commitment

    def execute(self, statement: object) -> None:
        self.executed.append(statement)

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.committed = True


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        hashed_password=hash_password("correct-password"),
        is_active=True,
        account_deleted_at=None,
        portal_contact_visible=True,
        email_opt_in=True,
        sms_opt_in=True,
        email="client@example.com",
        contact_email="billing@example.com",
        first_name="Client",
        last_name="Test",
        address_line="1 rue Test",
        postal_code="75001",
        city="Paris",
        phone="0100000000",
        mobile_phone_1="0600000000",
        mobile_phone_2=None,
        home_phone=None,
        birth_date=None,
        important_info="Note",
        private_note="Private",
        student_site=None,
        client_status="ACTIVE",
        lesson_reminder_email_opt_in=True,
        lesson_reminder_sms_opt_in=True,
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _payload(password: str = "correct-password") -> ClientAccountDeletionRequest:
    return ClientAccountDeletionRequest(current_password=password, confirm_account_deletion=True)


class ClientAccountDeletionTests(unittest.TestCase):
    def test_account_deletion_is_blocked_while_a_commitment_is_active(self) -> None:
        user = _user()
        db = _FakeDb(active_commitment=uuid4())

        with self.assertRaises(HTTPException) as raised:
            delete_client_account(_payload(), db=db, current_user=user)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, "ACCOUNT_DELETION_ACTIVE_COMMITMENT")
        self.assertTrue(user.is_active)
        self.assertEqual(db.executed, [])
        self.assertFalse(db.committed)

    def test_account_deletion_revokes_access_without_changing_contracts(self) -> None:
        user = _user()
        original_password_hash = user.hashed_password
        db = _FakeDb(active_commitment=None)

        result = delete_client_account(_payload(), db=db, current_user=user)

        self.assertEqual(result.message, "ACCOUNT_DELETED")
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.account_deleted_at)
        self.assertNotEqual(user.hashed_password, original_password_hash)
        self.assertFalse(user.portal_contact_visible)
        self.assertFalse(user.email_opt_in)
        self.assertFalse(user.sms_opt_in)
        self.assertTrue(user.email.startswith("deleted+"))
        self.assertIsNone(user.first_name)
        self.assertIsNone(user.last_name)
        self.assertEqual(len(db.executed), 4)
        self.assertEqual(db.added, [user])
        self.assertTrue(db.committed)

    def test_account_deletion_requires_the_current_password(self) -> None:
        user = _user()
        db = _FakeDb()

        with self.assertRaises(HTTPException) as raised:
            delete_client_account(_payload("incorrect-password"), db=db, current_user=user)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "CURRENT_PASSWORD_INCORRECT")
        self.assertFalse(db.committed)


if __name__ == "__main__":
    unittest.main()
