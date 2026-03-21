from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.quotes import _ensure_public_token, _load_quote
from app.api.routes.typeform_intakes import (
    _answer,
    _demo_payload,
    _ingest_typeform_payload,
    _refresh_intake_analysis,
    create_draft_quote_from_typeform_intake,
)
from app.db.session import SessionLocal
from app.models.catalog import CourseType
from app.models.typeform_intake import TypeformFormConfig, TypeformIntake
from app.models.user import User, UserRole

LOCAL_FRONTEND_BASE = "http://localhost:3000"
SOURCE_FORM_ID = "tf_local_eveil_clean_2026_pompe"
SOURCE_CODE = "LOCAL_EVEIL_CLEAN_2026_POMPE"
REAL_EVEIL_ACTIVITY_CODE = "ACT_EVEIL_MUSICAL_98E099"


def _require_admin(db) -> User:
    admin = db.scalar(
        select(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .limit(1)
    )
    if admin is None:
        raise RuntimeError("Aucun utilisateur admin actif trouve en base locale")
    return admin


def _ensure_clean_form_config(db) -> None:
    real_eveil = db.scalar(select(CourseType).where(CourseType.code == REAL_EVEIL_ACTIVITY_CODE).limit(1))
    if real_eveil is None:
        raise RuntimeError(f"L'activite {REAL_EVEIL_ACTIVITY_CODE} est introuvable en base locale")

    row = db.scalar(select(TypeformFormConfig).where(TypeformFormConfig.typeform_form_id == SOURCE_FORM_ID).limit(1))
    config_json = {
        "label": "Local propre · Paris Pompe · Eveil musical · 2025-2026",
        "field_mapping": {
            "parent_first_name": ["parent_first_name", "prenom_parent"],
            "parent_last_name": ["parent_last_name", "nom_parent"],
            "parent_email": ["parent_email", "email_parent"],
            "parent_phone": ["parent_phone", "telephone_parent"],
            "parent_address_line_1": ["parent_address_line_1", "adresse_parent", "Address"],
            "parent_address_line_2": ["parent_address_line_2", "adresse_parent_ligne_2", "Address line 2"],
            "parent_city": ["parent_city", "ville_parent", "City/Town"],
            "parent_postal_code": ["parent_postal_code", "code_postal_parent", "Zip/Post Code"],
            "parent_country": ["parent_country", "pays_parent", "Country"],
            "child_first_name": ["child_first_name", "prenom_enfant"],
            "child_last_name": ["child_last_name", "nom_enfant"],
            "child_birth_date": ["child_birth_date", "date_naissance_enfant"],
            "requested_days": ["requested_days", "jours_souhaites"],
            "requested_times": ["requested_times", "horaires_souhaites"],
            "requested_formula_type": ["requested_formula_type", "formule_souhaitee"],
            "requested_payment_method": [
                "requested_payment_method",
                "mode_reglement_souhaite",
                "Mode de règlement souhaité pour l'année à venir",
            ],
            "notes": ["notes", "commentaires"],
        },
        "field_labels": {
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
        },
        "location_overrides": [
            {
                "location_code": "POMPE",
                "match_values": ["paris_pompe", "Paris 16 - Rue de la Pompe", "Rue de la Pompe"],
            }
        ],
        "line_templates": [
            {
                "kind": "activity",
                "activity_code": real_eveil.code,
                "quantity": "1",
            }
        ],
    }
    if row is None:
        row = TypeformFormConfig(
            typeform_form_id=SOURCE_FORM_ID,
            source_code=SOURCE_CODE,
            location_code="POMPE",
            school_year_label="2025-2026",
            audience_segment="eveil",
            default_quote_type="Forfait 2025-2026",
            default_quote_type_id=None,
            default_pricing_catalog_id=None,
            default_payment_plan_id=None,
            default_legal_entity_id=None,
            default_location_id=None,
            default_language="fr",
            configuration_json=config_json,
            is_active=True,
        )
    else:
        row.source_code = SOURCE_CODE
        row.location_code = "POMPE"
        row.school_year_label = "2025-2026"
        row.audience_segment = "eveil"
        row.default_quote_type = row.default_quote_type or "Forfait 2025-2026"
        row.default_language = row.default_language or "fr"
        row.configuration_json = config_json
        row.is_active = True
    db.add(row)
    db.flush()


def _create_intake(db) -> TypeformIntake:
    response_id = f"clean_eveil_real_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    payload = _demo_payload(
        form_id=SOURCE_FORM_ID,
        response_id=response_id,
        answers=[
            _answer("prenom_parent", "Claire"),
            _answer("nom_parent", "Martin"),
            _answer("email_parent", "claire.martin.clean@piano-academie.test"),
            _answer("telephone_parent", "+33644221133"),
            _answer("Address", "30, rue Vineuse"),
            _answer("Address line 2", ""),
            _answer("City/Town", "Paris"),
            _answer("Zip/Post Code", "75116"),
            _answer("Country", "France"),
            _answer("prenom_enfant", "Jules"),
            _answer("nom_enfant", "Martin"),
            _answer("date_naissance_enfant", "2022-06-15"),
            _answer("jours_souhaites", ["Mercredi"]),
            _answer("horaires_souhaites", ["10:00", "16:00"]),
            _answer("formule_souhaitee", "Eveil musical"),
            _answer("Mode de règlement souhaité pour l'année à venir", "Cheque en 2 fois"),
            _answer(
                "commentaires",
                "Demande formulee le 17 mars 2026.",
            ),
        ],
    )
    return _ingest_typeform_payload(db, payload)


