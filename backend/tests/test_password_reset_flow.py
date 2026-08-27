from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from starlette.requests import Request

from app.api.routes.auth import (
    PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS,
    forgot_password,
    reset_password,
)
from app.models.ops import PasswordResetToken
from app.schemas.auth import ForgotPasswordRequest, ResetPasswordRequest


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/forgot-password",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email="olivia.zhu@hotmail.fr",
        is_active=True,
        first_name="Olivia",
        last_name="Zhu",
        preferred_language="fr",
        hashed_password="old-hash",
        updated_at=None,
    )


def test_repeated_forgot_password_request_keeps_the_existing_link() -> None:
    user = _user()
    recent_token = SimpleNamespace(created_at=datetime.now(timezone.utc))
    db = MagicMock()
    db.scalar.side_effect = [user, recent_token]

    with patch("app.api.routes.auth._enforce_forgot_password_rate_limits"), patch(
        "app.api.routes.auth.send_email"
    ) as send_email:
        response = forgot_password(
            ForgotPasswordRequest(email=user.email),
            request=_request(),
            db=db,
        )

    assert "e-mail" in response.message
    send_email.assert_not_called()
    db.add.assert_not_called()
    db.execute.assert_not_called()


def test_new_reset_link_expires_within_thirty_minutes_without_invalidating_older_links() -> None:
    user = _user()
    db = MagicMock()
    db.scalar.side_effect = [user, None]
    started_at = datetime.now(timezone.utc)
    sender = SimpleNamespace(
        from_email="contact@piano-academie.com",
        from_name="Piano Académie",
        reply_to="contact@piano-academie.com",
        subject_prefix="",
    )

    with patch("app.api.routes.auth._enforce_forgot_password_rate_limits"), patch(
        "app.api.routes.auth.secrets.token_urlsafe",
        return_value="new-reset-token",
    ), patch(
        "app.api.routes.auth._hash_reset_token",
        return_value="hashed-reset-token",
    ), patch(
        "app.api.routes.auth._frontend_url",
        return_value="https://app.piano-academie.com/login",
    ), patch(
        "app.api.routes.auth._password_reset_template",
        return_value=("Reset", "{reset_url}", "TEXT"),
    ), patch(
        "app.api.routes.auth.resolve_sender_profile",
        return_value=sender,
    ), patch(
        "app.api.routes.auth.send_email"
    ) as send_email:
        forgot_password(
            ForgotPasswordRequest(email=user.email),
            request=_request(),
            db=db,
        )

    token = db.add.call_args.args[0]
    assert isinstance(token, PasswordResetToken)
    assert token.user_id == user.id
    assert started_at + timedelta(minutes=29, seconds=59) <= token.expires_at
    assert token.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=30)
    db.execute.assert_not_called()
    db.commit.assert_called_once()
    send_email.assert_called_once()


def test_successful_reset_invalidates_all_other_active_links_and_returns_email() -> None:
    user = _user()
    token_row = SimpleNamespace(user_id=user.id, id=uuid4(), used_at=None)
    db = MagicMock()
    db.scalar.side_effect = [token_row, user]

    with patch("app.api.routes.auth._enforce_reset_password_rate_limits"), patch(
        "app.api.routes.auth._hash_reset_token",
        return_value="hashed-reset-token",
    ), patch(
        "app.api.routes.auth.hash_password",
        return_value="new-hash",
    ):
        response = reset_password(
            ResetPasswordRequest(token="x" * 48, password="new-password"),
            request=_request(),
            db=db,
        )

    assert user.hashed_password == "new-hash"
    assert token_row.used_at is not None
    db.execute.assert_called_once()
    db.commit.assert_called_once()
    assert response.email == user.email
    assert "bien été modifié" in response.message


def test_cooldown_is_one_minute() -> None:
    assert PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS == 60
