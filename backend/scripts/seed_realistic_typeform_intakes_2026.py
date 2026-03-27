from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import delete, select

from app.api.routes.typeform_intakes import (
    _answer,
    _demo_payload,
    _ingest_typeform_payload,
    _refresh_intake_analysis,
    _utcnow,
)
from app.db.session import SessionLocal
from app.models.catalog import CourseType, Location
from app.models.ops import LegalEntity
from app.models.quote import PaymentPlan, PricingCatalog, QuoteType
from app.models.typeform_intake import TypeformFormConfig, TypeformIntake
from app.models.user import User, UserRole

LOCAL_FRONTEND_BASE = "http://localhost:3000"

FORM_PARIS_EVEIL = "MzQIz2u9"
FORM_PARIS_INITIATION = "CQSkTglB"
FORM_PARIS_CHILD = "qFdJ47yB"
FORM_PARIS_SLOT = "xbWmPSsx"

ACTIVITY_EVEIL = "ACT_EVEIL_MUSICAL_98E099"
ACTIVITY_CHILD_ONSITE = "PIANO_GROUP_ONSITE_1H"
ACTIVITY_CHILD_ONLINE = "PIANO_GROUP_ONLINE_1H"
ACTIVITY_MASTERCLASS = "ACT_MASTERCLASS_D84DC5"

NO_ACTIVITY_PREFIXES = ("TF_DEMO_", "TF_REALISTIC_2026_")


@dataclass(frozen=True)
class SeededIntakeCase:
    label: str
    source_form_id: str
    expected_status: str
    actual_status: str
    intake_id: str
    intake_url: str
    detected_location: str | None
    notes: str


def _require_admin(db) -> User:
    admin = db.scalar(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).limit(1))
    if admin is None:
        raise RuntimeError("Aucun utilisateur admin actif trouve en base locale")
    return admin


def _load_core_refs(
    db,
) -> tuple[LegalEntity, QuoteType, PricingCatalog, PaymentPlan, dict[str, Location], dict[str, CourseType]]:
    legal_entity = db.scalar(
        select(LegalEntity)
        .where(LegalEntity.is_active.is_(True))
        .order_by(LegalEntity.name.asc())
        .limit(1)
    )
    quote_type = db.scalar(select(QuoteType).where(QuoteType.is_active.is_(True)).order_by(QuoteType.created_at.asc()).limit(1))
    catalog = db.scalar(select(PricingCatalog).where(PricingCatalog.is_active.is_(True)).order_by(PricingCatalog.created_at.asc()).limit(1))
    payment_plan = db.scalar(select(PaymentPlan).where(PaymentPlan.is_active.is_(True)).order_by(PaymentPlan.created_at.asc()).limit(1))
    if legal_entity is None or quote_type is None or catalog is None or payment_plan is None:
        raise RuntimeError("Configuration devis incomplete: entite legale, type de devis, catalogue et plan de paiement obligatoires")

    location_codes = {"ASSAS", "ONLINE", "POMPE", "RICHELIEU", "SCHEFFER"}
    location_by_code = {
        row.code: row
        for row in db.scalars(select(Location).where(Location.code.in_(sorted(location_codes)), Location.active.is_(True))).all()
    }
    missing_locations = location_codes - set(location_by_code)
    if missing_locations:
        raise RuntimeError(f"Locations actives introuvables: {', '.join(sorted(missing_locations))}")

    activity_codes = {
        ACTIVITY_EVEIL,
        ACTIVITY_CHILD_ONSITE,
        ACTIVITY_CHILD_ONLINE,
        ACTIVITY_MASTERCLASS,
    }
    activity_by_code = {
        row.code: row
        for row in db.scalars(select(CourseType).where(CourseType.code.in_(sorted(activity_codes)), CourseType.active.is_(True))).all()
    }
    missing_activities = activity_codes - set(activity_by_code)
    if missing_activities:
        raise RuntimeError(
            "Activites existantes introuvables en base locale: "
            + ", ".join(sorted(missing_activities))
        )

    return legal_entity, quote_type, catalog, payment_plan, location_by_code, activity_by_code


