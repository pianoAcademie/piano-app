from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.clients import _invoice_period_totals_from_lines_or_metadata
from app.services.invoice_documents import CompanyIdentity, InvoicePeriodLine, render_invoice_period_pdf, summarize_invoice_period_lines


class InvoicePeriodTotalsTests(unittest.TestCase):
    def test_summarize_invoice_period_lines_aggregates_by_currency_and_vat_rate(self) -> None:
        lines = [
            InvoicePeriodLine(
                date_label="01/04/2026",
                type_label="Reservation",
                label="Studio de repetition - Rue de Richelieu",
                quantity=1,
                amount_excl_vat=Decimal("12.50"),
                vat_rate=Decimal("20.00"),
                vat_amount=Decimal("2.50"),
                total_incl_vat=Decimal("15.00"),
                currency="EUR",
            )
        ]

        totals_by_currency, totals_by_currency_and_vat_rate = summarize_invoice_period_lines(lines)

        self.assertEqual(
            totals_by_currency,
            {
                "EUR": {
                    "amount_excl_vat": Decimal("12.50"),
                    "vat_amount": Decimal("2.50"),
                    "total_incl_vat": Decimal("15.00"),
                }
            },
        )
        self.assertEqual(
            totals_by_currency_and_vat_rate,
            {
                "EUR": {
                    Decimal("20.00"): {
                        "amount_excl_vat": Decimal("12.50"),
                        "vat_amount": Decimal("2.50"),
                        "total_incl_vat": Decimal("15.00"),
                    }
                }
            },
        )

    def test_client_invoice_pdf_prefers_line_totals_over_legacy_metadata(self) -> None:
        lines = [
            InvoicePeriodLine(
                date_label="01/04/2026",
                type_label="Reservation",
                label="Reservation studio de repetition - Rue de Richelieu",
                quantity=1,
                amount_excl_vat=Decimal("12.50"),
                vat_rate=Decimal("20.00"),
                vat_amount=Decimal("2.50"),
                total_incl_vat=Decimal("15.00"),
                currency="EUR",
            )
        ]
        metadata = {"totals_by_currency": {"EUR": "15.00"}}

        totals = _invoice_period_totals_from_lines_or_metadata(lines, metadata)

        self.assertEqual(
            totals,
            {
                "EUR": {
                    "amount_excl_vat": Decimal("12.50"),
                    "vat_amount": Decimal("2.50"),
                    "total_incl_vat": Decimal("15.00"),
                }
            },
        )

    def test_render_invoice_period_pdf_displays_totals_by_vat_rate(self) -> None:
        identity = CompanyIdentity(
            company_name="Piano Academie",
            company_email="comptabilite@piano-academie.com",
            company_phone="+33 1 86 47 60 88",
            company_siren="828051417",
            company_siret="82805141700032",
            company_vat_number="FR74828051417",
            company_address="1, rue de Richelieu, 75001 Paris (France)",
            company_legal_form="SAS",
            company_share_capital="5000 EUR",
            company_logo_jpeg=None,
            company_logo_width_px=None,
            company_logo_height_px=None,
        )
        lines = [
            InvoicePeriodLine(
                date_label="01/04/2026",
                type_label="Reservation",
                label="Reservation studio de repetition - Rue de Richelieu",
                quantity=1,
                amount_excl_vat=Decimal("12.50"),
                vat_rate=Decimal("20.00"),
                vat_amount=Decimal("2.50"),
                total_incl_vat=Decimal("15.00"),
                currency="EUR",
            )
        ]

        with patch("app.services.invoice_documents._company_identity", return_value=identity):
            pdf = render_invoice_period_pdf(
                db=object(),
                invoice_number="PA26-0028",
                issued_at=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                client_id="client-1",
                client_name="Hector Souza",
                period_label="01/04/2026 - 01/04/2026",
                lines=lines,
                totals_by_currency={
                    "EUR": {
                        "amount_excl_vat": Decimal("15.00"),
                        "vat_amount": Decimal("0.00"),
                        "total_incl_vat": Decimal("15.00"),
                    }
                },
                note=None,
                client_billing_address="France",
                due_date=date(2026, 4, 1),
            )

        payload = pdf.decode("latin-1", errors="ignore")
        self.assertIn("Devise / TVA", payload)
        self.assertIn("EUR - 20.00%", payload)
        self.assertIn("(12.50)", payload)
        self.assertIn("(2.50)", payload)


if __name__ == "__main__":
    unittest.main()
