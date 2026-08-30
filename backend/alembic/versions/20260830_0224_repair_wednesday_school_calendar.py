"""Repair three Wednesday series against the Paris school calendar.

Revision ID: 20260830_0224
Revises: 20260830_0223
Create Date: 2026-08-30

The production-only data repair is deliberately delegated to the guarded,
idempotent script shipped with this revision. Empty development and test
databases skip it because the three reviewed anchor students do not exist.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260830_0224"
down_revision = "20260830_0223"
branch_labels = None
depends_on = None


ANCHOR_STUDENT_IDS = (
    "026a58f4-27ef-46ef-a49a-5e55a2d577e3",
    "c367d74b-e4f2-45e7-969b-7a4466b2f0d7",
    "73d93bd4-9b48-44f4-91fd-78b9c4622296",
)


def upgrade() -> None:
    bind = op.get_bind()
    anchor_count = int(
        bind.scalar(
            sa.text(
                """
                SELECT count(*)
                FROM users
                WHERE id IN (
                    CAST(:anchor_1 AS uuid),
                    CAST(:anchor_2 AS uuid),
                    CAST(:anchor_3 AS uuid)
                )
                """
            ),
            {
                "anchor_1": ANCHOR_STUDENT_IDS[0],
                "anchor_2": ANCHOR_STUDENT_IDS[1],
                "anchor_3": ANCHOR_STUDENT_IDS[2],
            },
        )
        or 0
    )
    if anchor_count == 0:
        print("Skip Wednesday school-calendar repair: reviewed production anchors are absent.")
        return
    if anchor_count != len(ANCHOR_STUDENT_IDS):
        raise RuntimeError(
            "Wednesday school-calendar repair refused: "
            f"expected {len(ANCHOR_STUDENT_IDS)} reviewed anchors, found {anchor_count}."
        )

    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "repair_prod_wednesday_school_calendar_20260830.py"
    )
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
            "Wednesday school-calendar repair failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if "|summary|result=applied|" not in result.stdout:
        raise RuntimeError("Wednesday school-calendar repair returned without a verified apply summary.")


def downgrade() -> None:
    # This migration corrects operational dates and linked records. Reversing
    # it would knowingly restore sessions during holidays and a public holiday.
    pass
