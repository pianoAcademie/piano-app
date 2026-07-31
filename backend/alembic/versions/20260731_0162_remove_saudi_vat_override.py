"""remove Saudi VAT override for French-supplied live services

Revision ID: 20260731_0162
Revises: 20260731_0161
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op


revision = "20260731_0162"
down_revision = "20260731_0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM vat_rules
        WHERE country_code = 'SA'
          AND valid_from IN (DATE '2018-01-01', DATE '2020-07-01');
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO vat_rules (country_code, service_code, vat_rate, valid_from, valid_to)
        SELECT 'SA', service_code, 5.00, DATE '2018-01-01', DATE '2020-06-30'
        FROM (
            SELECT DISTINCT service_code
            FROM vat_rules
            WHERE country_code = 'FR'
        ) AS supported_services;

        INSERT INTO vat_rules (country_code, service_code, vat_rate, valid_from)
        SELECT 'SA', service_code, 15.00, DATE '2020-07-01'
        FROM (
            SELECT DISTINCT service_code
            FROM vat_rules
            WHERE country_code = 'FR'
        ) AS supported_services;
        """
    )
