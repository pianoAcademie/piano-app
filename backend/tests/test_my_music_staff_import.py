from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import (
    _mms_decode_csv_bytes,
    _mms_parent_contacts_from_row,
    _mms_parse_csv_rows,
    _mms_parse_date,
    _mms_synthetic_email,
)


class MyMusicStaffImportTests(unittest.TestCase):
    def test_parse_semicolon_csv_and_parent_contact_headers(self) -> None:
        raw = (
            "\ufeffNom de famille;Prénom;ID étudiant My Music Staff;ID de la famille My Music Staff;"
            "Nom de famille du parent contact 1;Prénom du parent contact 1;Contact du parent 1 courriel;"
            "Contact parent 1 téléphone portable;Adresse de contact du parent 1\n"
            "Dupont;Alice;sdt_123;fml_456;Martin;Julie;julie@example.com;0612345678;1 rue Test\n"
        )

        rows = _mms_parse_csv_rows(raw)
        contacts = _mms_parent_contacts_from_row(rows[0])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Prénom"], "Alice")
        self.assertEqual(contacts[0]["first_name"], "Julie")
        self.assertEqual(contacts[0]["last_name"], "Martin")
        self.assertEqual(contacts[0]["email"], "julie@example.com")
        self.assertEqual(contacts[0]["mobile_phone_1"], "0612345678")
        self.assertEqual(contacts[0]["address_line"], "1 rue Test")

    def test_date_and_synthetic_email_are_stable(self) -> None:
        self.assertEqual(str(_mms_parse_date("03/05/2020")), "2020-05-03")
        self.assertEqual(_mms_parse_date(""), None)
        self.assertEqual(_mms_synthetic_email("child", "sdt_mByFJG", "fallback"), "mms-child-sdt-mbyfjg@no-email.local")

    def test_decode_accepts_utf8_bom(self) -> None:
        content = "Nom de famille;Prénom\nHu;Jeanne\n".encode("utf-8-sig")

        decoded = _mms_decode_csv_bytes(content)

        self.assertTrue(decoded.startswith("Nom de famille"))


if __name__ == "__main__":
    unittest.main()
