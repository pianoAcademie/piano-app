"""register quote document bindings by course type

Revision ID: 20260430_0103
Revises: 20260429_0102
Create Date: 2026-04-30 09:20:00.000000
"""

from __future__ import annotations

from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260430_0103"
down_revision: Union[str, None] = "20260429_0102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BINDING_DEFINITIONS = [
    {
        "activity_code": "PIANO_GROUP_ONSITE_1H",
        "quote_template_code": "TEMPLATE_COURS_COLLECTIF_ENFANT",
        "terms_template_code": "CGV_ENFANTS_GROUPE_2026_2027",
        "notes": "Auto binding 2026-2027: cours collectif enfant",
    },
    {
        "activity_code": "ACT_INITIATION_AU_PIANO_E9BD5B",
        "quote_template_code": "INITIATION",
        "terms_template_code": "CGV_INITIATION_2025",
        "notes": "Auto binding 2026-2027: initiation",
    },
    {
        "activity_code": "ACT_EVEIL_MUSICAL_98E099",
        "quote_template_code": "TEMPLATE_EVEIL_MUSICAL",
        "terms_template_code": "CGV_EVEIL_MUSICAL_PARIS",
        "notes": "Auto binding 2026-2027: eveil musical",
    },
    {
        "activity_code": "ACT_COURS_COLLECTIFS_ADO_ADULTES_394F7E",
        "quote_template_code": "TEMPLATE_ADO",
        "terms_template_code": "CGV_ADOLESCENTS_2026_2027",
        "notes": "Auto binding 2026-2027: ado",
    },
]


def _select_id(connection: sa.Connection, table_name: str, code: str) -> Any | None:
    return connection.execute(
        sa.text(
            f"""
            SELECT id
            FROM {table_name}
            WHERE code = :code
            LIMIT 1
            """
        ),
        {"code": code},
    ).scalar()


def _load_bindings(connection: sa.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT *
                FROM quote_document_bindings
                """
            )
        ).mappings().all()
    ]


def _find_binding(
    rows: list[dict[str, Any]],
    *,
    prospect_type: str | None,
    context_type: str | None,
    activity_family: str | None,
    activity_id: Any | None,
    quote_type_id: Any | None,
    language: str | None,
    currency: str | None,
    is_active: bool,
) -> dict[str, Any] | None:
    for row in rows:
        if bool(row.get("is_active")) is not is_active:
            continue
        if row.get("prospect_type") != prospect_type:
            continue
        if row.get("context_type") != context_type:
            continue
        if row.get("activity_family") != activity_family:
            continue
        if row.get("activity_id") != activity_id:
            continue
        if row.get("quote_type_id") != quote_type_id:
            continue
        if row.get("language") != language:
            continue
        if row.get("currency") != currency:
            continue
        return row
    return None


def _upsert_binding(
    connection: sa.Connection,
    rows: list[dict[str, Any]],
    *,
    prospect_type: str | None,
    context_type: str | None,
    activity_family: str | None,
    activity_id: Any | None,
    quote_type_id: Any | None,
    language: str | None,
    currency: str | None,
    quote_template_id: Any | None,
    terms_template_id: Any | None,
    priority: int,
    notes: str,
) -> None:
    existing = _find_binding(
        rows,
        prospect_type=prospect_type,
        context_type=context_type,
        activity_family=activity_family,
        activity_id=activity_id,
        quote_type_id=quote_type_id,
        language=language,
        currency=currency,
        is_active=True,
    )
    params = {
        "prospect_type": prospect_type,
        "context_type": context_type,
        "activity_family": activity_family,
        "activity_id": activity_id,
        "quote_type_id": quote_type_id,
        "language": language,
        "currency": currency,
        "quote_template_id": quote_template_id,
        "terms_template_id": terms_template_id,
        "priority": priority,
        "notes": notes,
    }
    if existing is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO quote_document_bindings (
                    prospect_type,
                    context_type,
                    activity_family,
                    activity_id,
                    quote_type_id,
                    language,
                    currency,
                    quote_template_id,
                    terms_template_id,
                    priority,
                    is_active,
                    notes,
                    created_at,
                    updated_at
                ) VALUES (
                    :prospect_type,
                    :context_type,
                    :activity_family,
                    :activity_id,
                    :quote_type_id,
                    :language,
                    :currency,
                    :quote_template_id,
                    :terms_template_id,
                    :priority,
                    true,
                    :notes,
                    now(),
                    now()
                )
                """
            ),
            params,
        )
        rows.append(
            {
                **params,
                "is_active": True,
            }
        )
        return
    connection.execute(
        sa.text(
            """
            UPDATE quote_document_bindings
            SET quote_template_id = :quote_template_id,
                terms_template_id = :terms_template_id,
                priority = :priority,
                notes = :notes,
                updated_at = now()
            WHERE id = :binding_id
            """
        ),
        {
            **params,
            "binding_id": existing["id"],
        },
    )