def _pick_clean_option(analysis: dict[str, object]) -> tuple[str, str]:
    recommendations = list(analysis.get("session_recommendations") or [])
    for recommendation in recommendations:
        options = list(getattr(recommendation, "options", []) or [])
        for option in options:
            weekday = str(getattr(option, "weekday_label", "")).strip().lower()
            start_time = str(getattr(option, "start_time_label", "")).strip()
            if weekday == "mercredi" and start_time in {"10:00", "16:00"}:
                return str(getattr(recommendation, "activity_id")), str(getattr(option, "session_id"))
    raise RuntimeError("Aucun creneau mercredi 10h/16h n'a ete trouve pour l'intake propre")


def main() -> None:
    with SessionLocal() as db:
        admin = _require_admin(db)
        _ensure_clean_form_config(db)
        intake = _create_intake(db)

        analysis = _refresh_intake_analysis(db, intake)
        activity_id, session_id = _pick_clean_option(analysis)

        current_resolution = dict(intake.resolution_json or {})
        slot_resolution = dict(current_resolution.get("slot_resolution") or {})
        selected_session_ids = dict(slot_resolution.get("selected_session_ids") or {})
        selected_session_ids[activity_id] = session_id
        slot_resolution["selected_session_ids"] = selected_session_ids
        current_resolution["slot_resolution"] = slot_resolution
        intake.resolution_json = current_resolution
        db.add(intake)

        _refresh_intake_analysis(db, intake)
        db.commit()
        db.refresh(intake)

        quote_result = create_draft_quote_from_typeform_intake(
            intake_id=UUID(str(intake.id)),
            db=db,
            current_user=admin,
        )
        quote = _load_quote(db, quote_result.quote_id, lock=False)
        _ensure_public_token(quote)
        db.add(quote)
        db.commit()
        db.refresh(quote)

        print(f"INTAKE_ID={intake.id}")
        print(f"INTAKE_URL={LOCAL_FRONTEND_BASE}/admin/intakes/{intake.id}")
        print(f"QUOTE_ID={quote.id}")
        print(f"QUOTE_NUMBER={quote.quote_number}")
        print(f"QUOTE_ADMIN_URL={LOCAL_FRONTEND_BASE}/admin/quotes/{quote.id}")
        print(f"QUOTE_PUBLIC_URL={LOCAL_FRONTEND_BASE}/q/{quote.id}?t={quote.public_token}")


if __name__ == "__main__":
    main()
