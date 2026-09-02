from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import sys
import unittest

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.auth import _access_token_expiry_minutes, _token_response, refresh_session
from app.models.ops import AuthRefreshSession
from app.models.user import UserRole
from app.schemas.auth import RefreshSessionRequest


class _FakeDb:
    def __init__(self, scalars: list[object] | None = None) -> None:
        self.scalars = list(scalars or [])
        self.added: list[object] = []
        self.commits = 0
        self.rolled_back = False

    def scalar(self, _statement: object) -> object | None:
        return self.scalars.pop(0) if self.scalars else None

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rolled_back = True


def _user(role: UserRole) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), role=role, is_active=True)


class AuthRefreshSessionTests(unittest.TestCase):
    def test_role_specific_access_lifetimes(self) -> None:
        self.assertEqual(_access_token_expiry_minutes(UserRole.CLIENT), 120)
        self.assertEqual(_access_token_expiry_minutes(UserRole.PROF), 480)
        self.assertEqual(_access_token_expiry_minutes(UserRole.ADMIN), 480)

    def test_login_token_response_creates_revocable_refresh_session(self) -> None:
        db = _FakeDb()
        user = _user(UserRole.CLIENT)
        with patch("app.api.routes.auth.secrets.token_urlsafe", return_value="r" * 64):
            response = _token_response(db, user=user)

        self.assertEqual(response.role, "client")
        self.assertEqual(response.access_token_expires_in_seconds, 2 * 60 * 60)
        self.assertEqual(response.refresh_token, "r" * 64)
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.added), 1)
        self.assertIsInstance(db.added[0], AuthRefreshSession)

    def test_refresh_reuses_valid_server_side_session_and_issues_new_access_token(self) -> None:
        user = _user(UserRole.PROF)
        row = SimpleNamespace(
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
            revoked_at=None,
            last_used_at=None,
        )
        db = _FakeDb([row, user])
        response = refresh_session(RefreshSessionRequest(refresh_token="x" * 64), db)

        self.assertEqual(response.role, "prof")
        self.assertEqual(response.access_token_expires_in_seconds, 8 * 60 * 60)
        self.assertIsNotNone(row.last_used_at)
        self.assertEqual(db.commits, 1)

    def test_invalid_refresh_session_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            refresh_session(RefreshSessionRequest(refresh_token="x" * 64), _FakeDb())
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
