"""prevent duplicate external teacher invoice submissions

Revision ID: 20260903_0237
Revises: 20260902_0236
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_0237"
down_revision = "20260902_0236"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "teacher_monthly_statements",
        sa.Column("external_invoice_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "teacher_monthly_statements",
        sa.Column("external_invoice_file_name", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE teacher_monthly_statements AS statement
        SET external_invoice_sent_at = (
                SELECT audit.created_at
                FROM teacher_invoice_audit_events AS audit
                WHERE audit.statement_id = statement.id
                  AND audit.event_type = 'teacher_statement_external_invoice_sent'
                ORDER BY audit.created_at ASC
                LIMIT 1
            ),
            external_invoice_file_name = (
                SELECT NULLIF(audit.payload ->> 'file_name', '')
                FROM teacher_invoice_audit_events AS audit
                WHERE audit.statement_id = statement.id
                  AND audit.event_type = 'teacher_statement_external_invoice_sent'
                ORDER BY audit.created_at ASC
                LIMIT 1
            )
        WHERE EXISTS (
            SELECT 1
            FROM teacher_invoice_audit_events AS audit
            WHERE audit.statement_id = statement.id
              AND audit.event_type = 'teacher_statement_external_invoice_sent'
        )
        """
    )


def downgrade():
    op.drop_column("teacher_monthly_statements", "external_invoice_file_name")
    op.drop_column("teacher_monthly_statements", "external_invoice_sent_at")
