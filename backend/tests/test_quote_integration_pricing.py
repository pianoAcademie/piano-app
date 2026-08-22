from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    QUOTE_ANNUAL_INVOICE_PERIOD_END,
    QUOTE_ANNUAL_INVOICE_PERIOD_START,
    _quote_annual_invoice_amounts,
    _quote_annual_invoice_selected_payments,
    _create_followup_annual_invoices,
    _quote_per_course_discounts_by_schedule_key,
)


def _service(*, activity_id, quantity: str, amount: str, second: bool = False):
    return SimpleNamespace(
        id=uuid4(),
        activity_id=activity_id,
        line_category="service",
        line_type="item",
        quantity=quantity,
        amount_ttc=amount,
        meta={
            "typeform_second_course": second,
            "typeform_automatic_line": "second_piano_course" if second else None,
        },
    )


def _discount(*, title: str, quantity: str, amount: str, code: str):
    return SimpleNamespace(
        id=uuid4(),
        activity_id=None,
        line_category="product",
        line_type="discount",
        title=title,
        quantity=quantity,
        amount_ttc=amount,
        meta={"discount_rule_code": code},
    )


class QuoteIntegrationPricingTests(unittest.TestCase):
    def test_annual_invoice_metadata_freezes_quote_lines_period_and_deposit(self) -> None:
        class _FakeScalars:
            def all(self):
                return []

        class _FakeSession:
            def scalars(self, _statement):
                return _FakeScalars()

            def flush(self):
                return None

        seller_id = uuid4()
        booking_id = uuid4()
        manual_id = uuid4()
        deposit_payment_id = uuid4()
        note_id = uuid4()
        quote = SimpleNamespace(
            id=uuid4(),
            quote_number="DV-TEST-ANNUAL",
            legal_entity_id=seller_id,
            school_year_label="2026-2027",
        )
        student = SimpleNamespace(id=uuid4(), first_name="Lina", last_name="Martin", email="lina@example.test")
        billing = SimpleNamespace(id=uuid4())
        actor = SimpleNamespace(id=uuid4())
        payments = [
            SimpleNamespace(
                id=booking_id,
                source="BOOKING",
                occurred_at=datetime(2026, 9, 3, 16, tzinfo=timezone.utc),
                total_incl_vat=Decimal("1188.00"),
                currency="EUR",
                seller_legal_entity_id=seller_id,
                billing_entity="PIANO_ACADEMIE",
            ),
            SimpleNamespace(
                id=manual_id,
                source="MANUAL",
                occurred_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
                total_incl_vat=Decimal("280.00"),
                currency="EUR",
                seller_legal_entity_id=seller_id,
                billing_entity="PIANO_ACADEMIE",
            ),
        ]
        deposit_payment = SimpleNamespace(
            id=deposit_payment_id,
            currency="EUR",
            total_incl_vat=Decimal("-200.00"),
        )
        captured_messages: list[str] = []

        def create_note(*_args, **kwargs):
            captured_messages.append(kwargs["message"])
            return SimpleNamespace(id=note_id)

        with patch("app.api.routes.quotes._build_admin_client_payments", return_value=payments), patch(
            "app.api.routes.quotes._quote_annual_invoice_applied_deposit_payments",
            return_value=[deposit_payment],
        ), patch(
            "app.api.routes.quotes._invoice_recipient_snapshot_for_client",
            return_value={"client_name": "Parent Martin", "client_billing_address": "1 rue de Paris"},
        ), patch(
            "app.api.routes.quotes._allocate_invoice_number_for_seller_entity",
            return_value="PA26-TEST",
        ), patch(
            "app.api.routes.quotes.build_company_identity_snapshot",
            return_value={"legal_name": "PIANO ACADEMIE"},
        ), patch(
            "app.api.routes.quotes._create_client_note",
            side_effect=create_note,
        ), patch(
            "app.api.routes.quotes._persist_invoice_lines_for_note",
        ) as persist_lines:
            created_invoice_note_ids: list[object] = []
            result = _create_followup_annual_invoices(
                _FakeSession(),
                quote=quote,
                student=student,
                billing=billing,
                current_user=actor,
                booking_ids=[booking_id],
                transaction_ids=[manual_id],
                deposit_invoice_note_id=uuid4(),
                created_invoice_note_ids=created_invoice_note_ids,
            )

        self.assertEqual(result, [note_id])
        self.assertEqual(created_invoice_note_ids, [note_id])
        self.assertEqual(
            {row.id for row in persist_lines.call_args.kwargs["payments"]},
            {booking_id, manual_id},
        )
        metadata = json.loads(captured_messages[0].split("INVOICE_RANGE::", 1)[1])
        self.assertEqual(metadata["start_date"], "2026-08-01")
        self.assertEqual(metadata["end_date"], "2027-06-30")
        self.assertEqual(metadata["layout"], "COMPILED")
        self.assertEqual(metadata["auto_layout_style"], "CONDENSED")
        self.assertEqual(metadata["totals_by_currency"], {"EUR": "1468.00"})
        self.assertEqual(metadata["applied_payment_totals_by_currency"], {"EUR": "-200.00"})
        self.assertEqual(metadata["total_to_pay_by_currency"], {"EUR": "1268.00"})
        self.assertEqual(metadata["source_quote_id"], str(quote.id))
        self.assertTrue(metadata["annual_invoice_auto_generated"])

    def test_annual_invoice_selects_all_quote_items_in_the_fixed_school_period(self) -> None:
        booking_before = uuid4()
        booking_first_day = uuid4()
        booking_last_day = uuid4()
        booking_after = uuid4()
        manual_item = uuid4()
        unrelated_manual = uuid4()
        payments = [
            SimpleNamespace(
                id=booking_before,
                source="BOOKING",
                occurred_at=datetime(2026, 7, 31, 12, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=booking_first_day,
                source="BOOKING",
                occurred_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=booking_last_day,
                source="BOOKING",
                occurred_at=datetime(2027, 6, 30, 12, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=booking_after,
                source="BOOKING",
                occurred_at=datetime(2027, 7, 1, 12, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=manual_item,
                source="MANUAL",
                occurred_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=unrelated_manual,
                source="MANUAL",
                occurred_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
            ),
        ]

        selected = _quote_annual_invoice_selected_payments(
            payments,
            booking_ids={booking_before, booking_first_day, booking_last_day, booking_after},
            transaction_ids={manual_item},
        )

        self.assertEqual(QUOTE_ANNUAL_INVOICE_PERIOD_START.isoformat(), "2026-08-01")
        self.assertEqual(QUOTE_ANNUAL_INVOICE_PERIOD_END.isoformat(), "2027-06-30")
        self.assertEqual({row.id for row in selected}, {booking_first_day, booking_last_day, manual_item})

    def test_annual_invoice_deducts_the_paid_deposit_from_the_amount_due(self) -> None:
        payments = [
            SimpleNamespace(currency="EUR", total_incl_vat=Decimal("1188.00")),
            SimpleNamespace(currency="EUR", total_incl_vat=Decimal("280.00")),
        ]
        deposit_payments = [
            SimpleNamespace(currency="EUR", total_incl_vat=Decimal("-200.00")),
        ]

        totals, applied, total_to_pay = _quote_annual_invoice_amounts(
            payments,
            applied_payments=deposit_payments,
        )

        self.assertEqual(totals, {"EUR": Decimal("1468.00")})
        self.assertEqual(applied, {"EUR": Decimal("-200.00")})
        self.assertEqual(total_to_pay, {"EUR": Decimal("1268.00")})

    def test_discounts_are_assigned_to_one_schedule_only(self) -> None:
        activity_id = uuid4()
        primary = _service(activity_id=activity_id, quantity="33", amount="1254")
        second = _service(activity_id=activity_id, quantity="32", amount="1024", second=True)
        family = _discount(
            title="Remise famille",
            quantity="33",
            amount="-132",
            code="REMISE_FAMILLE",
        )
        second_family = _discount(
            title="Remise famille - 2e cours",
            quantity="32",
            amount="-96",
            code="REMISE_FAMILLE_DEUXIEME_COURS",
        )

        result = _quote_per_course_discounts_by_schedule_key(
            [primary, second, family, second_family],
            {str(activity_id)},
        )

        self.assertEqual(result[f"{activity_id}:line:{primary.id}"], [family])
        self.assertEqual(result[f"{activity_id}:second_piano_course"], [second_family])

    def test_second_course_label_wins_when_quantities_differ(self) -> None:
        activity_id = uuid4()
        primary = _service(activity_id=activity_id, quantity="32", amount="704")
        second = _service(activity_id=activity_id, quantity="31", amount="558", second=True)
        discount = _discount(
            title="Remise 2e cours - Bar-le-Duc",
            quantity="32",
            amount="-64",
            code="REMISE_DEUXIEME_COURS_BAR_LE_DUC",
        )

        result = _quote_per_course_discounts_by_schedule_key(
            [primary, second, discount],
            {str(activity_id)},
        )

        self.assertEqual(result[f"{activity_id}:second_piano_course"], [discount])

    def test_flat_loyalty_discount_targets_only_positive_primary_service(self) -> None:
        piano_id = uuid4()
        solfege_id = uuid4()
        piano = _service(activity_id=piano_id, quantity="32", amount="1216")
        solfege = _service(activity_id=solfege_id, quantity="26", amount="0")
        discount = _discount(
            title="Remise fidélité",
            quantity="1",
            amount="-2",
            code="REMISE_FIDELITE",
        )

        result = _quote_per_course_discounts_by_schedule_key(
            [piano, solfege, discount],
            set(),
        )

        self.assertEqual(result[str(piano_id)], [discount])
        self.assertNotIn(str(solfege_id), result)


if __name__ == "__main__":
    unittest.main()
