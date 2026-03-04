"""archive communications older than one year

Revision ID: 20260307_0058
Revises: 20260307_0057
Create Date: 2026-03-07 09:10:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260307_0058"
down_revision: Union[str, None] = "20260307_0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("communication_logs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_communication_logs_archived_at", "communication_logs", ["archived_at"], unique=False)
    op.execute(
        """
        UPDATE communication_logs
        SET archived_at = now()
        WHERE archived_at IS NULL
          AND occurred_at < (now() - interval '1 year')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_communication_logs_archived_at", table_name="communication_logs")
    op.drop_column("communication_logs", "archived_at")
