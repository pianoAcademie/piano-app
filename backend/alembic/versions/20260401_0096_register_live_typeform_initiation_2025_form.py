"""register live Typeform initiation 2025-2026 form config

Revision ID: 20260401_0096
Revises: 20260331_0095
Create Date: 2026-04-01 11:45:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260401_0096"
down_revision: Union[str, None] = "20260331_0095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TYPEFORM_FORM_ID = "zq6MdOTY"
SOURCE_CODE = "TYPEFORM_PARIS_INITIATION_2025_2026_RICHELIEU"
LEGACY_INITIATION_FORM_ID = "CQSkTglB"
LEGACY_INITIATION_SOURCE_CODE = "REAL_2026_PARIS_INITIATION_EXISTING_CATALOG"
PREFERRED_ACTIVITY_CODE = "ACT_EVEIL_MUSICAL_98E099"
PREFERRED_LOCATION_CODE = "RICHELIEU"
SCHOOL_YEAR_LABEL = "2025-2026"
AUDIENCE_SEGMENT = "eveil"
FORM_LABEL = "Initiation 2025 - 2026"


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def _mapping_with_fallback(
    base: dict[str, Any],
    key: str,
    fallback_values: list[str],
) -> None:
    existing = base.get(key)
    if isinstance(existing, list) and existing:
        merged: list[str] = []
        seen: set[str] = set()
        for raw in [*existing, *fallback_values]:
            text_value = str(raw).strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            merged.append(text_value)
        base[key] = merged
        return
    base[key] = fallback_values


def _pick_base_config(connection: sa.Connection) -> dict[str, Any] | None:
    candidates = [
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM typeform_form_configs
                WHERE typeform_form_id = :form_id
                LIMIT 1
                """
            ),
            {"form_id": LEGACY_INITIATION_FORM_ID},
        ).mappings().first(),
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM typeform_form_configs
                WHERE source_code = :source_code
                LIMIT 1
                """
            ),
            {"source_code": LEGACY_INITIATION_SOURCE_CODE},
        ).mappings().first(),
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM typeform_form_configs
                WHERE audience_segment = :segment
                  AND lower(coalesce(configuration_json->>'label', '')) LIKE '%initiation%'
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"segment": AUDIENCE_SEGMENT},
        ).mappings().first(),
        connection.execute(
            sa.text(
                """
                SELECT *
                FROM typeform_form_configs
                WHERE audience_segment = :segment
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"segment": AUDIENCE_SEGMENT},
        ).mappings().first(),
    ]
    for row in candidates:
        if row is not None:
            return dict(row)
    return None


