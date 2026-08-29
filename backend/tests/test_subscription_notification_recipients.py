from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import subscription_billing


class SubscriptionNotificationRecipientTests(unittest.TestCase):
    def test_configured_recipient_replaces_account_contact(self) -> None:
        with patch.object(
            subscription_billing,
            "list_admin_recipients_for_type",
            return_value=["ventes@piano-academie.com"],
        ), patch.object(
            subscription_billing,
            "_get_setting_text",
            return_value="administration@piano-academie.com",
        ):
            recipients = subscription_billing._admin_recipients_for_notification(
                object(),  # type: ignore[arg-type]
                notification_type="subscription_payment_success_admin",
            )

        self.assertEqual(recipients, ["ventes@piano-academie.com"])

    def test_recipient_falls_back_to_account_contact(self) -> None:
        with patch.object(
            subscription_billing,
            "list_admin_recipients_for_type",
            return_value=[],
        ), patch.object(
            subscription_billing,
            "_get_setting_text",
            return_value=" Administration@Piano-Academie.com ",
        ):
            recipients = subscription_billing._admin_recipients_for_notification(
                object(),  # type: ignore[arg-type]
                notification_type="subscription_payment_success_admin",
            )

        self.assertEqual(recipients, ["administration@piano-academie.com"])
