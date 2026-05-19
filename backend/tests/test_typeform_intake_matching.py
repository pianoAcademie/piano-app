from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.typeform_intakes import (
    CLIENT_MODE_EXISTING,
    CLIENT_MODE_EXISTING_FAMILY,
    CLIENT_MODE_NEW_PARENT_CHILD,
    _default_resolution,
    _extract_estimated_solfege_level,
    _find_existing_adult_parent_client,
    _future_school_year_candidate_configs,
    _activity_matches_line_for_slot_fallback,
    _intake_list_out_fast,
    _line_allows_session_modality,
    _normalize_payload,
    _session_recommendations_have_options,
    _should_search_onsite_solfege_without_main_slot_filters,
    _should_try_future_school_year_config,
    _solfege_slot_proposal_from_normalized,
    _stored_messages,
    _template_for_runtime_context,
    _template_matches_when,
    _template_matches_segment_target,
    _typeform_default_quote_template,
    _typeform_default_terms_template,
    _typeform_session_option_from_row,
)
from app.services.referrals import referral_category_for_location


class TypeformIntakeMatchingTests(unittest.TestCase):
    def test_bar_le_duc_child_course_mode_templates_match_full_typeform_labels(self) -> None:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "20260516_0116_register_typeform_bld_child_2026_2027.py"
        )
        spec = importlib.util.spec_from_file_location("bld_child_config", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        line_templates = module._build_configuration_json()["line_templates"]

        self.assertTrue(
            any(
                template.get("activity_code") == "PIANO_GROUP_ONSITE_1H"
                and _template_matches_when(
                    template,
                    {"requested_course_mode": "Cours collectif de 1h  (22€/h)"},
                )
                for template in line_templates
            )
        )
        self.assertTrue(
            any(
                template.get("activity_code") == "ACT_COURS_PARTICULIER_5DFFD9"
                and _template_matches_when(
                    template,
                    {"requested_course_mode": "Cours particulier de 1h (40€/h)"},
                )
                for template in line_templates
            )
        )

    def test_bar_le_duc_adult_ten_course_templates_limit_quantity_and_planning(self) -> None:
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "20260516_0117_register_typeform_bld_adult_2026_2027.py"
        )
        spec = importlib.util.spec_from_file_location("bld_adult_config", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        line_templates = module._build_configuration_json()["line_templates"]
        templates_by_product = {}
        for template in line_templates:
            when = template.get("when") or {}
            for product_label in when.get("requested_products") or []:
                templates_by_product[product_label] = template

        collective_pack = templates_by_product["Engagement sur 10 cours - 26€ / cours"]
        private_pack = templates_by_product["Engagement 10 cours - 45€/h"]

        self.assertEqual(collective_pack["quantity"], "10")
        self.assertEqual(collective_pack["unit_price_ttc"], "26.00")
        self.assertEqual(collective_pack["planning_session_limit"], 10)
        self.assertEqual(private_pack["quantity"], "10")
        self.assertEqual(private_pack["unit_price_ttc"], "45.00")
        self.assertEqual(private_pack["planning_session_limit"], 10)

    def test_online_runtime_context_switches_main_piano_template_to_online_activity(self) -> None:
        template = {
            "kind": "activity",
            "activity_code": "PIANO_GROUP_ONSITE_1H",
            "quantity": "1",
        }

        adjusted = _template_for_runtime_context(
            template,
            runtime_context={
                "location_code": "ONLINE",
                "location_name": "Online",
                "requested_location": "Online",
            },
        )

        self.assertEqual(adjusted["activity_code"], "PIANO_GROUP_ONLINE_1H")
        self.assertEqual(template["activity_code"], "PIANO_GROUP_ONSITE_1H")

    def test_online_preview_line_rejects_onsite_fallback_session_activity(self) -> None:
        line = SimpleNamespace(
            code="PIANO_GROUP_ONLINE_1H",
            title="Cours de piano collectif en ligne - enfants (1h)",
            description="",
            meta={},
        )
        onsite_activity = SimpleNamespace(
            code="PIANO_GROUP_ONSITE_1H",
            name="Cours de piano collectif en presentiel (1h)",
            mode="ONSITE",
        )
        onsite_location = SimpleNamespace(
            code="RICHELIEU",
            name="Rue de Richelieu",
            is_online=False,
        )

        self.assertFalse(
            _line_allows_session_modality(  # type: ignore[arg-type]
                line,
                activity=onsite_activity,
                location=onsite_location,
            )
        )

    def test_normalize_payload_maps_bar_le_duc_adult_2026_form(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "adult_first_name": ["2d3d1cd8-5215-4292-888f-c8688d356cc3", "ZN78ePa7AnX6"],
                    "adult_last_name": ["0c0a414f-c030-4b18-b726-f46bd68ec3bd", "sYKCB2fi6fdH"],
                    "adult_phone": ["c8ba5893-faae-440d-bf57-b2f8c76f917c", "BO1ssvO3bLJL"],
                    "adult_email": ["30122284-9b96-4710-8ef9-85323f3b8cec", "hmdaAxufGIRz"],
                    "requested_location": ["d2e24218-ca13-4d0f-9aee-aed62064f0f8", "RSRrFMDX3r4x"],
                    "requested_course_mode": ["79fc9436-3876-45d8-a606-42aeb5b9c16e", "lPTgRaXnUe5o"],
                    "requested_days": ["cd2aae75-5f1a-41da-8d11-bb06317aa9ec", "ABQSpJCI7SmU"],
                    "requested_times": ["cd2aae75-5f1a-41da-8d11-bb06317aa9ec", "ABQSpJCI7SmU"],
                    "requested_slot_preferences": ["cd2aae75-5f1a-41da-8d11-bb06317aa9ec", "ABQSpJCI7SmU"],
                    "requested_formula_type": [
                        "30e7993e-e094-441a-b91d-c7be27eb1855",
                        "uWCHtvziDdRS",
                        "f152efb5-e514-4942-98b5-3b015ffe5e93",
                        "qC2pwm0mhUzu",
                    ],
                    "requested_payment_method": ["535e5e4f-d896-41d5-b50e-8a2b4e7f48da", "k9dOy8nuYY7K"],
                    "referral_referrer_name": ["70497518-c91a-43c7-9920-6e90e8830e86", "Lb81oigIiqU6"],
                    "parent_address_line_1": ["ec7d84dd-11cc-4be9-a83f-02ba534d22ae", "nZqbjdldKlGl"],
                    "parent_address_line_2": ["5958df0f-5002-4bd6-a113-82aa86d34edf", "r9rqOu76ZxaF"],
                    "parent_city": ["d83e7e5f-ccea-492f-9def-330ef62ba6c4", "MggGi7xdaaab"],
                    "parent_postal_code": ["a3481f83-b489-4b87-a8e6-03f79dd319fc", "yMQwiMEkLC1g"],
                    "parent_country": ["becf196f-056f-43cf-93fd-d2a7ed578167", "kJpVBNj2XTcx"],
                    "notes": ["ebf82582-33fe-4051-ba9e-fdd8ffeaf2e2", "Fy01o3nzrQxK"],
                },
                "field_labels": {},
                "default_course_mode": "onsite",
            },
            audience_segment="adult",
            location_code="BAR_LE_DUC",
        )
        payload = {
            "form_response": {
                "form_id": "reOoXM3G",
                "token": "01KRRF9W1935Q379JQ775ZDTVP",
                "answers": [
                    {"text": "Lorem ipsum dolor", "field": {"id": "ZN78ePa7AnX6", "ref": "2d3d1cd8-5215-4292-888f-c8688d356cc3"}},
                    {"text": "Lorem ipsum dolor", "field": {"id": "sYKCB2fi6fdH", "ref": "0c0a414f-c030-4b18-b726-f46bd68ec3bd"}},
                    {"phone_number": "+34123456789", "field": {"id": "BO1ssvO3bLJL", "ref": "c8ba5893-faae-440d-bf57-b2f8c76f917c"}},
                    {"email": "an_account@example.com", "field": {"id": "hmdaAxufGIRz", "ref": "30122284-9b96-4710-8ef9-85323f3b8cec"}},
                    {"text": "Famille Martin", "field": {"id": "Lb81oigIiqU6", "ref": "70497518-c91a-43c7-9920-6e90e8830e86"}},
                    {"choice": {"label": "Ecole à Bar-le-Duc"}, "field": {"id": "RSRrFMDX3r4x", "ref": "d2e24218-ca13-4d0f-9aee-aed62064f0f8"}},
                    {"choices": {"labels": ["21h"]}, "field": {"id": "px8eLzv9bFn9", "ref": "0649fefc-8b95-4d23-a1a2-51dfc1d21b99", "title": "lundi"}},
                    {"choices": {"labels": ["21h"]}, "field": {"id": "aHzc7LQ5osRR", "ref": "0b6ea79b-3cfb-4743-a119-2d8d7e3f7313", "title": "mardi"}},
                    {"choice": {"label": "Cours collectif"}, "field": {"id": "lPTgRaXnUe5o", "ref": "79fc9436-3876-45d8-a606-42aeb5b9c16e"}},
                    {"choice": {"label": "Engagement 10 cours - 45€/h"}, "field": {"id": "qC2pwm0mhUzu", "ref": "f152efb5-e514-4942-98b5-3b015ffe5e93"}},
                    {"choice": {"label": "Engagement sur 10 cours - 26€ / cours"}, "field": {"id": "uWCHtvziDdRS", "ref": "30e7993e-e094-441a-b91d-c7be27eb1855"}},
                    {
                        "choices": {
                            "labels": [
                                "Lundi 8h30",
                                "Lundi 13h30",
                                "Mardi 9h",
                                "Mardi 13h30",
                                "Mercredi 18h",
                                "Jeudi 9h",
                                "Jeudi 13h30",
                                "Jeudi 18h",
                                "Vendredi 9h",
                                "Vendredi 13h30",
                                "Vendredi 18h",
                                "Samedi 11h",
                            ]
                        },
                        "field": {"id": "ABQSpJCI7SmU", "ref": "cd2aae75-5f1a-41da-8d11-bb06317aa9ec"},
                    },
                    {"choice": {"label": "Carte bleue en 1 fois"}, "field": {"id": "k9dOy8nuYY7K", "ref": "535e5e4f-d896-41d5-b50e-8a2b4e7f48da"}},
                    {"text": "12 rue test", "field": {"id": "nZqbjdldKlGl", "ref": "ec7d84dd-11cc-4be9-a83f-02ba534d22ae"}},
                    {"text": "Bar-le-Duc", "field": {"id": "MggGi7xdaaab", "ref": "d83e7e5f-ccea-492f-9def-330ef62ba6c4"}},
                    {"text": "55000", "field": {"id": "yMQwiMEkLC1g", "ref": "a3481f83-b489-4b87-a8e6-03f79dd319fc"}},
                    {"text": "FR", "field": {"id": "kJpVBNj2XTcx", "ref": "becf196f-056f-43cf-93fd-d2a7ed578167"}},
                    {"text": "A rappeler", "field": {"id": "Fy01o3nzrQxK", "ref": "ebf82582-33fe-4051-ba9e-fdd8ffeaf2e2"}},
                ],
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["customer_type"], "adult")
        self.assertEqual(normalized["parent_first_name"], "Lorem ipsum dolor")
        self.assertEqual(normalized["parent_email"], "an_account@example.com")
        self.assertIsNone(normalized["child_first_name"])
        self.assertEqual(normalized["requested_location"], "Ecole à Bar-le-Duc")
        self.assertEqual(normalized["requested_course_mode"], "Cours collectif")
        self.assertEqual(normalized["requested_formula_type"], "Engagement sur 10 cours - 26€ / cours")
        self.assertEqual(normalized["requested_payment_method"], "Carte bleue en 1 fois")
        self.assertEqual(normalized["requested_days"], ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"])
        self.assertEqual(normalized["requested_times"], ["08:30", "13:30", "09:00", "18:00", "11:00"])
        self.assertIn(
            {"day": "lundi", "time": "08:30", "location": "Ecole à Bar-le-Duc", "segment": "adult"},
            normalized["requested_slot_preferences"],
        )
        self.assertNotIn(
            {"day": "lundi", "time": "21:00", "location": "Ecole à Bar-le-Duc", "segment": "adult"},
            normalized["requested_slot_preferences"],
        )
        self.assertEqual(normalized["referral_referrer_name"], "Famille Martin")
        self.assertEqual(normalized["referral_category"], "BAR_LE_DUC")
        self.assertEqual(normalized["notes"], "A rappeler")

    def test_normalize_payload_maps_bar_le_duc_child_2026_form(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
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
                    "requested_products": [
                        "73c6edff-7d0f-4baa-84fc-56ddd8b5c4b3",
                        "H1LopXWsHma8",
                        "f2bc039a-9456-46f0-b860-fd81fa342aca",
                        "Q7leRDfe4wTM",
                    ],
                    "requested_payment_method": ["f152efb5-e514-4942-98b5-3b015ffe5e93", "W9ZnW7AdVH0G"],
                    "parent_address_line_1": ["d84f87be-fe9c-43d5-a551-0fc4d8aabc66", "irKBXhUR5Ti2"],
                    "parent_city": ["8c9d688e-d1d1-4e8b-8eb2-ab2cd6fbcd14", "7Fyg54gNOgGe"],
                    "parent_postal_code": ["a57c3db2-7d59-4f11-96b1-791a72b3fa2e", "BOIx8tD4Z4r7"],
                    "parent_country": ["8419db4d-e71f-4926-a222-58ac21279e2d", "9OMEruKHdKJp"],
                },
                "field_labels": {},
                "default_course_mode": "onsite",
            },
            audience_segment="child",
            location_code="BAR_LE_DUC",
        )
        payload = {
            "form_response": {
                "form_id": "G9u3xvbq",
                "token": "0n5f6x9bhklqcpgy454d0n5y3hduvss5",
                "definition": {
                    "fields": [
                        {"id": "qmBlUlA9XMO1", "ref": "77d16e29-8e2d-4867-aa7c-6cc2f6074a62", "title": "First name"},
                        {"id": "AswXIZsbprkp", "ref": "73f75eee-a672-4dac-a55e-92ac04ac25d3", "title": "Last name"},
                        {"id": "9DWagra6QUSO", "ref": "990536e3-2dbd-4dc6-aa83-38b3e5d0c3b3", "title": "First name"},
                        {"id": "1rSy4mKm5FzS", "ref": "cc910847-903d-4e99-ad87-7ddcfa3376a4", "title": "Last name"},
                    ]
                },
                "answers": [
                    {"text": "Estela", "field": {"id": "qmBlUlA9XMO1", "ref": "77d16e29-8e2d-4867-aa7c-6cc2f6074a62"}},
                    {"text": "Oliviero", "field": {"id": "AswXIZsbprkp", "ref": "73f75eee-a672-4dac-a55e-92ac04ac25d3"}},
                    {"phone_number": "+33641387046", "field": {"id": "WemFEoLBLCfg", "ref": "3b1048c2-8cd1-45e5-aa25-4605f77cba20"}},
                    {"email": "nomys2015@gmail.com", "field": {"id": "wwZMSEUL9FKT", "ref": "cd68bc34-56dd-4ac9-90ed-cdb079b9d326"}},
                    {"text": "Alex", "field": {"id": "9DWagra6QUSO", "ref": "990536e3-2dbd-4dc6-aa83-38b3e5d0c3b3"}},
                    {"text": "Oliviero", "field": {"id": "1rSy4mKm5FzS", "ref": "cc910847-903d-4e99-ad87-7ddcfa3376a4"}},
                    {"boolean": True, "field": {"id": "0JAR3XxExv3M", "ref": "4ce9aa87-f9d3-4907-8db4-53155fdd8c60", "title": "S'agit-il d'une réinscription ?"}},
                    {"date": "2000-02-03", "field": {"id": "K2HfGcFB6GPZ", "ref": "25c23245-2a27-491c-aca8-250e2813e68c"}},
                    {"choice": {"label": "Bar-le-Duc"}, "field": {"id": "IwHJg6AeDOQh", "ref": "29b0a590-74e2-486c-af59-493e6f83ff67"}},
                    {"choice": {"label": "Cours collectif de 1h  (22€/h)"}, "field": {"id": "H1LopXWsHma8", "ref": "73c6edff-7d0f-4baa-84fc-56ddd8b5c4b3"}},
                    {"choices": {"labels": ["jeudi 15h30"]}, "field": {"id": "bJJJmkeJGVoM", "ref": "3cabba30-1103-440a-b4b9-3dac258fdef3"}},
                    {"choice": {"label": "Ne sais pas"}, "field": {"id": "pAHENgKA6Qqu", "ref": "99a98c03-9418-4bca-8028-5ce334f5a696", "title": "Estimation du niveau de votre enfant en solfège"}},
                    {"choice": {"label": "Non"}, "field": {"id": "Q7leRDfe4wTM", "ref": "f2bc039a-9456-46f0-b860-fd81fa342aca"}},
                    {"choice": {"label": "CB mensuelle"}, "field": {"id": "W9ZnW7AdVH0G", "ref": "f152efb5-e514-4942-98b5-3b015ffe5e93"}},
                    {"text": "3 All. de Vademont", "field": {"id": "irKBXhUR5Ti2", "ref": "d84f87be-fe9c-43d5-a551-0fc4d8aabc66"}},
                    {"text": "Bar-le-Duc", "field": {"id": "7Fyg54gNOgGe", "ref": "8c9d688e-d1d1-4e8b-8eb2-ab2cd6fbcd14"}},
                    {"text": "55000", "field": {"id": "BOIx8tD4Z4r7", "ref": "a57c3db2-7d59-4f11-96b1-791a72b3fa2e"}},
                    {"text": "FR", "field": {"id": "9OMEruKHdKJp", "ref": "8419db4d-e71f-4926-a222-58ac21279e2d"}},
                ],
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["customer_type"], "child")
        self.assertEqual(normalized["parent_first_name"], "Estela")
        self.assertEqual(normalized["parent_last_name"], "Oliviero")
        self.assertEqual(normalized["parent_email"], "nomys2015@gmail.com")
        self.assertEqual(normalized["child_first_name"], "Alex")
        self.assertEqual(normalized["child_last_name"], "Oliviero")
        self.assertEqual(normalized["child_birth_date"], "2000-02-03")
        self.assertEqual(normalized["requested_location"], "Bar-le-Duc")
        self.assertEqual(normalized["requested_course_mode"], "Cours collectif de 1h  (22€/h)")
        self.assertEqual(normalized["requested_days"], ["jeudi"])
        self.assertEqual(normalized["requested_times"], ["15:30"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [{"day": "jeudi", "time": "15:30", "location": "Bar-le-Duc", "segment": "child"}],
        )
        self.assertEqual(normalized["requested_payment_method"], "CB mensuelle")
        self.assertEqual(normalized["parent_address_line_1"], "3 All. de Vademont")
        self.assertEqual(normalized["parent_city"], "Bar-le-Duc")
        self.assertEqual(normalized["parent_postal_code"], "55000")
        self.assertTrue(normalized["is_reenrollment"])

    def test_bar_le_duc_document_codes_are_preferred_for_intake_defaults(self) -> None:
        class FakeScalars:
            def __init__(self, rows: list[SimpleNamespace]) -> None:
                self._rows = rows

            def all(self) -> list[SimpleNamespace]:
                return self._rows

        class FakeDb:
            def __init__(self, rows: list[SimpleNamespace]) -> None:
                self._rows = rows

            def scalars(self, _stmt: object) -> FakeScalars:
                return FakeScalars(self._rows)

        config = SimpleNamespace(
            default_language="fr",
            audience_segment="adult",
            location_code="BAR_LE_DUC",
            source_code="typeform_bld_adult_2026_2027",
            configuration_json={
                "default_quote_template_codes": ["TEMPLATE_BLD_ADULTES"],
                "default_terms_template_codes": ["CGV_BLD_ADULTES_2026_2027"],
            },
        )
        quote_template = SimpleNamespace(
            code="TEMPLATE_BLD_ADULTES",
            name="Template Adultes Bar-le-Duc",
            description="",
            target="adult",
            language="fr",
        )
        terms_template = SimpleNamespace(
            code="CGV_BLD_ADULTES_2026_2027",
            name="CGV Adultes Bar-le-Duc",
            description="",
            target="adult",
            language="fr",
        )

        self.assertIs(
            _typeform_default_quote_template(FakeDb([quote_template]), config=config),  # type: ignore[arg-type]
            quote_template,
        )
        self.assertIs(
            _typeform_default_terms_template(FakeDb([terms_template]), config=config),  # type: ignore[arg-type]
            terms_template,
        )

    def test_bar_le_duc_document_names_are_preferred_when_codes_are_unknown(self) -> None:
        class FakeScalars:
            def __init__(self, rows: list[SimpleNamespace]) -> None:
                self._rows = rows

            def all(self) -> list[SimpleNamespace]:
                return self._rows

        class FakeDb:
            def __init__(self, rows: list[SimpleNamespace]) -> None:
                self._rows = rows

            def scalars(self, _stmt: object) -> FakeScalars:
                return FakeScalars(self._rows)

        config = SimpleNamespace(
            default_language="fr",
            audience_segment="child",
            location_code="BAR_LE_DUC",
            source_code="typeform_bld_child_2026_2027",
            configuration_json={},
        )
        generic_child = SimpleNamespace(
            code="TEMPLATE_COURS_COLLECTIF_ENFANT",
            name="Template enfants generique",
            description="",
            target="child",
            language="fr",
        )
        bar_le_duc_child = SimpleNamespace(
            code="CUSTOM_CHILD_TERMS",
            name="CGV enfants Bar-le-Duc",
            description="",
            target="child",
            language="fr",
        )

        selected = _typeform_default_terms_template(
            FakeDb([generic_child, bar_le_duc_child]),  # type: ignore[arg-type]
            config=config,
        )

        self.assertIs(selected, bar_le_duc_child)

    def test_child_intake_does_not_select_parent_client_as_quote_target(self) -> None:
        adult_client_id = uuid4()

        resolution = _default_resolution(
            normalized={
                "customer_type": "child",
                "parent_first_name": "Karen",
                "parent_last_name": "Lafon",
                "child_first_name": "Natalie",
                "child_last_name": "Lafon",
            },
            stored_resolution={},
            client_candidates=[
                {
                    "client_id": adult_client_id,
                    "client_kind": "ADULT",
                    "display_name": "Karen Lafon",
                    "confidence": 107,
                }
            ],
            family_candidates=[],
        )

        self.assertEqual(resolution["client_resolution"]["mode"], CLIENT_MODE_NEW_PARENT_CHILD)
        self.assertIsNone(resolution["client_resolution"]["selected_client_id"])

    def test_child_intake_can_select_existing_child_client_as_quote_target(self) -> None:
        child_client_id = uuid4()

        resolution = _default_resolution(
            normalized={
                "customer_type": "child",
                "parent_first_name": "Karen",
                "parent_last_name": "Lafon",
                "child_first_name": "Natalie",
                "child_last_name": "Lafon",
            },
            stored_resolution={},
            client_candidates=[
                {
                    "client_id": child_client_id,
                    "client_kind": "CHILD",
                    "display_name": "Natalie Lafon",
                    "confidence": 107,
                }
            ],
            family_candidates=[],
        )

        self.assertEqual(resolution["client_resolution"]["mode"], CLIENT_MODE_EXISTING)
        self.assertEqual(resolution["client_resolution"]["selected_client_id"], str(child_client_id))

    def test_child_intake_does_not_auto_select_sibling_family_candidate(self) -> None:
        parent_client_id = uuid4()
        sibling_client_id = uuid4()

        resolution = _default_resolution(
            normalized={
                "customer_type": "child",
                "parent_first_name": "Alice",
                "parent_last_name": "Avenel",
                "parent_email": "alice@example.test",
                "child_first_name": "Edward",
                "child_last_name": "Avenel",
            },
            stored_resolution={},
            client_candidates=[],
            family_candidates=[
                {
                    "adult_client_id": parent_client_id,
                    "child_client_id": sibling_client_id,
                    "billing_client_id": parent_client_id,
                    "display_name": "Alice Avenel -> Rose Avenel",
                    "confidence": 116,
                    "child_identity_score": 24,
                }
            ],
        )

        self.assertEqual(resolution["client_resolution"]["mode"], CLIENT_MODE_NEW_PARENT_CHILD)
        self.assertIsNone(resolution["client_resolution"]["selected_family_child_client_id"])

    def test_child_intake_can_auto_select_existing_family_when_child_identity_matches(self) -> None:
        parent_client_id = uuid4()
        child_client_id = uuid4()

        resolution = _default_resolution(
            normalized={
                "customer_type": "child",
                "parent_first_name": "Alice",
                "parent_last_name": "Avenel",
                "parent_email": "alice@example.test",
                "child_first_name": "Rose",
                "child_last_name": "Avenel",
            },
            stored_resolution={},
            client_candidates=[],
            family_candidates=[
                {
                    "adult_client_id": parent_client_id,
                    "child_client_id": child_client_id,
                    "billing_client_id": parent_client_id,
                    "display_name": "Alice Avenel -> Rose Avenel",
                    "confidence": 116,
                    "child_identity_score": 52,
                }
            ],
        )

        self.assertEqual(resolution["client_resolution"]["mode"], CLIENT_MODE_EXISTING_FAMILY)
        self.assertEqual(resolution["client_resolution"]["selected_family_child_client_id"], str(child_client_id))

    def test_existing_parent_client_can_be_found_by_email_or_phone(self) -> None:
        email_parent = SimpleNamespace(id=uuid4(), first_name="Myriam", last_name="Demian")
        phone_parent = SimpleNamespace(
            id=uuid4(),
            phone=None,
            mobile_phone_1="+33 6 86 17 47 61",
            mobile_phone_2=None,
            home_phone=None,
        )

        class EmailDb:
            def scalar(self, _stmt: object) -> object:
                return email_parent

        class PhoneScalars:
            def all(self) -> list[object]:
                return [phone_parent]

        class PhoneDb:
            def scalar(self, _stmt: object) -> None:
                return None

            def scalars(self, _stmt: object) -> PhoneScalars:
                return PhoneScalars()

        self.assertIs(
            _find_existing_adult_parent_client(  # type: ignore[arg-type]
                EmailDb(),
                {"parent_email": "myriamthera@hotmail.com"},
            ),
            email_parent,
        )
        self.assertIs(
            _find_existing_adult_parent_client(  # type: ignore[arg-type]
                PhoneDb(),
                {"parent_phone": "+33686174761"},
            ),
            phone_parent,
        )

    def test_intake_list_fast_uses_stored_fields_without_reanalysis(self) -> None:
        config_id = uuid4()
        intake = SimpleNamespace(
            id=uuid4(),
            source_form_id="G8eqpU6H",
            source_response_id="response-1",
            received_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            intake_status="READY_FOR_DRAFT_QUOTE",
            detected_location="Rue d'Assas",
            detected_segment="child",
            detected_school_year="2026-2027",
            related_quote_id=None,
            form_config_id=config_id,
            normalized_payload_json={
                "customer_type": "child",
                "parent_first_name": "Pauline",
                "parent_last_name": "Castelnau-Marchand",
                "parent_email": "pauline@example.test",
                "child_first_name": "Victoria",
                "child_last_name": "De Vilmarest",
            },
            warnings_json=[{"message": "A verifier"}],
            blocking_reasons_json=[],
        )
        config = SimpleNamespace(
            configuration_json={"label": "Paris Enfants 2026-2027"},
            source_code="typeform_paris_child_2026_2027_multisite",
            audience_segment="enfants",
            school_year_label="2026-2027",
        )

        row = _intake_list_out_fast(intake, config=config)

        self.assertEqual(row.source_form_label, "Paris Enfants 2026-2027")
        self.assertEqual(row.prospect_label, "Pauline Castelnau-Marchand")
        self.assertEqual(row.child_label, "Victoria De Vilmarest")
        self.assertEqual(row.warnings, ["A verifier"])
        self.assertEqual(row.blockages, [])

    def test_stored_messages_accepts_legacy_string_entries(self) -> None:
        self.assertEqual(
            _stored_messages(["A verifier", {"message": "A verifier"}, {"message": "Autre"}]),
            ["A verifier", "Autre"],
        )

    def test_normalize_payload_extracts_free_text_referral_and_category(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["location"],
                },
                "field_labels": {},
            },
            audience_segment="enfants",
            location_code="paris",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "location", "title": "Lieu du cours souhaité"},
                        "choice": {"label": "Paris 06 - Rue d'Assas"},
                    },
                    {
                        "field": {"id": "referral-free-text", "title": "Famille qui vous a recommandé"},
                        "text": "Famille Martin",
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["referral_referrer_name"], "Famille Martin")
        self.assertEqual(normalized["referral_category"], "PARIS")

    def test_referral_category_distinguishes_home_online_bar_le_duc_and_paris_sites(self) -> None:
        self.assertEqual(referral_category_for_location("Paris 16 - Rue Scheffer"), "PARIS")
        self.assertEqual(referral_category_for_location("Paris 16 - Rue de la Pompe"), "PARIS")
        self.assertEqual(referral_category_for_location("Paris 01 - Rue Richelieu"), "PARIS")
        self.assertEqual(referral_category_for_location("Paris 06 - Rue d'Assas"), "PARIS")
        self.assertEqual(referral_category_for_location("Vidéo Call"), "ONLINE")
        self.assertEqual(referral_category_for_location("Domicile"), "DOMICILE")
        self.assertEqual(referral_category_for_location("Bar-le-Duc"), "BAR_LE_DUC")

    def test_document_template_target_matches_child_segment_aliases(self) -> None:
        child_template = SimpleNamespace(target="enfants", code="quote_child", name="Modele enfants", description="")
        teen_template = SimpleNamespace(target="ados", code="quote_teen", name="Modele ados", description="")

        self.assertTrue(_template_matches_segment_target(child_template, segment="child"))
        self.assertFalse(_template_matches_segment_target(teen_template, segment="child"))

    def test_normalize_payload_falls_back_to_creneau_label_for_slot_preferences(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["requested_location"],
                },
                "field_labels": {},
            },
            audience_segment="eveil",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "requested_location", "title": "Lieu du cours d'initiation"},
                        "choice": {"label": "Paris 1 - Rue de Richelieu"},
                    },
                    {
                        "field": {"id": "94250c22-17f0-47f1-975c-4dbb18656bd8", "title": "Créneau initiation - Rue Richelieu"},
                        "choice": {"label": "Mercredi 15h"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["mercredi"])
        self.assertEqual(normalized["requested_times"], ["15:00"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [
                {
                    "day": "mercredi",
                    "time": "15:00",
                    "location": "Paris 1 - Rue de Richelieu",
                    "segment": "eveil",
                }
            ],
        )

    def test_normalize_payload_falls_back_to_time_row_labels_when_mapping_is_stale(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["requested_location"],
                    # Simulate stale stored field ids that no longer match the live Typeform fields.
                    "requested_days": ["obsolete-requested-days-id"],
                    "requested_times": ["obsolete-requested-times-id"],
                    "requested_slot_preferences": ["obsolete-slot-pref-id"],
                },
                "field_labels": {},
            },
            audience_segment="enfants",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "requested_location", "title": "Lieu du cours souhaite"},
                        "choice": {"label": "Paris 01 - Rue Richelieu"},
                    },
                    {
                        "field": {"id": "000338cf-1", "title": "14h-15h"},
                        "choice": {"label": "Mercredi"},
                    },
                    {
                        "field": {"id": "000338cf-2", "title": "15h-16h"},
                        "choice": {"label": "Mercredi"},
                    },
                    {
                        "field": {"id": "000338cf-3", "title": "16h-17h"},
                        "choice": {"label": "Mercredi"},
                    },
                    {
                        "field": {"id": "000338cf-4", "title": "17h-18h"},
                        "choice": {"label": "Mercredi"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["mercredi"])
        self.assertEqual(normalized["requested_times"], ["14:00", "15:00", "16:00", "17:00"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [
                {
                    "day": "mercredi",
                    "time": "14:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "mercredi",
                    "time": "15:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "mercredi",
                    "time": "16:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "mercredi",
                    "time": "17:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
            ],
        )

    def test_normalize_payload_does_not_mix_solfege_choice_into_main_requested_slots(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["requested_location"],
                    "requested_days": ["obsolete-requested-days-id"],
                    "requested_times": ["obsolete-requested-times-id"],
                    "requested_slot_preferences": ["obsolete-slot-pref-id"],
                },
                "field_labels": {},
            },
            audience_segment="enfants",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "requested_location", "title": "Lieu du cours souhaité"},
                        "choice": {"label": "Paris 01 - Rue Richelieu"},
                    },
                    {
                        "field": {"id": "course-day", "title": "Quel jour souhaitez vous prendre des cours"},
                        "choice": {"label": "samedi"},
                    },
                    {
                        "field": {"id": "course-saturday-hours", "title": "Horaire de nos cours le samedi"},
                        "choices": {"labels": ["14h", "12h", "11h"]},
                    },
                    {
                        "field": {"id": "solfege-level", "title": "Débutants (5 - 6 ans)"},
                        "choice": {"label": "mercredi - 18h05"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["samedi"])
        self.assertEqual(normalized["requested_times"], ["14:00", "12:00", "11:00"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [
                {
                    "day": "samedi",
                    "time": "14:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "samedi",
                    "time": "12:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "samedi",
                    "time": "11:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
            ],
        )
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "mercredi",
                    "time": "18:05",
                    "location": "En ligne",
                    "segment": "enfants",
                }
            ],
        )

    def test_onsite_solfege_without_explicit_slot_does_not_reuse_main_course_preferences(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_scheffer",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "main-day", "title": "Quel jour souhaitez vous prendre des cours"},
                        "choice": {"label": "mardi"},
                    },
                    {
                        "field": {"id": "main-time", "title": "Horaire de nos cours en semaine"},
                        "choice": {"label": "17h"},
                    },
                    {
                        "field": {"id": "onsite-solfege", "title": "Cours de solfège en présentiel"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Débutant - âge 5 ou 6 ans (Niveau 1)"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["mardi"])
        self.assertEqual(normalized["requested_times"], ["17:00"])
        self.assertEqual(normalized["requested_solfege_slot_preferences"], [])
        self.assertTrue(normalized["requested_onsite_solfege"])
        self.assertEqual(normalized["requested_solfege_modality"], "onsite")
        self.assertTrue(
            _should_search_onsite_solfege_without_main_slot_filters(
                line_is_solfege=True,
                line_solfege_modality="onsite",
                solfege_requested_slot_preferences=[],
            )
        )
        self.assertFalse(
            _should_search_onsite_solfege_without_main_slot_filters(
                line_is_solfege=True,
                line_solfege_modality="onsite",
                solfege_requested_slot_preferences=[{"day": "mercredi", "time": "17:00"}],
            )
        )

    def test_normalize_payload_detects_pass_recup_reenrollment_and_solfege_level(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "reenrollment", "title": "S'agit-il d'une réinscription ?"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "pass-rec", "title": "Pass Récup'"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "onsite-solfege", "title": "Cours de solfège en présentiel"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Très bonnes notions de solfège - Niveau 4"},
                    },
                    {
                        "field": {"id": "solfege-slot", "title": "Niveau 4"},
                        "choice": {"label": "jeudi - 18h50"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertTrue(normalized["requested_pass_recup"])
        self.assertTrue(normalized["is_reenrollment"])
        self.assertTrue(normalized["requested_onsite_solfege"])
        self.assertIn("Pass Recup", normalized["requested_products"])
        self.assertIn("Cours de solfege en presentiel", normalized["requested_products"])
        self.assertEqual(normalized["estimated_solfege_level"], "4")
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "jeudi",
                    "time": "18:50",
                    "location": "paris_richelieu",
                    "segment": "enfants",
                }
            ],
        )

    def test_normalize_payload_detects_online_solfege_slot_as_requested_product(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_assas",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "solfege-online-slot", "title": "Solfège en ligne"},
                        "choice": {"label": "mardi - 17h05"},
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Débutant ou une année de solfège et âge > 7 ans (Niveau 2)"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertFalse(normalized["requested_onsite_solfege"])
        self.assertTrue(normalized["requested_online_solfege"])
        self.assertEqual(normalized["requested_solfege_modality"], "online")
        self.assertIn("Cours de solfege en ligne", normalized["requested_products"])
        self.assertEqual(normalized["estimated_solfege_level"], "2")
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "mardi",
                    "time": "17:05",
                    "location": "En ligne",
                    "segment": "enfants",
                }
            ],
        )

    def test_normalize_payload_treats_level_slot_as_online_solfege_when_presentiel_is_false(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_assas",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "onsite-solfege", "title": "Cours de solfège en présentiel"},
                        "boolean": False,
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Très bonnes notions de solfège - Niveau 4"},
                    },
                    {
                        "field": {"id": "solfege-slot", "title": "Niveau 4"},
                        "choice": {"label": "mardi - 17h05"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertFalse(normalized["requested_onsite_solfege"])
        self.assertTrue(normalized["requested_online_solfege"])
        self.assertEqual(normalized["requested_solfege_modality"], "online")
        self.assertIn("Cours de solfege en ligne", normalized["requested_products"])
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "mardi",
                    "time": "17:05",
                    "location": "En ligne",
                    "segment": "enfants",
                }
            ],
        )

    def test_extract_solfege_level_works_with_typeform_slot_without_session_recommendation(self) -> None:
        level = _extract_estimated_solfege_level(
            normalized={
                "estimated_solfege_level": "4",
                "requested_solfege_slot_preferences": [{"day": "mardi", "time": "17:05"}],
                "requested_products": ["Cours de solfege en ligne"],
            },
            session_recommendations=[],
        )

        self.assertEqual(level, "4")

    def test_online_solfege_slot_proposal_does_not_use_main_course_location(self) -> None:
        class FakeScalars:
            def all(self) -> list[object]:
                return [
                    SimpleNamespace(
                        level_code="1",
                        modality="ONLINE",
                        location_id=None,
                        duration_minutes=45,
                        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                ]

        class FakeDb:
            def scalars(self, _stmt: object) -> FakeScalars:
                return FakeScalars()

        proposal = _solfege_slot_proposal_from_normalized(
            FakeDb(),  # type: ignore[arg-type]
            normalized={
                "estimated_solfege_level": "1",
                "requested_solfege_modality": "online",
                "requested_solfege_slot_preferences": [
                    {"day": "mardi", "time": "17:05", "location": "Paris 06 - Rue d'Assas"}
                ],
                "requested_products": ["Cours de solfege en ligne"],
            },
            runtime_context={
                "location_id": str(uuid4()),
                "location_name": "Rue d'Assas",
            },
            session_recommendations=[],
        )

        self.assertEqual(proposal["location_label"], "En ligne")
        self.assertIsNone(proposal["location_id"])
        self.assertNotIn("Assas", str(proposal["label"]))

    def test_option_does_not_mark_other_site_as_preferred_when_location_is_resolved(self) -> None:
        preferred_location_id = uuid4()
        option = _typeform_session_option_from_row(
            session_obj=SimpleNamespace(
                id=uuid4(),
                title="Eveil musical",
                start_at_utc=datetime(2026, 5, 16, 9, 0, tzinfo=timezone.utc),
                end_at_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                timezone="Europe/Paris",
                recurrence_rule="WEEKLY",
                recurrence_group_id=None,
                capacity_max=12,
            ),
            activity=SimpleNamespace(id=uuid4(), name="Eveil musical"),
            location=SimpleNamespace(id=uuid4(), code="BAR_LE_DUC", name="Bar-le-Duc", timezone="Europe/Paris"),
            booked_count=0,
            config=SimpleNamespace(default_location_id=None, location_code="paris_richelieu"),
            requested_location="paris_richelieu",
            resolved_location_id=preferred_location_id,
            requested_slot_preferences=[],
            requested_days=set(),
            requested_times=[],
        )

        self.assertIsNotNone(option)
        assert option is not None
        self.assertNotIn("lieu prefere", option.reasons)

    def test_option_requires_requested_day_when_slot_preferences_are_explicit(self) -> None:
        option = _typeform_session_option_from_row(
            session_obj=SimpleNamespace(
                id=uuid4(),
                title="Eveil musical",
                start_at_utc=datetime(2026, 5, 16, 9, 0, tzinfo=timezone.utc),  # Saturday
                end_at_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                timezone="Europe/Paris",
                recurrence_rule="WEEKLY",
                recurrence_group_id=None,
                capacity_max=12,
            ),
            activity=SimpleNamespace(id=uuid4(), name="Eveil musical"),
            location=SimpleNamespace(id=uuid4(), code="RICHELIEU", name="Rue de Richelieu", timezone="Europe/Paris"),
            booked_count=0,
            config=SimpleNamespace(default_location_id=None, location_code="paris_richelieu"),
            requested_location="Paris 1 - Rue de Richelieu",
            resolved_location_id=uuid4(),
            requested_slot_preferences=[{"day": 2, "time": 900}],  # Wednesday 15:00
            requested_days={2},
            requested_times=[900],
        )

        self.assertIsNone(option)

    def test_collective_teen_adult_activity_matches_fallback_line_label(self) -> None:
        line = SimpleNamespace(
            code="",
            title="Cours collectifs ado/adultes",
            description="",
            meta={
                "typeform_template": {
                    "title": "Cours collectifs ado/adultes",
                }
            },
        )
        activity = SimpleNamespace(
            code="ACT_COURS_COLLECTIFS_ADO_ADULTES_394F7E",
            name="Cours collectif Ado /adultes",
        )

        self.assertTrue(_activity_matches_line_for_slot_fallback(activity, line))  # type: ignore[arg-type]

    def test_should_try_future_school_year_config_when_slots_are_requested_but_no_option_matches(self) -> None:
        should_try = _should_try_future_school_year_config(
            config=SimpleNamespace(source_code="typeform_paris_child_2025_2026_multisite", school_year_label="2025-2026"),
            normalized={
                "requested_slot_preferences": [{"day": "mercredi", "time": "14:00"}],
                "requested_days": ["mercredi"],
                "requested_times": ["14:00"],
            },
            session_recommendations=[],
        )

        self.assertTrue(should_try)

    def test_session_recommendations_have_options_detects_model_options(self) -> None:
        recommendations = [
            SimpleNamespace(
                options=[SimpleNamespace(selection_label="Chaque mercredi · 14:00-15:00")],
                manual_options=[],
            )
        ]

        self.assertTrue(_session_recommendations_have_options(recommendations))

    def test_future_school_year_candidate_configs_prefers_same_family_and_next_year(self) -> None:
        current = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_child_2025_2026_multisite",
            school_year_label="2025-2026",
            location_code="RICHELIEU",
            audience_segment="child",
        )
        next_year = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_child_2026_2027_multisite",
            school_year_label="2026-2027",
            location_code="RICHELIEU",
            audience_segment="child",
            is_active=True,
        )
        wrong_family = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_eveil_2026_2027_multisite",
            school_year_label="2026-2027",
            location_code="RICHELIEU",
            audience_segment="child",
            is_active=True,
        )
        wrong_location = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_child_2026_2027_multisite",
            school_year_label="2026-2027",
            location_code="POMPE",
            audience_segment="child",
            is_active=True,
        )

        class _FakeScalars:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return list(self._rows)

        class _FakeDb:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self, _stmt):
                return _FakeScalars(self._rows)

        rows = [wrong_family, wrong_location, next_year]
        selected = _future_school_year_candidate_configs(_FakeDb(rows), current_config=current)

        self.assertEqual(selected, [next_year])


if __name__ == "__main__":
    unittest.main()
