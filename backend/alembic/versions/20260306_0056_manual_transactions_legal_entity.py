"""add legal_entity_id on manual transactions

Revision ID: 20260306_0056
Revises: 20260306_0055
Create Date: 2026-03-06 23:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260306_0056"
down_revision: Union[str, None] = "20260306_0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_manual_transactions",
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_client_manual_transactions_legal_entity_id",
        "client_manual_transactions",
        "legal_entities",
        ["legal_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_client_manual_transactions_legal_entity_id",
        "client_manual_transactions",
        ["legal_entity_id"],
        unique=False,
    )

    op.execute(
        """
        WITH manual_line_entity AS (
            SELECT
                line.source_payment_id AS transaction_id,
                min(line.seller_legal_entity_id::text)::uuid AS seller_legal_entity_id
            FROM client_invoice_lines AS line
            WHERE line.source = 'MANUAL'
              AND line.seller_legal_entity_id IS NOT NULL
            GROUP BY line.source_payment_id
            HAVING COUNT(DISTINCT line.seller_legal_entity_id) = 1
        )
        UPDATE client_manual_transactions AS tx
        SET legal_entity_id = manual_line_entity.seller_legal_entity_id
        FROM manual_line_entity
        WHERE tx.id = manual_line_entity.transaction_id
          AND tx.legal_entity_id IS NULL
        """
    )

    op.execute(
        """
        WITH note_payload AS (
            SELECT
                note.id,
                substring(note.message FROM 'INVOICE_RANGE::(\\{.*\\})')::jsonb AS payload
            FROM client_note_entries AS note
            WHERE position('INVOICE_RANGE::' IN note.message) > 0
        ),
        reconciled_note_entity AS (
            SELECT DISTINCT ON (manual_transaction_id)
                manual_transaction_id,
                seller_legal_entity_id
            FROM (
                SELECT
                    (payment_ref.value)::uuid AS manual_transaction_id,
                    NULLIF(payload ->> 'seller_legal_entity_id', '')::uuid AS seller_legal_entity_id,
                    note.id AS note_id
                FROM note_payload AS note
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN note.payload ? 'reconciled_manual_payment_ids'
                        THEN note.payload -> 'reconciled_manual_payment_ids'
                        ELSE '[]'::jsonb
                    END
                ) AS payment_ref(value)
                WHERE note.payload IS NOT NULL
                  AND NULLIF(note.payload ->> 'seller_legal_entity_id', '') IS NOT NULL
                  AND payment_ref.value ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            ) AS parsed
            ORDER BY manual_transaction_id, note_id
        )
        UPDATE client_manual_transactions AS tx
        SET legal_entity_id = reconciled_note_entity.seller_legal_entity_id
        FROM reconciled_note_entity
        WHERE tx.id = reconciled_note_entity.manual_transaction_id
          AND tx.legal_entity_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_client_manual_transactions_legal_entity_id", table_name="client_manual_transactions")
    op.drop_constraint("fk_client_manual_transactions_legal_entity_id", "client_manual_transactions", type_="foreignkey")
    op.drop_column("client_manual_transactions", "legal_entity_id")
