"""Correct the untouched teacher invoice template tax wording.

Revision ID: 20260829_0221
Revises: 20260829_0220
Create Date: 2026-08-29
"""

from __future__ import annotations

from alembic import op

revision = "20260829_0221"
down_revision = "20260829_0220"
branch_labels = None
depends_on = None

LEGACY_TEMPLATE = (
    "<h1>Facture professeur</h1><p>Numero: {{invoice_number_display}}</p>"
    "<p>Periode: {{invoice_period_label}}</p><p>Total TTC: {{totals_ttc}}</p>"
)

UPDATED_TEMPLATE = """\
<h1>Facture professeur</h1>
<p><strong>Numero :</strong> {{invoice_number_display}}</p>
<p><strong>Date :</strong> {{invoice_date}} | <strong>Echeance :</strong> {{due_date}}</p>
<p><strong>Periode :</strong> {{invoice_period_label}}</p>
<hr />
<h2>Emetteur (professeur)</h2>
<p>{{teacher_full_name}}<br/>{{teacher_company_name}}<br/>{{teacher_company_address}}<br/>SIRET : {{teacher_siret_display}}<br/>IBAN : {{teacher_iban}}</p>
<h2>Payeur</h2>
<p>{{payor_company_name}}<br/>{{payor_company_address}}<br/>SIRET : {{payor_company_siret}}<br/>TVA : {{payor_company_vat}}</p>
<h2>Prestations</h2>
<p>{{lines_by_course_type}}</p>
<h2>Totaux</h2>
<p>Total HT : {{totals_ht}}<br/>{{vat_summary}}<br/><strong>Net a payer : {{amount_payable}}</strong></p>
<p>{{payment_instructions}}</p>
<p>{{late_payment_penalty_text}}</p>
"""


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(
        """
        UPDATE document_templates
        SET html_template = %s,
            version = version + 1,
            updated_at = now()
        WHERE key = 'teacher_invoice'
          AND html_template = %s
        """,
        (UPDATED_TEMPLATE, LEGACY_TEMPLATE),
    )


def downgrade() -> None:
    # Do not replace a template that may have been edited after this migration.
    pass
