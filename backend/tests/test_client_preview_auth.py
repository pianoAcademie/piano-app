from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api.deps import get_current_user, is_read_only_client_preview
from app.api.routes.impersonation import start_admin_client_impersonation
from app.core.config import settings
from app.models.user import UserRole


class _FakeDb:
    def __init__(self, user: object) -> None:
        self.user = user

    def scalar(self, _statement: object) -> object:
        return self.user


def _request(method: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/v1/users/me",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 123),
        }
    )


class ClientPreviewAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.claims = {
            "sub": "de5e07d4-fd90-4673-8eee-275174362452",
            "role": "client",
            "imp": True,
            "preview_read_only": True,
            "target_role": "client",
            "act": "admin-id",
        }
        self.credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="preview-token")

    def test_read_only_client_preview_requires_signed_impersonation_shape(self) -> None:
        self.assertTrue(is_read_only_client_preview(self.claims))

    def test_read_only_client_preview_rejects_incomplete_or_non_client_claims(self) -> None:
        self.assertFalse(is_read_only_client_preview({"preview_read_only": True, "target_role": "client"}))
        self.assertFalse(
            is_read_only_client_preview(
                {
                    "imp": True,
                    "preview_read_only": True,
                    "target_role": "teacher",
                    "act": "admin-id",
                }
            )
        )

    def test_inactive_client_can_be_read_in_signed_preview(self) -> None:
        inactive_user = SimpleNamespace(is_active=False)
        with patch("app.api.deps.jwt.decode", return_value=self.claims):
            result = get_current_user(_request("GET"), self.credentials, _FakeDb(inactive_user))
        self.assertIs(result, inactive_user)

    def test_admin_can_start_preview_for_inactive_client(self) -> None:
        client_id = UUID(self.claims["sub"])
        inactive_client = SimpleNamespace(
            id=client_id,
            role=UserRole.CLIENT,
            is_active=False,
            first_name="Lan Nhi",
            last_name="Do",
            email="client@example.com",
        )
        actor = SimpleNamespace(id=uuid4())

        result = start_admin_client_impersonation(client_id, _FakeDb(inactive_client), actor)
        token_claims = jwt.decode(
            result.access_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        self.assertTrue(token_claims["imp"])
        self.assertTrue(token_claims["preview_read_only"])
        self.assertEqual(token_claims["target_role"], "client")
        self.assertEqual(result.redirect_path, "/client?tab=home")

    def test_signed_preview_blocks_write_requests(self) -> None:
        inactive_user = SimpleNamespace(is_active=False)
        with patch("app.api.deps.jwt.decode", return_value=self.claims):
            with self.assertRaises(HTTPException) as raised:
                get_current_user(_request("POST"), self.credentials, _FakeDb(inactive_user))
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Client preview is read-only")

    def test_normal_token_still_rejects_inactive_client(self) -> None:
        inactive_user = SimpleNamespace(is_active=False)
        normal_claims = {"sub": self.claims["sub"], "role": "client"}
        with patch("app.api.deps.jwt.decode", return_value=normal_claims):
            with self.assertRaises(HTTPException) as raised:
                get_current_user(_request("GET"), self.credentials, _FakeDb(inactive_user))
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
