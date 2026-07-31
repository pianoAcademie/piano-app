"""apply zero French VAT to Saudi customer services

Revision ID: 20260731_0163
Revises: 20260731_0162
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op


revision = "20260731_0163"
down_revision = "20260731_0162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO vat_rules (country_code, service_code, vat_rate, valid_from)
        SELECT 'SA', service_code, 0.00, DATE '2025-01-01'
        FROM (
            SELECT DISTINCT service_code
            FROM vat_rules
            WHERE country_code = 'FR'
        ) AS supported_services
        WHERE NOT EXISTS (
            SELECT 1
            FROM vat_rules existing
            WHERE existing.country_code = 'SA'
              AND existing.service_code = supported_services.service_code
              AND existing.valid_from = DATE '2025-01-01'
        );

        UPDATE bookings AS booking
        SET price_excl_vat_snapshot = booking.total_incl_vat_snapshot,
            vat_rate_snapshot = 0.00,
            vat_amount_snapshot = 0.00
        FROM course_sessions AS session,
             course_types AS course_type,
             locations AS location,
             users AS student
        WHERE session.id = booking.session_id
          AND course_type.id = session.course_type_id
          AND location.id = session.location_id
          AND student.id = booking.user_id
          AND (course_type.mode = 'ONLINE'::delivery_mode OR location.is_online IS TRUE)
          AND COALESCE(
                (
                    SELECT COALESCE(
                        NULLIF(UPPER(TRIM(adult.residence_country)), ''),
                        NULLIF(UPPER(TRIM(adult.address_country)), '')
                    )
                    FROM client_family_links AS family_link
                    JOIN users AS adult ON adult.id = family_link.adult_user_id
                    WHERE family_link.child_user_id = student.id
                    ORDER BY family_link.is_billing_recipient DESC, family_link.created_at ASC
                    LIMIT 1
                ),
                NULLIF(UPPER(TRIM(student.residence_country)), ''),
                NULLIF(UPPER(TRIM(student.address_country)), '')
              ) = 'SA'
          AND NOT EXISTS (
                SELECT 1
                FROM client_invoice_lines AS invoice_line
                WHERE invoice_line.source = 'BOOKING'
                  AND invoice_line.source_payment_id = booking.id
              );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM vat_rules
        WHERE country_code = 'SA'
          AND valid_from = DATE '2025-01-01'
          AND vat_rate = 0.00;
        """
    )
