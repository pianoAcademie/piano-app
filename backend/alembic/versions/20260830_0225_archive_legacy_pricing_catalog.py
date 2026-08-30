"""Archive the legacy 2025-2026 pricing catalog.

Revision ID: 20260830_0225
Revises: 20260830_0224
Create Date: 2026-08-30

The migration is deliberately scoped to the reviewed production catalog IDs.
Empty development and test databases skip the data update.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260830_0225"
down_revision = "20260830_0224"
branch_labels = None
depends_on = None


LEGACY_CATALOG_ID = "d43afa83-9217-4328-9f51-633af70a2fcc"
CURRENT_CATALOG_ID = "7c505ff3-c921-48dd-b632-92a55c57af78"


def upgrade() -> None:
    bind = op.get_bind()
    legacy = bind.execute(
        sa.text(
            """
            SELECT school_year_label, is_default, is_active
            FROM pricing_catalogs
            WHERE id = CAST(:catalog_id AS uuid)
            FOR UPDATE
            """
        ),
        {"catalog_id": LEGACY_CATALOG_ID},
    ).mappings().one_or_none()
    if legacy is None:
        print("Skip legacy pricing-catalog archive: reviewed production catalog is absent.")
        return
    if legacy["school_year_label"] != "2025-2026":
        raise RuntimeError("Legacy pricing-catalog archive refused: the reviewed catalog has an unexpected school year.")

    current = bind.execute(
        sa.text(
            """
            SELECT school_year_label, is_default, is_active, lifecycle_status
            FROM pricing_catalogs
            WHERE id = CAST(:catalog_id AS uuid)
            FOR UPDATE
            """
        ),
        {"catalog_id": CURRENT_CATALOG_ID},
    ).mappings().one_or_none()
    if current is None or current["school_year_label"] != "2026-2027":
        raise RuntimeError("Legacy pricing-catalog archive refused: the reviewed current catalog is absent or unexpected.")
    if not current["is_active"] or not current["is_default"] or current["lifecycle_status"] != "PUBLISHED":
        raise RuntimeError("Legacy pricing-catalog archive refused: the 2026-2027 catalog is not active, default and published.")

    bind.execute(
        sa.text(
            """
            UPDATE pricing_catalogs
            SET is_active = false,
                is_default = false,
                lifecycle_status = 'ARCHIVED',
                published_at = NULL,
                updated_at = now()
            WHERE id = CAST(:catalog_id AS uuid)
            """
        ),
        {"catalog_id": LEGACY_CATALOG_ID},
    )


def downgrade() -> None:
    # Do not reactivate an expired price catalog during a rollback.
    pass
