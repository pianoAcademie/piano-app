from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.client_portal_access import (
    create_password_setup_url,
    send_client_portal_access_email,
)


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.executed: list[object] = []

    def execute(self, statement: object) -> None:
        self.executed.append(statement)

    def add(self, value: object) -> None:
        self.added.append(value)


class ClientPortalAccessTests(unittest.TestCase):
    def test_setup_url_stores_only_the_token_hash(self) -> None:
        db = _FakeSession()
        user = SimpleNamespace(id=uuid4())
        raw_token = "a-private-single-use-token"

        with patch(
            "app.services.client_portal_access.secrets.token_urlsafe",
            return_value=raw_token,
        ), patch(
            "app.services.client_portal_access.resolve_frontend_base_url",
            return_value="https://app.example.test",
        ):
            url = create_password_setup_url(db, user=user)

        self.assertEqual(url, f"https://app.example.test/login?reset_token={raw_token}")
        self.assertEqual(len(db.added), 1)
        self.assertEqual(
            db.added[0].token_hash,
            hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        )
        self.assertNotEqual(db.added[0].token_hash, raw_token)

    def test_french_setup_email_contains_secure_action_and_is_logged_for_user(self) -> None:
        db = _FakeSession()
        user = SimpleNamespace(
            id=uuid4(),
            email="client@example.test",
            first_name="Camille",
            last_name="Martin",
            preferred_language="fr",
        )
        template = {
            "subject": "Accès de {first_name}",
            "body": "{access_intro}|{email}|{primary_label}|{primary_url}",
            "body_format": "HTML",
        }
        sender = SimpleNamespace(
            from_email="contact@example.test",
            from_name="Piano Academie",
            reply_to="contact@example.test",
            subject_prefix="",
        )

        with patch(
            "app.services.client_portal_access.resolve_predefined_template",
            return_value=template,
        ), patch(
            "app.services.client_portal_access.resolve_sender_profile",
            return_value=sender,
        ), patch(
            "app.services.client_portal_access.create_password_setup_url",
            return_value="https://app.example.test/login?reset_token=private",
        ), patch(
            "app.services.client_portal_access.resolve_frontend_base_url",
            return_value="https://app.example.test",
        ), patch(
            "app.services.client_portal_access.send_email",
            return_value="mail-test",
        ) as send_email_mock:
            message_id = send_client_portal_access_email(
                db,
                user=user,
                password_setup_required=True,
                raise_on_failure=True,
            )

        self.assertEqual(message_id, "mail-test")
        sent = send_email_mock.call_args.kwargs
        self.assertEqual(sent["recipient_user_id"], user.id)
        self.assertIs(sent["db"], db)
        self.assertEqual(sent["body_format"], "HTML")
        self.assertIn("Choisir mon mot de passe", sent["body"])
        self.assertIn("reset_token=private", sent["body"])
        self.assertNotIn("mot de passe temporaire", sent["body"].lower())

    def test_english_registered_user_is_sent_to_login_without_reset_token(self) -> None:
        db = _FakeSession()
        user = SimpleNamespace(
            id=uuid4(),
            email="client@example.test",
            first_name="Alex",
            last_name="Taylor",
            preferred_language="en",
        )
        template = {
            "subject": "Access ready",
            "body": "{access_intro}|{primary_label}|{primary_url}",
            "body_format": "HTML",
        }
        sender = SimpleNamespace(
            from_email="contact@example.test",
            from_name="Piano Academie",
            reply_to="contact@example.test",
            subject_prefix="",
        )

        with patch(
            "app.services.client_portal_access.resolve_predefined_template",
            return_value=template,
        ), patch(
            "app.services.client_portal_access.resolve_sender_profile",
            return_value=sender,
        ), patch(
            "app.services.client_portal_access.resolve_frontend_base_url",
            return_value="https://app.example.test",
        ), patch(
            "app.services.client_portal_access.send_email",
            return_value="mail-test",
        ) as send_email_mock:
            send_client_portal_access_email(
                db,
                user=user,
                password_setup_required=False,
            )

        sent_body = send_email_mock.call_args.kwargs["body"]
        self.assertIn("Open my client portal", sent_body)
        self.assertIn("https://app.example.test/login", sent_body)
        self.assertNotIn("reset_token", sent_body)


if __name__ == "__main__":
    unittest.main()
