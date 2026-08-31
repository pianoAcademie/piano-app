"""Move Diane Ceroux with accent-safe identity matching.

Revision ID: 20260828_0218
Revises: 20260828_0217
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "20260828_0218"
down_revision = "20260828_0217"
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
    # Operational data move: reversing automatically would be unsafe.
    pass
