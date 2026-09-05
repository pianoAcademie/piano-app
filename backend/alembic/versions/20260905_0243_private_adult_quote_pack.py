"""Add the private-adult quote template and preserve bounded session packs.

Revision ID: 20260905_0243
Revises: 20260905_0242
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260905_0243"
down_revision: Union[str, None] = "20260905_0242"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATE_ID = "1b23be93-bf4d-4cc0-8725-59e8a433c6c6"
VERSION_ID = "f389b1a8-a367-42b6-8cfb-cc152362c82b"
ACTIVITY_ID = "8121f385-6cb9-4bd8-a1b1-db42f0cd8f08"
QUOTE_NUMBER = "DV-20260905113805-D1F1"


def upgrade() -> None:
    connection = op.get_bind()
    source = connection.execute(
        sa.text(
            """
            SELECT qtv.content_snapshot
            FROM quote_templates qt
            JOIN quote_template_versions qtv ON qtv.id = qt.current_version_id
            WHERE qt.code = 'TEMPLATE_COURS_PARTICULIER_ENFANT'
            LIMIT 1
            """
        )
    ).mappings().first()
    source_content = dict(source["content_snapshot"] or {}) if source is not None else {
        "subject_template": "Votre devis {quote_number} Piano Academie",
        "body_template": (
            "<p style='text-align:center'>Piano Academie</p>"
            "<p style='text-align:center'>Votre devis d’inscription</p>"
            "<p>{prospect_identity_block_html}</p><p>{page_break_html}</p>"
            "<p>{activities_planning_table_html}</p><p>{services_table_html}</p>"
            "<p>{adjustments_section_html}</p><p>{products_section_html}</p>"
            "<p>{kits_section_html}</p><p>{financial_recap_block_html}</p>"
            "<p>{payment_method_block_html}</p><p>{payment_schedule_summary}</p>"
            "<p>{payment_schedule_table_html}</p><p>{options_section_html}</p>"
            "<p>{page_break_html}</p><p>{calendar_activity_semesters_html}</p>"
        ),
    }

    connection.execute(
        sa.text(
            """
            INSERT INTO quote_templates (
                id, code, name, template_type, target, language, description,
                is_active, status, current_version_id, is_default
            ) VALUES (
                CAST(:template_id AS uuid), 'TEMPLATE_COURS_PARTICULIER_ADULTE',
                'Template cours particulier adulte', 'quote_body', 'adult', 'fr',
                'Cours particuliers adultes à l''école : carnet de 10 cours ou engagement annuel.',
                true, 'published', CAST(:version_id AS uuid), false
            )
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                target = EXCLUDED.target,
                description = EXCLUDED.description,
                is_active = true,
                status = 'published',
                updated_at = now()
            """
        ),
        {"template_id": TEMPLATE_ID, "version_id": VERSION_ID},
    )
    actual_template_id = connection.execute(
        sa.text("SELECT id FROM quote_templates WHERE code = 'TEMPLATE_COURS_PARTICULIER_ADULTE'")
    ).scalar_one()
    version_id = connection.execute(
        sa.text(
            """
            INSERT INTO quote_template_versions (
                id, quote_template_id, version_number, content_snapshot,
                is_active_version, published_at, changelog
            ) VALUES (
                CAST(:version_id AS uuid), :template_id, 1,
                CAST(:content AS jsonb), true, now(),
                'Création du modèle cours particulier adulte sans Pass Récup.'
            )
            ON CONFLICT (quote_template_id, version_number) DO UPDATE SET
                content_snapshot = EXCLUDED.content_snapshot,
                is_active_version = true,
                published_at = COALESCE(quote_template_versions.published_at, now()),
                updated_at = now()
            RETURNING id
            """
        ),
        {
            "version_id": VERSION_ID,
            "template_id": actual_template_id,
            "content": json.dumps(source_content, ensure_ascii=True),
        },
    ).scalar_one()
    connection.execute(
        sa.text(
            """
            UPDATE quote_templates
            SET current_version_id = :version_id, updated_at = now()
            WHERE id = :template_id
            """
        ),
        {"version_id": version_id, "template_id": actual_template_id},
    )

    connection.execute(
        sa.text(
            """
            UPDATE quote_document_bindings
            SET quote_template_id = :template_id,
                quote_template_version_id = :version_id,
                updated_at = now()
            WHERE prospect_type = 'adult'
              AND activity_id = CAST(:activity_id AS uuid)
              AND language = 'fr'
              AND is_active = true
            """
        ),
        {"template_id": actual_template_id, "version_id": version_id, "activity_id": ACTIVITY_ID},
    )

    quote = connection.execute(
        sa.text("SELECT id, calendar_snapshot, meta FROM quotes WHERE quote_number = :number"),
        {"number": QUOTE_NUMBER},
    ).mappings().first()
    if quote is None:
        return

    calendar = dict(quote["calendar_snapshot"] or {})
    sessions = sorted(
        [dict(row) for row in (calendar.get("sessions") or []) if isinstance(row, dict)],
        key=lambda row: (str(row.get("date") or ""), str(row.get("start_time") or "")),
    )[:10]
    blocks = [dict(row) for row in (calendar.get("blocks") or []) if isinstance(row, dict)]
    for block in blocks:
        if str(block.get("activity_id") or "") != ACTIVITY_ID:
            continue
        block["planning_session_limit"] = 10
        block["planning_session_limit_source"] = "quote_line"
        block["sessions_count"] = len(sessions)
        if sessions:
            block["end_date"] = str(sessions[-1].get("date") or block.get("end_date") or "")
    calendar["sessions"] = sessions
    calendar["blocks"] = blocks
    calendar["sessions_count"] = len(sessions)

    meta = dict(quote["meta"] or {})
    meta.update(
        {
            "pass_recup_mode": "disabled",
            "pass_recup_enabled": False,
            "quote_template_uuid": str(actual_template_id),
            "quote_template_version_id": str(version_id),
            "quote_template_code": "TEMPLATE_COURS_PARTICULIER_ADULTE",
            "quote_template_name": "Template cours particulier adulte",
        }
    )
    connection.execute(
        sa.text(
            """
            UPDATE quote_lines
            SET meta = COALESCE(meta, '{}'::jsonb)
                       || '{"commitment_kind":"ten_course_pack","planning_session_limit":10}'::jsonb,
                updated_at = now()
            WHERE quote_id = :quote_id
              AND activity_id = CAST(:activity_id AS uuid)
              AND line_category = 'service'
              AND line_type = 'item'
              AND pricing_unit = 'session'
              AND quantity = 10
            """
        ),
        {"quote_id": quote["id"], "activity_id": ACTIVITY_ID},
    )
    connection.execute(
        sa.text(
            """
            UPDATE quotes
            SET quote_template_id = :template_id,
                quote_template_version_id = :version_id,
                calendar_snapshot = CAST(:calendar AS jsonb),
                meta = CAST(:meta AS jsonb),
                document_status = 'stale',
                document_snapshot_id = NULL,
                document_hash = NULL,
                document_generated_at = NULL,
                pdf_storage_key = NULL,
                updated_at = now()
            WHERE id = :quote_id
            """
        ),
        {
            "template_id": actual_template_id,
            "version_id": version_id,
            "calendar": json.dumps(calendar, ensure_ascii=True),
            "meta": json.dumps(meta, ensure_ascii=True),
            "quote_id": quote["id"],
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO quote_events (quote_id, event_type, actor_type, payload)
            VALUES (
                :quote_id, 'quote_adult_pack_repaired', 'system',
                CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "quote_id": quote["id"],
            "payload": json.dumps(
                {
                    "reason": "Dedicated adult private lesson template and 10-session pack calendar",
                    "sessions_count": len(sessions),
                    "quote_template_id": str(actual_template_id),
                },
                ensure_ascii=True,
            ),
        },
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE quote_document_bindings
            SET quote_template_id = NULL,
                quote_template_version_id = NULL,
                updated_at = now()
            WHERE prospect_type = 'adult'
              AND activity_id = CAST(:activity_id AS uuid)
              AND language = 'fr'
              AND quote_template_id = CAST(:template_id AS uuid)
            """
        ),
        {"activity_id": ACTIVITY_ID, "template_id": TEMPLATE_ID},
    )
    connection.execute(
        sa.text("DELETE FROM quote_template_versions WHERE quote_template_id = CAST(:id AS uuid)"),
        {"id": TEMPLATE_ID},
    )
    connection.execute(
        sa.text("DELETE FROM quote_templates WHERE id = CAST(:id AS uuid)"),
        {"id": TEMPLATE_ID},
    )
