"""Add the dedicated upcoming trial courses permission.

Revision ID: 20260828_0214
Revises: 20260827_0213
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260828_0214"
down_revision = "20260827_0213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "professor_permissions",
        sa.Column(
            "can_view_upcoming_trials",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Preserve the expected manager preset for existing collaborators.  The
    # predicate mirrors the manager-profile checkbox shown in the BackOffice.
    op.execute(
        """
        UPDATE professor_permissions
        SET can_view_upcoming_trials = true
        WHERE can_edit_planning = true
          AND can_view_planning_simulation = true
          AND can_view_clients = true
          AND can_access_collaborators = true
          AND can_view_intakes = true
          AND can_view_quotes = true
        """
    )


def downgrade() -> None:
    op.drop_column("professor_permissions", "can_view_upcoming_trials")
