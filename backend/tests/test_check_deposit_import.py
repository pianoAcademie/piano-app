from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import _append_check_tracking_note, _check_import_match_note
from app.schemas.admin import AdminCheckDepositImportRowIn


class CheckDepositImportTests(unittest.TestCase):
    def test_import_match_note_keeps_payer_reference_and_amount_context(self) -> None:
        row = AdminCheckDepositImportRowIn(
            row_number=12,
            reference="  CHQ 88991  ",
            amount_incl_vat=Decimal("320.00"),
            payer_name="Mme Martin",
        )

        note = _check_import_match_note(row)

        self.assertEqual(
            note,
            "Rapprochement import: ligne 12, nom cheque: Mme Martin, reference scannee: CHQ 88991, montant scanne: 320.00.",
        )

    def test_append_check_tracking_note_does_not_duplicate_same_line(self) -> None:
        description = "Depot banque: bordereau A le 2026-05-09."

        updated = _append_check_tracking_note(description, "Depot banque: bordereau A le 2026-05-09.")

        self.assertEqual(updated, description)


if __name__ == "__main__":
    unittest.main()