def _location_override(location_code: str, *match_values: str) -> dict[str, object]:
    return {
        "location_code": location_code,
        "match_values": list(match_values),
    }


def _child_field_mapping() -> dict[str, object]:
    return {
        "parent_first_name": ["parent_first_name"],
        "parent_last_name": ["parent_last_name"],
        "parent_email": ["parent_email"],
        "parent_phone": ["parent_phone"],
        "parent_address_line_1": ["parent_address_line_1", "Address"],
        "parent_address_line_2": ["parent_address_line_2", "Address line 2"],
        "parent_city": ["parent_city", "City/Town"],
        "parent_postal_code": ["parent_postal_code", "Zip/Post Code"],
        "parent_country": ["parent_country", "Country"],
        "child_first_name": ["child_first_name"],
        "child_last_name": ["child_last_name"],
        "child_birth_date": ["child_birth_date"],
        "requested_course_mode": ["requested_course_mode"],
        "requested_location": ["requested_location"],
        "requested_days": ["requested_days"],
        "requested_times": ["requested_times"],
        "requested_slot_preferences": ["requested_slot_preferences"],
        "requested_formula_type": ["requested_formula_type"],
        "requested_payment_method": ["requested_payment_method"],
        "notes": ["notes"],
    }


def _child_field_labels() -> dict[str, object]:
    return {
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
        "requested_course_mode": "Mode de cours",
        "requested_location": "Lieu souhaite",
        "requested_days": "Jours souhaites",
        "requested_times": "Horaires souhaites",
        "requested_slot_preferences": "Preferences de creneaux",
        "requested_formula_type": "Formule souhaitee",
        "requested_payment_method": "Mode de reglement souhaite",
        "notes": "Commentaires",
        "re_enrollment": "Reinscription",
        "solfege_enabled": "Cours de solfege",
        "solfege_level": "Niveau de solfege",
        "booster_requested": "Classes Booster",
        "second_course_requested": "Deuxieme cours",
        "pass_recup": "Pass Recup",
        "allo_piano": "Allo Piano",
        "slot_selection": "Selection de creneaux",
    }


