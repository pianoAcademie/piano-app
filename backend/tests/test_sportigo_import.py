from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.sportigo_import import (
    SportigoCreditLot,
    _billing_method,
    _pack_plan_code,
    parse_sportigo_manifest,
)


class SportigoImportManifestTests(unittest.TestCase):
    def test_refunded_member_is_excluded_from_future_imports(self) -> None:
        content = (
            "sportigo_member_id;first_name;last_name;email;monthly;monthly_next_payment_at;credits_json\n"
            '1717363;Rona;Kreiner;rekreiner22@gmail.com;0;;"[{""type"":""studio"",""value"":10}]"\n'
        ).encode()

        rows, errors = parse_sportigo_manifest(content)

        self.assertEqual(errors, [])
        self.assertEqual(rows, [])

    def test_parser_groups_same_credit_type_and_expiration(self) -> None:
        content = (
            "sportigo_member_id;first_name;last_name;email;monthly;monthly_next_payment_at;credits_json\n"
            '42;Alice;Martin;alice@example.com;oui;2026-08-10T00:00:00+02:00;'
            '"[{""type"":""studio"",""value"":2,""expiration_date"":""2026-12-31T00:00:00+01:00""},'
            '{""type"":""studio"",""value"":3,""expiration_date"":""2026-12-31T18:45:00+01:00""}]"\n'
        ).encode()

        rows, errors = parse_sportigo_manifest(content)

        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].monthly)
        self.assertEqual(rows[0].credits[0].value, 5)
        self.assertEqual(_pack_plan_code(rows[0].credits[0]), "SPORTIGO-MIG-PACK-STUDIO-20261231")

    def test_parser_rejects_duplicate_member_id(self) -> None:
        content = (
            "sportigo_member_id;first_name;last_name;monthly;credits_json\n"
            "42;Alice;Martin;non;[]\n"
            "42;Alice;Martin;non;[]\n"
        ).encode()

        rows, errors = parse_sportigo_manifest(content)

        self.assertEqual(len(rows), 1)
        self.assertTrue(any("en double" in error for error in errors))

    def test_parser_requires_next_payment_for_monthly_subscription(self) -> None:
        content = (
            "sportigo_member_id;first_name;last_name;monthly;credits_json\n"
            "42;Alice;Martin;oui;[]\n"
        ).encode()

        rows, errors = parse_sportigo_manifest(content)

        self.assertEqual(rows, [])
        self.assertTrue(any("prochaine échéance" in error for error in errors))

    def test_billing_method_preserves_sepa_and_defaults_other_methods_to_card(self) -> None:
        self.assertEqual(_billing_method("sepa-mollie"), "SEPA_DEBIT")
        self.assertEqual(_billing_method("cb-mollie"), "CARD_ONLINE")
        self.assertEqual(_billing_method("cheque"), "CARD_ONLINE")

if __name__ == "__main__":
    unittest.main()
