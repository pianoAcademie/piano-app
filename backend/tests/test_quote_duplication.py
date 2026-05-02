from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import duplicate_quote
from app.models.quote import Quote, QuoteEvent, QuoteLine


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

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)


class QuoteDuplicationTests(unittest.TestCase):
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
            meta={"foo": "bar"},
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
        self.assertEqual(clone.meta.get("duplicated_from"), str(source_id))

        self.assertEqual(duplicated_line.vat_rate, Decimal("20.000"))
        self.assertEqual(duplicated_line.unit_price_ht, Decimal("31.67"))
        self.assertEqual(duplicated_line.unit_vat_amount, Decimal("6.33"))
        self.assertEqual(duplicated_line.amount_ht, Decimal("981.77"))
        self.assertEqual(duplicated_line.amount_vat, Decimal("196.23"))
        self.assertEqual(duplicated_line.amount_ttc, Decimal("1178.00"))
        self.assertEqual(duplicated_line.code, "PIANO_GROUP_ONSITE_1H")

        self.assertEqual(duplicate_event.event_type, "quote_duplicated")
        self.assertEqual(duplicate_event.payload.get("source_quote_id"), str(source_id))


if __name__ == "__main__":
    unittest.main()
