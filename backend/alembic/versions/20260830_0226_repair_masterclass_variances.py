"""Repair reviewed Masterclass variances and document confirmed choices.

Revision ID: 20260830_0226
Revises: 20260830_0225
Create Date: 2026-08-30

The production-only repair is delegated to a guarded and idempotent script.
Empty development and test databases skip it because the reviewed quote does
not exist.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260830_0226"
down_revision = "20260830_0225"
branch_labels = None
depends_on = None


YAZ_QUOTE_ID = "320fb300-9f0f-4fa1-80b2-f0aca09c3fa4"


def upgrade() -> None:
    bind = op.get_bind()
    quote_count = int(
        bind.scalar(
            sa.text("SELECT count(*) FROM quotes WHERE id = CAST(:quote_id AS uuid)"),
            {"quote_id": YAZ_QUOTE_ID},
        )
        or 0
    )
    if quote_count == 0:
        print("Skip Masterclass variance repair: reviewed production quote is absent.")
        return
    if quote_count != 1:
        raise RuntimeError(f"Masterclass variance repair refused: expected one reviewed quote, found {quote_count}.")

    script = Path(__file__).resolve().parents[2] / "scripts" / "repair_prod_masterclass_variances_20260830.py"
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
            "Masterclass variance repair failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if "|summary|result=applied|" not in result.stdout:
        raise RuntimeError("Masterclass variance repair returned without a verified apply summary.")


def downgrade() -> None:
    # Reversing this migration would knowingly restore an extra booking and
    # remove the structured decisions recorded by the administrator.
    pass
