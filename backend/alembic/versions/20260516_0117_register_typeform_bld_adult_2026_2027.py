"""register Bar-le-Duc adult 2026-2027 Typeform config

Revision ID: 20260516_0117
Revises: 20260516_0116
Create Date: 2026-05-16 16:05:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0117"
down_revision: Union[str, None] = "20260516_0116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TYPEFORM_FORM_ID = "reOoXM3G"
SOURCE_CODE = "typeform_bld_adult_2026_2027"
SCHOOL_YEAR_LABEL = "2026-2027"
AUDIENCE_SEGMENT = "adult"
FORM_LABEL = "Bar-le-Duc Adultes 2026-2027"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_active_id(connection: sa.Connection, table_name: str, *, active_column: str = "is_active") -> Any | None:
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


def _location_id(connection: sa.Connection, code: str) -> Any | None:
    return connection.execute(
        sa.text(
            """
            SELECT id
            FROM locations
            WHERE active IS TRUE
              AND code = :code
            LIMIT 1
            """
        ),
        {"code": code},
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
    return row["id"], _text(row["name"]) or None


def _base_config(connection: sa.Connection) -> dict[str, Any]:
    for source_code in (
        "typeform_paris_adult_2026_2027_multisite",
        "typeform_bld_child_2026_2027",
        "typeform_paris_child_2026_2027_multisite",
    ):
        row = connection.execute(
            sa.text(
                """
                SELECT *
                FROM typeform_form_configs
                WHERE source_code = :source_code
                LIMIT 1
                """
            ),
            {"source_code": source_code},
        ).mappings().first()
        if row is not None:
            return dict(row)
    return {}


def _build_configuration_json() -> dict[str, Any]:
    field_mapping = {
        "adult_first_name": ["2d3d1cd8-5215-4292-888f-c8688d356cc3", "ZN78ePa7AnX6", "First name"],
        "adult_last_name": ["0c0a414f-c030-4b18-b726-f46bd68ec3bd", "sYKCB2fi6fdH", "Last name"],
        "adult_phone": ["c8ba5893-faae-440d-bf57-b2f8c76f917c", "BO1ssvO3bLJL", "Phone number"],
        "adult_email": ["30122284-9b96-4710-8ef9-85323f3b8cec", "hmdaAxufGIRz", "Email"],
        "requested_location": ["d2e24218-ca13-4d0f-9aee-aed62064f0f8", "RSRrFMDX3r4x", "Lieu du cours"],
        "requested_course_mode": ["79fc9436-3876-45d8-a606-42aeb5b9c16e", "lPTgRaXnUe5o", "Type de cours souhaité"],
        "requested_days": ["cd2aae75-5f1a-41da-8d11-bb06317aa9ec", "ABQSpJCI7SmU"],
        "requested_times": ["cd2aae75-5f1a-41da-8d11-bb06317aa9ec", "ABQSpJCI7SmU"],
        "requested_slot_preferences": ["cd2aae75-5f1a-41da-8d11-bb06317aa9ec", "ABQSpJCI7SmU"],
        "requested_formula_type": [
            "30e7993e-e094-441a-b91d-c7be27eb1855",
            "uWCHtvziDdRS",
            "f152efb5-e514-4942-98b5-3b015ffe5e93",
            "qC2pwm0mhUzu",
        ],
        "requested_payment_method": [
            "535e5e4f-d896-41d5-b50e-8a2b4e7f48da",
            "k9dOy8nuYY7K",
            "Mode de règlement souhaité pour l'année à venir",
        ],
        "requested_products": [
            "79fc9436-3876-45d8-a606-42aeb5b9c16e",
            "lPTgRaXnUe5o",
            "30e7993e-e094-441a-b91d-c7be27eb1855",
            "uWCHtvziDdRS",
            "f152efb5-e514-4942-98b5-3b015ffe5e93",
            "qC2pwm0mhUzu",
            "22752d18-e883-4f90-a288-9e23326664c7",
            "yMLytJiz0tvA",
        ],
        "referral_referrer_name": ["70497518-c91a-43c7-9920-6e90e8830e86", "Lb81oigIiqU6"],
        "parent_address_line_1": ["ec7d84dd-11cc-4be9-a83f-02ba534d22ae", "nZqbjdldKlGl", "Address"],
        "parent_address_line_2": ["5958df0f-5002-4bd6-a113-82aa86d34edf", "r9rqOu76ZxaF", "Address line 2"],
        "parent_city": ["d83e7e5f-ccea-492f-9def-330ef62ba6c4", "MggGi7xdaaab", "City/Town"],
        "parent_postal_code": ["a3481f83-b489-4b87-a8e6-03f79dd319fc", "yMQwiMEkLC1g", "Zip/Post Code"],
        "parent_country": ["becf196f-056f-43cf-93fd-d2a7ed578167", "kJpVBNj2XTcx", "Country"],
        "notes": ["ebf82582-33fe-4051-ba9e-fdd8ffeaf2e2", "Fy01o3nzrQxK", "Autres points"],
    }
    field_labels = {
        "2d3d1cd8-5215-4292-888f-c8688d356cc3": "Prenom adulte",
        "0c0a414f-c030-4b18-b726-f46bd68ec3bd": "Nom adulte",
        "c8ba5893-faae-440d-bf57-b2f8c76f917c": "Telephone",
        "30122284-9b96-4710-8ef9-85323f3b8cec": "Email",
        "bd675e72-8572-4088-8103-e3338c5927bd": "Societe",
        "70497518-c91a-43c7-9920-6e90e8830e86": "Parrainage",
        "d2e24218-ca13-4d0f-9aee-aed62064f0f8": "Lieu du cours",
        "79fc9436-3876-45d8-a606-42aeb5b9c16e": "Type de cours souhaite",
        "f152efb5-e514-4942-98b5-3b015ffe5e93": "Engagement cours particulier",
        "f07b3d0b-6220-45a3-be3f-e709b08d4057": "Creneaux particuliers souhaites",
        "30e7993e-e094-441a-b91d-c7be27eb1855": "Mode de cours collectif souhaite",
        "cd2aae75-5f1a-41da-8d11-bb06317aa9ec": "Creneaux collectif",
        "535e5e4f-d896-41d5-b50e-8a2b4e7f48da": "Mode de reglement souhaite",
        "22752d18-e883-4f90-a288-9e23326664c7": "Date de demarrage souhaitee",
        "ec7d84dd-11cc-4be9-a83f-02ba534d22ae": "Adresse",
        "5958df0f-5002-4bd6-a113-82aa86d34edf": "Complement d'adresse",
        "d83e7e5f-ccea-492f-9def-330ef62ba6c4": "Ville",
        "59dc579c-e8cb-4156-9d6f-c50aa21d7152": "Region",
        "a3481f83-b489-4b87-a8e6-03f79dd319fc": "Code postal",
        "becf196f-056f-43cf-93fd-d2a7ed578167": "Pays",
        "ebf82582-33fe-4051-ba9e-fdd8ffeaf2e2": "Autres points",
    }
    line_templates = [
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_COLLECTIF_ADULTE_2342BD",
            "quantity": "10",
            "unit_price_ttc": "26.00",
            "price_mode": "override",
            "allow_price_override": True,
            "commitment_kind": "ten_course_pack",
            "planning_session_limit": 10,
            "when": {
                "requested_course_mode": ["Cours collectif"],
                "requested_products": ["Engagement sur 10 cours - 26€ / cours"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_COLLECTIF_ADULTE_2342BD",
            "quantity": "1",
            "unit_price_ttc": "22.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": ["Cours collectif"],
                "requested_products": ["Engagement annuel - 22€ / cours"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_5DFFD9",
            "quantity": "10",
            "unit_price_ttc": "45.00",
            "price_mode": "override",
            "allow_price_override": True,
            "commitment_kind": "ten_course_pack",
            "planning_session_limit": 10,
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_products": ["Engagement 10 cours - 45€/h"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_5DFFD9",
            "quantity": "1",
            "unit_price_ttc": "40.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_products": ["Engagement sur année scolaire - 40€/h"],
            },
        },
    ]
    return {
        "label": FORM_LABEL,
        "field_mapping": field_mapping,
        "field_labels": field_labels,
        "line_templates": line_templates,
        "default_quote_template_codes": [
            "TEMPLATE_BAR_LE_DUC_ADULTE",
            "TEMPLATE_BAR_LE_DUC_ADULTES",
            "TEMPLATE_BLD_ADULTE",
            "TEMPLATE_BLD_ADULTES",
            "TEMPLATE_COURS_ADULTE_BAR_LE_DUC",
            "TEMPLATE_COURS_ADULTES_BLD",
        ],
        "default_terms_template_codes": [
            "CGV_BAR_LE_DUC_ADULTES_2026_2027",
            "CGV_BLD_ADULTES_2026_2027",
            "CGV_ADULTES_BAR_LE_DUC_2026_2027",
            "CGV_ADULTES_BLD_2026_2027",
        ],
        "default_vat_rate": "20.00",
        "default_course_mode": "onsite",
        "default_pre_registration_deposit_enabled": True,
        "default_pre_registration_deposit_amount_ttc": "200.00",
        "location_overrides": [
            {
                "match_values": ["Ecole à Bar-le-Duc", "Ecole a Bar-le-Duc", "Bar-le-Duc", "Bar le Duc", "BAR_LE_DUC"],
                "location_code": "BAR_LE_DUC",
            },
            {
                "match_values": ["Videocall", "Vidéo Call", "Video Call", "Online", "En ligne"],
                "location_code": "ONLINE",
            },
        ],
    }


def upgrade() -> None:
    connection = op.get_bind()
    base_config = _base_config(connection)
    default_quote_type_id, default_quote_type_name = _first_active_quote_type(connection)

    params = {
        "typeform_form_id": TYPEFORM_FORM_ID,
        "source_code": SOURCE_CODE,
        "location_code": "BAR_LE_DUC",
        "school_year_label": SCHOOL_YEAR_LABEL,
        "audience_segment": AUDIENCE_SEGMENT,
        "default_quote_type": _text(base_config.get("default_quote_type")) or default_quote_type_name,
        "default_quote_type_id": base_config.get("default_quote_type_id") or default_quote_type_id,
        "default_pricing_catalog_id": base_config.get("default_pricing_catalog_id")
        or _first_active_id(connection, "pricing_catalogs"),
        "default_payment_plan_id": base_config.get("default_payment_plan_id")
        or _first_active_id(connection, "payment_plans"),
        "default_legal_entity_id": base_config.get("default_legal_entity_id")
        or _first_active_id(connection, "legal_entities"),
        "default_location_id": _location_id(connection, "BAR_LE_DUC") or base_config.get("default_location_id"),
        "configuration_json": json.dumps(_build_configuration_json(), ensure_ascii=True),
    }

    existing = connection.execute(
        sa.text(
            """
            SELECT id
            FROM typeform_form_configs
            WHERE typeform_form_id = :typeform_form_id
               OR source_code = :source_code
            LIMIT 1
            """
        ),
        {"typeform_form_id": TYPEFORM_FORM_ID, "source_code": SOURCE_CODE},
    ).mappings().first()

    if existing is None:
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
            {**params, "id": existing["id"]},
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
        {"typeform_form_id": TYPEFORM_FORM_ID, "source_code": SOURCE_CODE},
    )
