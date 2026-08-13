from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.plan_invoice_access import assert_plan_invoice_download_token, create_plan_invoice_download_token


class PlanInvoiceAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings_patch = patch(
            "app.services.plan_invoice_access.settings",
            SimpleNamespace(invoice_download_secret="test-invoice-secret-with-more-than-32-characters"),
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

    def test_signed_token_is_bound_to_subscription(self) -> None:
        subscription_id = uuid4()
        token = create_plan_invoice_download_token(subscription_id=subscription_id, now=self.now)
        assert_plan_invoice_download_token(token=token, subscription_id=subscription_id, now=self.now)
        with self.assertRaises(HTTPException) as context:
            assert_plan_invoice_download_token(token=token, subscription_id=uuid4(), now=self.now)
        self.assertEqual(context.exception.status_code, 403)

    def test_tampered_token_is_rejected(self) -> None:
        subscription_id = uuid4()
        token = create_plan_invoice_download_token(subscription_id=subscription_id, now=self.now)
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with self.assertRaises(HTTPException) as context:
            assert_plan_invoice_download_token(token=tampered, subscription_id=subscription_id, now=self.now)
        self.assertEqual(context.exception.status_code, 403)

    def test_expired_token_is_rejected(self) -> None:
        subscription_id = uuid4()
        token = create_plan_invoice_download_token(
            subscription_id=subscription_id,
            expires_delta=timedelta(minutes=5),
            now=self.now,
        )
        with self.assertRaises(HTTPException) as context:
            assert_plan_invoice_download_token(
                token=token,
                subscription_id=subscription_id,
                now=self.now + timedelta(minutes=6),
            )
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
