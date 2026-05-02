"""backfill pass recup products as service nature

Revision ID: 20260430_0105
Revises: 20260430_0104
Create Date: 2026-04-30 10:32:00.000000
"""

from alembic import op


revision = "20260430_0105"
down_revision = "20260430_0104"
branch_labels = None
depends_on = None


_PASS_RECUP_WHERE = """
regexp_replace(
    translate(
        lower(
            coalesce(title, '') || ' ' ||
            coalesce(barcode, '') || ' ' ||
            coalesce(short_description, '') || ' ' ||
            coalesce(long_description, '')
        ),
        'àáâäãåçèéêëìíîïñòóôöõùúûüýÿ',
        'aaaaaaceeeeiiiinooooouuuuyy'
    ),
    '[^a-z0-9]+',
    '',
    'g'
) LIKE '%passrecup%'
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE catalog_products
        SET nature = 'service'
        WHERE {_PASS_RECUP_WHERE}
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE catalog_products
        SET nature = 'material'
        WHERE {_PASS_RECUP_WHERE}
        """
    )
