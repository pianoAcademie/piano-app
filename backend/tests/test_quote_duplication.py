from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _add_duplicated_child_quote_lines,
    _cancel_unselected_quote_variants,
    _create_quote_revision_from_change_request,
    _quote_admin_stats,
    _quote_list_stmt,
    _quote_meta_for_duplicated_child,
    duplicate_quote,
    duplicate_quote_for_child,
)
from app.schemas.quote import QuoteDuplicateForChildRequest
from app.models.quote import Prospect, Quote, QuoteEvent, QuoteLine


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0
        self.refreshed: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_count += 1
        for item in self.added:
            if isinstance(item, Quote) and getattr(item, "id", None) is None:
                item.id = uuid4()

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)

    def scalar(self, _statement: object) -> object | None:
        return None


class QuoteDuplicationTests(unittest.TestCase):
    def test_quote_search_splits_full_name_into_required_tokens(self) -> None:
        statement = _quote_list_stmt(q="  Maxine   Lafon  ")
        compiled = statement.compile()
        parameter_values = set(compiled.params.values())

        self.assertIn("%Maxine%", parameter_values)
        self.assertIn("%Lafon%", parameter_values)
        self.assertEqual(len(statement._where_criteria), 2)

    def test_change_requested_quotes_are_excluded_from_potential_enrollments(self) -> None:
        approved = Quote(
            quote_number="DV-APPROVED",
            context_type="acquisition",
            status="approved",
            meta={},
            calendar_snapshot={"blocks": [{"location_label": "Paris"}]},
        )
        paris_change_request = Quote(
            quote_number="DV-CHANGE-PARIS",
            context_type="acquisition",
            status="change_requested",
            meta={},
            calendar_snapshot={"blocks": [{"location_label": "Paris"}]},
        )
        bld_change_request = Quote(
            quote_number="DV-CHANGE-BLD",
            context_type="acquisition",
            status="change_requested",
            meta={},
            calendar_snapshot={"blocks": [{"location_label": "Bar-le-Duc"}]},
        )

        stats = _quote_admin_stats([approved, paris_change_request, bld_change_request])

        self.assertEqual(stats["changeRequests"], 2)
        self.assertEqual(stats["potentialEnrollments"], 1)
        self.assertEqual(stats["potentialParis"], 1)
        self.assertEqual(stats["potentialBarLeDuc"], 0)

    def test_duplicate_quote_preserves_tax_and_document_fields(self) -> None:
        source_id = uuid4()
        quote_template_id = uuid4()
        quote_template_version_id = uuid4()
        terms_template_id = uuid4()
        terms_template_version_id = uuid4()
        activity_id = uuid4()
        current_user = SimpleNamespace(id=uuid4())
        db = _FakeSession()

        source = SimpleNamespace(
            id=source_id,
            context_type="acquisition",
            quote_type="forfait",
            quote_type_id=uuid4(),
            pricing_catalog_id=uuid4(),
            prospect_id=uuid4(),
            client_id=None,
            location_id=uuid4(),
            legal_entity_id=uuid4(),
            payment_plan_id=uuid4(),
            quote_template_id=quote_template_id,
            quote_template_version_id=quote_template_version_id,
            terms_template_id=terms_template_id,
            terms_template_version_id=terms_template_version_id,
            version_number=2,
            currency="EUR",
            total_ttc=Decimal("1178.00"),
            expiry_days=15,
            school_year_label="2026-2027",
            language="fr",
            vat_rate=Decimal("20.00"),
            estimated_solfege_level="2",
            solfege_duration_minutes=45,
            selected_solfege_slot={"slot": "pending"},
            calendar_snapshot={"blocks": []},
            payment_terms_snapshot={"plan": "monthly"},
            cgv_snapshot={"version": "v1"},
            price_snapshot={"catalog": "2026"},
            meta={
                "foo": "bar",
                "variant_group_id": str(uuid4()),
                "planning_hold_released": True,
            },
        )
        line = SimpleNamespace(
            line_category="service",
            line_type="item",
            master_item_type="activity",
            master_item_id=None,
            activity_id=activity_id,
            product_id=None,
            kit_id=None,
            code="PIANO_GROUP_ONSITE_1H",
            title="Cours collectif",
            description="Cours collectif en presentiel",
            duration_minutes=60,
            pricing_unit="session",
            quantity=Decimal("31.00"),
            vat_rate=Decimal("20.000"),
            unit_price_ht=Decimal("31.67"),
            unit_vat_amount=Decimal("6.33"),
            unit_price_ttc=Decimal("38.00"),
            amount_ht=Decimal("981.77"),
            amount_vat=Decimal("196.23"),
            amount_ttc=Decimal("1178.00"),
            sort_order=0,
            meta={"source": "activity"},
        )

        expected_response = {"quote": {"id": "new-quote"}}

        with patch("app.api.routes.quotes._load_quote", return_value=source), patch(
            "app.api.routes.quotes._load_quote_lines",
            return_value=[line],
        ), patch(
            "app.api.routes.quotes._quote_detail_out",
            return_value=expected_response,
        ), patch(
            "app.api.routes.quotes._new_quote_number",
            return_value="DV-TEST-DUPLICATE",
        ):
            result = duplicate_quote(source_id, db=db, current_user=current_user)

        self.assertEqual(result, expected_response)
        self.assertEqual(db.flush_count, 1)
        self.assertEqual(db.commit_count, 1)

        clone = next(item for item in db.added if isinstance(item, Quote))
        duplicated_line = next(item for item in db.added if isinstance(item, QuoteLine))
        duplicate_event = next(item for item in db.added if isinstance(item, QuoteEvent))

        self.assertEqual(clone.quote_template_id, quote_template_id)
        self.assertEqual(clone.quote_template_version_id, quote_template_version_id)
        self.assertEqual(clone.terms_template_id, terms_template_id)
        self.assertEqual(clone.terms_template_version_id, terms_template_version_id)
        self.assertEqual(clone.language, "fr")
        self.assertEqual(clone.vat_rate, Decimal("20.00"))
        self.assertEqual(clone.parent_quote_id, source_id)
        self.assertEqual(clone.version_number, 3)
        self.assertIsNone(clone.expires_at)
        self.assertEqual(clone.meta.get("duplicated_from"), str(source_id))
        self.assertNotIn("variant_group_id", clone.meta)
        self.assertNotIn("planning_hold_released", clone.meta)

        self.assertEqual(duplicated_line.vat_rate, Decimal("20.000"))
        self.assertEqual(duplicated_line.unit_price_ht, Decimal("31.67"))
        self.assertEqual(duplicated_line.unit_vat_amount, Decimal("6.33"))
        self.assertEqual(duplicated_line.amount_ht, Decimal("981.77"))
        self.assertEqual(duplicated_line.amount_vat, Decimal("196.23"))
        self.assertEqual(duplicated_line.amount_ttc, Decimal("1178.00"))
        self.assertEqual(duplicated_line.code, "PIANO_GROUP_ONSITE_1H")

        self.assertEqual(duplicate_event.event_type, "quote_duplicated")
        self.assertEqual(duplicate_event.payload.get("source_quote_id"), str(source_id))

    def test_duplicate_as_variant_links_quotes_without_releasing_the_shared_hold(self) -> None:
        source_id = uuid4()
        current_user = SimpleNamespace(id=uuid4())
        db = _FakeSession()
        source = Quote(
            id=source_id,
            quote_number="DV-SOURCE",
            context_type="acquisition",
            quote_type="forfait",
            status="sent",
            version_number=1,
            currency="EUR",
            total_ttc=Decimal("1200.00"),
            expiry_days=10,
            meta={"foo": "bar"},
        )
        expected_response = {"quote": {"id": "variant"}}

        with patch("app.api.routes.quotes._load_quote", return_value=source), patch(
            "app.api.routes.quotes._load_quote_lines", return_value=[]
        ), patch("app.api.routes.quotes._quote_detail_out", return_value=expected_response), patch(
            "app.api.routes.quotes._new_quote_number", return_value="DV-VARIANT"
        ):
            result = duplicate_quote(source_id, as_variant=True, db=db, current_user=current_user)

        clone = next(item for item in db.added if isinstance(item, Quote) and item is not source)
        group_id = source.meta.get("variant_group_id")
        self.assertEqual(result, expected_response)
        self.assertTrue(group_id)
        self.assertEqual(clone.meta.get("variant_group_id"), group_id)
        self.assertEqual(clone.meta.get("variant_of_quote_id"), str(source_id))
        self.assertNotIn("planning_hold_released", source.meta)
        self.assertNotIn("planning_hold_released", clone.meta)
        self.assertIn(
            "quote_variant_created",
            {item.event_type for item in db.added if isinstance(item, QuoteEvent)},
        )

    def test_approving_variant_cancels_other_pending_variants(self) -> None:
        group_id = str(uuid4())
        selected = Quote(
            id=uuid4(),
            quote_number="DV-A",
            context_type="acquisition",
            status="sent",
            meta={"variant_group_id": group_id},
        )
        sibling = Quote(
            id=uuid4(),
            quote_number="DV-B",
            context_type="acquisition",
            status="sent",
            meta={"variant_group_id": group_id},
        )
        db = _FakeSession()
        now = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)

        cancelled = _cancel_unselected_quote_variants(
            db,
            selected=selected,
            variants=[selected, sibling],
            cancelled_at=now,
        )

        self.assertEqual(cancelled, [sibling])
        self.assertEqual(sibling.status, "cancelled")
        self.assertEqual(sibling.cancelled_at, now)
        self.assertIs(sibling.meta.get("planning_hold_released"), True)
        self.assertEqual(sibling.meta.get("variant_selected_quote_id"), str(selected.id))
        event = next(item for item in db.added if isinstance(item, QuoteEvent))
        self.assertEqual(event.event_type, "quote_variant_cancelled")

    def test_variant_cannot_be_approved_after_another_variant(self) -> None:
        group_id = str(uuid4())
        selected = Quote(
            id=uuid4(),
            quote_number="DV-B",
            context_type="acquisition",
            status="sent",
            meta={"variant_group_id": group_id},
        )
        approved = Quote(
            id=uuid4(),
            quote_number="DV-A",
            context_type="acquisition",
            status="approved",
            meta={"variant_group_id": group_id},
        )
        db = _FakeSession()

        with self.assertRaises(HTTPException) as raised:
            _cancel_unselected_quote_variants(
                db,
                selected=selected,
                variants=[selected, approved],
                cancelled_at=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(selected.status, "sent")

    def test_change_request_revision_creates_editable_draft_and_locks_source(self) -> None:
        source_id = uuid4()
        now = datetime(2026, 5, 18, 10, 30, tzinfo=timezone.utc)
        db = _FakeSession()
        source = Quote(
            id=source_id,
            quote_number="DV-SOURCE",
            context_type="acquisition",
            quote_type="forfait",
            quote_type_id=uuid4(),
            pricing_catalog_id=uuid4(),
            prospect_id=uuid4(),
            client_id=None,
            location_id=uuid4(),
            legal_entity_id=uuid4(),
            payment_plan_id=uuid4(),
            quote_template_id=uuid4(),
            quote_template_version_id=uuid4(),
            terms_template_id=uuid4(),
            terms_template_version_id=uuid4(),
            status="change_requested",
            version_number=1,
            currency="EUR",
            total_ttc=Decimal("1432.00"),
            expiry_days=10,
            school_year_label="2026-2027",
            language="fr",
            vat_rate=Decimal("20.00"),
            selected_solfege_slot={},
            calendar_snapshot={"sessions": []},
            payment_terms_snapshot={"schedule": []},
            cgv_snapshot={"version": "Bar-le-Duc"},
            price_snapshot={"total_ttc": "1432.00"},
            meta={
                "recipient_email": "parent@example.com",
                "public_response_last_action": "change_requested",
                "public_response_last_message": "Changer le creneau",
            },
            document_status="frozen",
        )
        line = QuoteLine(
            quote_id=source_id,
            line_category="service",
            line_type="item",
            code="PIANO",
            title="Cours",
            quantity=Decimal("32.00"),
            amount_ttc=Decimal("1216.00"),
            meta={"source": "activity"},
        )

        with patch("app.api.routes.quotes._new_quote_number", return_value="DV-REVISION"):
            clone = _create_quote_revision_from_change_request(
                db,
                source=source,
                lines=[line],
                message="Changer le creneau",
                requested_at=now,
            )

        copied_line = next(item for item in db.added if isinstance(item, QuoteLine))
        events = [item for item in db.added if isinstance(item, QuoteEvent)]

        self.assertEqual(clone.status, "created")
        self.assertEqual(clone.document_status, "stale")
        self.assertEqual(clone.parent_quote_id, source_id)
        self.assertEqual(clone.version_number, 2)
        self.assertIsNone(clone.expires_at)
        self.assertEqual(clone.meta.get("revision_reason"), "public_change_request")
        self.assertIs(clone.meta.get("planning_hold_released"), True)
        self.assertNotIn("public_response_last_action", clone.meta)
        self.assertEqual(source.status, "replaced")
        self.assertEqual(source.meta.get("change_request_revision_quote_id"), str(clone.id))
        self.assertEqual(source.meta.get("change_request_revision_quote_number"), "DV-REVISION")
        self.assertEqual(source.meta.get("replaced_by_quote_id"), str(clone.id))
        self.assertEqual(source.meta.get("replaced_by_quote_number"), "DV-REVISION")
        self.assertIs(source.meta.get("planning_hold_released"), True)
        self.assertEqual(copied_line.quote_id, clone.id)
        replaced_event = next(event for event in events if event.event_type == "quote_replaced")
        self.assertEqual(replaced_event.payload.get("replacement_quote_id"), str(clone.id))
        self.assertIs(replaced_event.payload.get("planning_slots_released"), True)
        self.assertIn("quote_change_request_revision_created", {event.event_type for event in events})
        self.assertIn("quote_created_from_change_request", {event.event_type for event in events})

    def test_duplicate_quote_for_child_creates_sibling_prospect_and_quote(self) -> None:
        source_id = uuid4()
        parent_id = uuid4()
        source_child_id = uuid4()
        current_user = SimpleNamespace(id=uuid4())
        db = _FakeSession()

        source = SimpleNamespace(
            id=source_id,
            context_type="acquisition",
            quote_type="forfait",
            quote_type_id=uuid4(),
            pricing_catalog_id=uuid4(),
            prospect_id=source_child_id,
            client_id=None,
            location_id=uuid4(),
            legal_entity_id=uuid4(),
            payment_plan_id=uuid4(),
            quote_template_id=uuid4(),
            quote_template_version_id=uuid4(),
            terms_template_id=uuid4(),
            terms_template_version_id=uuid4(),
            version_number=1,
            currency="EUR",
            total_ttc=Decimal("1534.00"),
            expiry_days=10,
            school_year_label="2026-2027",
            language="fr",
            vat_rate=Decimal("20.00"),
            estimated_solfege_level="1",
            solfege_duration_minutes=45,
            selected_solfege_slot={"weekday": 1, "start_time": "17:05"},
            calendar_snapshot={"blocks": [{"activity_label": "Cours collectif"}]},
            payment_terms_snapshot={"schedule": []},
            cgv_snapshot={"version": "v1"},
            price_snapshot={"total_ttc": "1534.00"},
            meta={"foo": "bar"},
        )
        parent = SimpleNamespace(
            id=parent_id,
            first_name="Pauline",
            last_name="Castelnau-Marchand",
            email="pauline@example.com",
            phone="+33600000000",
            meta={"adult_address": "10 Rue Vavin"},
        )
        source_child = SimpleNamespace(id=source_child_id)
        line = SimpleNamespace(
            line_category="service",
            line_type="item",
            master_item_type="activity",
            master_item_id=None,
            activity_id=uuid4(),
            product_id=None,
            kit_id=None,
            code="PIANO_GROUP_ONSITE_1H",
            title="Cours collectif",
            description=None,
            duration_minutes=60,
            pricing_unit="session",
            quantity=Decimal("33.00"),
            vat_rate=Decimal("20.000"),
            unit_price_ht=Decimal("31.67"),
            unit_vat_amount=Decimal("6.33"),
            unit_price_ttc=Decimal("38.00"),
            amount_ht=Decimal("1045.11"),
            amount_vat=Decimal("208.89"),
            amount_ttc=Decimal("1254.00"),
            sort_order=0,
            meta={"source": "activity"},
        )
        expected_response = {"quote": {"id": "new-child-quote"}}

        with patch("app.api.routes.quotes._load_quote", return_value=source), patch(
            "app.api.routes.quotes._load_quote_lines",
            return_value=[line],
        ), patch(
            "app.api.routes.quotes._quote_source_parent_for_sibling",
            return_value=(parent, source_child),
        ), patch(
            "app.api.routes.quotes._quote_detail_out",
            return_value=expected_response,
        ), patch(
            "app.api.routes.quotes._new_quote_number",
            return_value="DV-TEST-SIBLING",
        ), patch("app.api.routes.quotes.ensure_referral_for_sibling_quote") as ensure_referral:
            result = duplicate_quote_for_child(
                source_id,
                QuoteDuplicateForChildRequest(
                    first_name="Archibald",
                    last_name="De Vilmarest",
                    birth_date="2020-08-07",
                    notes="Mentionne dans le Typeform de Victoria",
                ),
                db=db,
                current_user=current_user,
            )

        self.assertEqual(result, expected_response)

        child = next(item for item in db.added if isinstance(item, Prospect))
        clone = next(item for item in db.added if isinstance(item, Quote))
        duplicate_event = next(item for item in db.added if isinstance(item, QuoteEvent))

        self.assertEqual(child.first_name, "Archibald")
        self.assertEqual(child.last_name, "De Vilmarest")
        self.assertEqual(child.email, "pauline@example.com")
        self.assertEqual(child.parent_prospect_id, parent_id)
        self.assertEqual(child.meta["prospect_type"], "child")
        self.assertEqual(child.meta["child"]["birth_date"], "2020-08-07")

        self.assertEqual(clone.prospect_id, child.id)
        self.assertIsNone(clone.client_id)
        self.assertEqual(clone.parent_quote_id, source_id)
        self.assertIsNone(clone.expires_at)
        self.assertEqual(clone.meta.get("duplicated_for_child_name"), "Archibald De Vilmarest")
        ensure_referral.assert_called_once_with(
            db,
            source_quote_id=source_id,
            sibling_quote_id=clone.id,
            sibling_prospect_id=child.id,
        )
        self.assertEqual(duplicate_event.event_type, "quote_duplicated_for_child")

    def test_duplicate_quote_for_child_rewrites_typeform_child_identity(self) -> None:
        source_id = uuid4()
        child_id = uuid4()
        source_meta = {
            "source": "typeform_intake",
            "annual_pricing_review": {"student_id": str(uuid4()), "decisions": [{"line_id": str(uuid4())}]},
            "recipient_email": "parent@example.com",
            "typeform_intake": {
                "intake_id": str(uuid4()),
                "normalized_payload": {
                    "parent_first_name": "Angela",
                    "parent_last_name": "Zghun",
                    "parent_email": "parent@example.com",
                    "child_first_name": "Marco",
                    "child_last_name": "NORMA",
                    "child_full_name": "Marco NORMA",
                    "child_birth_date": "2018-02-06",
                    "requested_times": ["18:00"],
                },
            },
        }

        meta = _quote_meta_for_duplicated_child(
            source_meta,
            child_first_name="Camila",
            child_last_name="NORMA",
            child_birth_date="2014-04-18",
            extra={
                "duplicated_from": str(source_id),
                "duplicated_for_child_client_id": str(child_id),
                "duplicated_for_child_name": "Camila NORMA",
            },
        )

        normalized = meta["typeform_intake"]["normalized_payload"]
        self.assertEqual(normalized["parent_first_name"], "Angela")
        self.assertEqual(normalized["child_first_name"], "Camila")
        self.assertEqual(normalized["child_last_name"], "NORMA")
        self.assertEqual(normalized["child_full_name"], "Camila NORMA")
        self.assertEqual(normalized["child_birth_date"], "2014-04-18")
        self.assertEqual(normalized["requested_times"], ["18:00"])
        self.assertEqual(meta["duplicated_from"], str(source_id))
        self.assertEqual(meta["duplicated_for_child_client_id"], str(child_id))
        self.assertNotIn("annual_pricing_review", meta)

    def test_duplicate_child_lines_drop_source_pricing_audit_and_remap_line_planning_key(self) -> None:
        source_line_id = uuid4()
        activity_id = uuid4()
        source_key = f"{activity_id}:line:{source_line_id}"
        source_line = SimpleNamespace(
            id=source_line_id,
            line_category="service",
            line_type="item",
            master_item_type="activity",
            master_item_id=None,
            activity_id=activity_id,
            product_id=None,
            kit_id=None,
            code="PIANO_GROUP_ONSITE_1H",
            title="Cours collectif",
            description=None,
            duration_minutes=60,
            pricing_unit="session",
            quantity=Decimal("33.00"),
            vat_rate=Decimal("20.000"),
            unit_price_ht=Decimal("31.67"),
            unit_vat_amount=Decimal("6.33"),
            unit_price_ttc=Decimal("38.00"),
            amount_ht=Decimal("1045.11"),
            amount_vat=Decimal("208.89"),
            amount_ttc=Decimal("1254.00"),
            sort_order=0,
            meta={
                "recommendation_key": source_key,
                "annual_course_key": str(source_line_id),
                "annual_decision": {"line_id": str(source_line_id)},
            },
        )
        clone = Quote(
            id=uuid4(),
            quote_number="DV-CHILD",
            context_type="acquisition",
            status="created",
            calendar_snapshot={
                "blocks": [{"activity_id": str(activity_id), "recommendation_key": source_key}],
                "sessions": [{"activity_id": str(activity_id), "recommendation_key": source_key}],
            },
        )
        db = _FakeSession()

        _add_duplicated_child_quote_lines(
            db,
            source_lines=[source_line],
            clone=clone,
            now=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )

        copied = next(item for item in db.added if isinstance(item, QuoteLine))
        copied_key = copied.meta["recommendation_key"]
        self.assertNotEqual(copied_key, source_key)
        self.assertIn(str(copied.id), copied_key)
        self.assertNotIn("annual_course_key", copied.meta)
        self.assertNotIn("annual_decision", copied.meta)
        self.assertEqual(clone.calendar_snapshot["blocks"][0]["recommendation_key"], copied_key)
        self.assertEqual(clone.calendar_snapshot["sessions"][0]["recommendation_key"], copied_key)


if __name__ == "__main__":
    unittest.main()
