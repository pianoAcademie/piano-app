from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.catalog import Professor
from app.models.payout import ProfessorSalaryPayment, SalaryPaymentMethod
from app.models.user import User, UserRole
from app.services.collaborator_payment_notifications import (
    build_collaborator_payment_confirmation_email,
    schedule_collaborator_payment_confirmation,
)


def _professor() -> Professor:
    return Professor(
        id=uuid4(),
        first_name="Estela",
        last_name="Oliviero",
        email="Estela@example.com",
    )


def _payment(*, method: SalaryPaymentMethod = SalaryPaymentMethod.BANK_TRANSFER) -> ProfessorSalaryPayment:
    return ProfessorSalaryPayment(
        id=uuid4(),
        professor_id=uuid4(),
        reference_date=date(2026, 8, 31),
        payment_date=date(2026, 8, 29),
        invoice_number="FAC-2026-0088",
        payment_method=method,
        amount_excl_vat=Decimal("100.00"),
        amount_incl_vat=Decimal("120.00"),
        currency_code="EUR",
        settled_payout_count=4,
        created_at=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
    )


class CollaboratorPaymentNotificationTests(unittest.TestCase):
    def test_french_email_contains_invoice_amount_date_and_method(self) -> None:
        email = build_collaborator_payment_confirmation_email(
            professor=_professor(),
            payment=_payment(method=SalaryPaymentMethod.CHEQUE),
            language="fr",
        )

        self.assertEqual(email.subject, "Paiement de votre facture FAC-2026-0088")
        self.assertIn("120,00 EUR", email.body)
        self.assertIn("29/08/2026", email.body)
        self.assertIn("Chèque", email.body)

    def test_english_email_contains_transaction_details(self) -> None:
        email = build_collaborator_payment_confirmation_email(
            professor=_professor(),
            payment=_payment(),
            language="en",
        )

        self.assertEqual(email.subject, "Payment of your invoice FAC-2026-0088")
        self.assertIn("120.00 EUR", email.body)
        self.assertIn("Bank transfer", email.body)

    @patch("app.services.collaborator_payment_notifications.create_notification_if_new")
    def test_schedule_uses_payment_scoped_idempotency_key(self, create_notification_if_new: MagicMock) -> None:
        professor = _professor()
        payment = _payment()
        recipient = User(
            id=uuid4(),
            email=professor.email.lower(),
            hashed_password="unused",
            role=UserRole.PROF,
            preferred_language="en",
        )
        db = MagicMock()
        db.scalar.return_value = recipient
        notification_id = uuid4()
        create_notification_if_new.return_value = SimpleNamespace(id=notification_id)

        scheduled = schedule_collaborator_payment_confirmation(
            db,
            professor=professor,
            payment=payment,
        )

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0].notification_id, notification_id)
        kwargs = create_notification_if_new.call_args.kwargs
        self.assertEqual(
            kwargs["idempotency_key"],
            f"collaborator-payment:{payment.id}:confirmation:estela@example.com",
        )
        self.assertEqual(kwargs["recipient_contact_id"], recipient.id)
        self.assertEqual(kwargs["related_entity_id"], payment.id)

    @patch("app.services.collaborator_payment_notifications.create_notification_if_new")
    def test_existing_notification_is_not_enqueued_again(self, create_notification_if_new: MagicMock) -> None:
        db = MagicMock()
        db.scalar.return_value = None
        create_notification_if_new.return_value = None

        scheduled = schedule_collaborator_payment_confirmation(
            db,
            professor=_professor(),
            payment=_payment(),
        )

        self.assertEqual(scheduled, [])


if __name__ == "__main__":
    unittest.main()
