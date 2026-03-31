from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.booking_confirmation_templates import render_booking_confirmation_email
from app.services.client_purchase_notifications import send_payment_success_notifications
from app.services.messaging_templates import render_template_content


class ClientEmailTemplateTests(unittest.TestCase):
    def test_render_template_content_keeps_html_or_css_braces_and_replaces_placeholders(self) -> None:
        template = (
            "<style>.hero{color:#172033;}</style>"
            "<div class=\"hero\">Bonjour {first_name} {{last_name}}</div>"
        )

        rendered = render_template_content(
            template,
            {
                "first_name": "Hector",
                "last_name": "Souza",
            },
        )

        self.assertIn(".hero{color:#172033;}", rendered)
        self.assertIn("Bonjour Hector Souza", rendered)
        self.assertNotIn("{first_name}", rendered)
        self.assertNotIn("{{last_name}}", rendered)

    def test_payment_success_notifications_send_paid_invoice_template(self) -> None:
        with patch(
            "app.services.client_purchase_notifications._send_template_email",
            side_effect=["msg-payment", "msg-invoice"],
        ) as send_template_email, patch(
            "app.services.client_purchase_notifications._frontend_url",
            return_value="https://app.piano-academie.com/client?tab=finance",
        ):
            result = send_payment_success_notifications(
                db=object(),
                to_email="hector@example.com",
                first_name="Hector",
                last_name="Souza",
                payment_label="Abonnement annuel",
                payment_reference="sub-123",
                paid_at=datetime(2026, 3, 31, 8, 15, tzinfo=timezone.utc),
                transactions_url="https://app.piano-academie.com/client?tab=finance&finance_view=transactions",
                invoice_url="https://app.piano-academie.com/client/invoices/abc/download",
                invoice_number="PA26-0009",
                amount_paid=Decimal("30.00"),
                currency="EUR",
            )

        self.assertEqual(result["payment_confirmation_message_id"], "msg-payment")
        self.assertEqual(result["invoice_message_id"], "msg-invoice")
        self.assertEqual(send_template_email.call_args_list[1].kwargs["template_code"], "INVOICE_PAID")
        self.assertEqual(send_template_email.call_args_list[1].kwargs["delivery_context"], "CLIENT_INVOICE_PAID")
        self.assertEqual(
            send_template_email.call_args_list[1].kwargs["context"]["account_url"],
            "https://app.piano-academie.com/client?tab=finance",
        )

    def test_booking_confirmation_uses_client_planning_link(self) -> None:
        template = {
            "active": True,
            "subject": "Confirmation - {activity_name}",
            "body": "<a href=\"{account_url}\">Compte</a>",
            "body_format": "HTML",
        }
        with patch(
            "app.services.booking_confirmation_templates.resolve_predefined_template",
            return_value=template,
        ), patch(
            "app.services.booking_confirmation_templates._frontend_url",
            return_value="https://app.piano-academie.com/client?tab=planning",
        ):
            rendered = render_booking_confirmation_email(
                db=object(),
                audience="CLIENT",
                recipient_name="Hector",
                student_name="Gabriel TEST01",
                activity_name="Eveil musical",
                start_at=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
                timezone_name="Europe/Paris",
                location_name="Rue de la Pompe",
                teacher_name="Service Administration",
            )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.body_format, "HTML")
        self.assertIn("/client?tab=planning", rendered.body)

    def test_booking_confirmation_omits_teacher_row_when_absent(self) -> None:
        template = {
            "active": True,
            "subject": "Confirmation - {activity_name}",
            "body": (
                "<ul>"
                "<li><strong>Eleve :</strong> {student_name}</li>"
                "<li><strong>Lieu :</strong> {location_name}</li>"
                "<li><strong>Professeur :</strong> {teacher_name}</li>"
                "</ul>"
            ),
            "body_format": "HTML",
        }
        with patch(
            "app.services.booking_confirmation_templates.resolve_predefined_template",
            return_value=template,
        ), patch(
            "app.services.booking_confirmation_templates._frontend_url",
            return_value="https://app.piano-academie.com/client?tab=planning",
        ):
            rendered = render_booking_confirmation_email(
                db=object(),
                audience="CLIENT",
                recipient_name="Hector",
                student_name="Hector Souza",
                activity_name="Reservation studio de repetition",
                start_at=datetime(2026, 3, 31, 15, 0, tzinfo=timezone.utc),
                timezone_name="Europe/Paris",
                location_name="Rue de Richelieu",
                teacher_name="",
            )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertNotIn("Professeur", rendered.body)
        self.assertNotIn("A confirmer", rendered.body)


if __name__ == "__main__":
    unittest.main()
