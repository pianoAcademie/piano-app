from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import app.models
from app.api.routes import admin_clients as invoices
from app.api.routes import invoice_partial_payments as routes
from app.db.base import Base
from app.models.client_record import ClientManualTransaction, ClientNoteEntry
from app.models.ops import LegalEntity
from app.models.user import User, UserRole
from app.schemas.admin import AdminClientManualTransactionCreateRequest
from app.services import invoice_partial_payments as service
from app.services import payment_checkout as gateway
from app.services.payment_checkout import PaymentLookupResult, CheckoutCreateResult
from app.services.payment_provider import PaymentProvider


def invoice_metadata():
    return {"kind": "INVOICE_RANGE", "invoice_number": "TEST-PARTIAL-1096", "start_date": "2026-09-01",
        "end_date": "2027-06-30", "issued_date": "2026-08-31", "due_date": "2026-09-01", "layout": "DETAILED",
        "totals_by_currency": {"EUR": "1096.00"}, "total_to_pay_by_currency": {"EUR": "1096.00"},
        "invoice_status": "ISSUED", "document_type": "INVOICE", "auto_include_previous_balance": False,
        "billing_entity": "Piano Test", "included_payment_keys": []}


class PartialPaymentUnitTests(unittest.TestCase):
    def test_amount_validation(self):
        for amount in ("0", "-1", "NaN", "Infinity", "396.001", "0.99"):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                routes.CreateRequest(request_id=uuid4(), amount=amount)
        self.assertEqual(routes.CreateRequest(request_id=uuid4(), amount="396.00").amount, Decimal("396"))

    def test_negative_balance_is_not_collectible(self):
        data = invoice_metadata()
        data["total_to_pay_by_currency"] = {"EUR": "-20.00"}
        self.assertEqual(service.balance(data), Decimal("-20"))
        with self.assertRaises(HTTPException):
            service.ensure_payable(data)

    def test_paid_cancelled_and_credit_note_are_not_payable(self):
        for key, value in [("invoice_status", "PAID"), ("invoice_status", "CANCELLED"), ("document_type", "CREDIT_NOTE")]:
            data = invoice_metadata()
            data[key] = value
            with self.subTest(value=value), self.assertRaises(HTTPException):
                service.ensure_payable(data)

    def test_metadata_round_trip_preserves_requests_and_attempts(self):
        data = invoice_metadata()
        data[service.FIELD] = [{"id": str(uuid4()), "amount": "396.00", "status": "PENDING", "attempts": [
            {"id": str(uuid4()), "provider_reference": "pay_first", "status": "FAILED"},
            {"id": str(uuid4()), "provider_reference": "pay_second", "status": "PENDING"}]}]
        note = ClientNoteEntry(message=invoices._build_invoice_range_note_message(data))
        self.assertEqual(invoices._parse_invoice_range_note_entry(note)[service.FIELD], data[service.FIELD])

    def test_tokens_bound_to_invoice_request_and_attempt(self):
        note = SimpleNamespace(id=uuid4(), user_id=uuid4())
        data = invoice_metadata()
        row = {"id": str(uuid4()), "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
        token = service.token_for(note, data, row)
        service.verify_token(token, note, data, row)
        with self.assertRaises(HTTPException):
            service.verify_token(token, note, data, {**row, "id": str(uuid4())})
        with self.assertRaises(HTTPException):
            service.verify_token(token, SimpleNamespace(id=uuid4(), user_id=note.user_id), data, row)
        with self.assertRaises(HTTPException):
            service.verify_token(token, note, data, row, attempt_id=str(uuid4()))
        expired = service.token_for(note, data, {**row, "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
        with self.assertRaises(HTTPException):
            service.verify_token(expired, note, data, row)

    def test_full_checkout_guard(self):
        data = invoice_metadata()
        data[service.FIELD] = [{"id": str(uuid4()), "status": "READY", "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}]
        with self.assertRaises(HTTPException):
            service.assert_no_active_partial_request(data)
        data[service.FIELD][0]["status"] = "PAID"
        service.assert_no_active_partial_request(data)

    def test_psp_amount_currency_extraction(self):
        cases = [
            (gateway._payplug_lookup_payment, {"id": "pay_test", "is_paid": True, "amount": 39600, "currency": "EUR"}, "_request_json"),
            (gateway._mollie_lookup_payment, {"id": "tr_test", "status": "paid", "amount": {"value": "396.00", "currency": "EUR"}}, "_request_json"),
            (gateway._stripe_lookup_payment, {"id": "cs_test", "mode": "payment", "payment_status": "paid", "amount_total": 39600, "currency": "eur"}, "_request_form"),
            (gateway._stripe_lookup_payment, {"id": "pi_test", "status": "succeeded", "amount_received": 39600, "currency": "eur"}, "_request_form"),
        ]
        for lookup, payload, method in cases:
            with self.subTest(provider=lookup.__name__, ref=payload["id"]), patch.object(gateway, method, return_value=(200, payload, "ok")):
                result = lookup("test-only", payload["id"])
            self.assertTrue(result.paid)
            self.assertEqual(result.amount, Decimal("396"))
            self.assertEqual(result.currency, "EUR")


@unittest.skipUnless(os.getenv("PARTIAL_PAYMENT_TEST_DATABASE_URL"), "Requires an isolated PostgreSQL test database")
class PartialPaymentPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ["PARTIAL_PAYMENT_TEST_DATABASE_URL"]
        if not url.endswith("/partial_payment_test"):
            raise RuntimeError("Refusing to run against anything except the dedicated partial_payment_test database")
        cls.engine = create_engine(url)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False)

    def setUp(self):
        self.db = self.Session()
        self.actor = User(id=uuid4(), email=f"admin-{uuid4()}@example.test", hashed_password="unused", role=UserRole.ADMIN)
        self.owner = User(id=uuid4(), email=f"parent-{uuid4()}@example.test", first_name="Émilie", last_name="Test", hashed_password="unused", role=UserRole.CLIENT)
        self.entity = LegalEntity(id=uuid4(), name="Piano test", invoice_prefix=f"T{uuid4().hex[:6]}")
        self.db.add_all([self.actor, self.owner, self.entity])
        self.db.flush()
        data = invoice_metadata()
        data["seller_legal_entity_id"] = str(self.entity.id)
        self.note = ClientNoteEntry(id=uuid4(), user_id=self.owner.id, entry_type="AUTO", message=invoices._build_invoice_range_note_message(data))
        self.db.add(self.note)
        self.db.commit()
        self.owner_id, self.note_id, self.entity_id = self.owner.id, self.note.id, self.entity.id
        self.email_patch = patch.object(invoices, "send_email", return_value="fake-message-id")
        self.email = self.email_patch.start()
        self.sender_patch = patch.object(invoices, "resolve_sender_profile", return_value=SimpleNamespace(from_email="school@example.test", from_name="Piano", reply_to="school@example.test", subject_prefix=""))
        self.sender_patch.start()
        self.addCleanup(self.db.close)
        self.addCleanup(self.email_patch.stop)
        self.addCleanup(self.sender_patch.stop)

    def new_request(self, amount="396.00", request_id=None):
        rid = request_id or uuid4()
        result = service.create_request(self.db, client_id=self.owner_id, note_id=self.note_id, request_id=rid, amount=Decimal(amount), actor=self.actor)
        return rid, result

    def load_request(self, rid):
        note, data, payer = service.load(self.db, self.owner_id, self.note_id)
        return note, data, service.find(data, rid), payer

    def add_attempt(self, rid, status="PENDING"):
        note, data, row, _ = self.load_request(rid)
        attempt = {"id": str(uuid4()), "status": status, "provider": "PAYPLUG", "provider_reference": f"pay_{uuid4().hex}",
            "legal_entity_id": str(self.entity_id), "checkout_url": "https://secure.payplug.com/test"}
        row["attempts"].append(attempt)
        row["status"] = status
        service.save(self.db, note, data)
        return attempt

    def lookup(self, rid, attempt, **changes):
        fields = dict(success=True, provider=PaymentProvider.PAYPLUG, provider_reference=attempt["provider_reference"], status="PAID", paid=True,
            cancelled=False, failed=False, metadata={"client_id": str(self.owner_id), "note_id": str(self.note_id), "partial_request_id": str(rid),
                "partial_attempt_id": attempt["id"]}, message="ok", amount=Decimal("396"), currency="EUR")
        fields.update(changes)
        return PaymentLookupResult(**fields)

    def transaction_count(self):
        return self.db.scalar(select(func.count()).select_from(ClientManualTransaction).where(ClientManualTransaction.user_id == self.owner_id))

    def pay(self, rid, attempt, **changes):
        note, data, row, _ = self.load_request(rid)
        current = next(a for a in row["attempts"] if a["id"] == attempt["id"])
        service.settle(self.db, note, data, row, current, self.lookup(rid, attempt, **changes))
        service.save(self.db, note, data)
        return data

    def test_creation_sends_branded_link_without_recording_payment_or_new_invoice(self):
        rid, result = self.new_request()
        self.assertTrue(result["sent"])
        self.assertEqual(result["remaining_after_payment"], "700.00")
        self.assertEqual(self.transaction_count(), 0)
        note, data, row, payer = self.load_request(rid)
        self.assertEqual(service.balance(data), Decimal("1096"))
        self.assertEqual(data["invoice_status"], "ISSUED")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ClientNoteEntry).where(ClientNoteEntry.user_id == self.owner_id)), 1)
        body = self.email.call_args.kwargs["body"]
        for text in ("PIANO ACADÉMIE", "396,00 €", "700,00 €", "TEST-PARTIAL-1096"):
            self.assertIn(text, body)
        self.assertEqual(self.email.call_args.kwargs["to_email"], payer.email)

    def test_double_submit_same_id_is_idempotent(self):
        rid, _ = self.new_request()
        self.new_request(request_id=rid)
        self.email.assert_called_once()
        self.assertEqual(len(self.load_request(rid)[1][service.FIELD]), 1)
        with self.assertRaises(HTTPException):
            self.new_request()

    def test_email_failure_retains_same_request_for_retry(self):
        self.email.side_effect = RuntimeError("SMTP unavailable")
        rid, result = self.new_request()
        self.assertFalse(result["sent"])
        self.assertEqual(self.transaction_count(), 0)
        self.email.side_effect = None
        _, result = self.new_request(request_id=rid)
        self.assertTrue(result["sent"])

    def test_invalid_or_excessive_amount_creates_nothing(self):
        for amount in ("1096", "1200", "0", "-1", "396.001"):
            with self.subTest(amount=amount), self.assertRaises(HTTPException):
                self.new_request(amount)
            self.db.rollback()
        self.email.assert_not_called()
        self.assertEqual(self.transaction_count(), 0)

    def test_396_payment_keeps_700_due_and_duplicate_callback_is_noop(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        data = self.pay(rid, attempt)
        self.assertEqual(data["totals_by_currency"], {"EUR": "1096.00"})
        self.assertEqual(service.balance(data), Decimal("700"))
        self.assertEqual(data["invoice_status"], "ISSUED")
        self.assertEqual(data["applied_payment_lines"][0]["amount"], "396.00")
        row = self.db.scalar(select(ClientManualTransaction).where(ClientManualTransaction.user_id == self.owner_id))
        self.assertEqual(row.total_incl_vat, Decimal("-396"))
        data = self.pay(rid, attempt)
        self.assertEqual(service.balance(data), Decimal("700"))
        self.assertEqual(self.transaction_count(), 1)

    def test_pending_and_failed_payments_do_not_change_balance(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        for fields in ({"paid": False, "status": "PENDING"}, {"paid": False, "status": "FAILED", "failed": True}):
            data = self.pay(rid, attempt, **fields)
            self.assertEqual(service.balance(data), Decimal("1096"))
            self.assertEqual(data["invoice_status"], "ISSUED")
            self.assertEqual(self.transaction_count(), 0)

    def test_wrong_amount_currency_reference_or_metadata_is_rejected(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        for changes in ({"amount": Decimal("1096")}, {"amount": None}, {"currency": "USD"}, {"metadata": {}},
                        {"provider_reference": "pay_someone_else"}, {"success": False}, {"cancelled": True}):
            with self.subTest(changes=changes), self.assertRaises(HTTPException):
                self.pay(rid, attempt, **changes)
            self.db.rollback()
        self.assertEqual(self.transaction_count(), 0)

    def test_cash_then_card_settles_invoice_without_recreating_cash(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        note, data, row, _ = self.load_request(rid)
        cash = ClientManualTransaction(user_id=self.owner_id, transaction_type="PAYMENT", status="COMPLETED", label="Espèces reçues",
            total_incl_vat=-Decimal("700"), amount_excl_vat=-Decimal("700"), vat_amount=0, vat_rate=0, currency="EUR", reference="CASH", legal_entity_id=self.entity_id)
        self.db.add(cash)
        self.db.flush()
        data["reconciled_manual_payment_ids"] = [str(cash.id)]
        data.update(invoices._synchronize_invoice_range_reconciled_payment_metadata(self.db, client_id=self.owner_id, note_id=self.note_id,
            note_created_at=note.created_at, metadata=data))
        service.save(self.db, note, data)
        data = self.pay(rid, attempt)
        self.assertEqual(service.balance(data), Decimal("0"))
        self.assertEqual(data["invoice_status"], "PAID")
        self.assertEqual(self.transaction_count(), 2)

    def test_card_then_actual_cash_entry_closes_original_invoice(self):
        rid, _ = self.new_request()
        self.pay(rid, self.add_attempt(rid))
        # Exercise the existing manual-payment endpoint, not a synthetic balance update.
        payload = AdminClientManualTransactionCreateRequest(transaction_type="PAYMENT", amount_incl_vat="700",
            payment_method_code="CASH", currency="EUR", legal_entity_id=self.entity_id,
            reconciled_invoice_note_ids=[self.note_id], send_receipt_email=False)
        invoices.create_admin_client_manual_transaction(self.owner_id, payload, self.db, self.actor)
        data = self.load_request(rid)[1]
        self.assertEqual(service.balance(data), Decimal("0"))
        self.assertEqual(data["invoice_status"], "PAID")
        self.assertEqual(data["totals_by_currency"], {"EUR": "1096.00"})
        self.assertEqual(self.transaction_count(), 2)

    def test_family_split_preserves_allocated_previous_payments(self):
        note, data, _ = service.load(self.db, self.owner_id, self.note_id)
        data.update(family_billing_split_group_id=str(uuid4()),
            total_to_pay_by_currency={"EUR": "896.00"}, applied_payment_totals_by_currency={"EUR": "-200.00"},
            applied_payment_lines=[{"date": "01/08/2026", "method": "Virement", "reference": "allocated-share", "amount": "200.00", "currency": "EUR"}])
        service.save(self.db, note, data)
        rid, _ = self.new_request()
        data = self.pay(rid, self.add_attempt(rid))
        self.assertEqual(service.balance(data), Decimal("500"))
        self.assertEqual(data["applied_payment_totals_by_currency"], {"EUR": "-596.00"})
        self.assertEqual(len(data["applied_payment_lines"]), 2)
        self.assertEqual(data["invoice_status"], "ISSUED")
        self.assertEqual(self.transaction_count(), 1)

    def test_failed_attempt_can_retry_but_callbacks_remain_bound_to_each_reference(self):
        rid, _ = self.new_request()
        failed_attempt = self.add_attempt(rid)
        self.pay(rid, failed_attempt, paid=False, failed=True, status="FAILED")
        successful_attempt = self.add_attempt(rid)
        self.pay(rid, successful_attempt)
        data = self.pay(rid, failed_attempt, paid=False, failed=True, status="FAILED")
        self.assertEqual(service.balance(data), Decimal("700"))
        self.assertEqual(self.transaction_count(), 1)
        self.assertEqual(service.find(data, rid)["status"], "PAID")

    def test_receipt_mentions_remaining_due_not_full_invoice_paid(self):
        rid, _ = self.new_request()
        self.pay(rid, self.add_attempt(rid))
        note, data, row, payer = self.load_request(rid)
        subject, body = service.branded_message(note, data, row, payer, receipt=True)
        self.assertIn("396,00 €", subject)
        self.assertIn("700,00 €", body)
        self.assertNotIn("La facture est soldée", body)
        service.send_message(self.db, note, data, row, payer, receipt=True)
        service.send_message(self.db, note, data, row, payer, receipt=True)
        self.assertEqual(self.email.call_count, 2)  # One request, one receipt.

    def test_card_then_received_uncashed_check_does_not_close_invoice(self):
        rid, _ = self.new_request()
        self.pay(rid, self.add_attempt(rid))
        payload = AdminClientManualTransactionCreateRequest(transaction_type="PAYMENT", amount_incl_vat="700",
            payment_method_code="CHECK", currency="EUR", legal_entity_id=self.entity_id,
            reconciled_invoice_note_ids=[self.note_id], mark_reconciled_invoices_paid=True)
        invoices.create_admin_client_manual_transaction(self.owner_id, payload, self.db, self.actor)
        data = self.load_request(rid)[1]
        self.assertEqual(data["invoice_status"], "ISSUED")
        self.assertEqual(self.transaction_count(), 2)

    def test_cancel_is_blocked_while_bank_checkout_is_open(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        with patch.object(service, "lookup_payment", return_value=self.lookup(rid, attempt, paid=False, status="PENDING")):
            with self.assertRaises(HTTPException):
                service.cancel_request(self.db, self.owner_id, self.note_id, rid)
        self.db.rollback()
        self.assertEqual(self.load_request(rid)[2]["status"], "PENDING")

    def test_uncertain_checkout_cannot_create_second_charge(self):
        rid, _ = self.new_request()
        note, data, row, _ = self.load_request(rid)
        token = service.token_for(note, data, row)
        uncertain = CheckoutCreateResult(False, PaymentProvider.PAYPLUG, None, "pay_unknown", "PENDING", "incomplete", False)
        with patch.object(service, "create_checkout_session", return_value=uncertain) as create, patch.object(service, "resolve_webhook_secret", return_value="test-secret"):
            for _ in range(2):
                with self.assertRaises(HTTPException):
                    service.checkout(self.db, client_id=self.owner_id, note_id=self.note_id, request_id=rid, token=token)
                self.db.rollback()
        create.assert_called_once()
        self.assertEqual(self.load_request(rid)[2]["status"], "REVIEW")

    def test_changed_balance_blocks_checkout_before_any_psp_call(self):
        rid, _ = self.new_request()
        note, data, row, _ = self.load_request(rid)
        data["total_to_pay_by_currency"] = {"EUR": "200.00"}
        # Persist an explicit prior balance as in an older carry-balance invoice.
        data["auto_include_previous_balance"] = True
        service.save(self.db, note, data)
        token = service.token_for(note, data, row)
        with patch.object(service, "create_checkout_session") as create, self.assertRaises(HTTPException):
            service.checkout(self.db, client_id=self.owner_id, note_id=self.note_id, request_id=rid, token=token)
        create.assert_not_called()

    def test_checkout_double_click_reuses_pending_reference(self):
        rid, _ = self.new_request()
        note, data, row, _ = self.load_request(rid)
        token = service.token_for(note, data, row)
        created = CheckoutCreateResult(True, PaymentProvider.PAYPLUG, "https://secure.payplug.com/test", "pay_checkout", "PENDING", "ok", False)
        with patch.object(service, "create_checkout_session", return_value=created) as create, patch.object(service, "resolve_webhook_secret", return_value="test-secret"):
            self.assertEqual(service.checkout(self.db, client_id=self.owner_id, note_id=self.note_id, request_id=rid, token=token), created.checkout_url)
            attempt = self.load_request(rid)[2]["attempts"][0]
            with patch.object(service, "lookup_payment", return_value=self.lookup(rid, attempt, paid=False, status="PENDING")):
                self.assertEqual(service.checkout(self.db, client_id=self.owner_id, note_id=self.note_id, request_id=rid, token=token), created.checkout_url)
        create.assert_called_once()
        self.assertEqual(create.call_args.args[1].amount, Decimal("396"))
        self.assertEqual(self.transaction_count(), 0)

    def test_cancel_unopened_link_and_preserve_invoice(self):
        rid, _ = self.new_request()
        service.cancel_request(self.db, self.owner_id, self.note_id, rid)
        note, data, row, _ = self.load_request(rid)
        self.assertEqual(row["status"], "CANCELLED")
        self.assertEqual(service.balance(data), Decimal("1096"))
        with self.assertRaises(HTTPException):
            service.checkout(self.db, client_id=self.owner_id, note_id=self.note_id, request_id=rid, token=service.token_for(note, data, row))

    def test_active_link_blocks_invoice_deletion_and_family_split(self):
        rid, _ = self.new_request()
        for action in (invoices.delete_admin_client_range_invoice, invoices.split_admin_client_range_invoice_by_family):
            with self.subTest(action=action.__name__), self.assertRaises(HTTPException) as caught:
                action(self.owner_id, self.note_id, self.db, self.actor)
            self.assertEqual(caught.exception.status_code, 409)
            self.db.rollback()
        self.assertEqual(service.balance(self.load_request(rid)[1]), Decimal("1096"))

    def test_two_concurrent_callbacks_create_one_transaction(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        lookup = self.lookup(rid, attempt)
        def execute():
            with self.Session() as db:
                note, data, _ = service.load(db, self.owner_id, self.note_id)
                row = service.find(data, rid)
                service.settle(db, note, data, row, row["attempts"][0], lookup)
                service.save(db, note, data)
        self.db.rollback()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: execute(), range(2)))
        self.db.expire_all()
        self.assertEqual(self.transaction_count(), 1)
        self.assertEqual(service.balance(self.load_request(rid)[1]), Decimal("700"))

    def test_return_url_never_trusts_browser_success(self):
        rid, _ = self.new_request()
        attempt = self.add_attempt(rid)
        note, data, row, _ = self.load_request(rid)
        token = service.token_for(note, data, row, attempt_id=attempt["id"])
        with patch.object(service, "lookup_payment", return_value=self.lookup(rid, attempt, paid=False, failed=True, status="FAILED")):
            response = routes.payment_return(self.owner_id, self.note_id, rid, UUID(attempt["id"]), BackgroundTasks(), token, "success", self.db)
        self.assertIn("Paiement non confirmé", response.body.decode())
        self.assertEqual(self.transaction_count(), 0)

    def test_bad_webhook_secret_does_not_call_provider(self):
        with patch.object(service, "resolve_webhook_secret", return_value="expected"), patch.object(service, "lookup_payment") as lookup:
            with self.assertRaises(HTTPException) as caught:
                routes.webhook(self.owner_id, self.note_id, uuid4(), uuid4(), BackgroundTasks(), "test-token", "bad", self.db)
        self.assertEqual(caught.exception.status_code, 401)
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
