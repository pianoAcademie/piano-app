from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services import referrals


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeDb:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.added: list[object] = []

    def scalars(self, _stmt: object) -> _ScalarRows:
        return _ScalarRows(self.rows)

    def add(self, row: object) -> None:
        self.added.append(row)


class _SequencedFakeDb(_FakeDb):
    def __init__(self, rows_by_call: list[list[object]]) -> None:
        super().__init__([])
        self.rows_by_call = rows_by_call
        self.calls = 0

    def scalars(self, _stmt: object) -> _ScalarRows:
        rows = self.rows_by_call[self.calls] if self.calls < len(self.rows_by_call) else []
        self.calls += 1
        return _ScalarRows(rows)


class ReferralPaymentRuleTests(unittest.TestCase):
    def test_paid_total_counts_only_cashed_payment_statuses(self) -> None:
        payment_ids = [uuid4(), uuid4(), uuid4(), uuid4(), uuid4()]
        db = _FakeDb(
            [
                SimpleNamespace(id=payment_ids[0], status="CHECK_RECEIVED", currency="EUR", total_incl_vat=Decimal("200.00")),
                SimpleNamespace(id=payment_ids[1], status="CHECK_DEPOSITED", currency="EUR", total_incl_vat=Decimal("300.00")),
                SimpleNamespace(id=payment_ids[2], status="CHECK_REFUSED", currency="EUR", total_incl_vat=Decimal("700.00")),
                SimpleNamespace(id=payment_ids[3], status="PAID", currency="EUR", total_incl_vat=Decimal("400.00")),
                SimpleNamespace(id=payment_ids[4], status="COMPLETED", currency="EUR", total_incl_vat=Decimal("-50.00")),
                SimpleNamespace(id=uuid4(), status="PAID", currency="USD", total_incl_vat=Decimal("999.00")),
            ]
        )
        metadata = {"reconciled_manual_payment_ids": [str(payment_id) for payment_id in payment_ids]}

        total = referrals._paid_total_for_invoice(db, metadata, currency="EUR")

        self.assertEqual(total, Decimal("450.00"))

    def test_quote_ids_with_referral_ancestors_includes_sibling_source_quote(self) -> None:
        source_quote_id = uuid4()
        sibling_quote_id = uuid4()
        db = _SequencedFakeDb(
            [
                [SimpleNamespace(id=sibling_quote_id, parent_quote_id=source_quote_id)],
                [SimpleNamespace(id=source_quote_id, parent_quote_id=None)],
            ]
        )

        quote_ids = referrals.quote_ids_with_referral_ancestors(db, {sibling_quote_id})

        self.assertEqual(quote_ids, {sibling_quote_id, source_quote_id})

    def test_invoice_below_threshold_updates_progress_without_granting_credit(self) -> None:
        reward = SimpleNamespace(
            quote_id=uuid4(),
            status=referrals.REFERRAL_STATUS_AWAITING_PAYMENT,
            credit_transaction_id=None,
            referrer_user_id=uuid4(),
            referred_client_id=uuid4(),
            referred_student_id=None,
            trigger_ratio=Decimal("0.5000"),
            metadata_json={},
        )
        db = _FakeDb([reward])
        note = SimpleNamespace(id=uuid4())
        metadata = {"totals_by_currency": {"EUR": "1000.00"}, "payment_currency": "EUR"}
        config = SimpleNamespace(enabled=True, currency="EUR", trigger_ratio=Decimal("0.5000"))

        with (
            patch.object(referrals, "referral_program_config", return_value=config),
            patch.object(referrals, "quote_ids_from_invoice_metadata", return_value={reward.quote_id}),
            patch.object(referrals, "quote_ids_with_referral_ancestors", return_value={reward.quote_id}),
            patch.object(referrals, "_paid_total_for_invoice", return_value=Decimal("499.99")),
            patch.object(referrals, "grant_referral_credit") as grant_credit,
        ):
            granted = referrals.evaluate_referrals_for_invoice(db, client_id=reward.referred_client_id, note=note, metadata=metadata)

        self.assertEqual(granted, [])
        grant_credit.assert_not_called()
        self.assertEqual(reward.trigger_invoice_note_id, note.id)
        self.assertEqual(reward.metadata_json["last_invoice_total"], "1000.00")
        self.assertEqual(reward.metadata_json["last_paid_total"], "499.99")
        self.assertEqual(reward.metadata_json["last_threshold_ratio"], "0.5000")

    def test_invoice_at_threshold_grants_credit(self) -> None:
        reward = SimpleNamespace(
            quote_id=uuid4(),
            status=referrals.REFERRAL_STATUS_AWAITING_PAYMENT,
            credit_transaction_id=None,
            referrer_user_id=uuid4(),
            referred_client_id=uuid4(),
            referred_student_id=None,
            trigger_ratio=Decimal("0.5000"),
            metadata_json={},
        )
        db = _FakeDb([reward])
        note = SimpleNamespace(id=uuid4())
        metadata = {"totals_by_currency": {"EUR": "1000.00"}, "payment_currency": "EUR"}
        config = SimpleNamespace(enabled=True, currency="EUR", trigger_ratio=Decimal("0.5000"))
        credited_reward = SimpleNamespace(id=reward.quote_id, status=referrals.REFERRAL_STATUS_CREDIT_GRANTED)

        with (
            patch.object(referrals, "referral_program_config", return_value=config),
            patch.object(referrals, "quote_ids_from_invoice_metadata", return_value={reward.quote_id}),
            patch.object(referrals, "quote_ids_with_referral_ancestors", return_value={reward.quote_id}),
            patch.object(referrals, "_paid_total_for_invoice", return_value=Decimal("500.00")),
            patch.object(referrals, "grant_referral_credit", return_value=credited_reward) as grant_credit,
        ):
            granted = referrals.evaluate_referrals_for_invoice(db, client_id=reward.referred_client_id, note=note, metadata=metadata)

        self.assertEqual(granted, [credited_reward])
        grant_credit.assert_called_once()

    def test_sibling_quote_invoice_can_trigger_source_quote_referral(self) -> None:
        source_quote_id = uuid4()
        sibling_quote_id = uuid4()
        reward = SimpleNamespace(
            quote_id=source_quote_id,
            status=referrals.REFERRAL_STATUS_AWAITING_PAYMENT,
            credit_transaction_id=None,
            referrer_user_id=uuid4(),
            referred_client_id=None,
            referred_student_id=None,
            trigger_ratio=Decimal("0.5000"),
            metadata_json={},
        )
        db = _FakeDb([reward])
        referred_client_id = uuid4()
        note = SimpleNamespace(id=uuid4())
        metadata = {"totals_by_currency": {"EUR": "1000.00"}, "payment_currency": "EUR"}
        config = SimpleNamespace(enabled=True, currency="EUR", trigger_ratio=Decimal("0.5000"))
        credited_reward = SimpleNamespace(id=reward.quote_id, status=referrals.REFERRAL_STATUS_CREDIT_GRANTED)

        with (
            patch.object(referrals, "referral_program_config", return_value=config),
            patch.object(referrals, "quote_ids_from_invoice_metadata", return_value={sibling_quote_id}),
            patch.object(referrals, "quote_ids_with_referral_ancestors", return_value={sibling_quote_id, source_quote_id}),
            patch.object(referrals, "_paid_total_for_invoice", return_value=Decimal("500.00")),
            patch.object(referrals, "grant_referral_credit", return_value=credited_reward) as grant_credit,
        ):
            granted = referrals.evaluate_referrals_for_invoice(db, client_id=referred_client_id, note=note, metadata=metadata)

        self.assertEqual(granted, [credited_reward])
        self.assertEqual(reward.referred_client_id, referred_client_id)
        grant_credit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
