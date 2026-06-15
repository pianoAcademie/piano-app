"""add English quote terms templates

Revision ID: 20260615_0151
Revises: 20260609_0151
Create Date: 2026-06-15 14:45:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0151"
down_revision: Union[str, None] = "20260609_0151"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENGLISH_TERMS = {
    "CGV_ADOLESCENTS_2026_2027_EN": {
        "source_code": "CGV_ADOLESCENTS_2026_2027",
        "name": "Enrollment terms 2026-2027 - Teen/adult group lessons",
        "version_label": "Enrollment terms 2026-2027 - Teen/adult group lessons",
        "description": "English terms and conditions for 2026-2027 teen/adult group lessons.",
        "content": """
<h2>General terms of sale and enrollment 2026-2027</h2>
<h3>Teen/adult group lessons</h3>
<p>These terms apply to the enrollment in teen/adult group lessons for the 2026-2027 school year. Enrollment is confirmed after acceptance of the quote and payment according to the schedule stated in the quote.</p>
<h3>Enrollment and commitment</h3>
<p>The selected course, location, day, time, duration and price are those shown in the quote. Enrollment is personal and valid for the school year indicated in the quote.</p>
<h3>Payment</h3>
<p>The total amount, deposit if applicable, payment method and due dates are shown in the quote. Any bank, card or financing fees are handled according to the payment method selected by the client.</p>
<h3>Absences and make-up lessons</h3>
<p>Group lessons missed by the student are not automatically refundable. Make-up options, when available, depend on the rules and capacity of the school and may require prior notice.</p>
<h3>Schedule changes</h3>
<p>Piano Academie may adjust a schedule, teacher, room or location when required for operational reasons. In that case, the school will offer a suitable alternative whenever possible.</p>
<h3>Cancellation</h3>
<p>Cancellation requests must be sent in writing. Fees already due remain payable, except where a mandatory legal right of withdrawal or another written agreement applies.</p>
<h3>Image rights and personal data</h3>
<p>Personal data is processed only for enrollment, billing, course organization and client relationship management. Photos or videos are used only with the required authorization.</p>
<h3>Acceptance</h3>
<p>By accepting the quote, the client confirms that they have read and accepted these enrollment terms.</p>
""".strip(),
    },
    "TERMS_CHILD_GROUP_COURSE_2026_2027_EN": {
        "source_code": "CGV_ENFANTS_GROUPE_2026_2027",
        "name": "Enrollment terms 2026-2027 - Children's group lessons",
        "version_label": "Enrollment terms 2026-2027 - Children's group lessons",
        "description": "English terms and conditions for 2026-2027 children's group lessons.",
        "content": """
