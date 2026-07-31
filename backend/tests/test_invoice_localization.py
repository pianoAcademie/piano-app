from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.routes.admin_clients import (
    _append_invoice_note,
    _billing_address_label,
    _invoice_payment_label,
    _payment_source_label,
    _saudi_zero_vat_note,
)


class InvoiceLocalizationTests(unittest.TestCase):
    def test_english_invoice_labels_are_localized(self) -> None:
        self.assertEqual(_payment_source_label("BOOKING", language="en"), "Booking")
        self.assertEqual(
            _invoice_payment_label("Cours particulier - Online", language="en"),
            "Private piano lesson - Online",
        )

    def test_saudi_billing_address_uses_invoice_language(self) -> None:
        customer = SimpleNamespace(
            address_line="Riyadh",
            postal_code=None,
            city=None,
            address_country="SA",
            residence_country="SA",
        )

        self.assertEqual(_billing_address_label(customer, language="en"), "Riyadh, Saudi Arabia")
        self.assertEqual(_billing_address_label(customer, language="fr"), "Riyadh, Arabie saoudite")

    def test_zero_vat_note_is_english_and_not_duplicated(self) -> None:
        note = _saudi_zero_vat_note(language="en")

        self.assertIn("French VAT not applicable", note)
        self.assertEqual(_append_invoice_note(note, note), note)


if __name__ == "__main__":
    unittest.main()
