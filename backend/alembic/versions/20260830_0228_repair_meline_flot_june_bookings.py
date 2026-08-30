"""Repair Meline Flot's two June booking prices and annual-plan link.

Revision ID: 20260830_0228
Revises: 20260830_0227
Create Date: 2026-08-30

The production-only correction is delegated to a guarded, idempotent script.
Empty development and test databases skip it because the reviewed student is
absent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260830_0228"
down_revision = "20260830_0227"
branch_labels = None
depends_on = None


MELINE_FLOT_USER_ID = "4403cdfc-dfcf-434f-9512-d872839d7741"


def upgrade() -> None:
    bind = op.get_bind()
    student_count = int(
        bind.scalar(
            sa.text("SELECT count(*) FROM users WHERE id = CAST(:student_id AS uuid)"),
            {"student_id": MELINE_FLOT_USER_ID},
        )
        or 0
    )
    if student_count == 0:
        print("Skip Meline Flot June repair: reviewed production student is absent.")
        return
    if student_count != 1:
        raise RuntimeError(f"Meline Flot June repair refused: expected one reviewed student, found {student_count}.")

    script = Path(__file__).resolve().parents[2] / "scripts" / "repair_prod_meline_flot_june_bookings.py"
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
            "Meline Flot June repair failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if "|summary|result=applied|" not in result.stdout and "|summary|result=already_repaired|" not in result.stdout:
        raise RuntimeError("Meline Flot June repair returned without a verified apply summary.")


def downgrade() -> None:
    # Reversing this migration would restore the incorrect external-unit rate
    # and detach the two reviewed bookings from the annual package.
    pass