def _first_active_id(connection: sa.Connection, table_name: str, active_column: str = "is_active") -> Any | None:
    return connection.execute(
        sa.text(
            f"""
            SELECT id
            FROM {table_name}
            WHERE {active_column} IS TRUE
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).scalar()


def _first_active_quote_type(connection: sa.Connection) -> tuple[Any | None, str | None]:
    row = connection.execute(
        sa.text(
            """
            SELECT id, name
            FROM quote_types
            WHERE is_active IS TRUE
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).mappings().first()
    if row is None:
        return None, None
    return row["id"], str(row["name"])


def _preferred_activity_code(connection: sa.Connection) -> str | None:
    direct = connection.execute(
        sa.text(
            """
            SELECT code
            FROM course_types
            WHERE active IS TRUE
              AND code = :code
            LIMIT 1
            """
        ),
        {"code": PREFERRED_ACTIVITY_CODE},
    ).scalar()
    if direct:
        return str(direct)

    for pattern in ("%initiation%", "%eveil%"):
        row = connection.execute(
            sa.text(
                """
                SELECT code
                FROM course_types
                WHERE active IS TRUE
                  AND lower(name) LIKE :pattern
                ORDER BY name ASC
                LIMIT 1
                """
            ),
            {"pattern": pattern},
        ).scalar()
        if row:
            return str(row)
    return None


def _build_configuration_json(base_config: dict[str, Any], activity_code: str | None) -> dict[str, Any]:
    configuration_json = _json_object(base_config.get("configuration_json"))
    field_mapping = _json_object(configuration_json.get("field_mapping"))
    field_labels = _json_object(configuration_json.get("field_labels"))

    _mapping_with_fallback(field_mapping, "parent_first_name", ["parent_first_name", "prenom_parent"])
    _mapping_with_fallback(field_mapping, "parent_last_name", ["parent_last_name", "nom_parent"])
    _mapping_with_fallback(field_mapping, "parent_email", ["parent_email", "email_parent"])
    _mapping_with_fallback(field_mapping, "parent_phone", ["parent_phone", "telephone_parent"])
    _mapping_with_fallback(field_mapping, "parent_address_line_1", ["parent_address_line_1", "adresse_parent", "Address"])
    _mapping_with_fallback(field_mapping, "parent_address_line_2", ["parent_address_line_2", "adresse_parent_ligne_2", "Address line 2"])
    _mapping_with_fallback(field_mapping, "parent_city", ["parent_city", "ville_parent", "City/Town"])
    _mapping_with_fallback(field_mapping, "parent_postal_code", ["parent_postal_code", "code_postal_parent", "Zip/Post Code"])
    _mapping_with_fallback(field_mapping, "parent_country", ["parent_country", "pays_parent", "Country"])
    _mapping_with_fallback(field_mapping, "child_first_name", ["child_first_name", "prenom_enfant"])
    _mapping_with_fallback(field_mapping, "child_last_name", ["child_last_name", "nom_enfant"])
    _mapping_with_fallback(field_mapping, "child_birth_date", ["child_birth_date", "date_naissance_enfant"])
    _mapping_with_fallback(field_mapping, "requested_location", ["requested_location", "lieu_souhaite", "site_souhaite"])
    _mapping_with_fallback(field_mapping, "requested_days", ["requested_days", "jours_souhaites"])
    _mapping_with_fallback(field_mapping, "requested_times", ["requested_times", "horaires_souhaites"])
    _mapping_with_fallback(field_mapping, "requested_formula_type", ["requested_formula_type", "formule_souhaitee"])
    _mapping_with_fallback(
        field_mapping,
        "requested_payment_method",
        ["requested_payment_method", "mode_reglement_souhaite", "Mode de règlement souhaité pour l'année à venir"],
    )
    _mapping_with_fallback(field_mapping, "notes", ["notes", "commentaires"])

    field_labels.update(
        {
            "parent_first_name": "Prenom parent",
            "parent_last_name": "Nom parent",
            "parent_email": "Email parent",
            "parent_phone": "Telephone parent",
            "parent_address_line_1": "Adresse",
            "parent_address_line_2": "Complement adresse",
            "parent_city": "Ville",
            "parent_postal_code": "Code postal",
            "parent_country": "Pays",
            "child_first_name": "Prenom enfant",
            "child_last_name": "Nom enfant",
            "child_birth_date": "Date de naissance enfant",
            "requested_location": "Lieu souhaite",
            "requested_days": "Jours souhaites",
            "requested_times": "Horaires souhaites",
            "requested_formula_type": "Formule souhaitee",
            "requested_payment_method": "Mode de reglement souhaite",
            "notes": "Commentaires",
            "prenom_parent": "Prenom parent",
            "nom_parent": "Nom parent",
            "email_parent": "Email parent",
            "telephone_parent": "Telephone parent",
            "adresse_parent": "Adresse",
            "adresse_parent_ligne_2": "Complement adresse",
            "ville_parent": "Ville",
            "code_postal_parent": "Code postal",
            "pays_parent": "Pays",
            "Address": "Adresse",
            "Address line 2": "Complement adresse",
            "City/Town": "Ville",
            "Zip/Post Code": "Code postal",
            "Country": "Pays",
            "prenom_enfant": "Prenom enfant",
            "nom_enfant": "Nom enfant",
            "date_naissance_enfant": "Date de naissance enfant",
            "jours_souhaites": "Jours souhaites",
            "horaires_souhaites": "Horaires souhaites",
            "formule_souhaitee": "Formule souhaitee",
            "mode_reglement_souhaite": "Mode de reglement souhaite",
            "Mode de règlement souhaité pour l'année à venir": "Mode de reglement souhaite",
            "commentaires": "Commentaires",
        }
    )

    line_templates = configuration_json.get("line_templates")
    if activity_code:
        line_templates = [{"kind": "activity", "activity_code": activity_code, "quantity": "1"}]
    elif not isinstance(line_templates, list):
        line_templates = []

    configuration_json.update(
        {
            "label": FORM_LABEL,
            "default_vat_rate": str(configuration_json.get("default_vat_rate") or "20.00"),
            "default_course_mode": str(configuration_json.get("default_course_mode") or "onsite"),
            "field_mapping": field_mapping,
            "field_labels": field_labels,
            "line_templates": line_templates,
            "location_overrides": [
                {
                    "location_code": PREFERRED_LOCATION_CODE,
                    "match_values": [
                        "paris_richelieu",
                        "Paris 1 - Rue de Richelieu",
                        "Paris 01 - Rue de Richelieu",
                        "Richelieu",
                        "Rue de Richelieu",
                    ],
                }
            ],
        }
    )
    return configuration_json


def upgrade() -> None:
    connection = op.get_bind()
    base_config = _pick_base_config(connection) or {}
    preferred_activity_code = _preferred_activity_code(connection)

    default_quote_type_id, default_quote_type_name = _first_active_quote_type(connection)
    quote_type_id = base_config.get("default_quote_type_id") or default_quote_type_id
    quote_type_name = (
        str(base_config.get("default_quote_type")).strip()
        if base_config.get("default_quote_type")
        else default_quote_type_name
    )
    catalog_id = base_config.get("default_pricing_catalog_id") or _first_active_id(connection, "pricing_catalogs")
    payment_plan_id = base_config.get("default_payment_plan_id") or _first_active_id(connection, "payment_plans")
    legal_entity_id = base_config.get("default_legal_entity_id") or _first_active_id(connection, "legal_entities")
    location_id = base_config.get("default_location_id") or connection.execute(
        sa.text(
            """
            SELECT id
            FROM locations
            WHERE active IS TRUE
              AND code = :code
            LIMIT 1
            """
        ),
        {"code": PREFERRED_LOCATION_CODE},
    ).scalar()

    configuration_json = _build_configuration_json(base_config, preferred_activity_code)

    existing_row = connection.execute(
        sa.text(
            """
            SELECT id
            FROM typeform_form_configs
            WHERE typeform_form_id = :typeform_form_id
               OR source_code = :source_code
            LIMIT 1
            """
        ),
        {
            "typeform_form_id": TYPEFORM_FORM_ID,
            "source_code": SOURCE_CODE,
        },
    ).mappings().first()

    params = {
        "typeform_form_id": TYPEFORM_FORM_ID,
        "source_code": SOURCE_CODE,
        "location_code": "paris_richelieu",
        "school_year_label": SCHOOL_YEAR_LABEL,
        "audience_segment": AUDIENCE_SEGMENT,
        "default_quote_type": quote_type_name,
        "default_quote_type_id": quote_type_id,
        "default_pricing_catalog_id": catalog_id,
        "default_payment_plan_id": payment_plan_id,
        "default_legal_entity_id": legal_entity_id,
        "default_location_id": location_id,
        "configuration_json": json.dumps(configuration_json, ensure_ascii=True),
    }

    if existing_row is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO typeform_form_configs (
                    typeform_form_id,
                    source_code,
                    location_code,
                    school_year_label,
                    audience_segment,
                    default_quote_type,
                    default_quote_type_id,
                    default_pricing_catalog_id,
                    default_payment_plan_id,
                    default_legal_entity_id,
                    default_location_id,
                    default_language,
                    configuration_json,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (
                    :typeform_form_id,
                    :source_code,
                    :location_code,
                    :school_year_label,
                    :audience_segment,
                    :default_quote_type,
                    :default_quote_type_id,
                    :default_pricing_catalog_id,
                    :default_payment_plan_id,
                    :default_legal_entity_id,
                    :default_location_id,
                    'fr',
                    CAST(:configuration_json AS jsonb),
                    true,
                    now(),
                    now()
                )
                """
            ),
            params,
        )
    else:
        connection.execute(
            sa.text(
                """
                UPDATE typeform_form_configs
                SET typeform_form_id = :typeform_form_id,
                    source_code = :source_code,
                    location_code = :location_code,
                    school_year_label = :school_year_label,
                    audience_segment = :audience_segment,
                    default_quote_type = :default_quote_type,
                    default_quote_type_id = :default_quote_type_id,
                    default_pricing_catalog_id = :default_pricing_catalog_id,
                    default_payment_plan_id = :default_payment_plan_id,
                    default_legal_entity_id = :default_legal_entity_id,
                    default_location_id = :default_location_id,
                    default_language = 'fr',
                    configuration_json = CAST(:configuration_json AS jsonb),
                    is_active = true,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                **params,
                "id": existing_row["id"],
            },
        )

    connection.execute(
        sa.text(
            """
            UPDATE typeform_intakes
            SET form_config_id = (
                    SELECT id
                    FROM typeform_form_configs
                    WHERE typeform_form_id = :typeform_form_id
                    LIMIT 1
                ),
                updated_at = now()
            WHERE source_form_id = :typeform_form_id
            """
        ),
        {"typeform_form_id": TYPEFORM_FORM_ID},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE typeform_intakes
            SET form_config_id = NULL,
                updated_at = now()
            WHERE source_form_id = :typeform_form_id
            """
        ),
        {"typeform_form_id": TYPEFORM_FORM_ID},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM typeform_form_configs
            WHERE typeform_form_id = :typeform_form_id
               OR source_code = :source_code
            """
        ),
        {
            "typeform_form_id": TYPEFORM_FORM_ID,
            "source_code": SOURCE_CODE,
        },
    )
