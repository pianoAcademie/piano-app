"""set quote reminders to J-3 and J-1

Revision ID: 20260629_0155
Revises: 20260622_0154
Create Date: 2026-06-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260629_0155"
down_revision: Union[str, None] = "20260622_0154"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        update app_settings
        set value = '72,24',
            updated_at = now()
        where key = 'config_messaging_quote_reminder_lead_hours_csv'
          and value = '120,24'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        update app_settings
        set value = '120,24',
            updated_at = now()
        where key = 'config_messaging_quote_reminder_lead_hours_csv'
          and value = '72,24'
        """
    )
