from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
import csv
from uuid import uuid4

from pypdf import PdfReader

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.teacher_invoicing import _render_statement_csv, _session_attendance_csv_label
from app.services.invoice_documents import CompanyIdentity
from app.services.teacher_invoicing import ComputedStatement, ComputedStatementLine, month_bounds_utc
from app.services.teacher_statement_documents import render_teacher_statement_pdf


class TeacherMonthlyStatementTests(unittest.TestCase):
    def test_month_bounds_follow_paris_summer_time(self) -> None:
        start, end = month_bounds_utc(year=2026, month=7)

        self.assertEqual(start, datetime(2026, 6, 30, 22, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc))

    def test_month_bounds_follow_paris_winter_time(self) -> None:
        start, end = month_bounds_utc(year=2027, month=1)

        self.assertEqual(start, datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2027, 1, 31, 23, 0, tzinfo=timezone.utc))

    def test_attendance_is_exported_with_student_names(self) -> None:
        label = _session_attendance_csv_label(
            {
                "attendance": [
                    {"student_name": "Alice Martin", "status": "ATTENDED"},
                    {"student_name": "Leo Durand", "status": "EXCUSED_ABSENCE"},
                ]
            },
            language="fr",
        )

        self.assertEqual(label, "Alice Martin: Present(e) | Leo Durand: Absent(e) excuse(e)")

    def test_csv_ends_with_hours_and_net_amount_summary(self) -> None:
        payor_id = uuid4()
        line = ComputedStatementLine(
            course_type_id=uuid4(),
            course_type_label="Cours particulier",
            hours=Decimal("1.50"),
            unit_rate_ht=Decimal("40.00"),
            amount_ht=Decimal("60.00"),
            amount_ttc=Decimal("60.00"),
            meta={
                "session_items": [
                    {
                        "session_id": str(uuid4()),
                        "title": "Cours particulier",
                        "date": "2026-07-15",
                        "start_at_utc": "2026-07-15T08:00:00+00:00",
                        "end_at_utc": "2026-07-15T09:30:00+00:00",
                        "location_name": "Rue d Assas",
                        "modality": "ONSITE",
                        "duration_minutes": 90,
                        "unit_rate_ht": "40.00",
                        "amount_ht": "60.00",
                        "vat_amount": "0.00",
                        "amount_ttc": "60.00",
                        "attendance": [{"student_name": "Alice Martin", "status": "ATTENDED"}],
                    }
                ]
            },
        )
        computed = ComputedStatement(
            teacher_id=uuid4(),
            payor_legal_entity_id=payor_id,
            payor_legal_entity_name="Piano Academie",
            year=2026,
            month=7,
            attendance_complete=True,
            currency="EUR",
            totals_ht=Decimal("60.00"),
            totals_vat=Decimal("0.00"),
            totals_ttc=Decimal("60.00"),
            lines=[line],
            missing_sessions=[],
        )

        content = _render_statement_csv(
            [(SimpleNamespace(), computed)],
            year=2026,
            month=7,
            language="fr",
        )
        rows = list(csv.reader(StringIO(content), delimiter=";"))

        self.assertIn("presences_eleves", rows[0])
        self.assertIn("Alice Martin: Present(e)", rows[1])
        self.assertEqual(rows[-1][0], "RECAPITULATIF")
        self.assertEqual(rows[-1][8], "1.50 h")
        self.assertEqual(rows[-1][10], "60.00")

    def test_pdf_contains_official_statement_and_course_details(self) -> None:
        payor_id = uuid4()
        line = ComputedStatementLine(
            course_type_id=uuid4(),
            course_type_label="Cours collectif",
            hours=Decimal("1.00"),
            unit_rate_ht=Decimal("35.00"),
            amount_ht=Decimal("35.00"),
            amount_ttc=Decimal("35.00"),
            meta={
                "session_items": [
                    {
                        "session_id": str(uuid4()),
                        "title": "Cours collectif enfants",
                        "start_at_utc": "2026-07-15T08:00:00+00:00",
                        "end_at_utc": "2026-07-15T09:00:00+00:00",
                        "location_name": "Rue d Assas",
                        "duration_minutes": 60,
                        "unit_rate_ht": "35.00",
                        "amount_ht": "35.00",
                        "attendance": [{"student_name": "Alice Martin", "status": "ATTENDED"}],
                    }
                ]
            },
        )
        computed = ComputedStatement(
            teacher_id=uuid4(),
            payor_legal_entity_id=payor_id,
            payor_legal_entity_name="PIANO ACADEMIE",
            year=2026,
            month=7,
            attendance_complete=True,
            currency="EUR",
            totals_ht=Decimal("35.00"),
            totals_vat=Decimal("0.00"),
            totals_ttc=Decimal("35.00"),
            lines=[line],
            missing_sessions=[],
        )
        identity = CompanyIdentity(
            company_name="PIANO ACADEMIE",
            company_email="comptabilite@piano-academie.com",
            company_phone="+33 1 86 47 60 88",
            company_siren="828051417",
            company_siret="82805141700017",
            company_vat_number="FR74828051417",
            company_address="1, rue de Richelieu, 75001 Paris (France)",
            company_legal_form="SAS",
            company_share_capital="1 000 EUR",
            company_logo_jpeg=None,
            company_logo_width_px=None,
            company_logo_height_px=None,
        )

        content = render_teacher_statement_pdf(
            professor_name="Marie Dupont",
            year=2026,
            month=7,
            statements=[computed],
            identities={payor_id: identity},
            language="fr",
            generated_at=datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 3000)
        extracted = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        self.assertIn("RELEVE MENSUEL DE PRESTATIONS", extracted)
        self.assertIn("PIANO ACADEMIE", extracted)
        self.assertIn("SIRET: 82805141700017", extracted)
        self.assertIn("Cours collectif enfants", extracted)
        self.assertIn("Alice Martin", extracted)
        self.assertIn("35,00 EUR", extracted)


if __name__ == "__main__":
    unittest.main()
