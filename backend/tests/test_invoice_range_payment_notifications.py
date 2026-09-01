from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes import admin_clients
from app.models.client_record import ClientManualTransaction, ClientNoteEntry


class _FakeScalarResult:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = rows or []

    def all(self) -> list[object]:
        return self.rows


class _FakeDb:
    def __init__(self, scalar_rows: list[object] | None = None) -> None:
        self.added: list[object] = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.scalar_rows = scalar_rows or []

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_calls += 1
        for item in self.added:
            if isinstance(item, ClientManualTransaction) and item.id is None:
                item.id = uuid4()

    def commit(self) -> None:
        self.commit_calls += 1

    def scalars(self, *_args: object, **_kwargs: object) -> _FakeScalarResult:
        return _FakeScalarResult(self.scalar_rows)


class InvoiceRangePaymentNotificationTests(unittest.TestCase):
    def test_postprocessing_state_survives_note_round_trip(self) -> None:
        client_id = uuid4()
        metadata: dict[str, object] = {
            "kind": "INVOICE_RANGE",
            "invoice_number": "PA26-0296",
            "start_date": "2026-06-24",
            "end_date": "2026-06-24",
            "issued_date": "2026-06-24",
            "due_date": "2026-06-24",
            "layout": "NORMAL",
            "totals_by_currency": {"EUR": "200.00"},
            "billing_entity": "ENTITE_NON_DEFINIE",
            "invoice_status": "PAID",
            "payment_postprocessing_status": "COMPLETED",
            "payment_postprocessing_completed_at": "2026-08-08T15:14:25+00:00",
            "payment_postprocessing_completion_reason": "MANUAL_REPAIR_NO_NOTIFICATION_REPLAY",
        }
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message=admin_clients._build_invoice_range_note_message(metadata),
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )

        parsed = admin_clients._parse_invoice_range_note_entry(note)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["payment_postprocessing_status"], "COMPLETED")
        self.assertEqual(parsed["payment_postprocessing_completed_at"], "2026-08-08T15:14:25+00:00")
        self.assertEqual(parsed["payment_postprocessing_completion_reason"], "MANUAL_REPAIR_NO_NOTIFICATION_REPLAY")

    def test_already_paid_reconciliation_is_idempotent(self) -> None:
        db = _FakeDb()
        client_id = uuid4()
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0296",
            "invoice_status": "PAID",
            "paid_at": "2026-08-08T08:57:00+00:00",
            "payment_transaction_id": str(uuid4()),
        }

        with (
            patch.object(admin_clients, "_require_client"),
            patch.object(admin_clients, "_load_range_invoice_note", return_value=(note, metadata)),
            patch.object(admin_clients, "_invoice_range_metadata_with_display_totals", return_value=metadata),
            patch.object(admin_clients, "lookup_payment") as lookup_payment,
        ):
            result = admin_clients.reconcile_admin_client_range_invoice_public_payment_by_provider_reference(
                db,  # type: ignore[arg-type]
                client_id=client_id,
                note_id=note.id,
                provider_reference="pay_paid_123",
                defer_postprocessing=True,
            )

        lookup_payment.assert_not_called()
        self.assertTrue(result["paid"])
        self.assertFalse(result["processed"])
        self.assertEqual(result["reason"], "already_reconciled")
        self.assertEqual(db.commit_calls, 1)

    def test_deferred_payment_commits_before_notifications(self) -> None:
        db = _FakeDb()
        client_id = uuid4()
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0296",
            "total_to_pay_by_currency": {"EUR": "200.00"},
            "included_payment_keys": [f"BOOKING:{uuid4()}"],
        }

        with (
            patch.object(admin_clients, "_run_invoice_range_payment_notifications") as notifications,
            patch.object(admin_clients, "evaluate_referrals_for_invoice") as referrals,
            patch.object(
                admin_clients,
                "_propagate_paid_deposit_to_issued_long_period_invoice",
            ) as propagate_deposit,
        ):
            transaction_id, _paid_at = admin_clients._record_invoice_range_public_payment(
                db,  # type: ignore[arg-type]
                client_id=client_id,
                note=note,
                metadata=metadata,
                provider_reference="pay_paid_123",
                seller_legal_entity_id=None,
                defer_postprocessing=True,
            )

        notifications.assert_not_called()
        referrals.assert_not_called()
        propagate_deposit.assert_called_once_with(
            db,
            owner_client_id=client_id,
            source_note=note,
            source_metadata=metadata,
            payment_transaction_id=transaction_id,
        )
        self.assertIsNotNone(transaction_id)
        self.assertEqual(metadata["invoice_status"], "PAID")
        self.assertEqual(metadata["payment_postprocessing_status"], "PENDING")
        self.assertEqual(db.commit_calls, 1)

    def test_final_payment_does_not_reuse_deposit_transaction_from_same_category(self) -> None:
        client_id = uuid4()
        deposit_id = uuid4()
        deposit = ClientManualTransaction(
            id=deposit_id,
            user_id=client_id,
            student_user_id=client_id,
            transaction_type="PAYMENT",
            status="COMPLETED",
            label="Paiement en ligne facture PA26-0165",
            category="INVOICE_RANGE_PUBLIC_PAYMENT",
            occurred_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            amount_excl_vat=Decimal("-200.00"),
            vat_rate=Decimal("0.00"),
            vat_amount=Decimal("0.00"),
            total_incl_vat=Decimal("-200.00"),
            currency="EUR",
            reference="MODE:CARD_ONLINE|REF:pay_deposit",
        )
        db = _FakeDb([deposit])
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0448",
            "student_user_id": str(client_id),
            "total_to_pay_by_currency": {"EUR": "1063.00"},
            "reconciled_manual_payment_ids": [str(deposit_id)],
        }

        transaction_id, _paid_at = admin_clients._record_invoice_range_public_payment(
            db,  # type: ignore[arg-type]
            client_id=client_id,
            note=note,
            metadata=metadata,
            provider_reference="pay_final",
            seller_legal_entity_id=None,
            defer_postprocessing=True,
        )

        self.assertNotEqual(transaction_id, deposit_id)
        created_transactions = [item for item in db.added if isinstance(item, ClientManualTransaction)]
        self.assertEqual(len(created_transactions), 1)
        self.assertEqual(created_transactions[0].total_incl_vat, Decimal("-1063.00"))
        self.assertEqual(
            metadata["reconciled_manual_payment_ids"],
            [str(deposit_id), str(transaction_id)],
        )

    def test_multi_booking_invoice_payment_suppresses_individual_booking_confirmations(self) -> None:
        db = _FakeDb()
        client_id = uuid4()
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0206",
            "total_to_pay_by_currency": {"EUR": "1472.00"},
            "included_payment_keys": [f"BOOKING:{uuid4()}", f"BOOKING:{uuid4()}"],
            "payment_confirmation_emails_sent_at": "2026-06-18T16:00:00+00:00",
            "admin_payment_confirmation_emails_sent_at": "2026-06-18T16:00:00+00:00",
        }

        with (
            patch.object(admin_clients, "_send_invoice_range_booking_confirmation_emails") as send_booking_confirmations,
            patch.object(admin_clients, "evaluate_referrals_for_invoice"),
        ):
            transaction_id, _paid_at = admin_clients._record_invoice_range_public_payment(
                db,  # type: ignore[arg-type]
                client_id=client_id,
                note=note,
                metadata=metadata,
                provider_reference="VIR-20260618-03ECEB6D",
                seller_legal_entity_id=None,
                payment_method_code="BANK_TRANSFER",
                payment_label="Virement bancaire",
                transaction_category="INVOICE_RANGE_BANK_TRANSFER",
                public_note_reference_label="Virement bancaire",
            )

        send_booking_confirmations.assert_not_called()
        self.assertIsNotNone(transaction_id)
        self.assertEqual(metadata["invoice_status"], "PAID")
        self.assertEqual(metadata["booking_confirmation_emails_suppressed_reason"], "MULTI_BOOKING_INVOICE_RANGE_PAYMENT")
        self.assertIn("booking_confirmation_emails_sent_at", metadata)
        self.assertEqual(db.commit_calls, 1)
        created_transaction = next(item for item in db.added if isinstance(item, ClientManualTransaction))
        self.assertEqual(created_transaction.total_incl_vat, Decimal("-1472.00"))

    def test_paid_deposit_is_propagated_to_unique_issued_long_period_invoice(self) -> None:
        client_id = uuid4()
        student_id = uuid4()
        charge_id = uuid4()
        payment_id = uuid4()
        source_note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        source_metadata: dict[str, object] = {
            "invoice_number": "PA26-0100",
            "invoice_status": "PAID",
            "student_user_id": str(student_id),
            "included_payment_keys": [f"MANUAL:{charge_id}"],
        }
        target_metadata: dict[str, object] = {
            "kind": "INVOICE_RANGE",
            "invoice_number": "PA26-0700",
            "start_date": "2026-05-01",
            "end_date": "2027-06-30",
            "issued_date": "2026-08-17",
            "due_date": "2026-09-01",
            "layout": "NORMAL",
            "totals_by_currency": {"EUR": "1500.00"},
            "total_to_pay_by_currency": {"EUR": "1500.00"},
            "student_user_id": str(student_id),
            "billing_entity": "PIANO_ACADEMIE",
            "invoice_status": "ISSUED",
        }
        target_note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message=admin_clients._build_invoice_range_note_message(target_metadata),
            created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        )
        charge = ClientManualTransaction(
            id=charge_id,
            user_id=client_id,
            student_user_id=student_id,
            transaction_type="CHARGE",
            status="COMPLETED",
            label="Acompte de preinscription",
            category="PRE_REGISTRATION_DEPOSIT",
            occurred_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            amount_excl_vat=Decimal("166.67"),
            vat_rate=Decimal("20.00"),
            vat_amount=Decimal("33.33"),
            total_incl_vat=Decimal("200.00"),
            currency="EUR",
        )
        payment = ClientManualTransaction(
            id=payment_id,
            user_id=client_id,
            student_user_id=student_id,
            transaction_type="PAYMENT",
            status="COMPLETED",
            label="Paiement acompte",
            category="INVOICE_RANGE_PUBLIC_PAYMENT",
            occurred_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            amount_excl_vat=Decimal("-200.00"),
            vat_rate=Decimal("0.00"),
            vat_amount=Decimal("0.00"),
            total_incl_vat=Decimal("-200.00"),
            currency="EUR",
        )

        class _LateDepositDb:
            def __init__(self) -> None:
                self.scalar_calls = 0
                self.added: list[object] = []

            def scalars(self, *_args: object, **_kwargs: object) -> _FakeScalarResult:
                self.scalar_calls += 1
                rows_by_call = {1: [charge], 2: [target_note], 3: [], 4: []}
                return _FakeScalarResult(rows_by_call[self.scalar_calls])

            def get(self, *_args: object, **_kwargs: object) -> object:
                return payment

            def add(self, value: object) -> None:
                self.added.append(value)

        db = _LateDepositDb()

        def _synchronize(*_args: object, **kwargs: object) -> dict[str, object]:
            metadata = dict(kwargs["metadata"])  # type: ignore[arg-type]
            metadata["applied_payment_totals_by_currency"] = {"EUR": "-200.00"}
            metadata["total_to_pay_by_currency"] = {"EUR": "1300.00"}
            return metadata

        with patch.object(
            admin_clients,
            "_synchronize_invoice_range_reconciled_payment_metadata",
            side_effect=_synchronize,
        ):
            reconciled_note_id = admin_clients._propagate_paid_deposit_to_issued_long_period_invoice(
                db,  # type: ignore[arg-type]
                owner_client_id=client_id,
                source_note=source_note,
                source_metadata=source_metadata,
                payment_transaction_id=payment_id,
            )

        self.assertEqual(reconciled_note_id, target_note.id)
        persisted_metadata = admin_clients._parse_invoice_range_note_entry(target_note)
        self.assertIsNotNone(persisted_metadata)
        assert persisted_metadata is not None
        self.assertEqual(persisted_metadata["reconciled_manual_payment_ids"], [str(payment_id)])
        self.assertEqual(persisted_metadata["total_to_pay_by_currency"], {"EUR": "1300.00"})
        self.assertEqual(persisted_metadata["late_deposit_source_invoice_number"], "PA26-0100")
        self.assertEqual(persisted_metadata["invoice_status"], "ISSUED")

    def test_paid_deposit_matches_legacy_annual_invoice_through_manual_student_rows(self) -> None:
        client_id, student_id, charge_id, extra_id, payment_id = (uuid4() for _ in range(5))
        source_note = ClientNoteEntry(id=uuid4(), user_id=client_id, entry_type="AUTO", message="",
            created_at=datetime(2026, 8, 30, tzinfo=timezone.utc))
        source_metadata = {"invoice_number":"PA26-0413","invoice_status":"PAID",
            "included_payment_keys":[f"MANUAL:{charge_id}"]}
        target_metadata = {"kind":"INVOICE_RANGE","invoice_number":"PA26-0649",
            "start_date":"2026-05-01","end_date":"2027-06-30","issued_date":"2026-08-17",
            "due_date":"2026-09-01","layout":"NORMAL","billing_entity":"PIANO_ACADEMIE",
            "totals_by_currency":{"EUR":"4465.00"},
            "total_to_pay_by_currency":{"EUR":"200.00"},"invoice_status":"ISSUED",
            "included_payment_keys":[f"MANUAL:{extra_id}"]}
        target_note = ClientNoteEntry(id=uuid4(),user_id=client_id,entry_type="AUTO",
            message=admin_clients._build_invoice_range_note_message(target_metadata),
            created_at=datetime(2026,8,17,tzinfo=timezone.utc))
        def transaction(row_id: object, student: object, total: str) -> ClientManualTransaction:
            return ClientManualTransaction(id=row_id,user_id=client_id,student_user_id=student,
                transaction_type="CHARGE",status="COMPLETED",label="line",occurred_at=datetime.now(timezone.utc),
                amount_excl_vat=Decimal(total),vat_rate=Decimal("0"),vat_amount=Decimal("0"),
                total_incl_vat=Decimal(total),currency="EUR")
        charge = transaction(charge_id,student_id,"200")
        charge.category = "PRE_REGISTRATION_DEPOSIT"
        extra = transaction(extra_id,student_id,"25")
        payment = transaction(payment_id,student_id,"-200")
        payment.transaction_type = "PAYMENT"

        class Db:
            def __init__(self) -> None: self.calls=0; self.added=[]
            def scalars(self,*_a:object,**_k:object)->_FakeScalarResult:
                self.calls += 1
                return _FakeScalarResult({1:[charge],2:[target_note],3:[extra],4:[]}[self.calls])
            def get(self,*_a:object,**_k:object)->object: return payment
            def add(self,value:object)->None: self.added.append(value)
        db=Db()
        with patch.object(admin_clients,"_synchronize_invoice_range_reconciled_payment_metadata") as sync:
            sync.side_effect=lambda *_a,**kw:{**kw["metadata"],"total_to_pay_by_currency":{"EUR":"0.00"}}
            result=admin_clients._propagate_paid_deposit_to_issued_long_period_invoice(db,owner_client_id=client_id,
                source_note=source_note,source_metadata=source_metadata,payment_transaction_id=payment_id)  # type: ignore[arg-type]
        self.assertEqual(db.calls, 4)
        self.assertEqual(result,target_note.id)
        persisted=admin_clients._parse_invoice_range_note_entry(target_note)
        assert persisted is not None
        self.assertEqual(persisted["reconciled_manual_payment_ids"],[str(payment_id)])
        self.assertEqual(persisted["invoice_status"],"PAID")


if __name__ == "__main__":
    unittest.main()