def _ensure_form_config(
    db,
    *,
    typeform_form_id: str,
    source_code: str,
    location_code: str,
    school_year_label: str,
    audience_segment: str,
    quote_type: QuoteType,
    catalog: PricingCatalog,
    payment_plan: PaymentPlan,
    legal_entity: LegalEntity,
    location: Location,
    configuration_json: dict[str, object],
) -> TypeformFormConfig:
    row = db.scalar(select(TypeformFormConfig).where(TypeformFormConfig.typeform_form_id == typeform_form_id).limit(1))
    now = _utcnow()
    if row is None:
        row = TypeformFormConfig(
            typeform_form_id=typeform_form_id,
            source_code=source_code,
            location_code=location_code,
            school_year_label=school_year_label,
            audience_segment=audience_segment,
            default_quote_type=quote_type.name,
            default_quote_type_id=quote_type.id,
            default_pricing_catalog_id=catalog.id,
            default_payment_plan_id=payment_plan.id,
            default_legal_entity_id=legal_entity.id,
            default_location_id=location.id,
            default_language="fr",
            configuration_json=configuration_json,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    else:
        row.source_code = source_code
        row.location_code = location_code
        row.school_year_label = school_year_label
        row.audience_segment = audience_segment
        row.default_quote_type = quote_type.name
        row.default_quote_type_id = quote_type.id
        row.default_pricing_catalog_id = catalog.id
        row.default_payment_plan_id = payment_plan.id
        row.default_legal_entity_id = legal_entity.id
        row.default_location_id = location.id
        row.default_language = "fr"
        row.configuration_json = configuration_json
        row.is_active = True
        row.updated_at = now
    db.add(row)
    db.flush()
    return row


def _bootstrap_existing_catalog_configs(db) -> None:
    legal_entity, quote_type, catalog, payment_plan, location_by_code, _activity_by_code = _load_core_refs(db)
    school_year_label = quote_type.school_year_label or "Année 2025-2026"
    child_mapping = _child_field_mapping()
    child_labels = _child_field_labels()

    eveil_location_overrides = [
        _location_override("POMPE", "Paris 16 - Rue de la Pompe", "Paris 16e - Rue de la Pompe", "Pompe", "Rue de la Pompe"),
        _location_override("RICHELIEU", "Paris 1 - Rue de Richelieu", "Paris 01 - Rue de Richelieu", "Richelieu", "Rue de Richelieu"),
        _location_override("ASSAS", "Paris 6 - Rue d'Assas", "Paris 06 - Rue d'Assas", "Assas", "Rue d Assas"),
    ]
    child_location_overrides = [
        _location_override("POMPE", "Paris 16 - Rue de la Pompe", "Paris 16e - Rue de la Pompe", "Pompe", "Rue de la Pompe"),
        _location_override("RICHELIEU", "Paris 1 - Rue de Richelieu", "Paris 01 - Rue de Richelieu", "Richelieu", "Rue de Richelieu"),
        _location_override("ASSAS", "Paris 6 - Rue d'Assas", "Paris 06 - Rue d'Assas", "Assas", "Rue d Assas"),
        _location_override("SCHEFFER", "Paris 16 - Rue Scheffer", "Paris 16e - Rue Scheffer", "Scheffer", "Rue Scheffer"),
        _location_override("ONLINE", "Video Call", "Vidéo Call", "Vidéocall", "En ligne", "Online"),
    ]
    slot_location_overrides = [
        _location_override("SCHEFFER", "Paris 16 - Rue Scheffer", "Paris 16e - Rue Scheffer", "Scheffer", "Rue Scheffer"),
        _location_override("RICHELIEU", "Paris 1 - Rue de Richelieu", "Paris 01 - Rue de Richelieu", "Richelieu", "Rue de Richelieu"),
    ]

    _ensure_form_config(
        db,
        typeform_form_id=FORM_PARIS_EVEIL,
        source_code="REAL_2026_PARIS_EVEIL_EXISTING_CATALOG",
        location_code="POMPE",
        school_year_label=school_year_label,
        audience_segment="eveil",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["POMPE"],
        configuration_json={
            "label": "Reel 2026 · Paris · Eveil · Catalogue existant",
            "default_vat_rate": "20.00",
            "default_course_mode": "onsite",
            "field_mapping": child_mapping,
            "field_labels": child_labels,
            "line_templates": [
                {
                    "kind": "activity",
                    "activity_code": ACTIVITY_EVEIL,
                    "quantity": "1",
                }
            ],
            "location_overrides": eveil_location_overrides,
        },
    )
    _ensure_form_config(
        db,
        typeform_form_id=FORM_PARIS_INITIATION,
        source_code="REAL_2026_PARIS_INITIATION_EXISTING_CATALOG",
        location_code="RICHELIEU",
        school_year_label=school_year_label,
        audience_segment="eveil",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["RICHELIEU"],
        configuration_json={
            "label": "Reel 2026 · Paris · Initiation · Catalogue existant",
            "default_vat_rate": "20.00",
            "default_course_mode": "onsite",
            "field_mapping": child_mapping,
            "field_labels": child_labels,
            "line_templates": [
                {
                    "kind": "activity",
                    "activity_code": ACTIVITY_EVEIL,
                    "quantity": "1",
                }
            ],
            "location_overrides": eveil_location_overrides,
        },
    )
    _ensure_form_config(
        db,
        typeform_form_id=FORM_PARIS_CHILD,
        source_code="REAL_2026_PARIS_CHILD_EXISTING_CATALOG",
        location_code="POMPE",
        school_year_label=school_year_label,
        audience_segment="child",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["POMPE"],
        configuration_json={
            "label": "Reel 2026 · Paris · Enfant · Catalogue existant",
            "default_vat_rate": "20.00",
            "default_course_mode": "onsite",
            "field_mapping": child_mapping,
            "field_labels": child_labels,
            "line_templates": [
                {
                    "kind": "activity",
                    "activity_code": ACTIVITY_CHILD_ONLINE,
                    "quantity": "1",
                    "when": {
                        "requested_course_mode": ["online", "en ligne", "video call", "videocall"],
                    },
                },
                {
                    "kind": "activity",
                    "activity_code": ACTIVITY_CHILD_ONSITE,
                    "quantity": "1",
                    "when": {
                        "requested_course_mode": ["onsite", "presentiel", "ecole"],
                    },
                },
            ],
            "location_overrides": child_location_overrides,
        },
    )
    _ensure_form_config(
        db,
        typeform_form_id=FORM_PARIS_SLOT,
        source_code="REAL_2026_PARIS_SLOT_EXISTING_CATALOG",
        location_code="SCHEFFER",
        school_year_label=school_year_label,
        audience_segment="teen",
        quote_type=quote_type,
        catalog=catalog,
        payment_plan=payment_plan,
        legal_entity=legal_entity,
        location=location_by_code["SCHEFFER"],
        configuration_json={
            "label": "Reel 2026 · Paris · Slot selection · Catalogue existant",
            "default_vat_rate": "20.00",
            "default_course_mode": "onsite",
            "field_mapping": child_mapping,
            "field_labels": child_labels,
            "line_templates": [
                {
                    "kind": "activity",
                    "activity_code": ACTIVITY_MASTERCLASS,
                    "quantity": "1",
                }
            ],
            "location_overrides": slot_location_overrides,
        },
    )
    db.commit()


def _child_answers(
    *,
    parent_first_name: str,
    parent_last_name: str,
    parent_email: str,
    parent_phone: str,
    child_first_name: str,
    child_last_name: str,
    child_birth_date: str,
    location: str,
    days: list[str] | None,
    times: list[str] | None,
    formula: str,
    payment: str,
    notes: str,
    course_mode: str | None = None,
    slot_preferences: list[dict[str, str | None]] | None = None,
    extras: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    answers = [
        _answer("parent_first_name", parent_first_name),
        _answer("parent_last_name", parent_last_name),
        _answer("parent_email", parent_email),
        _answer("parent_phone", parent_phone),
        _answer("child_first_name", child_first_name),
        _answer("child_last_name", child_last_name),
        _answer("child_birth_date", child_birth_date),
        _answer("requested_location", location),
        _answer("requested_days", days or []),
        _answer("requested_times", times or []),
        _answer("requested_formula_type", formula),
        _answer("requested_payment_method", payment),
        _answer("notes", notes),
        _answer("Address", "12 avenue de Test"),
        _answer("Address line 2", ""),
        _answer("City/Town", "Paris"),
        _answer("Zip/Post Code", "75016"),
        _answer("Country", "France"),
    ]
    if course_mode:
        answers.append(_answer("requested_course_mode", course_mode))
    if slot_preferences:
        answers.append(_answer("requested_slot_preferences", slot_preferences))
    for key, value in (extras or {}).items():
        answers.append(_answer(key, value))
    return answers


def _select_matching_option(
    db,
    intake,
    *,
    location_contains: str,
    weekday_label: str,
    start_time_label: str,
) -> str:
    analysis = _refresh_intake_analysis(db, intake)
    recommendations = list(analysis.get("session_recommendations") or [])
    for recommendation in recommendations:
        options = list(getattr(recommendation, "options", []) or [])
        for option in options:
            location_name = str(getattr(option, "location_name", "") or "")
            weekday = str(getattr(option, "weekday_label", "") or "")
            start_time = str(getattr(option, "start_time_label", "") or "")
            if location_contains.lower() not in location_name.lower():
                continue
            if weekday != weekday_label:
                continue
            if start_time != start_time_label:
                continue

            current_resolution = dict(intake.resolution_json or {})
            slot_resolution = dict(current_resolution.get("slot_resolution") or {})
            selected_session_ids = dict(slot_resolution.get("selected_session_ids") or {})
            selected_session_ids[str(getattr(recommendation, "activity_id"))] = str(getattr(option, "session_id"))
            slot_resolution["selected_session_ids"] = selected_session_ids
            current_resolution["slot_resolution"] = slot_resolution
            intake.resolution_json = current_resolution
            db.add(intake)
            updated_analysis = _refresh_intake_analysis(db, intake)
            return str(updated_analysis.get("intake_status") or intake.intake_status or "").strip().upper()

    raise RuntimeError(
        f"Aucun creneau ne correspond au filtre selectionne: {location_contains} / {weekday_label} / {start_time_label}"
    )


def main() -> None:
    with SessionLocal() as db:
        _require_admin(db)
        _bootstrap_existing_catalog_configs(db)

        planned_cases = [
            {
                "label": "Paris eveil Pompe mercredi 10h arbitre",
                "form_id": FORM_PARIS_EVEIL,
                "response_id": "existing_catalog_2026_paris_eveil_pompe_wed10_ready",
                "expected_status": "READY_FOR_DRAFT_QUOTE",
                "notes": "Cas nominal eveil avec arbitrage pre-rempli sur le catalogue existant.",
                "select_option": {"location_contains": "Pompe", "weekday_label": "Mercredi", "start_time_label": "10:00"},
                "answers": _child_answers(
                    parent_first_name="Sarah",
                    parent_last_name="Pompe",
                    parent_email="sarah.eveil.pompe.ready@piano-academie.test",
                    parent_phone="+33610000101",
                    child_first_name="Noa",
                    child_last_name="Pompe",
                    child_birth_date="2020-09-03",
                    location="Paris 16 - Rue de la Pompe",
                    days=["Mercredi"],
                    times=["10:00"],
                    formula="Eveil musical",
                    payment="Carte bleue en 1 fois",
                    notes="Cas eveil reel rejoue sur activite existante, pret pour devis puis transformation.",
                ),
            },
            {
                "label": "Paris eveil multi-creneaux Pompe",
                "form_id": FORM_PARIS_EVEIL,
                "response_id": "existing_catalog_2026_paris_eveil_matching",
                "expected_status": "MATCHING_REQUIRED",
                "notes": "Cas eveil volontairement laisse sans arbitrage pour tester la selection de creneau.",
                "answers": _child_answers(
                    parent_first_name="Lea",
                    parent_last_name="Comparaison",
                    parent_email="lea.eveil.matching@piano-academie.test",
                    parent_phone="+33610000102",
                    child_first_name="Mila",
                    child_last_name="Comparaison",
                    child_birth_date="2021-05-11",
                    location="Paris 16 - Rue de la Pompe",
                    days=["Mercredi", "Samedi"],
                    times=["10:00", "16:00"],
                    formula="Eveil musical",
                    payment="Virement bancaire",
                    notes="Cas de matching sur plusieurs creneaux eveil existants a Pompe.",
                ),
            },
            {
                "label": "Paris initiation Richelieu arbitree",
                "form_id": FORM_PARIS_INITIATION,
                "response_id": "existing_catalog_2026_paris_initiation_richelieu_ready",
                "expected_status": "READY_FOR_DRAFT_QUOTE",
                "notes": "Cas initiation/eveil avec creneau Richelieu deja arbitre.",
                "select_option": {"location_contains": "Richelieu", "weekday_label": "Mercredi", "start_time_label": "16:00"},
                "answers": _child_answers(
                    parent_first_name="Diane",
                    parent_last_name="Richelieu",
                    parent_email="diane.initiation.richelieu.ready@piano-academie.test",
                    parent_phone="+33610000103",
                    child_first_name="Carla",
                    child_last_name="Richelieu",
                    child_birth_date="2021-03-20",
                    location="Paris 1 - Rue de Richelieu",
                    days=["Mercredi"],
                    times=["16:00"],
                    formula="Cours d initiation au piano",
                    payment="Cheque en 4 fois",
                    notes="Cas initiation reel rejoue sur activite eveil existante.",
                ),
            },
            {
                "label": "Paris enfant presentiel Pompe arbitre",
                "form_id": FORM_PARIS_CHILD,
                "response_id": "existing_catalog_2026_paris_child_onsite_ready",
                "expected_status": "READY_FOR_DRAFT_QUOTE",
                "notes": "Cas enfant presentiel avec arbitrage pre-rempli sur un cours collectif existant.",
                "select_option": {"location_contains": "Pompe", "weekday_label": "Mardi", "start_time_label": "17:00"},
                "answers": _child_answers(
                    parent_first_name="Camille",
                    parent_last_name="Presentiel",
                    parent_email="camille.child.onsite.ready@piano-academie.test",
                    parent_phone="+33610000104",
                    child_first_name="Emma",
                    child_last_name="Presentiel",
                    child_birth_date="2016-03-15",
                    location="Paris 16 - Rue de la Pompe",
                    days=["Mardi"],
                    times=["17:00"],
                    formula="Cours collectif enfant",
                    payment="Carte bleue en 1 fois",
                    notes="Cas enfant presentiel utile pour devis, transformation et facturation.",
                    course_mode="Presentiel",
                    extras={
                        "solfege_enabled": True,
                        "solfege_level": "Debutant - Niveau 1",
                        "pass_recup": True,
                    },
                ),
            },
            {
                "label": "Paris enfant online arbitre",
                "form_id": FORM_PARIS_CHILD,
                "response_id": "existing_catalog_2026_paris_child_online_ready",
                "expected_status": "READY_FOR_DRAFT_QUOTE",
                "notes": "Cas enfant online avec arbitrage pre-rempli sur les creneaux online existants.",
                "select_option": {"location_contains": "Online", "weekday_label": "Lundi", "start_time_label": "18:00"},
                "answers": _child_answers(
                    parent_first_name="Julie",
                    parent_last_name="Online",
                    parent_email="julie.child.online.ready@piano-academie.test",
                    parent_phone="+33610000105",
                    child_first_name="Theo",
                    child_last_name="Online",
                    child_birth_date="2014-11-09",
                    location="Video Call",
                    days=["Lundi"],
                    times=["18:00"],
                    formula="Cours collectif enfant en ligne",
                    payment="Virement bancaire",
                    notes="Cas online pour valider quote et transformation sans creation d activite.",
                    course_mode="En ligne",
                ),
            },
            {
                "label": "Paris enfant presentiel matching",
                "form_id": FORM_PARIS_CHILD,
                "response_id": "existing_catalog_2026_paris_child_matching",
                "expected_status": "MATCHING_REQUIRED",
                "notes": "Cas enfant presentiel laisse volontairement sans arbitrage.",
                "answers": _child_answers(
                    parent_first_name="Nadia",
                    parent_last_name="Matching",
                    parent_email="nadia.child.matching@piano-academie.test",
                    parent_phone="+33610000106",
                    child_first_name="Leo",
                    child_last_name="Matching",
                    child_birth_date="2015-08-19",
                    location="Paris 16 - Rue de la Pompe",
                    days=["Mardi"],
                    times=["17:00", "18:00"],
                    formula="Cours collectif enfant",
                    payment="Carte bleue en 1 fois",
                    notes="Cas matching pour tester l arbitrage manuel avant creation du devis.",
                    course_mode="Presentiel",
                ),
            },
            {
                "label": "MasterClass selection manuelle Scheffer",
                "form_id": FORM_PARIS_SLOT,
                "response_id": "existing_catalog_2026_masterclass_matching",
                "expected_status": "MATCHING_REQUIRED",
                "notes": "Cas avance inspire des selections explicites de creneaux.",
                "answers": _child_answers(
                    parent_first_name="Sophie",
                    parent_last_name="Masterclass",
                    parent_email="sophie.masterclass.matching@piano-academie.test",
                    parent_phone="+33610000107",
                    child_first_name="Adele",
                    child_last_name="Masterclass",
                    child_birth_date="2010-04-28",
                    location="Paris 16 - Rue Scheffer",
                    days=["Samedi"],
                    times=["09:00", "13:30"],
                    formula="MasterClass Concours",
                    payment="Carte bleue en 1 fois",
                    notes="Cas avance pour tester un arbitrage sur des seances masterclass existantes.",
                    course_mode="Presentiel",
                    extras={"slot_selection": ["Samedi 09h", "Samedi 13h30"]},
                ),
            },
            {
                "label": "MasterClass bloquee dimanche 07h",
                "form_id": FORM_PARIS_SLOT,
                "response_id": "existing_catalog_2026_masterclass_blocked",
                "expected_status": "BLOCKED",
                "notes": "Cas bloque sans creneau compatible sur les masterclass existantes.",
                "answers": _child_answers(
                    parent_first_name="Marc",
                    parent_last_name="Bloque",
                    parent_email="marc.masterclass.blocked@piano-academie.test",
                    parent_phone="+33610000108",
                    child_first_name="Lina",
                    child_last_name="Bloque",
                    child_birth_date="2011-01-14",
                    location="Paris 16 - Rue Scheffer",
                    days=["Dimanche"],
                    times=["07:00"],
                    formula="MasterClass Concours",
                    payment="Virement bancaire",
                    notes="Cas bloque pour verifier l absence de creneau masterclass compatible avec le catalogue existant.",
                    course_mode="Presentiel",
                    slot_preferences=[{"day": "Dimanche", "time": "07:00", "location": "Paris 16 - Rue Scheffer"}],
                ),
            },
        ]

        managed_response_ids = [str(case["response_id"]) for case in planned_cases]
        managed_response_ids.append("existing_catalog_2026_paris_child_blocked")
        db.execute(
            delete(TypeformIntake).where(TypeformIntake.source_response_id.in_(managed_response_ids))
        )
        db.commit()

        seeded_cases: list[SeededIntakeCase] = []
        for case in planned_cases:
            payload = _demo_payload(
                form_id=case["form_id"],
                response_id=case["response_id"],
                answers=case["answers"],
            )
            intake = _ingest_typeform_payload(db, payload)
            db.refresh(intake)

            if case.get("select_option"):
                actual_status = _select_matching_option(
                    db,
                    intake,
                    location_contains=str(case["select_option"]["location_contains"]),
                    weekday_label=str(case["select_option"]["weekday_label"]),
                    start_time_label=str(case["select_option"]["start_time_label"]),
                )
            else:
                analysis = _refresh_intake_analysis(db, intake)
                actual_status = str(analysis.get("intake_status") or intake.intake_status or "").strip().upper()

            db.commit()
            db.refresh(intake)

            expected_status = str(case["expected_status"]).strip().upper()
            if actual_status != expected_status:
                raise RuntimeError(
                    f"Statut inattendu pour '{case['label']}': attendu={expected_status} obtenu={actual_status}"
                )

            seeded_cases.append(
                SeededIntakeCase(
                    label=str(case["label"]),
                    source_form_id=str(case["form_id"]),
                    expected_status=expected_status,
                    actual_status=actual_status,
                    intake_id=str(intake.id),
                    intake_url=f"{LOCAL_FRONTEND_BASE}/admin/intakes/{intake.id}",
                    detected_location=str(intake.detected_location or "") or None,
                    notes=str(case["notes"]),
                )
            )

        typeform_activity_rows = db.scalars(
            select(CourseType.code).where(
                (CourseType.code.like("TF_DEMO_%")) | (CourseType.code.like("TF_REALISTIC_2026_%"))
            )
        ).all()
        print(
            json.dumps(
                {
                    "generated_at": _utcnow().isoformat(),
                    "count": len(seeded_cases),
                    "catalog_activities_used": [
                        ACTIVITY_EVEIL,
                        ACTIVITY_CHILD_ONSITE,
                        ACTIVITY_CHILD_ONLINE,
                        ACTIVITY_MASTERCLASS,
                    ],
                    "typeform_activity_count": len(typeform_activity_rows),
                    "cases": [asdict(item) for item in seeded_cases],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
