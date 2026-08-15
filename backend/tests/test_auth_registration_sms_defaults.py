from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.auth import register
from app.models.user import ClientKind, User
from app.schemas.auth import RegisterRequest


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def scalar(self, _statement: object) -> None:
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def refresh(self, _value: object) -> None:
        pass


def _registration_payload(**overrides: object) -> RegisterRequest:
    values: dict[str, object] = {
        "email": "client@example.test",
        "password": "password-test",
        "first_name": "Camille",
        "last_name": "Martin",
        "phone": "+33600000000",
        "address_line": "1 rue du Test",
        "postal_code": "75001",
        "city": "Paris",
        "transactional_sms_opt_in": True,
    }
    values.update(overrides)
    return RegisterRequest(**values)


class AuthRegistrationSmsDefaultsTests(unittest.TestCase):
    def _register(self, payload: RegisterRequest) -> _FakeSession:
        db = _FakeSession()
        with patch("app.api.routes.auth.hash_password", return_value="hashed"), patch(
            "app.api.routes.auth.send_client_portal_access_email"
        ):
            register(payload, db)
        return db

    def test_adult_registration_keeps_lesson_sms_reminders_disabled(self) -> None:
        db = self._register(_registration_payload())

        users = [value for value in db.added if isinstance(value, User)]
        self.assertEqual(len(users), 1)
        self.assertTrue(users[0].sms_opt_in)
        self.assertFalse(users[0].lesson_reminder_sms_opt_in)

    def test_parent_and_child_registration_keep_lesson_sms_reminders_disabled(self) -> None:
        db = self._register(
            _registration_payload(
                registration_subject_type="child",
                child_first_name="Lou",
                child_last_name="Martin",
                child_birth_date=date(2018, 5, 12),
            )
        )

        users = [value for value in db.added if isinstance(value, User)]
        self.assertEqual(len(users), 2)
        parent = next(value for value in users if value.client_kind == ClientKind.ADULT)
        child = next(value for value in users if value.client_kind == ClientKind.CHILD)
        self.assertTrue(parent.sms_opt_in)
        self.assertFalse(parent.lesson_reminder_sms_opt_in)
        self.assertFalse(child.lesson_reminder_sms_opt_in)


if __name__ == "__main__":
    unittest.main()
