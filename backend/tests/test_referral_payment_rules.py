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


class _ScalarFakeDb(_FakeDb):
    def __init__(self, scalar_rows: list[object | None]) -> None:
        super().__init__([])
        self.scalar_rows = scalar_rows
        self.scalar_calls = 0

    def scalar(self, _stmt: object) -> object | None:
        value = self.scalar_rows[self.scalar_calls] if self.scalar_calls < len(self.scalar_rows) else None
        self.scalar_calls += 1
        return value


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
                [],
                [SimpleNamespace(id=sibling_quote_id, parent_quote_id=source_quote_id)],
                [],
                [SimpleNamespace(id=source_quote_id, parent_quote_id=None)],
            ]
        )

        quote_ids = referrals.quote_ids_with_referral_ancestors(db, {sibling_quote_id})

        self.assertEqual(quote_ids, {sibling_quote_id, source_quote_id})

    def test_quote_ids_with_referral_ancestors_stops_when_sibling_has_own_reward(self) -> None:
        source_quote_id = uuid4()
        sibling_quote_id = uuid4()
        db = _SequencedFakeDb([[sibling_quote_id], [SimpleNamespace(id=sibling_quote_id, parent_quote_id=source_quote_id)]])

        quote_ids = referrals.quote_ids_with_referral_ancestors(db, {sibling_quote_id})

        self.assertEqual(quote_ids, {sibling_quote_id})

    def test_ensure_referral_for_sibling_quote_creates_second_reward_line(self) -> None:
        source_quote_id = uuid4()
        sibling_quote_id = uuid4()
        sibling_prospect_id = uuid4()
        referrer_id = uuid4()
        source_reward = SimpleNamespace(
            id=uuid4(),
            declared_referrer_text="De laroche",
            category="PARIS",
            match_status=referrals.REFERRAL_MATCH_MANUAL,
            referrer_user_id=referrer_id,
            match_confidence=100,
            match_candidates_json=[],
            reward_amount=Decimal("50.00"),
            currency="EUR",
            trigger_ratio=Decimal("0.5000"),
        )
        db = _ScalarFakeDb([None, source_reward])

        reward = referrals.ensure_referral_for_sibling_quote(
            db,
            source_quote_id=source_quote_id,
            sibling_quote_id=sibling_quote_id,
            sibling_prospect_id=sibling_prospect_id,
        )

        self.assertIsNotNone(reward)
        self.assertEqual(reward.quote_id, sibling_quote_id)
        self.assertIsNone(reward.typeform_intake_id)
        self.assertEqual(reward.referrer_user_id, referrer_id)
        self.assertEqual(reward.status, referrals.REFERRAL_STATUS_AWAITING_PAYMENT)
        self.assertEqual(reward.metadata_json["source_quote_id"], str(source_quote_id))
        self.assertEqual(reward.metadata_json["sibling_prospect_id"], str(sibling_prospect_id))
        self.assertEqual(db.added, [reward])

    def test_same_referral_family_detects_parent_child_link(self) -> None:
        parent_id = uuid4()
        child_id = uuid4()
        db = _SequencedFakeDb([[child_id]])

        self.assertTrue(
            referrals.is_same_referral_family(
                db,
                referrer_user_id=parent_id,
                referred_client_id=child_id,
                referred_student_id=None,
            )
        )

    def test_same_referral_family_detects_shared_child_between_adults(self) -> None:
        referrer_parent_id = uuid4()
        billing_parent_id = uuid4()
        child_id = uuid4()
        db = _SequencedFakeDb([[child_id], [child_id]])

        self.assertTrue(
            referrals.is_same_referral_family(
                db,
                referrer_user_id=referrer_parent_id,
                referred_client_id=billing_parent_id,
                referred_student_id=None,
            )
        )

    def test_binding_quote_blocks_same_family_referral(self) -> None:
        reward = SimpleNamespace(
            id=uuid4(),
            quote_id=uuid4(),
            referrer_user_id=uuid4(),
            status=referrals.REFERRAL_STATUS_NEEDS_REVIEW,
            match_status=referrals.REFERRAL_MATCH_AUTO,
            match_confidence=95,
            metadata_json={},
        )
        db = _ScalarFakeDb([reward])
        referred_client_id = uuid4()
        referred_student_id = uuid4()

        with patch.object(referrals, "is_same_referral_family", return_value=True):
            updated = referrals.bind_referral_after_quote_transformation(
                db,
                quote_id=reward.quote_id,
                referred_client_id=referred_client_id,
                referred_student_id=referred_student_id,
            )

        self.assertIs(updated, reward)
        self.assertEqual(reward.referred_client_id, referred_client_id)
        self.assertEqual(reward.referred_student_id, referred_student_id)
        self.assertEqual(reward.status, referrals.REFERRAL_STATUS_NEEDS_REVIEW)
        self.assertEqual(reward.match_status, referrals.REFERRAL_MATCH_UNMATCHED)
        self.assertIsNone(reward.referrer_user_id)
        self.assertEqual(reward.match_confidence, 0)
        self.assertTrue(reward.metadata_json["self_referral_blocked"])

    def test_manual_validation_rejects_same_family_referral(self) -> None:
        reward = SimpleNamespace(id=uuid4(), referred_client_id=uuid4(), referred_student_id=uuid4())
        db = _ScalarFakeDb([reward])

        with patch.object(referrals, "is_same_referral_family", return_value=True):
            with self.assertRaisesRegex(ValueError, "cannot refer itself"):
                referrals.manually_validate_referral(db, reward_id=reward.id, referrer_user_id=uuid4())

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
