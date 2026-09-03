"""assign legal entities to referral credits

Revision ID: 20260903_0238
Revises: 20260903_0237
"""

from alembic import op


revision = "20260903_0238"
down_revision = "20260903_0237"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE client_manual_transactions AS transaction
        SET legal_entity_id = quote.legal_entity_id,
            updated_at = now()
        FROM referral_rewards AS reward
        JOIN quotes AS quote ON quote.id = reward.quote_id
        WHERE reward.credit_transaction_id = transaction.id
          AND transaction.transaction_type = 'DISCOUNT'
          AND lower(COALESCE(transaction.category, '')) = 'parrainage'
          AND transaction.legal_entity_id IS NULL
          AND quote.legal_entity_id IS NOT NULL
        """
    )


def downgrade():
    # Keep repaired accounting assignments rather than restoring invalid data.
    pass
