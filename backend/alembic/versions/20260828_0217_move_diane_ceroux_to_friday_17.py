"""Move Diane Ceroux to Friday 17h for the 2026-2027 season.

Revision ID: 20260828_0217
Revises: 20260828_0216
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "20260828_0217"
down_revision = "20260828_0216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from scripts.move_prod_diane_ceroux_to_friday_17 import main as move_main

    # Share Alembic's connection and keep the repair inside its transaction.
    result = move_main(["--apply", "--allow-missing"], session_factory=lambda: Session(
        bind=op.get_bind(), join_transaction_mode="create_savepoint"))
    if result != 0:
        raise RuntimeError(f"Diane Ceroux booking move failed with exit code {result}")


def downgrade() -> None:
    # This migration reflects an operational schedule change requested by the
    # administrator. Moving the real bookings back automatically is unsafe.
    pass
