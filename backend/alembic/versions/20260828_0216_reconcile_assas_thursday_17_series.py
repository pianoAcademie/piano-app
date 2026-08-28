"""Reconcile the duplicated Assas Thursday 17h series.

Revision ID: 20260828_0216
Revises: 20260828_0215
Create Date: 2026-08-28
"""

from __future__ import annotations

revision = "20260828_0216"
down_revision = "20260828_0215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from scripts.reconcile_prod_assas_thursday_17_series import main as repair_main

    result = repair_main(["--apply", "--allow-missing"])
    if result != 0:
        raise RuntimeError(f"Assas Thursday 17h series reconciliation failed with exit code {result}")


def downgrade() -> None:
    # The migration removes only the empty duplicate schedule after preserving
    # every booking on the active series. Recreating the duplicate is unsafe.
    pass