<h2>General terms of sale and enrollment 2026-2027</h2>
<h3>Children's group lessons</h3>
<p>These terms apply to the enrollment of a child in group lessons for the 2026-2027 school year. Enrollment is confirmed after acceptance of the quote and payment according to the schedule stated in the quote.</p>
<h3>Enrollment and commitment</h3>
<p>The selected course, location, day, time, duration and price are those shown in the quote. Enrollment is personal and valid for the child and school year indicated in the quote.</p>
<h3>Legal representative</h3>
<p>The adult accepting the quote represents the child for enrollment, billing and administrative exchanges with Piano Academie.</p>
<h3>Payment</h3>
<p>The total amount, deposit if applicable, payment method and due dates are shown in the quote. Any bank, card or financing fees are handled according to the payment method selected by the client.</p>
<h3>Absences and make-up lessons</h3>
<p>Group lessons missed by the student are not automatically refundable. Make-up options, when available, depend on the rules and capacity of the school and may require prior notice.</p>
<h3>Schedule changes</h3>
<p>Piano Academie may adjust a schedule, teacher, room or location when required for operational reasons. In that case, the school will offer a suitable alternative whenever possible.</p>
<h3>Cancellation</h3>
<p>Cancellation requests must be sent in writing. Fees already due remain payable, except where a mandatory legal right of withdrawal or another written agreement applies.</p>
<h3>Image rights and personal data</h3>
<p>Personal data is processed only for enrollment, billing, course organization and client relationship management. Photos or videos of minors are used only with the required authorization.</p>
<h3>Acceptance</h3>
<p>By accepting the quote, the legal representative confirms that they have read and accepted these enrollment terms.</p>
""".strip(),
    },
}


def _select_one(connection: sa.Connection, sql: str, params: dict[str, Any]) -> Any | None:
    return connection.execute(sa.text(sql), params).mappings().first()


def _select_scalar(connection: sa.Connection, sql: str, params: dict[str, Any]) -> Any | None:
    return connection.execute(sa.text(sql), params).scalar()


def _ensure_terms_template(connection: sa.Connection, code: str, item: dict[str, str]) -> tuple[Any, Any]:
    existing = _select_one(
        connection,
        """
        SELECT id, current_version_id
        FROM terms_templates
        WHERE code = :code
        LIMIT 1
        """,
        {"code": code},
    )
    if existing is not None:
        template_id = existing["id"]
    else:
        source = _select_one(
            connection,
            """
            SELECT terms_type, target
            FROM terms_templates
            WHERE code = :source_code
            LIMIT 1
            """,
            {"source_code": item["source_code"]},
        )
        template_id = _select_scalar(
            connection,
            """
            INSERT INTO terms_templates (
                code, name, terms_type, target, language, description,
                is_active, status, created_at, updated_at
            ) VALUES (
                :code, :name, :terms_type, :target, 'en', :description,
                true, 'published', now(), now()
            )
            RETURNING id
            """,
            {
                "code": code,
                "name": item["name"],
                "terms_type": source["terms_type"] if source else "cgv",
                "target": source["target"] if source else None,
                "description": item["description"],
            },
        )

    version_id = _select_scalar(
        connection,
        """
        SELECT id
        FROM terms_template_versions
        WHERE terms_template_id = :template_id
          AND version_number = 1
        LIMIT 1
        """,
        {"template_id": template_id},
    )
    if version_id is None:
        version_id = _select_scalar(
            connection,
            """
            INSERT INTO terms_template_versions (
                terms_template_id, version_number, content_snapshot,
                is_active_version, published_at, changelog, created_at, updated_at
            ) VALUES (
                :template_id, 1, CAST(:content_snapshot AS jsonb),
                true, now(), :changelog, now(), now()
            )
            RETURNING id
            """,
            {
                "template_id": template_id,
                "content_snapshot": json.dumps(
                    {
                        "version_label": item["version_label"],
                        "content": item["content"],
                    }
                ),
                "changelog": "Initial English version for 2026-2027 quote terms.",
            },
        )

    connection.execute(
        sa.text(
            """
            UPDATE terms_template_versions
            SET is_active_version = (id = :version_id),
                updated_at = now()
            WHERE terms_template_id = :template_id
            """
        ),
        {"template_id": template_id, "version_id": version_id},
    )
    connection.execute(
        sa.text(
            """
            UPDATE terms_templates
            SET name = :name,
                language = 'en',
                description = :description,
                status = 'published',
                is_active = true,
                current_version_id = :version_id,
                updated_at = now()
            WHERE id = :template_id
            """
        ),
        {
            "template_id": template_id,
            "version_id": version_id,
            "name": item["name"],
            "description": item["description"],
        },
    )
    return template_id, version_id


def _clone_bindings_for_english_terms(
    connection: sa.Connection,
    *,
    source_code: str,
    english_template_id: Any,
    english_version_id: Any,
) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO quote_document_bindings (
                prospect_type, context_type, activity_family, activity_id, quote_type_id,
                language, currency, quote_template_id, quote_template_version_id,
                terms_template_id, terms_template_version_id, priority, is_active,
                notes, created_at, updated_at
            )
            SELECT
                b.prospect_type,
                b.context_type,
                b.activity_family,
                b.activity_id,
                b.quote_type_id,
                'en',
                b.currency,
                b.quote_template_id,
                b.quote_template_version_id,
                :english_template_id,
                :english_version_id,
                b.priority,
                true,
                CONCAT(COALESCE(b.notes, 'Auto binding'), ' - English terms'),
                now(),
                now()
            FROM quote_document_bindings b
            JOIN terms_templates source_terms ON source_terms.id = b.terms_template_id
            WHERE source_terms.code = :source_code
              AND b.is_active IS true
              AND COALESCE(b.language, 'fr') = 'fr'
              AND NOT EXISTS (
                  SELECT 1
                  FROM quote_document_bindings existing
                  WHERE existing.is_active IS true
                    AND existing.language = 'en'
                    AND existing.prospect_type IS NOT DISTINCT FROM b.prospect_type
                    AND existing.context_type IS NOT DISTINCT FROM b.context_type
                    AND existing.activity_family IS NOT DISTINCT FROM b.activity_family
                    AND existing.activity_id IS NOT DISTINCT FROM b.activity_id
                    AND existing.quote_type_id IS NOT DISTINCT FROM b.quote_type_id
                    AND existing.currency IS NOT DISTINCT FROM b.currency
              )
            """
        ),
        {
            "source_code": source_code,
            "english_template_id": english_template_id,
            "english_version_id": english_version_id,
        },
    )


def upgrade() -> None:
    connection = op.get_bind()
    for code, item in ENGLISH_TERMS.items():
        template_id, version_id = _ensure_terms_template(connection, code, item)
        _clone_bindings_for_english_terms(
            connection,
            source_code=item["source_code"],
            english_template_id=template_id,
            english_version_id=version_id,
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM quote_document_bindings
            WHERE language = 'en'
              AND terms_template_id IN (
                  SELECT id
                  FROM terms_templates
                  WHERE code IN :codes
              )
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(ENGLISH_TERMS)},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM terms_template_versions
            WHERE terms_template_id IN (
                SELECT id
                FROM terms_templates
                WHERE code IN :codes
            )
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(ENGLISH_TERMS)},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM terms_templates
            WHERE code IN :codes
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(ENGLISH_TERMS)},
    )
