from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.teacher_invoicing import _teacher_invoice_due_date
from app.services.teacher_invoice_documents import (
    default_teacher_invoice_context,
    render_teacher_invoice_html,
)


class TeacherInvoiceDocumentTests(unittest.TestCase):
    def test_invoice_due_date_is_thirty_calendar_days_after_issue(self) -> None:
        self.assertEqual(_teacher_invoice_due_date(date(2026, 8, 29)), date(2026, 9, 28))

    def test_legacy_template_receives_vat_summary_below_totals(self) -> None:
        template = """
        <html><body>
          <table><tr><td>TOTAL TTC</td><td>{{ totals_ttc }}</td></tr></table>
          <p>{{ payment_instructions }}</p>
          <p>{{ late_payment_penalty_text }}</p>
        </body></html>
        """
        context = default_teacher_invoice_context(language="fr")
        context["vat_summary"] = "TVA non applicable · article 293 B du CGI"
        rendered = render_teacher_invoice_html(html_template=template, context=context)

        self.assertIn("TVA non applicable · article 293 B du CGI", rendered)
        self.assertIn("30 jours", rendered)
        self.assertIn("trois fois le taux d’intérêt légal", rendered)
        self.assertIn("indemnité forfaitaire de 40 €", rendered)
        self.assertNotIn("CGV", rendered)

    def test_legacy_pdf_layout_replaces_unsupported_flexbox(self) -> None:
        template = """
        <style>
          .row { display:flex; gap:16px; }
          .col { flex:1; }
          .page { width: 210mm; min-height: 297mm; padding: 16mm; margin: 0 auto; box-sizing: border-box; }
        </style>
        <div class="page"><div class="row"><div class="col">A</div><div class="col">B</div></div></div>
        """
        rendered = render_teacher_invoice_html(
            html_template=template,
            context=default_teacher_invoice_context(language="fr"),
        )

        self.assertIn("display:table", rendered)
        self.assertIn("display:table-cell", rendered)
        self.assertNotIn("display:flex", rendered)
        self.assertNotIn("min-height: 297mm", rendered)


if __name__ == "__main__":
    unittest.main()
