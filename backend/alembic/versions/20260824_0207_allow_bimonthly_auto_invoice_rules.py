"""Allow bimonthly automatic invoice rules.

Revision ID: 20260824_0207
Revises: 20260824_0206
"""

from alembic import op


revision = "20260824_0207"
down_revision = "20260824_0206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_client_auto_invoice_rules_frequency",
        "client_auto_invoice_rules",
        type_="check",
    )
    op.create_check_constraint(
        "ck_client_auto_invoice_rules_frequency",
        "client_auto_invoice_rules",
        "frequency IN ('MONTHLY','BIMONTHLY','QUARTERLY','YEARLY')",
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE client_auto_invoice_rules
        SET frequency = 'MONTHLY'
        WHERE frequency = 'BIMONTHLY'
        """
    )
    op.drop_constraint(
        "ck_client_auto_invoice_rules_frequency",
        "client_auto_invoice_rules",
        type_="check",
    )
    op.create_check_constraint(
        "ck_client_auto_invoice_rules_frequency",
        "client_auto_invoice_rules",
        "frequency IN ('MONTHLY','QUARTERLY','YEARLY')",
    )
