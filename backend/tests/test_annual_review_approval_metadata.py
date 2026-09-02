from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
import unittest
from uuid import uuid4

from app.services.annual_pricing_review import (
    KEY,
    ensure_pricing_review_fingerprint,
    pricing_review_fingerprint,
    quote_fingerprint,
    review_fingerprint_matches,
)


class ApprovalMetadataTests(unittest.TestCase):
    def setUp(self):
        activity_id = uuid4()
        self.quote = SimpleNamespace(
            status="approved",
            school_year_label="2026-2027",
            client_id=uuid4(),
            location_id=uuid4(),
            pricing_catalog_id=uuid4(),
            currency="EUR",
            prospect_id=None,
            total_ttc=Decimal("1912"),
            quote_type="forfait",
            quote_type_id=uuid4(),
            meta={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_id": str(activity_id),
                        "start_time": "19:30",
                        "end_time": "20:15",
                        "selection_pending": False,
                    }
                ],
                "sessions": [],
            },
        )
        self.lines = [
            SimpleNamespace(
                id=uuid4(),
                activity_id=activity_id,
                quantity=26,
                unit_price_ttc=0,
                amount_ttc=0,
                vat_rate=20,
                meta={},
                title="Solfège niveau 3",
                line_type="item",
                pricing_unit="session",
                duration_minutes=45,
                line_category="service",
            )
        ]
        self.expected_fingerprint = quote_fingerprint(self.quote, self.lines)
        self.quote.calendar_snapshot["blocks"][0].update(
            duration_minutes=45,
            pending_slot_options=[],
        )

    def test_redundant_approval_metadata_is_accepted_without_mutation(self):
        before = deepcopy(self.quote.calendar_snapshot)
        self.assertTrue(review_fingerprint_matches(self.quote, self.lines, self.expected_fingerprint))
        self.assertEqual(self.quote.calendar_snapshot, before)

    def test_real_calendar_changes_remain_blocked(self):
        for field, value in [
            ("start_time", "19:00"),
            ("duration_minutes", 90),
            ("selection_pending", True),
            ("pending_slot_options", [{}]),
            ("activity_id", str(uuid4())),
        ]:
            with self.subTest(field=field):
                quote = deepcopy(self.quote)
                quote.calendar_snapshot["blocks"][0][field] = value
                self.assertFalse(review_fingerprint_matches(quote, self.lines, self.expected_fingerprint))

    def test_money_identity_and_line_changes_remain_blocked(self):
        for field, value in [("total_ttc", 1913), ("client_id", uuid4())]:
            with self.subTest(field=field):
                quote = deepcopy(self.quote)
                setattr(quote, field, value)
                self.assertFalse(review_fingerprint_matches(quote, self.lines, self.expected_fingerprint))
        for field, value in [
            ("quantity", 27),
            ("unit_price_ttc", 1),
            ("amount_ttc", 26),
            ("meta", {"discount": 10}),
        ]:
            with self.subTest(field=field):
                lines = deepcopy(self.lines)
                setattr(lines[0], field, value)
                self.assertFalse(review_fingerprint_matches(self.quote, lines, self.expected_fingerprint))

    def test_non_approved_quote_is_not_relaxed(self):
        self.quote.status = "sent"
        self.assertFalse(review_fingerprint_matches(self.quote, self.lines, self.expected_fingerprint))

    def test_exact_fingerprint_still_passes(self):
        current_fingerprint = quote_fingerprint(self.quote, self.lines)
        self.assertTrue(review_fingerprint_matches(self.quote, self.lines, current_fingerprint))

    def test_selected_free_solfege_slot_keeps_pricing_review_current(self):
        quote = deepcopy(self.quote)
        free_block = quote.calendar_snapshot["blocks"][0]
        free_block.update(
            weekday=-1,
            weekday_label="A choisir",
            start_time="",
            end_time="",
            location_id="online-location",
            location_label="Online",
            modality="ONLINE",
            selection_pending=True,
            pending_slot_options=[{"weekday": 2, "start_time": "19:30", "end_time": "20:15"}],
        )
        quote.calendar_snapshot["solfege"] = {"required": True}
        paid_activity_id = uuid4()
        paid_line = SimpleNamespace(
            id=uuid4(),
            activity_id=paid_activity_id,
            quantity=31,
            unit_price_ttc=38,
            amount_ttc=1178,
            vat_rate=20,
            meta={},
            title="Cours collectif",
            line_type="item",
            pricing_unit="session",
            duration_minutes=60,
            line_category="service",
        )
        lines = [*self.lines, paid_line]
        quote.calendar_snapshot["blocks"].append(
            {
                "activity_id": str(paid_activity_id),
                "weekday": 3,
                "start_time": "18:00",
                "end_time": "19:00",
                "location_id": "school-location",
            }
        )
        full_fingerprint = quote_fingerprint(quote, lines)
        pricing_fingerprint = pricing_review_fingerprint(quote, lines)

        free_block.update(
            weekday=2,
            weekday_label="Mercredi",
            start_time="19:30",
            end_time="20:15",
            duration_minutes=45,
            selection_pending=False,
            pending_slot_options=[],
        )
        quote.calendar_snapshot["solfege"]["selected_slot"] = {
            "weekday": 2,
            "start_time": "19:30",
            "end_time": "20:15",
        }

        self.assertNotEqual(full_fingerprint, quote_fingerprint(quote, lines))
        self.assertTrue(
            review_fingerprint_matches(quote, lines, full_fingerprint, pricing_fingerprint)
        )

        quote.calendar_snapshot["blocks"][1]["start_time"] = "18:30"
        self.assertFalse(
            review_fingerprint_matches(quote, lines, full_fingerprint, pricing_fingerprint)
        )

    def test_legacy_review_gets_pricing_fingerprint_before_selection(self):
        self.quote.meta = {KEY: {"fingerprint": self.expected_fingerprint}}
        self.assertTrue(ensure_pricing_review_fingerprint(self.quote, self.lines))
        stored = self.quote.meta[KEY]["pricing_fingerprint"]
        self.assertEqual(stored, pricing_review_fingerprint(self.quote, self.lines))
        self.assertFalse(ensure_pricing_review_fingerprint(self.quote, self.lines))


if __name__ == "__main__":
    unittest.main()
