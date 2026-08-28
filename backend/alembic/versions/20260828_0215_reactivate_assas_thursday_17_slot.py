"""Reactivate the accidentally cancelled Assas Thursday 17h occurrence.

Revision ID: 20260828_0215
Revises: 20260828_0214
Create Date: 2026-08-28
"""

from __future__ import annotations

revision = "20260828_0215"
down_revision = "20260828_0214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The guarded repair uses its own row-locking session and commits only after
    # validating the exact course and its single cancelled booking. It is
    # idempotent, so retrying the migration after an interruption is safe.
    from scripts.repair_prod_assas_thursday_17_slot import main as repair_main

    result = repair_main(["--apply", "--allow-missing"])
    if result != 0:
        raise RuntimeError(f"Assas slot repair failed with exit code {result}")


def downgrade() -> None:
    # This migration repairs an operational cancellation. Reversing it would
    # cancel a real lesson again, so the data change is intentionally retained.
    pass
