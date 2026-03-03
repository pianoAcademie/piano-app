"""add default payment provider on legal entities

Revision ID: 20260306_0055
Revises: 20260306_0054
Create Date: 2026-03-06 22:15:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260306_0055"
down_revision: Union[str, None] = "20260306_0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "legal_entities",
        sa.Column("default_payment_provider", sa.String(length=30), nullable=True, server_default=sa.text("'PAYPLUG'")),
    )
    op.execute(
        """
        UPDATE legal_entities
        SET default_payment_provider = COALESCE(
            (
                SELECT upper(trim(value))
                FROM app_settings
                WHERE key = 'config_payment_provider'
                LIMIT 1
            ),
            'PAYPLUG'
        )
        WHERE default_payment_provider IS NULL
           OR trim(default_payment_provider) = ''
        """
    )
    op.execute(
        """
        UPDATE legal_entities
        SET default_payment_provider = 'PAYPLUG'
        WHERE upper(default_payment_provider) NOT IN ('PAYPLUG', 'MOLLIE', 'STRIPE')
        """
    )
    op.execute("UPDATE legal_entities SET default_payment_provider = upper(default_payment_provider)")
    op.alter_column("legal_entities", "default_payment_provider", nullable=False)
    op.create_check_constraint(
        "ck_legal_entities_default_payment_provider",
        "legal_entities",
        "default_payment_provider IN ('PAYPLUG', 'MOLLIE', 'STRIPE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_legal_entities_default_payment_provider", "legal_entities", type_="check")
    op.drop_column("legal_entities", "default_payment_provider")
