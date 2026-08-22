from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.booking_confirmation_templates import render_booking_confirmation_email
from uuid import uuid4

from app.services.client_purchase_notifications import (
    plan_purchase_notification_label,
    send_client_payment_success_notifications,
    send_payment_success_notifications,
    send_plan_purchase_admin_notifications,
)
from app.services.messaging_templates import (
    PREDEFINED_TEMPLATE_DEFINITIONS,
    PREDEFINED_TEMPLATE_TRANSLATIONS,
    recipient_display_name,
    render_template_content,
)


class ClientEmailTemplateTests(unittest.TestCase):
    def test_trial_purchase_notification_uses_activity_specific_label(self) -> None:
        label = plan_purchase_notification_label(
            plan_name="Cours d'essai de piano en présentiel",
            price_breakdown=[
                {
                    "code": "TRIAL_COURSE",
                    "label": "Cours d'essai - Eveil musical",
                    "amount_ttc": "25.00",
                }
            ],
        )

        self.assertEqual(label, "Cours d’essai – Éveil musical")

    def test_external_predefined_email_templates_use_html_branding(self) -> None:
        external_codes = {
            "PASSWORD_RESET",
            "TEACHER_PORTAL_LOGIN_SETUP",
            "EVENT_REMINDER",
            "EVENT_CANCELLED",
            "AUTOMATIC_PAYMENT_FAILED",
            "BANK_TRANSFER_FAILED",
            "BIRTHDAY_EMAIL",
            "LESSON_NOTES",
            "NEW_FILE_ADDED",
        }
        definitions = {item.code: item for item in PREDEFINED_TEMPLATE_DEFINITIONS}

        self.assertTrue(external_codes.issubset(definitions))
        for code in external_codes:
            with self.subTest(code=code):
                definition = definitions[code]
                self.assertEqual(definition.body_format, "HTML")
                self.assertIn("PIANO ACADÉMIE", definition.body)

    def test_recipient_display_name_prefers_civility_first_and_last_name(self) -> None:
        self.assertEqual(
            recipient_display_name(civility="Madame", first_name="Nora", last_name="Martin", email="nora@example.com"),
            "Madame Nora Martin",
        )
        self.assertEqual(
            recipient_display_name(first_name="Nora", last_name="Martin", email="nora@example.com"),
            "Nora Martin",
        )

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
        self.assertEqual(send_template_email.call_args_list[1].kwargs["context"]["recipient_name"], "Hector Souza")
        self.assertEqual(
            send_template_email.call_args_list[1].kwargs["context"]["account_url"],
            "https://app.piano-academie.com/client?tab=finance",
        )

    def test_plan_purchase_notifications_use_public_invoice_download_url(self) -> None:
        subscription_id = uuid4()
        with patch(
            "app.services.client_purchase_notifications._send_template_email",
            side_effect=["msg-payment", "msg-invoice"],
        ) as send_template_email, patch(
            "app.services.client_purchase_notifications._frontend_url",
            side_effect=lambda path: f"https://app.piano-academie.com{path}",
        ), patch(
            "app.services.client_purchase_notifications.create_plan_invoice_download_token",
            return_value="signed.invoice.token",
        ), patch(
            "app.services.client_purchase_notifications._studio_booking_url",
            return_value="https://app.piano-academie.com/embed/planning?course_type_id=studio&location_group=paris",
        ):
            send_client_payment_success_notifications(
                db=object(),
                to_email="hector@example.com",
                first_name="Hector",
                last_name="Souza",
                plan_name="1 reservation de studio",
                subscription_id=subscription_id,
                paid_at=datetime(2026, 4, 3, 7, 0, tzinfo=timezone.utc),
                amount_paid=Decimal("15.00"),
                currency="EUR",
            )

        payment_kwargs = send_template_email.call_args_list[0].kwargs
        self.assertEqual(payment_kwargs["template_code"], "STUDIO_PAYMENT_CONFIRMED")
        self.assertEqual(
            payment_kwargs["context"]["booking_url"],
            "https://app.piano-academie.com/embed/planning?course_type_id=studio&location_group=paris",
        )
        invoice_context = send_template_email.call_args_list[1].kwargs["context"]
        self.assertEqual(
            invoice_context["invoice_url"],
            f"https://app.piano-academie.com/api/v1/public/invoices/plans/{subscription_id}/download?token=signed.invoice.token",
        )

    def test_non_studio_plan_keeps_standard_payment_confirmation(self) -> None:
        subscription_id = uuid4()
        with patch(
            "app.services.client_purchase_notifications._send_template_email",
            side_effect=["msg-payment", "msg-invoice"],
        ) as send_template_email, patch(
            "app.services.client_purchase_notifications._frontend_url",
            side_effect=lambda path: f"https://app.piano-academie.com{path}",
        ), patch(
            "app.services.client_purchase_notifications.create_plan_invoice_download_token",
            return_value="signed.invoice.token",
        ), patch(
            "app.services.client_purchase_notifications._studio_booking_url",
        ) as studio_booking_url:
            send_client_payment_success_notifications(
                db=object(),
                to_email="hector@example.com",
                first_name="Hector",
                last_name="Souza",
                plan_name="Carnet 10 cours collectifs",
                subscription_id=subscription_id,
                paid_at=datetime(2026, 4, 3, 7, 0, tzinfo=timezone.utc),
                amount_paid=Decimal("280.00"),
                currency="EUR",
            )

        studio_booking_url.assert_not_called()
        self.assertEqual(send_template_email.call_args_list[0].kwargs["template_code"], "PAYMENT_CONFIRMED")
        self.assertEqual(send_template_email.call_args_list[0].kwargs["context"]["booking_url"], "")

    def test_studio_payment_email_explains_booking_step_in_french_and_english(self) -> None:
        definition = next(
            item for item in PREDEFINED_TEMPLATE_DEFINITIONS if item.code == "STUDIO_PAYMENT_CONFIRMED"
        )
        english_body = PREDEFINED_TEMPLATE_TRANSLATIONS["STUDIO_PAYMENT_CONFIRMED"]["body"]["en"]
        context = {
            "first_name": "Matt",
            "payment_label": "1 reservation de studio",
            "amount_paid": "15.00",
            "currency": "EUR",
            "paid_at": "19/08/2026 22:46",
            "payment_reference": "payment-123",
            "booking_url": "https://app.piano-academie.com/embed/planning?course_type_id=studio",
            "invoice_number": "FAC-20260819-PAYMENT1",
            "invoice_url": "https://app.piano-academie.com/invoice",
            "transactions_url": "https://app.piano-academie.com/transactions",
        }

        french_rendered = render_template_content(definition.body, context)
        english_rendered = render_template_content(english_body, context)

        self.assertIn("Réserver mon studio", french_rendered)
        self.assertIn("vous n’aurez pas à payer une seconde fois", french_rendered)
        self.assertIn("Book my studio", english_rendered)
        self.assertIn("you will not need to pay again", english_rendered)
        self.assertIn(f'href="{context["booking_url"]}"', french_rendered)
        self.assertIn(f'href="{context["booking_url"]}"', english_rendered)

    def test_plan_purchase_admin_notification_uses_admin_recipients_and_paris_time(self) -> None:
        subscription_id = uuid4()
        client_id = uuid4()
        recipients = [
            type("Recipient", (), {"email": "admin@example.com"})(),
            type("Recipient", (), {"email": "ADMIN@example.com"})(),
        ]
        with patch(
            "app.services.client_purchase_notifications.resolve_admin_plan_purchase_recipients",
            return_value=recipients,
        ), patch(
            "app.services.client_purchase_notifications._send_template_email",
            return_value="msg-admin",
        ) as send_template_email, patch(
            "app.services.client_purchase_notifications._frontend_url",
            side_effect=lambda path: f"https://app.piano-academie.com{path}",
        ):
            result = send_plan_purchase_admin_notifications(
                db=object(),
                client_id=client_id,
                client_email="hector@example.com",
                first_name="Hector",
                last_name="Souza",
                plan_name="Carnet 10 cours",
                subscription_id=subscription_id,
                payment_reference="cs_test_123",
                payment_method="STRIPE",
                paid_at=datetime(2026, 8, 5, 18, 15, tzinfo=timezone.utc),
                amount_paid=Decimal("280.00"),
                currency="EUR",
                student_name="Gabriel Souza",
            )

        self.assertEqual(result, ["msg-admin"])
        self.assertEqual(send_template_email.call_count, 1)
        kwargs = send_template_email.call_args.kwargs
        self.assertEqual(kwargs["template_code"], "PLAN_PURCHASE_ADMIN")
        self.assertEqual(kwargs["delivery_context"], "ADMIN_PLAN_PURCHASE_CONFIRMED")
        self.assertEqual(kwargs["context"]["paid_at"], "05/08/2026 20:15")
        self.assertEqual(kwargs["context"]["amount_paid"], "280.00")
        self.assertEqual(kwargs["context"]["payment_method"], "STRIPE")
        self.assertEqual(kwargs["context"]["student_name"], "Gabriel Souza")
        self.assertIn(str(client_id), kwargs["context"]["client_url"])

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

    def test_booking_confirmation_uses_recipient_local_timezone(self) -> None:
        template = {
            "active": True,
            "subject": "Confirmation - {activity_name}",
            "body": "{session_date} {session_time} ({session_timezone})",
            "body_format": "TEXT",
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
                recipient_name="Sarah",
                student_name="Alya",
                activity_name="Cours en ligne",
                start_at=datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc),
                timezone_name="Asia/Riyadh",
                location_name="Online",
                teacher_name="Prof Test",
                language="en",
            )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.body, "03/08/2026 18:00 (Asia/Riyadh)")

    def test_trial_booking_confirmation_is_explicit_and_hides_technical_teacher(self) -> None:
        template = {
            "active": True,
            "subject": "Nouvelle réservation confirmée – {activity_name}",
            "body": (
                "<p>Type : {booking_type_label}</p>"
                "<p>Activité : {course_activity_name}</p>"
                "<li><strong>Professeur :</strong> {teacher_name}</li>"
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
                audience="ADMIN",
                recipient_name="Administration",
                student_name="Noa Lewinger",
                activity_name="Eveil musical",
                start_at=datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc),
                timezone_name="Europe/Paris",
                location_name="Rue de la Pompe",
                teacher_name="Service Administration",
                language="fr",
                is_trial_course=True,
            )

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertEqual(rendered.subject, "Nouvelle réservation confirmée – Cours d’essai – Éveil musical")
        self.assertIn("Type : Cours d’essai", rendered.body)
        self.assertIn("Activité : Éveil musical", rendered.body)
        self.assertNotIn("Professeur", rendered.body)
        self.assertNotIn("Service Administration", rendered.body)

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