def upgrade() -> None:
    connection = op.get_bind()
    quote_type_id = _select_id(connection, "quote_types", "FORFAIT_2026_2027")
    if quote_type_id is None:
        return

    bindings = _load_bindings(connection)

    for index, item in enumerate(BINDING_DEFINITIONS, start=1):
        activity_id = _select_id(connection, "course_types", item["activity_code"])
        quote_template_id = _select_id(connection, "quote_templates", item["quote_template_code"])
        terms_template_id = _select_id(connection, "terms_templates", item["terms_template_code"])
        if activity_id is None or quote_template_id is None or terms_template_id is None:
            continue
        _upsert_binding(
            connection,
            bindings,
            prospect_type="child",
            context_type=None,
            activity_family=None,
            activity_id=activity_id,
            quote_type_id=quote_type_id,
            language="fr",
            currency="EUR",
            quote_template_id=quote_template_id,
            terms_template_id=terms_template_id,
            priority=10 + index,
            notes=item["notes"],
        )

    # Keep the historic collective child acquisition rule aligned with the dedicated CGV.
    child_terms_template_id = _select_id(connection, "terms_templates", "CGV_ENFANTS_GROUPE_2026_2027")
    child_quote_template_id = _select_id(connection, "quote_templates", "TEMPLATE_COURS_COLLECTIF_ENFANT")
    existing_child_acquisition = _find_binding(
        bindings,
        prospect_type="child",
        context_type="acquisition",
        activity_family="piano_class",
        activity_id=None,
        quote_type_id=quote_type_id,
        language="fr",
        currency="EUR",
        is_active=True,
    )
    if existing_child_acquisition is not None and child_quote_template_id is not None and child_terms_template_id is not None:
        connection.execute(
            sa.text(
                """
                UPDATE quote_document_bindings
                SET quote_template_id = :quote_template_id,
                    terms_template_id = :terms_template_id,
                    updated_at = now()
                WHERE id = :binding_id
                """
            ),
            {
                "binding_id": existing_child_acquisition["id"],
                "quote_template_id": child_quote_template_id,
                "terms_template_id": child_terms_template_id,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    quote_type_id = _select_id(connection, "quote_types", "FORFAIT_2026_2027")
    if quote_type_id is None:
        return
    activity_ids = [
        _select_id(connection, "course_types", item["activity_code"])
        for item in BINDING_DEFINITIONS
    ]
    connection.execute(
        sa.text(
            """
            DELETE FROM quote_document_bindings
            WHERE prospect_type = 'child'
              AND context_type IS NULL
              AND activity_family IS NULL
              AND quote_type_id = :quote_type_id
              AND language = 'fr'
              AND currency = 'EUR'
              AND activity_id = ANY(:activity_ids)
            """
        ),
        {
            "quote_type_id": quote_type_id,
            "activity_ids": [item for item in activity_ids if item is not None],
        },
    )
