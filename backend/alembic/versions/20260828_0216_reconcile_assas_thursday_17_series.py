"""Reconcile the duplicated Assas Thursday 17h series.

Revision ID: 20260828_0216
Revises: 20260828_0215
Create Date: 2026-08-28
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "20260828_0216"
down_revision = "20260828_0215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from scripts.reconcile_prod_assas_thursday_17_series import main as repair_main

    # Keep repairs and the revision marker in Alembic's transaction, without
    # opening a competing connection while schema locks are held.
    result = repair_main(["--apply", "--allow-missing"], session_factory=lambda: Session(
        bind=op.get_bind(), join_transaction_mode="create_savepoint"))
    if result != 0:
        raise RuntimeError(f"Assas Thursday 17h series reconciliation failed with exit code {result}")


def downgrade() -> None:
    # The migration removes only the empty duplicate schedule after preserving
    # every booking on the active series. Recreating the duplicate is unsafe.
    pass
