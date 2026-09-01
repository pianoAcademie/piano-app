from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import sys
import unittest

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.auth import change_password
from app.schemas.auth import ChangePasswordRequest
from app.services.security import hash_password, verify_password


class _FakeDb:
    def __init__(self) -> None:
        self.executed: list[object] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement: object) -> None:
        self.executed.append(statement)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class AuthChangePasswordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = SimpleNamespace(
            id=uuid4(),
            hashed_password=hash_password("old-password"),
            updated_at=None,
        )
        self.db = _FakeDb()
        self.request = SimpleNamespace()

    def test_current_password_is_required_to_match(self) -> None:
        payload = ChangePasswordRequest(
            current_password="wrong-password",
            new_password="new-password",
        )

        with patch("app.api.routes.auth._enforce_auth_rate_limit"):
            with self.assertRaises(HTTPException) as raised:
                change_password(payload, self.request, self.user, self.db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "CURRENT_PASSWORD_INCORRECT")
        self.assertFalse(self.db.committed)

    def test_new_password_must_be_different(self) -> None:
        payload = ChangePasswordRequest(
            current_password="old-password",
            new_password="old-password",
        )

        with patch("app.api.routes.auth._enforce_auth_rate_limit"):
            with self.assertRaises(HTTPException) as raised:
                change_password(payload, self.request, self.user, self.db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "PASSWORD_UNCHANGED")
        self.assertFalse(self.db.committed)

    def test_password_is_changed_and_reset_links_are_invalidated(self) -> None:
        payload = ChangePasswordRequest(
            current_password="old-password",
            new_password="new-password",
        )

        with patch("app.api.routes.auth._enforce_auth_rate_limit"):
            response = change_password(payload, self.request, self.user, self.db)

        self.assertEqual(response.message, "PASSWORD_CHANGED")
        self.assertTrue(verify_password("new-password", self.user.hashed_password))
        self.assertFalse(verify_password("old-password", self.user.hashed_password))
        self.assertIsNotNone(self.user.updated_at)
        self.assertEqual(len(self.db.executed), 2)
        self.assertTrue(self.db.committed)
        self.assertFalse(self.db.rolled_back)


if __name__ == "__main__":
    unittest.main()
