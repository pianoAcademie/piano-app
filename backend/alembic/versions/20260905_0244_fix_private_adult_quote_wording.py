"""Correct the visible wording of the private-adult quote template.

Revision ID: 20260905_0244
Revises: 20260905_0243
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260905_0244"
down_revision: Union[str, None] = "20260905_0243"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    template = connection.execute(
        sa.text(
            """
            SELECT qt.id, qt.current_version_id, qtv.content_snapshot
            FROM quote_templates qt
            JOIN quote_template_versions qtv ON qtv.id = qt.current_version_id
            WHERE qt.code = 'TEMPLATE_COURS_PARTICULIER_ADULTE'
            """
        )
    ).mappings().first()
    if template is None:
        return

    content = dict(template["content_snapshot"] or {})
    subject = str(content.get("subject_template") or "")
    body = str(content.get("body_template") or "")
    content["subject_template"] = subject.replace(
        "cours particulier enfant", "cours particulier adulte"
    )
    content["body_template"] = (
        body.replace("cours particulier enfant", "cours particulier adulte")
        .replace("Informations de l’élève et du responsable", "Informations de l’élève adulte")
        .replace("Informations de l'eleve et du responsable", "Informations de l’élève adulte")
    )

    next_version = connection.execute(
        sa.text(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM quote_template_versions "
            "WHERE quote_template_id = :template_id"
        ),
        {"template_id": template["id"]},
    ).scalar_one()
    version_id = connection.execute(
        sa.text(
            """
            INSERT INTO quote_template_versions (
                quote_template_id, version_number, content_snapshot,
                is_active_version, published_at, changelog
            ) VALUES (
                :template_id, :version_number, CAST(:content AS jsonb),
                true, now(), 'Correction des libellés visibles du modèle adulte.'
            )
            RETURNING id
            """
        ),
        {
            "template_id": template["id"],
            "version_number": next_version,
            "content": json.dumps(content, ensure_ascii=True),
        },
    ).scalar_one()
    connection.execute(
        sa.text(
            "UPDATE quote_template_versions SET is_active_version = (id = :version_id) "
            "WHERE quote_template_id = :template_id"
        ),
        {"version_id": version_id, "template_id": template["id"]},
    )
    connection.execute(
        sa.text(
            "UPDATE quote_templates SET current_version_id = :version_id, updated_at = now() "
            "WHERE id = :template_id"
        ),
        {"version_id": version_id, "template_id": template["id"]},
    )
    connection.execute(
        sa.text(
            """
            UPDATE quote_document_bindings
            SET quote_template_version_id = :version_id, updated_at = now()
            WHERE quote_template_id = :template_id AND is_active = true
            """
        ),
        {"version_id": version_id, "template_id": template["id"]},
    )
    connection.execute(
        sa.text(
            """
            UPDATE quotes
            SET quote_template_version_id = :version_id,
                meta = COALESCE(meta, '{}'::jsonb)
                       || jsonb_build_object('quote_template_version_id', CAST(:version_id AS text)),
                document_status = 'stale',
                document_snapshot_id = NULL,
                document_hash = NULL,
                document_generated_at = NULL,
                pdf_storage_key = NULL,
                updated_at = now()
            WHERE quote_template_id = :template_id
              AND status NOT IN ('cancelled', 'expired')
            """
        ),
        {"version_id": version_id, "template_id": template["id"]},
    )


def downgrade() -> None:
    # Published document wording is intentionally not reverted.
    pass
