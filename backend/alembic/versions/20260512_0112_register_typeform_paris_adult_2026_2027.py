"""register Paris adult 2026-2027 Typeform config

Revision ID: 20260512_0112
Revises: 20260512_0111
Create Date: 2026-05-12 14:35:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260512_0112"
down_revision: Union[str, None] = "20260512_0111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TYPEFORM_FORM_ID = "XXTa2w7l"
SOURCE_CODE = "typeform_paris_adult_2026_2027_multisite"
BASE_SOURCE_CODES = (
    "typeform_paris_teen_2026_2027_multisite",
    "typeform_paris_child_2026_2027_multisite",
)
SCHOOL_YEAR_LABEL = "2026-2027"
AUDIENCE_SEGMENT = "adult"
FORM_LABEL = "Paris Adultes 2026-2027"


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _base_config(connection: sa.Connection) -> dict[str, Any]:
    for source_code in BASE_SOURCE_CODES:
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


def _build_configuration_json() -> dict[str, Any]:
    field_mapping = {
        "adult_first_name": ["2d3d1cd8-5215-4292-888f-c8688d356cc3", "DIfgjh6bib3j", "First name"],
        "adult_last_name": ["0c0a414f-c030-4b18-b726-f46bd68ec3bd", "QbRDTTOUq7W0", "Last name"],
        "adult_phone": ["c8ba5893-faae-440d-bf57-b2f8c76f917c", "tok21xM7uLOJ", "Phone number"],
        "adult_email": ["30122284-9b96-4710-8ef9-85323f3b8cec", "PNl0gONEB6Q6", "Email"],
        "requested_course_mode": ["79fc9436-3876-45d8-a606-42aeb5b9c16e", "0tpf3U7hU3G8", "Type de cours souhaité"],
        "requested_location": ["d2e24218-ca13-4d0f-9aee-aed62064f0f8", "88lgCy4IMt6V", "Lieu du cours"],
        "requested_days": [
            "d8312f9d-94d0-4e65-92c9-38cde16df09a",
            "pKElYkUKtZa0",
            "ce9bbda8-002a-46f7-bd58-9827ab66d5e0",
            "8n1B6hHGETiB",
        ],
        "requested_times": [
            "77b96cdb-c971-4877-8b4a-eb8fdc063d43",
            "4SfVS0BoVTKu",
            "98d13168-f7e1-4e58-9e2e-1d3bef4d3be9",
            "IbnP6HsitgyZ",
            "f07b3d0b-6220-45a3-be3f-e709b08d4057",
            "2LV5QcfUvVVH",
            "d445628b-b9d1-4fcf-b581-02655ed51b15",
            "FwZRsTIYQJXl",
            "ab7b874d-705d-40ee-bcea-2cadc8fd58b3",
            "EJyntok40ln6",
        ],
        "requested_slot_preferences": [
            "d8312f9d-94d0-4e65-92c9-38cde16df09a",
            "ce9bbda8-002a-46f7-bd58-9827ab66d5e0",
            "77b96cdb-c971-4877-8b4a-eb8fdc063d43",
            "98d13168-f7e1-4e58-9e2e-1d3bef4d3be9",
            "f07b3d0b-6220-45a3-be3f-e709b08d4057",
            "d445628b-b9d1-4fcf-b581-02655ed51b15",
            "ab7b874d-705d-40ee-bcea-2cadc8fd58b3",
        ],
        "requested_formula_type": [
            "30e7993e-e094-441a-b91d-c7be27eb1855",
            "sz1kXkTn2Wjg",
            "91403673-42ba-4a07-b86a-a4a746d996ca",
            "GdAAy03bwRUl",
            "0c29e9b2-726c-42e4-821f-04f9276aca21",
            "0v0ZGM7IdkR4",
            "f152efb5-e514-4942-98b5-3b015ffe5e93",
            "Rtj59j0xx8ZH",
            "c3347eaa-a6ba-4e61-8f08-64d055d74c37",
            "a3U6j55qbN2J",
            "c1ab40e3-adad-4410-bffb-9e2238eed970",
            "B3wacsTEhZ15",
        ],
        "requested_payment_method": [
            "535e5e4f-d896-41d5-b50e-8a2b4e7f48da",
            "ySrV1EBM60Z6",
            "Mode de règlement souhaité pour l'année à venir",
        ],
        "requested_products": [
            "79fc9436-3876-45d8-a606-42aeb5b9c16e",
            "d2e24218-ca13-4d0f-9aee-aed62064f0f8",
            "91403673-42ba-4a07-b86a-a4a746d996ca",
            "0c29e9b2-726c-42e4-821f-04f9276aca21",
            "f152efb5-e514-4942-98b5-3b015ffe5e93",
            "c3347eaa-a6ba-4e61-8f08-64d055d74c37",
            "c1ab40e3-adad-4410-bffb-9e2238eed970",
            "30e7993e-e094-441a-b91d-c7be27eb1855",
            "22752d18-e883-4f90-a288-9e23326664c7",
        ],
        "parent_address_line_1": ["ec7d84dd-11cc-4be9-a83f-02ba534d22ae", "dItzJRP5jTDp", "Address"],
        "parent_address_line_2": ["5958df0f-5002-4bd6-a113-82aa86d34edf", "yY1CHwvfy1Em", "Address line 2"],
        "parent_city": ["d83e7e5f-ccea-492f-9def-330ef62ba6c4", "AAhMXqERXUke", "City/Town"],
        "parent_postal_code": ["a3481f83-b489-4b87-a8e6-03f79dd319fc", "lasmPPRKGEZv", "Zip/Post Code"],
        "parent_country": ["becf196f-056f-43cf-93fd-d2a7ed578167", "9hseirMjV7dN", "Country"],
        "notes": ["ebf82582-33fe-4051-ba9e-fdd8ffeaf2e2", "k0sqcwi3ORqn", "Autres points"],
    }
    field_labels = {
        "2d3d1cd8-5215-4292-888f-c8688d356cc3": "Prénom adulte",
        "0c0a414f-c030-4b18-b726-f46bd68ec3bd": "Nom adulte",
        "c8ba5893-faae-440d-bf57-b2f8c76f917c": "Téléphone",
        "30122284-9b96-4710-8ef9-85323f3b8cec": "Email",
        "bd675e72-8572-4088-8103-e3338c5927bd": "Société",
        "79fc9436-3876-45d8-a606-42aeb5b9c16e": "Type de cours souhaité",
        "d2e24218-ca13-4d0f-9aee-aed62064f0f8": "Lieu du cours",
        "91403673-42ba-4a07-b86a-a4a746d996ca": "Engagement domicile",
        "d8312f9d-94d0-4e65-92c9-38cde16df09a": "Jours domicile souhaités",
        "77b96cdb-c971-4877-8b4a-eb8fdc063d43": "Horaires domicile souhaités",
        "0c29e9b2-726c-42e4-821f-04f9276aca21": "Engagement vidéocall",
        "ce9bbda8-002a-46f7-bd58-9827ab66d5e0": "Jours vidéocall souhaités",
        "98d13168-f7e1-4e58-9e2e-1d3bef4d3be9": "Horaires vidéocall souhaités",
        "f152efb5-e514-4942-98b5-3b015ffe5e93": "Engagement particulier",
        "f07b3d0b-6220-45a3-be3f-e709b08d4057": "Créneaux particuliers souhaités",
        "c3347eaa-a6ba-4e61-8f08-64d055d74c37": "Engagement particulier",
        "d445628b-b9d1-4fcf-b581-02655ed51b15": "Créneaux particuliers souhaités",
        "c1ab40e3-adad-4410-bffb-9e2238eed970": "Engagement particulier",
        "ab7b874d-705d-40ee-bcea-2cadc8fd58b3": "Créneaux particuliers souhaités",
        "535e5e4f-d896-41d5-b50e-8a2b4e7f48da": "Mode de règlement souhaité",
        "30e7993e-e094-441a-b91d-c7be27eb1855": "Mode de cours collectif souhaité",
        "22752d18-e883-4f90-a288-9e23326664c7": "Date de démarrage souhaitée",
        "ec7d84dd-11cc-4be9-a83f-02ba534d22ae": "Adresse",
        "5958df0f-5002-4bd6-a113-82aa86d34edf": "Complément d'adresse",
        "d83e7e5f-ccea-492f-9def-330ef62ba6c4": "Ville",
        "59dc579c-e8cb-4156-9d6f-c50aa21d7152": "Région",
        "a3481f83-b489-4b87-a8e6-03f79dd319fc": "Code postal",
        "becf196f-056f-43cf-93fd-d2a7ed578167": "Pays",
        "ebf82582-33fe-4051-ba9e-fdd8ffeaf2e2": "Autres points",
    }
    line_templates = [
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_COLLECTIF_ADULTE_2342BD",
            "quantity": "1",
            "when": {"requested_course_mode": ["Cours collectif"]},
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_DOMICILE_523319",
            "quantity": "1",
            "unit_price_ttc": "90.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_location": ["Domicile"],
                "requested_formula_type": ["10 cours renouvelables - 90€/h"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_DOMICILE_523319",
            "quantity": "1",
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_location": ["Domicile"],
                "requested_formula_type": ["Année scolaire - 80€/h"],
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
                "requested_location": ["Videocall", "Vidéo Call", "Video Call"],
                "requested_formula_type": ["10 cours renouvelables - 40€/h"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_5DFFD9",
            "quantity": "1",
            "unit_price_ttc": "35.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_location": ["Videocall", "Vidéo Call", "Video Call"],
                "requested_formula_type": ["Année scolaire - 35€/h"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_5DFFD9",
            "quantity": "1",
            "unit_price_ttc": "70.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_formula_type": ["Engagement 5 cours - 70€/h"],
            },
        },
        {
            "kind": "activity",
            "activity_code": "ACT_COURS_PARTICULIER_5DFFD9",
            "quantity": "1",
            "unit_price_ttc": "60.00",
            "price_mode": "override",
            "allow_price_override": True,
            "when": {
                "requested_course_mode": ["Cours particulier"],
                "requested_formula_type": ["Engagement sur année scolaire - 60€/h"],
            },
        },
    ]
    return {
        "label": FORM_LABEL,
        "field_mapping": field_mapping,
        "field_labels": field_labels,
        "line_templates": line_templates,
        "default_vat_rate": "20.00",
        "default_course_mode": "onsite",
        "default_pre_registration_deposit_enabled": True,
        "default_pre_registration_deposit_amount_ttc": "200.00",
        "location_overrides": [
            {
                "match_values": ["Domicile", "A domicile", "À domicile"],
                "location_code": "DOMICILE",
            },
            {
                "match_values": ["Videocall", "Vidéo Call", "Video Call", "Online", "En ligne"],
                "location_code": "ONLINE",
            },
            {
                "match_values": ["Ecole - Paris 16e - Scheffer", "Paris 16 - Rue Scheffer", "Rue Scheffer"],
                "location_code": "SCHEFFER",
            },
            {
                "match_values": ["Ecole - Paris 16e - Pompe", "Paris 16 - Rue de la Pompe", "Rue de la Pompe"],
                "location_code": "POMPE",
            },
            {
                "match_values": ["Ecole - Paris 1er - Richelieu", "Paris 01 - Rue Richelieu", "Rue de Richelieu", "Richelieu"],
                "location_code": "RICHELIEU",
            },
            {
                "match_values": ["Ecole - Paris 6e - Assas", "Paris 06 - Rue d'Assas", "Rue d'Assas", "Rue d Assas"],
                "location_code": "ASSAS",
            },
        ],
    }


def upgrade() -> None:
    connection = op.get_bind()
    base_config = _base_config(connection)
    default_quote_type_id, default_quote_type_name = _first_active_quote_type(connection)

    quote_type_id = base_config.get("default_quote_type_id") or default_quote_type_id
    quote_type_name = _text(base_config.get("default_quote_type")) or default_quote_type_name
    catalog_id = base_config.get("default_pricing_catalog_id") or _first_active_id(connection, "pricing_catalogs")
    payment_plan_id = base_config.get("default_payment_plan_id") or _first_active_id(connection, "payment_plans")
    legal_entity_id = base_config.get("default_legal_entity_id") or _first_active_id(connection, "legal_entities")
    location_id = _location_id(connection, "SCHEFFER") or base_config.get("default_location_id")
    configuration_json = _build_configuration_json()

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

    params = {
        "typeform_form_id": TYPEFORM_FORM_ID,
        "source_code": SOURCE_CODE,
        "location_code": "PARIS_MULTI_SITE",
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
