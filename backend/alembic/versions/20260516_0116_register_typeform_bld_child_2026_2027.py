"""register Bar-le-Duc child 2026-2027 Typeform config

Revision ID: 20260516_0116
Revises: 20260516_0115
Create Date: 2026-05-16 15:45:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0116"
down_revision: Union[str, None] = "20260516_0115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TYPEFORM_FORM_ID = "G9u3xvbq"
SOURCE_CODE = "typeform_bld_child_2026_2027"
SCHOOL_YEAR_LABEL = "2026-2027"
AUDIENCE_SEGMENT = "child"
FORM_LABEL = "Bar-le-Duc Enfants 2026-2027"


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
        "typeform_paris_child_2026_2027_multisite",
        "typeform_paris_teen_2026_2027_multisite",
        "typeform_paris_adult_2026_2027_multisite",
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
        "parent_first_name": ["77d16e29-8e2d-4867-aa7c-6cc2f6074a62", "qmBlUlA9XMO1"],
        "parent_last_name": ["73f75eee-a672-4dac-a55e-92ac04ac25d3", "AswXIZsbprkp"],
        "parent_phone": ["3b1048c2-8cd1-45e5-aa25-4605f77cba20", "WemFEoLBLCfg"],
        "parent_email": ["cd68bc34-56dd-4ac9-90ed-cdb079b9d326", "wwZMSEUL9FKT"],
        "child_first_name": ["990536e3-2dbd-4dc6-aa83-38b3e5d0c3b3", "9DWagra6QUSO"],
        "child_last_name": ["cc910847-903d-4e99-ad87-7ddcfa3376a4", "1rSy4mKm5FzS"],
        "child_birth_date": ["25c23245-2a27-491c-aca8-250e2813e68c", "K2HfGcFB6GPZ"],
        "requested_location": ["29b0a590-74e2-486c-af59-493e6f83ff67", "IwHJg6AeDOQh"],
        "requested_course_mode": ["73c6edff-7d0f-4baa-84fc-56ddd8b5c4b3", "H1LopXWsHma8"],
        "requested_days": ["3cabba30-1103-440a-b4b9-3dac258fdef3", "bJJJmkeJGVoM"],
        "requested_times": ["3cabba30-1103-440a-b4b9-3dac258fdef3", "bJJJmkeJGVoM"],
        "requested_slot_preferences": ["3cabba30-1103-440a-b4b9-3dac258fdef3", "bJJJmkeJGVoM"],
        "estimated_solfege_level": ["99a98c03-9418-4bca-8028-5ce334f5a696", "pAHENgKA6Qqu"],
        "requested_products": [
            "73c6edff-7d0f-4baa-84fc-56ddd8b5c4b3",
            "H1LopXWsHma8",
            "f2bc039a-9456-46f0-b860-fd81fa342aca",
            "Q7leRDfe4wTM",
        ],
        "requested_payment_method": ["f152efb5-e514-4942-98b5-3b015ffe5e93", "W9ZnW7AdVH0G"],
        "parent_address_line_1": ["d84f87be-fe9c-43d5-a551-0fc4d8aabc66", "irKBXhUR5Ti2", "Address"],
        "parent_city": ["8c9d688e-d1d1-4e8b-8eb2-ab2cd6fbcd14", "7Fyg54gNOgGe", "City/Town"],
        "parent_postal_code": ["a57c3db2-7d59-4f11-96b1-791a72b3fa2e", "BOIx8tD4Z4r7", "Zip/Post Code"],
        "parent_country": ["8419db4d-e71f-4926-a222-58ac21279e2d", "9OMEruKHdKJp", "Country"],
    }
    field_labels = {
        "77d16e29-8e2d-4867-aa7c-6cc2f6074a62": "Prenom parent",
        "73f75eee-a672-4dac-a55e-92ac04ac25d3": "Nom parent",
        "3b1048c2-8cd1-45e5-aa25-4605f77cba20": "Telephone parent",
        "cd68bc34-56dd-4ac9-90ed-cdb079b9d326": "Email parent",
        "990536e3-2dbd-4dc6-aa83-38b3e5d0c3b3": "Prenom enfant",
        "cc910847-903d-4e99-ad87-7ddcfa3376a4": "Nom enfant",
        "25c23245-2a27-491c-aca8-250e2813e68c": "Date de naissance enfant",
        "29b0a590-74e2-486c-af59-493e6f83ff67": "Lieu du cours souhaite",
        "73c6edff-7d0f-4baa-84fc-56ddd8b5c4b3": "Mode de cours a l'ecole souhaite",
        "3cabba30-1103-440a-b4b9-3dac258fdef3": "Cours en presentiel a l'ecole",
        "99a98c03-9418-4bca-8028-5ce334f5a696": "Estimation du niveau de solfege",
        "f2bc039a-9456-46f0-b860-fd81fa342aca": "2e cours collectif",
        "f152efb5-e514-4942-98b5-3b015ffe5e93": "Mode de reglement souhaite",
        "d84f87be-fe9c-43d5-a551-0fc4d8aabc66": "Adresse",
        "8c9d688e-d1d1-4e8b-8eb2-ab2cd6fbcd14": "Ville",
        "a57c3db2-7d59-4f11-96b1-791a72b3fa2e": "Code postal",
        "8419db4d-e71f-4926-a222-58ac21279e2d": "Pays",
    }
    line_templates = [
        {
            "kind": "activity",
            "activity_code": "PIANO_GROUP_ONSITE_1H",
            "quantity": "1",
            "unit_price_ttc": "22.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": [
                    "Cours collectif",
                    "Cours collectif de 1h",
                    "Cours collectif de 1h (22€/h)",
                    "Cours collectif de 1h  (22€/h)",
                ]
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
                "requested_course_mode": [
                    "Cours particulier",
                    "Cours particulier de 1h",
                    "Cours particulier de 1h (40€/h)",
                ]
            },
        },
    ]
    return {
        "label": FORM_LABEL,
        "field_mapping": field_mapping,
        "field_labels": field_labels,
        "line_templates": line_templates,
        "default_quote_template_codes": [
            "TEMPLATE_BAR_LE_DUC_ENFANT",
            "TEMPLATE_BAR_LE_DUC_ENFANTS",
            "TEMPLATE_BLD_ENFANT",
            "TEMPLATE_BLD_ENFANTS",
            "TEMPLATE_COURS_COLLECTIF_ENFANT_BAR_LE_DUC",
            "TEMPLATE_COURS_COLLECTIF_ENFANT_BLD",
        ],
        "default_terms_template_codes": [
            "CGV_BAR_LE_DUC_ENFANTS_2026_2027",
            "CGV_BLD_ENFANTS_2026_2027",
            "CGV_ENFANTS_BAR_LE_DUC_2026_2027",
            "CGV_ENFANTS_BLD_2026_2027",
        ],
        "default_vat_rate": "20.00",
        "default_course_mode": "onsite",
        "default_pre_registration_deposit_enabled": True,
        "default_pre_registration_deposit_amount_ttc": "200.00",
        "location_overrides": [
            {
                "match_values": ["Bar-le-Duc", "Bar le Duc", "BAR_LE_DUC"],
                "location_code": "BAR_LE_DUC",
            },
            {
                "match_values": ["Vidéo Call", "Video Call", "Videocall", "Online", "En ligne"],
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
