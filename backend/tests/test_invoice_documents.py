from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import _normalize_invoice_range_metadata
from app.api.routes.clients import _invoice_period_totals_from_lines_or_metadata
from app.services.invoice_documents import (
    CompanyIdentity,
    InvoiceAppliedPaymentLine,
    InvoicePeriodLine,
    render_invoice_period_pdf,
    summarize_invoice_period_lines,
)


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

    def test_render_invoice_period_pdf_displays_applied_payment_details(self) -> None:
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
                label="Cours collectif",
                quantity=1,
                amount_excl_vat=Decimal("100.00"),
                vat_rate=Decimal("20.00"),
                vat_amount=Decimal("20.00"),
                total_incl_vat=Decimal("120.00"),
                currency="EUR",
            )
        ]

        with patch("app.services.invoice_documents._company_identity", return_value=identity):
            pdf = render_invoice_period_pdf(
                db=object(),
                invoice_number="PA26-0030",
                issued_at=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                client_id="client-1",
                client_name="Hector Souza",
                period_label="01/04/2026 - 01/04/2026",
                lines=lines,
                totals_by_currency={
                    "EUR": {
                        "amount_excl_vat": Decimal("100.00"),
                        "vat_amount": Decimal("20.00"),
                        "total_incl_vat": Decimal("120.00"),
                    }
                },
                note=None,
                client_billing_address="France",
                due_date=date(2026, 4, 1),
                applied_payment_totals_by_currency={"EUR": Decimal("-30.00")},
                applied_payment_lines=[
                    InvoiceAppliedPaymentLine(
                        date_label="05/04/2026",
                        method_label="CB en ligne",
                        reference_label="Acompte",
                        amount=Decimal("30.00"),
                        currency="EUR",
                    )
                ],
            )

        payload = pdf.decode("latin-1", errors="ignore")
        self.assertIn("Paiements recus / imputes", payload)
        self.assertIn("CB en ligne", payload)
        self.assertIn("Acompte", payload)
        self.assertIn("30.00 EUR", payload)

    def test_render_invoice_period_pdf_payment_button_is_clickable(self) -> None:
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
        payment_url = "https://app.piano-academie.com/api/v1/public/payments/invoices/range/client/note?token=test"

        with patch("app.services.invoice_documents._company_identity", return_value=identity):
            pdf = render_invoice_period_pdf(
                db=object(),
                invoice_number="PA26-0042",
                issued_at=datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
                client_id="client-1",
                client_name="Coraline Schnee",
                period_label="01/05/2026 - 30/06/2027",
                lines=[
                    InvoicePeriodLine(
                        date_label="01/05/2026",
                        type_label="Reservation",
                        label="Cours collectif",
                        quantity=1,
                        amount_excl_vat=Decimal("100.00"),
                        vat_rate=Decimal("20.00"),
                        vat_amount=Decimal("20.00"),
                        total_incl_vat=Decimal("120.00"),
                        currency="EUR",
                    )
                ],
                totals_by_currency={
                    "EUR": {
                        "amount_excl_vat": Decimal("100.00"),
                        "vat_amount": Decimal("20.00"),
                        "total_incl_vat": Decimal("120.00"),
                    }
                },
                total_to_pay_by_currency={"EUR": Decimal("120.00")},
                note=None,
                client_billing_address="France",
                due_date=date(2026, 9, 1),
                payment_link_url=payment_url,
            )

        payload = pdf.decode("latin-1", errors="ignore")
        self.assertIn("/Subtype /Link", payload)
        self.assertIn(f"/S /URI /URI ({payment_url})", payload)
        self.assertRegex(payload, r"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Annots \[")

    def test_render_invoice_period_pdf_prefers_frozen_company_identity_override(self) -> None:
        frozen_identity = CompanyIdentity(
            company_name="Piano Academie Figee",
            company_email="frozen@example.com",
            company_phone="+33 1 00 00 00 00",
            company_siren="111111111",
            company_siret="11111111100011",
            company_vat_number="FR11111111111",
            company_address="1 rue figee 75001 Paris (France)",
            company_legal_form="SAS",
            company_share_capital="5000 EUR",
            company_logo_jpeg=None,
            company_logo_width_px=None,
            company_logo_height_px=None,
        )
        live_identity = CompanyIdentity(
            company_name="Piano Academie Modifiee",
            company_email="changed@example.com",
            company_phone="+33 1 99 99 99 99",
            company_siren="999999999",
            company_siret="99999999900099",
            company_vat_number="FR99999999999",
            company_address="99 rue changee 75001 Paris (France)",
            company_legal_form="SARL",
            company_share_capital="9000 EUR",
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

        with patch("app.services.invoice_documents._company_identity", return_value=live_identity):
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
                        "amount_excl_vat": Decimal("12.50"),
                        "vat_amount": Decimal("2.50"),
                        "total_incl_vat": Decimal("15.00"),
                    }
                },
                note=None,
                client_billing_address="France",
                due_date=date(2026, 4, 1),
                company_identity_override=frozen_identity,
            )

        payload = pdf.decode("latin-1", errors="ignore")
        self.assertIn("Piano Academie Figee", payload)
        self.assertNotIn("Piano Academie Modifiee", payload)

    def test_render_invoice_period_pdf_renders_line_detail_with_preserved_breaks(self) -> None:
        identity = CompanyIdentity(
            company_name="Piano Academie",
            company_email="compta@example.com",
            company_phone=None,
            company_siren=None,
            company_siret=None,
            company_vat_number=None,
            company_address="1 rue de Richelieu, 75001 Paris",
            company_legal_form=None,
            company_share_capital=None,
            company_logo_jpeg=None,
            company_logo_width_px=None,
            company_logo_height_px=None,
        )
        lines = [
            InvoicePeriodLine(
                date_label="01/05/2026 - 30/06/2027",
                type_label="Produit",
                label="Kit de demarrage - Gustave Guisnel",
                quantity=1,
                amount_excl_vat=Decimal("225.00"),
                vat_rate=Decimal("20.00"),
                vat_amount=Decimal("45.00"),
                total_incl_vat=Decimal("270.00"),
                currency="EUR",
                detail_label="Contenu:\n- 2 x Cours de controle\n- Jeu de Notes",
            )
        ]

        with patch("app.services.invoice_documents._company_identity", return_value=identity):
            pdf = render_invoice_period_pdf(
                db=object(),
                invoice_number="PA26-0042",
                issued_at=datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
                client_id="client-1",
                client_name="Coraline Schnee",
                period_label="01/05/2026 - 30/06/2027",
                lines=lines,
                totals_by_currency={
                    "EUR": {
                        "amount_excl_vat": Decimal("225.00"),
                        "vat_amount": Decimal("45.00"),
                        "total_incl_vat": Decimal("270.00"),
                    }
                },
                note=None,
                client_billing_address="France",
                due_date=date(2026, 9, 1),
            )

        payload = pdf.decode("latin-1", errors="ignore")
        self.assertIn("Kit de demarrage - Gustave Guisnel", payload)
        self.assertIn("Contenu:", payload)
        self.assertIn("2 x Cours de controle", payload)
        self.assertIn("Jeu de Notes", payload)
        self.assertIn("Date d echeance: 01/09/2026", payload)

    def test_normalize_invoice_range_metadata_preserves_frozen_snapshots(self) -> None:
        payload = {
            "kind": "INVOICE_RANGE",
            "invoice_number": "PA26-0001",
            "issued_date": "2026-04-01",
            "due_date": "2026-04-01",
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
            "layout": "DETAILED",
            "totals_by_currency": {"EUR": "15.00"},
            "billing_entity": "PIANO_ACADEMIE",
            "invoice_status": "ISSUED",
            "client_name": "Hector Souza",
            "client_billing_address": "1 rue de Richelieu, 75001 Paris, France",
            "issuer_snapshot": {
                "company_name": "Piano Academie",
                "company_email": "compta@example.com",
                "company_phone": "+33 1 86 47 60 88",
                "company_siren": "828051417",
                "company_siret": "82805141700032",
                "company_vat_number": "FR74828051417",
                "company_address": "1, rue de Richelieu, 75001 Paris (France)",
                "company_legal_form": "SAS",
                "company_share_capital": "5000 EUR",
            },
        }

        normalized = _normalize_invoice_range_metadata(payload)

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["client_name"], "Hector Souza")
        self.assertEqual(normalized["client_billing_address"], "1 rue de Richelieu, 75001 Paris, France")
        self.assertEqual(normalized["issuer_snapshot"]["company_name"], "Piano Academie")


if __name__ == "__main__":
    unittest.main()
