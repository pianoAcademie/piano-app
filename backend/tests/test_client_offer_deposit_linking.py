from __future__ import annotations

from types import SimpleNamespace
import unittest
from uuid import uuid4

from app.api.routes.clients import (
    _client_offer_fields,
    _invoice_source_quote_id,
    _quote_id_from_deposit_reference,
)


class ClientOfferDepositLinkingTests(unittest.TestCase):
    def test_quote_id_from_deposit_reference_requires_exact_reference(self) -> None:
        quote_id = uuid4()

        self.assertEqual(
            _quote_id_from_deposit_reference(f"QUOTE:{quote_id}:DEPOSIT"),
            quote_id,
        )
        self.assertIsNone(_quote_id_from_deposit_reference(f"QUOTE:{quote_id}:OTHER"))
        self.assertIsNone(_quote_id_from_deposit_reference(f"prefix QUOTE:{quote_id}:DEPOSIT"))

    def test_invoice_source_quote_id_prefers_explicit_metadata(self) -> None:
        explicit_quote_id = uuid4()
        transaction_quote_id = uuid4()
        transaction_id = uuid4()

        resolved = _invoice_source_quote_id(
            {
                "source_quote_id": str(explicit_quote_id),
                "included_payment_keys": [f"MANUAL:{transaction_id}"],
            },
            manual_transactions_by_id={
                transaction_id: SimpleNamespace(reference=f"QUOTE:{transaction_quote_id}:DEPOSIT")
            },
        )

        self.assertEqual(resolved, explicit_quote_id)

    def test_invoice_source_quote_id_recovers_legacy_deposit_link(self) -> None:
        quote_id = uuid4()
        transaction_id = uuid4()

        resolved = _invoice_source_quote_id(
            {"included_payment_keys": [f"MANUAL:{transaction_id}"]},
            manual_transactions_by_id={
                transaction_id: SimpleNamespace(reference=f"QUOTE:{quote_id}:DEPOSIT")
            },
        )

        self.assertEqual(resolved, quote_id)

    def test_invoice_source_quote_id_rejects_ambiguous_legacy_links(self) -> None:
        first_transaction_id = uuid4()
        second_transaction_id = uuid4()

        resolved = _invoice_source_quote_id(
            {
                "included_payment_keys": [
                    f"MANUAL:{first_transaction_id}",
                    f"MANUAL:{second_transaction_id}",
                ]
            },
            manual_transactions_by_id={
                first_transaction_id: SimpleNamespace(reference=f"QUOTE:{uuid4()}:DEPOSIT"),
                second_transaction_id: SimpleNamespace(reference=f"QUOTE:{uuid4()}:DEPOSIT"),
            },
        )

        self.assertIsNone(resolved)

    def test_paid_deposit_is_deducted_from_offer_remaining_amount(self) -> None:
        subscription_id = uuid4()
        quote_id = uuid4()
        invoice_note_id = uuid4()
        quote = SimpleNamespace(
            id=quote_id,
            quote_number="DV-20260512094758-E181",
            school_year_label="2026-2027",
            total_ttc="1482.00",
            currency="EUR",
            meta={
                "pre_registration_deposit": {
                    "enabled": True,
                    "amount_ttc": "200.00",
                }
            },
        )

        fields = _client_offer_fields(
            subscription_id=subscription_id,
            quote_by_subscription_id={subscription_id: quote},
            option_rows_by_quote_id={},
            deposit_metadata_by_quote_id={
                quote_id: (
                    SimpleNamespace(id=invoice_note_id),
                    {
                        "invoice_status": "PAID",
                        "paid_at": "2026-05-30T10:31:33+00:00",
                    },
                )
            },
        )

        self.assertEqual(str(fields["offer_total_ttc"]), "1482.00")
        self.assertEqual(str(fields["offer_deposit_amount_ttc"]), "200.00")
        self.assertEqual(fields["offer_deposit_status"], "PAID")
        self.assertEqual(str(fields["offer_remaining_ttc"]), "1282.00")


if __name__ == "__main__":
    unittest.main()
