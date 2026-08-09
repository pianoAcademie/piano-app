from __future__ import annotations

import unittest

from app.services.legacy_invoice_import import _parse_manifest


class LegacyInvoiceManifestTests(unittest.TestCase):
    def test_parses_valid_manifest(self) -> None:
        content = (
            "sportigo_member_id;invoice_number;issued_at;label;total_incl_vat;currency;file_name\n"
            "882175;FA-PIANO-2026-787;2026-07-11 02:31:19+02;Abonnement mensuel;125;EUR;FA-PIANO-2026-787.pdf\n"
        ).encode("utf-8")
        rows, errors = _parse_manifest(content)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].invoice_number, "FA-PIANO-2026-787")
        self.assertEqual(str(rows[0].total_incl_vat), "125.00")

    def test_rejects_duplicate_reference_and_unsafe_path(self) -> None:
        content = (
            "sportigo_member_id;invoice_number;issued_at;label;total_incl_vat;currency;file_name\n"
            "1;FA-1;2026-01-01T00:00:00+01;Cours;10;EUR;../FA-1.pdf\n"
            "1;FA-1;2026-01-01T00:00:00+01;Cours;10;EUR;FA-1.pdf\n"
        ).encode("utf-8")
        rows, errors = _parse_manifest(content)
        self.assertEqual(len(rows), 1)
        self.assertTrue(any("invalide" in error for error in errors))

    def test_parses_credit_note_with_negative_amount(self) -> None:
        content = (
            "sportigo_member_id;invoice_number;issued_at;label;total_incl_vat;currency;file_name\n"
            "1072975;FA-PIANO-2026-849;2026-08-03T09:16:14+02;Avoir facture FA-PIANO-2026-306;-125;EUR;FA-PIANO-2026-849.pdf\n"
        ).encode("utf-8")
        rows, errors = _parse_manifest(content)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0].total_incl_vat), "-125.00")

    def test_rejects_zero_amount(self) -> None:
        content = (
            "sportigo_member_id;invoice_number;issued_at;label;total_incl_vat;currency;file_name\n"
            "1072975;FA-PIANO-2026-849;2026-08-03T09:16:14+02;Avoir;0;EUR;FA-PIANO-2026-849.pdf\n"
        ).encode("utf-8")
        rows, errors = _parse_manifest(content)
        self.assertEqual(rows, [])
        self.assertTrue(any("montant invalide" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
