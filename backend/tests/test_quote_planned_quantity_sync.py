from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _split_aggregated_planned_quote_lines,
    _sync_typeform_planned_quote_line_quantities,
)
from fastapi import HTTPException
from app.models.quote import QuoteLine
from app.services.quotes.line_sessions import normalize_duplicate_planning_group_keys, resolve_line_sessions
from app.services.quotes.quote_documents import _calendar_snapshot_with_line_recommendation_keys


def _line(*, activity_id, quantity: str, automatic_key: str | None = None, planned: bool = True):
    meta: dict[str, object] = {}
    if automatic_key:
        meta["typeform_automatic_line"] = automatic_key
    if planned:
        meta["typeform_planned_quantity_applied"] = True
        meta["typeform_planned_quantity"] = quantity
    return SimpleNamespace(
        id=uuid4(),
        activity_id=activity_id,
        line_category="service",
        line_type="item",
        pricing_unit="session",
        quantity=Decimal(quantity),
        unit_price_ht=Decimal("18.33"),
        unit_vat_amount=Decimal("3.67"),
        amount_ht=Decimal("0.00"),
        amount_vat=Decimal("0.00"),
        amount_ttc=Decimal("0.00"),
        meta=meta,
        updated_at=None,
    )


class QuotePlannedQuantitySyncTests(unittest.TestCase):
    def kenza(self):
        activity = uuid4()
        first = _line(activity_id=activity, quantity="63.00")
        second = _line(activity_id=activity, quantity="31.00", automatic_key="second_piano_course")
        first.unit_price_ht, first.unit_vat_amount = Decimal("31.67"), Decimal("6.33")
        second.unit_price_ht, second.unit_vat_amount = Decimal("26.67"), Decimal("5.33")
        old_key = f"{activity}:line:{uuid4()}"
        second_key = f"{activity}:second_piano_course"
        snapshot = {"blocks": [{"activity_id":str(activity), "recommendation_key":key} for key in (old_key, second_key)],
                    "sessions": [{"activity_id":str(activity), "recommendation_key":key, "date":f"session-{i}"}
                                 for key, count in ((old_key,32),(second_key,31)) for i in range(count)]}
        return first, second, snapshot, old_key

    def test_kenza_primary_is_32_not_63_and_repeated_save_is_stable(self):
        first, second, snapshot, old_key = self.kenza()
        self.assertTrue(_sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot))
        self.assertEqual((first.quantity,second.quantity),(Decimal(32),Decimal(31)))
        self.assertEqual(first.amount_ttc + second.amount_ttc + Decimal(305), Decimal(2513))
        self.assertEqual(first.meta["recommendation_key"],old_key)
        self.assertFalse(_sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot))
        # The editor can recreate database rows: saved group identity must survive.
        first.id,second.id = uuid4(),uuid4()
        self.assertFalse(_sync_typeform_planned_quote_line_quantities([second,first],calendar_snapshot=snapshot))
        hydrated = _calendar_snapshot_with_line_recommendation_keys(None,snapshot,lines=[second,first])
        self.assertEqual(hydrated['blocks'][0]['recommendation_key'],old_key)
        self.assertEqual({id(l):len(s) for l,s,_ in resolve_line_sessions([first,second],hydrated)}, {id(first):32,id(second):31})

    def test_explicit_line_key_overrides_automatic_tag(self):
        first,second,snapshot,old_key = self.kenza()
        first.meta.update(recommendation_key=old_key,typeform_automatic_line="legacy-primary")
        _sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot)
        self.assertEqual(first.quantity,32)

    def test_unknown_explicit_key_blocks_instead_of_falling_back(self):
        first,second,snapshot,_ = self.kenza()
        first.meta['recommendation_key']='missing-group'
        with self.assertRaises(HTTPException) as error:
            _sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot)
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(first.quantity,63)
        self.assertEqual(second.meta.get('recommendation_key'),None)

    def test_two_unmatched_lines_never_use_order_or_price_to_guess(self):
        first,second,snapshot,_ = self.kenza()
        second.meta.pop('typeform_automatic_line')
        with self.assertRaises(HTTPException):
            _sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot)
        self.assertEqual(first.quantity,63)

    def test_same_group_cannot_pay_two_lines(self):
        first,second,snapshot,old_key = self.kenza()
        first.meta['recommendation_key']=old_key
        second.meta['recommendation_key']=old_key
        with self.assertRaises(HTTPException):
            _sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot)

    def test_generic_group_is_not_activity_aggregate_when_second_group_exists(self):
        first,second,snapshot,old_key = self.kenza()
        for session in snapshot['sessions']:
            if session['recommendation_key']==old_key:
                session['recommendation_key']=str(first.activity_id)
        _sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot)
        self.assertEqual(first.quantity,32)

    def test_manual_second_course_is_not_modified_or_absorbed(self):
        first,second,snapshot,_ = self.kenza()
        second.meta['typeform_planned_quantity_applied']=False
        second.quantity=Decimal(25)
        _sync_typeform_planned_quote_line_quantities([first,second],calendar_snapshot=snapshot)
        self.assertEqual((first.quantity,second.quantity),(Decimal(32),Decimal(25)))

    def test_single_legacy_line_can_cover_multiple_groups(self):
        first,_,snapshot,_ = self.kenza()
        _sync_typeform_planned_quote_line_quantities([first],calendar_snapshot=snapshot)
        self.assertEqual(first.quantity,63)

    def test_realigns_intake_line_to_final_planning_count(self) -> None:
        activity_id = uuid4()
        line = _line(
            activity_id=activity_id,
            quantity="29.00",
            automatic_key="online_solfege",
        )
        recommendation_key = f"{activity_id}:online_solfege"
        snapshot = {
            "sessions": [
                {
                    "activity_id": str(activity_id),
                    "recommendation_key": recommendation_key,
                    "date": f"2027-01-{day:02d}",
                }
                for day in range(1, 27)
            ]
        }

        changed = _sync_typeform_planned_quote_line_quantities([line], calendar_snapshot=snapshot)

        self.assertTrue(changed)
        self.assertEqual(line.quantity, Decimal("26.00"))
        self.assertEqual(line.amount_ht, Decimal("476.58"))
        self.assertEqual(line.amount_vat, Decimal("95.42"))
        self.assertEqual(line.amount_ttc, Decimal("572.00"))
        self.assertEqual(line.meta["typeform_planned_quantity"], "26.00")

    def test_keeps_manual_line_quantity_unchanged(self) -> None:
        activity_id = uuid4()
        line = _line(activity_id=activity_id, quantity="29.00", planned=False)
        snapshot = {
            "sessions": [
                {"activity_id": str(activity_id), "date": f"2027-02-{day:02d}"}
                for day in range(1, 27)
            ]
        }

        changed = _sync_typeform_planned_quote_line_quantities([line], calendar_snapshot=snapshot)

        self.assertFalse(changed)
        self.assertEqual(line.quantity, Decimal("29.00"))

    def test_uses_recommendation_key_for_duplicate_activity_lines(self) -> None:
        activity_id = uuid4()
        first = _line(activity_id=activity_id, quantity="5.00", automatic_key="first")
        second = _line(activity_id=activity_id, quantity="5.00", automatic_key="second")
        snapshot = {
            "sessions": [
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:first"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:first"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:second"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:second"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:second"},
            ]
        }

        changed = _sync_typeform_planned_quote_line_quantities([first, second], calendar_snapshot=snapshot)

        self.assertTrue(changed)
        self.assertEqual(first.quantity, Decimal("2.00"))
        self.assertEqual(second.quantity, Decimal("3.00"))

    def test_splits_one_aggregate_line_into_two_planning_series(self) -> None:
        activity_id = uuid4()
        quote_id = uuid4()
        aggregate = QuoteLine(
            quote_id=quote_id,
            line_category="service",
            line_type="item",
            activity_id=activity_id,
            title="Cours de piano collectif en presentiel (1h)",
            pricing_unit="session",
            quantity=Decimal("65.00"),
            vat_rate=Decimal("20.000"),
            unit_price_ht=Decimal("31.67"),
            unit_vat_amount=Decimal("6.33"),
            unit_price_ttc=Decimal("38.00"),
            amount_ht=Decimal("2058.55"),
            amount_vat=Decimal("411.45"),
            amount_ttc=Decimal("2470.00"),
            sort_order=0,
            meta={
                "recommendation_key": str(activity_id),
                "typeform_planned_quantity_applied": True,
                "typeform_planned_quantity": "65.00",
            },
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "series_key": "tuesday-series",
                    "recommendation_key": str(activity_id),
                    "weekday": 1,
                    "start_time": "18:00",
                },
                {
                    "activity_id": str(activity_id),
                    "series_key": "thursday-series",
                    "weekday": 3,
                    "start_time": "18:00",
                },
            ],
            "sessions": [
                {
                    "activity_id": str(activity_id),
                    "series_key": series_key,
                    "recommendation_key": str(activity_id),
                    "date": f"session-{series_key}-{index}",
                }
                for series_key, count in (("tuesday-series", 33), ("thursday-series", 32))
                for index in range(count)
            ],
        }
        normalized, changed = normalize_duplicate_planning_group_keys(snapshot)

        class FakeDb:
            def __init__(self):
                self.added = []

            def add(self, row):
                self.added.append(row)

            def flush(self):
                return None

        db = FakeDb()
        split_lines, split = _split_aggregated_planned_quote_lines(
            db,
            [aggregate],
            calendar_snapshot=normalized,
        )

        self.assertTrue(changed)
        self.assertTrue(split)
        self.assertEqual([line.quantity for line in split_lines], [Decimal("33.00"), Decimal("32.00")])
        self.assertEqual([line.amount_ttc for line in split_lines], [Decimal("1254.00"), Decimal("1216.00")])
        self.assertEqual(sum((line.amount_ttc for line in split_lines), Decimal("0.00")), Decimal("2470.00"))
        self.assertEqual(len({line.meta["recommendation_key"] for line in split_lines}), 2)
        self.assertEqual(len(db.added), 1)


if __name__ == "__main__":
    unittest.main()
