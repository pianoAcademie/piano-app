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

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import (
    _invoice_payments_with_routed_referral_credits,
    _invoice_payments_with_referral_credit_tax,
    _invoice_referral_credit_tax_breakdown,
)
from app.api.routes.quotes import (
    QUOTE_ANNUAL_INVOICE_PERIOD_END,
    QUOTE_ANNUAL_INVOICE_PERIOD_START,
    _create_followup_booking,
    _create_followup_annual_invoices,
    _quote_annual_invoice_amounts,
    _quote_annual_invoice_referral_credits_for_invoice,
    _quote_annual_invoice_selected_payments,
    _quote_per_course_discounts_by_schedule_key,
)
from app.schemas.admin import AdminClientPaymentOut


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
    def test_followup_booking_locks_price_accepted_in_quote(self) -> None:
        class _FakeSession:
            def __init__(self):
                self.scalar_results = iter([None, None])
                self.added = []

            def scalar(self, _statement):
                return next(self.scalar_results)

            def add(self, row):
                self.added.append(row)

            def flush(self):
                return None

        fake_db = _FakeSession()
        session_id = uuid4()
        student_id = uuid4()
        created_booking_ids = []
        quote_price = (
            Decimal("18.33"),
            Decimal("20.000"),
            Decimal("3.67"),
            Decimal("22.00"),
            "EUR",
        )

        with patch("app.api.routes.quotes._count_booked", return_value=0), patch(
            "app.api.routes.quotes._mark_first_course_if_needed"
        ), patch("app.api.routes.quotes.ensure_booking_reminder"), patch(
            "app.api.routes.quotes.schedule_booking_created_notifications"
        ):
            booking = _create_followup_booking(
                fake_db,
                session_obj=SimpleNamespace(
                    id=session_id,
                    course_type_id=uuid4(),
                    capacity_max=6,
                ),
                student=SimpleNamespace(id=student_id),
                subscription=None,
                plan=None,
                now=datetime(2026, 8, 30, tzinfo=timezone.utc),
                created_booking_ids=created_booking_ids,
                pricing_snapshot_override=quote_price,
            )

        self.assertIsNotNone(booking)
        self.assertTrue(booking.pricing_snapshot_locked)
        self.assertEqual(booking.total_incl_vat_snapshot, Decimal("22.00"))
        self.assertEqual(fake_db.added, [booking])

    def test_annual_invoice_metadata_freezes_quote_lines_period_and_deposit(self) -> None:
        class _FakeScalars:
            def all(self):
                return []

        class _FakeSession:
            def __init__(self):
                self.added_rows = []

            def scalars(self, _statement):
                return _FakeScalars()

            def flush(self):
                return None

            def add_all(self, rows):
                self.added_rows.extend(rows)

        seller_id = uuid4()
        booking_id = uuid4()
        manual_id = uuid4()
        deposit_payment_id = uuid4()
        referral_credit_ids = [uuid4(), uuid4()]
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
                vat_rate=Decimal("20.000"),
                currency="EUR",
                seller_legal_entity_id=seller_id,
                billing_entity="PIANO_ACADEMIE",
            ),
            SimpleNamespace(
                id=manual_id,
                source="MANUAL",
                occurred_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
                total_incl_vat=Decimal("280.00"),
                vat_rate=Decimal("20.000"),
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
        referral_credits = [
            SimpleNamespace(
                id=credit_id,
                user_id=billing.id,
                occurred_at=datetime(2026, 8, 20 + index, 12, tzinfo=timezone.utc),
                label=f"Avoir parrainage {index + 1}",
                currency="EUR",
                total_incl_vat=Decimal("-50.00"),
            )
            for index, credit_id in enumerate(referral_credit_ids)
        ]
        captured_messages: list[str] = []
        fake_session = _FakeSession()

        def create_note(*_args, **kwargs):
            captured_messages.append(kwargs["message"])
            return SimpleNamespace(id=note_id)

        with patch("app.api.routes.quotes._build_admin_client_payments", return_value=payments), patch(
            "app.api.routes.quotes._quote_annual_invoice_applied_deposit_payments",
            return_value=[deposit_payment],
        ), patch(
            "app.api.routes.quotes._quote_annual_invoice_available_referral_credits",
            return_value=referral_credits,
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
                fake_session,
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
        self.assertEqual(metadata["totals_by_currency"], {"EUR": "1368.00"})
        self.assertEqual(metadata["applied_payment_totals_by_currency"], {"EUR": "-200.00"})
        self.assertEqual(metadata["total_to_pay_by_currency"], {"EUR": "1168.00"})
        self.assertEqual(metadata["referral_credit_transaction_ids"], [str(value) for value in referral_credit_ids])
        self.assertEqual(metadata["referral_credit_total_ttc"], "100.00")
        self.assertTrue(all(f"MANUAL:{value}" in metadata["included_payment_keys"] for value in referral_credit_ids))
        self.assertEqual({row.source_payment_id for row in fake_session.added_rows}, set(referral_credit_ids))
        self.assertTrue(all(row.amount_excl_vat == Decimal("-41.67") for row in fake_session.added_rows))
        self.assertTrue(all(row.vat_rate == Decimal("20.000") for row in fake_session.added_rows))
        self.assertTrue(all(row.vat_amount == Decimal("-8.33") for row in fake_session.added_rows))
        self.assertTrue(all(row.total_incl_vat == Decimal("-50.00") for row in fake_session.added_rows))
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

    def test_annual_invoice_deducts_multiple_referral_credits_from_total_and_amount_due(self) -> None:
        payments = [SimpleNamespace(currency="EUR", total_incl_vat=Decimal("1396.00"))]
        credits = [
            SimpleNamespace(currency="EUR", total_incl_vat=Decimal("-50.00")),
            SimpleNamespace(currency="EUR", total_incl_vat=Decimal("-50.00")),
        ]

        totals, applied, total_to_pay = _quote_annual_invoice_amounts(
            payments,
            applied_payments=[],
            referral_credits=credits,
        )

        self.assertEqual(totals, {"EUR": Decimal("1296.00")})
        self.assertEqual(applied, {})
        self.assertEqual(total_to_pay, {"EUR": Decimal("1296.00")})

    def test_annual_invoice_keeps_credit_available_when_it_exceeds_amount_due(self) -> None:
        credit = SimpleNamespace(currency="EUR", total_incl_vat=Decimal("-50.00"))

        selected = _quote_annual_invoice_referral_credits_for_invoice(
            [credit],
            total_to_pay={"EUR": Decimal("40.00")},
        )

        self.assertEqual(selected, [])

    def test_referral_credit_tax_is_derived_from_the_invoiced_purchase(self) -> None:
        payment = SimpleNamespace(
            source="BOOKING",
            manual_transaction_type=None,
            category=None,
            currency="EUR",
            total_incl_vat=Decimal("120.00"),
            vat_rate=Decimal("20.000"),
        )

        amount_excl_vat, vat_rate, vat_amount = _invoice_referral_credit_tax_breakdown(
            total_incl_vat=Decimal("-50.00"),
            currency="EUR",
            invoice_payments=[payment],
        )

        self.assertEqual(amount_excl_vat, Decimal("-41.67"))
        self.assertEqual(vat_rate, Decimal("20.000"))
        self.assertEqual(vat_amount, Decimal("-8.33"))

    def test_referral_credit_tax_rejects_mixed_vat_rates(self) -> None:
        payments = [
            SimpleNamespace(
                source="BOOKING",
                manual_transaction_type=None,
                category=None,
                currency="EUR",
                total_incl_vat=Decimal("120.00"),
                vat_rate=Decimal("20.000"),
            ),
            SimpleNamespace(
                source="MANUAL",
                manual_transaction_type="CHARGE",
                category="Produit",
                currency="EUR",
                total_incl_vat=Decimal("105.50"),
                vat_rate=Decimal("5.500"),
            ),
        ]

        with self.assertRaises(HTTPException) as raised:
            _invoice_referral_credit_tax_breakdown(
                total_incl_vat=Decimal("-50.00"),
                currency="EUR",
                invoice_payments=payments,
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_manual_invoice_normalizes_referral_credit_without_changing_ttc(self) -> None:
        purchase = AdminClientPaymentOut(
            id=uuid4(),
            source="BOOKING",
            occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            label="Cours",
            status="PENDING",
            amount_excl_vat=Decimal("100.00"),
            vat_rate=Decimal("20.000"),
            vat_amount=Decimal("20.00"),
            total_incl_vat=Decimal("120.00"),
            currency="EUR",
            reference=None,
        )
        credit = AdminClientPaymentOut(
            id=uuid4(),
            source="MANUAL",
            occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            label="Avoir parrainage",
            status="COMPLETED",
            amount_excl_vat=Decimal("-50.00"),
            vat_rate=Decimal("0.000"),
            vat_amount=Decimal("0.00"),
            total_incl_vat=Decimal("-50.00"),
            currency="EUR",
            reference="REFERRAL:test",
            manual_transaction_type="DISCOUNT",
            category="Parrainage",
        )

        normalized = _invoice_payments_with_referral_credit_tax([purchase, credit])

        normalized_credit = normalized[1]
        self.assertEqual(normalized_credit.amount_excl_vat, Decimal("-41.67"))
        self.assertEqual(normalized_credit.vat_rate, Decimal("20.000"))
        self.assertEqual(normalized_credit.vat_amount, Decimal("-8.33"))
        self.assertEqual(normalized_credit.total_incl_vat, Decimal("-50.00"))

    def test_entity_less_referral_credit_follows_unique_positive_purchase_seller(self) -> None:
        seller_id = uuid4()
        purchase = AdminClientPaymentOut(
            id=uuid4(), source="BOOKING", occurred_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
            label="Cours", status="PENDING", amount_excl_vat=Decimal("18.33"),
            vat_rate=Decimal("20.000"), vat_amount=Decimal("3.67"), total_incl_vat=Decimal("22.00"),
            currency="EUR", reference=None, seller_legal_entity_id=seller_id, billing_entity="PIANO ACADEMIE",
        )
        credit = AdminClientPaymentOut(
            id=uuid4(), source="MANUAL", occurred_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            label="Avoir parrainage", status="COMPLETED", amount_excl_vat=Decimal("-50.00"),
            vat_rate=Decimal("0.000"), vat_amount=Decimal("0.00"), total_incl_vat=Decimal("-50.00"),
            currency="EUR", reference="REFERRAL:test", manual_transaction_type="DISCOUNT",
            category="Parrainage",
        )

        routed = _invoice_payments_with_routed_referral_credits([purchase, credit])

        self.assertEqual(routed[1].seller_legal_entity_id, seller_id)
        self.assertEqual(routed[1].billing_entity, "PIANO ACADEMIE")

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
