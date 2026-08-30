"""Repair Lina Ghemari's missing Friday booking and invoice allocation.

Revision ID: 20260830_0227
Revises: 20260830_0226
Create Date: 2026-08-30

The production-only correction is delegated to a guarded, idempotent script.
Empty development and test databases skip it because the reviewed quote is
absent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260830_0227"
down_revision = "20260830_0226"
branch_labels = None
depends_on = None


LINA_QUOTE_ID = "229310dd-508c-4f42-a3d9-36c1ac134389"


def upgrade() -> None:
    bind = op.get_bind()
    quote_count = int(
        bind.scalar(
            sa.text("SELECT count(*) FROM quotes WHERE id = CAST(:quote_id AS uuid)"),
            {"quote_id": LINA_QUOTE_ID},
        )
        or 0
    )
    if quote_count == 0:
        print("Skip Lina Friday repair: reviewed production quote is absent.")
        return
    if quote_count != 1:
        raise RuntimeError(f"Lina Friday repair refused: expected one reviewed quote, found {quote_count}.")

    script = Path(__file__).resolve().parents[2] / "scripts" / "repair_prod_lina_ghemari_friday_20260830.py"
    result = subprocess.run(
        [sys.executable, str(script), "--apply"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        raise RuntimeError(
            "Lina Friday repair failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if "|summary|result=applied|" not in result.stdout and "|summary|result=already_repaired|" not in result.stdout:
        raise RuntimeError("Lina Friday repair returned without a verified apply summary.")


def downgrade() -> None:
    # Reversing this migration would knowingly remove an annual booking and
    # restore an incorrect invoice allocation.
    pass
