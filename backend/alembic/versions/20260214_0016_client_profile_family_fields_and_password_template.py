"""add extended client profile fields

Revision ID: 20260214_0016
Revises: 20260214_0015
Create Date: 2026-02-14 17:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260214_0016"
down_revision = "20260214_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("postal_code", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column(
        "users",
        sa.Column("address_country", sa.String(length=2), nullable=False, server_default=sa.text("'FR'")),
    )
    op.add_column("users", sa.Column("mobile_phone_1", sa.String(length=30), nullable=True))
    op.add_column("users", sa.Column("mobile_phone_2", sa.String(length=30), nullable=True))
    op.add_column("users", sa.Column("home_phone", sa.String(length=30), nullable=True))
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("important_info", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE users
        SET mobile_phone_1 = phone
        WHERE mobile_phone_1 IS NULL
          AND phone IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE users
        SET address_country = COALESCE(address_country, residence_country, 'FR')
        WHERE address_country IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("users", "important_info")
    op.drop_column("users", "birth_date")
    op.drop_column("users", "home_phone")
    op.drop_column("users", "mobile_phone_2")
    op.drop_column("users", "mobile_phone_1")
    op.drop_column("users", "address_country")
    op.drop_column("users", "city")
    op.drop_column("users", "postal_code")
