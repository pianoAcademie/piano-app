from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import (
    _append_invoice_change_summary_to_email_body,
    approve_admin_client_billing_adjustment,
    create_admin_client_quote_change,
    _normalize_quote_change_financial_impact,
)
from app.models.client_record import ClientBillingAdjustment, ClientManualTransaction, StudentQuoteChange
from app.schemas.admin import AdminClientPaymentOut, AdminStudentQuoteChangeCreateRequest


class _FakeAdjustmentDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_calls = 0
        self.commit_calls = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_calls += 1
        for item in self.added:
            if isinstance(item, (ClientBillingAdjustment, ClientManualTransaction, StudentQuoteChange)) and item.id is None:
                item.id = uuid4()

    def commit(self) -> None:
        self.commit_calls += 1


def _payment_out_for_created_manual_transaction(db: _FakeAdjustmentDb) -> list[AdminClientPaymentOut]:
    created = next(item for item in db.added if isinstance(item, ClientManualTransaction))
    return [
        AdminClientPaymentOut(
            id=created.id,
            source="MANUAL",
            occurred_at=created.occurred_at,
            label=created.label,
            status=created.status,
            amount_excl_vat=created.amount_excl_vat,
            vat_rate=created.vat_rate,
            vat_amount=created.vat_amount,
            total_incl_vat=created.total_incl_vat,
            currency=created.currency,
            reference=created.reference,
            seller_legal_entity_id=created.legal_entity_id,
            billing_entity="PIANO ACADEMIE",
            manual_transaction_type=created.transaction_type,
            student_user_id=created.student_user_id,
            description=created.description,
            category=created.category,
        )
    ]


class BillingAdjustmentApprovalTests(unittest.TestCase):
    def test_financial_impact_sign_follows_billing_action(self) -> None:
        self.assertEqual(
            _normalize_quote_change_financial_impact(Decimal("120.00"), "TO_INVOICE"),
            Decimal("120.00"),
        )
        self.assertEqual(
            _normalize_quote_change_financial_impact(Decimal("-120.00"), "TO_INVOICE"),
            Decimal("120.00"),
        )
        self.assertEqual(
            _normalize_quote_change_financial_impact(Decimal("60.00"), "TO_CREDIT"),
            Decimal("-60.00"),
        )
        self.assertEqual(
            _normalize_quote_change_financial_impact(Decimal("-60.00"), "TO_CREDIT"),
            Decimal("-60.00"),
        )
        self.assertEqual(
            _normalize_quote_change_financial_impact(Decimal("-15.555"), "MANUAL_REVIEW"),
            Decimal("-15.56"),
        )

    def test_invoice_email_summary_is_appended_to_default_body(self) -> None:
        summary = (
            "Changements depuis la derniere facture emise :\n"
            "- 2026-10-30 - Camille: Ajout cours piano 30 minutes (45.00 EUR, a facturer)"
        )

        text_body = _append_invoice_change_summary_to_email_body(
            "Bonjour, votre facture est disponible.",
            change_summary=summary,
            body_format="TEXT",
        )
        html_body = _append_invoice_change_summary_to_email_body(
            "<p>Bonjour, votre facture est disponible.</p>",
            change_summary=summary,
            body_format="HTML",
        )

        self.assertIn("Changements depuis la derniere facture emise", text_body)
        self.assertIn("Ajout cours piano", text_body)
        self.assertIn("<ul><li>2026-10-30 - Camille", html_body)

    def test_invoice_email_summary_helper_leaves_empty_summary_out(self) -> None:
        self.assertEqual(
            _append_invoice_change_summary_to_email_body(
                "Bonjour, votre facture est disponible.",
                change_summary="",
                body_format="TEXT",
            ),
            "Bonjour, votre facture est disponible.",
        )

    def test_create_credit_change_creates_ready_negative_adjustment(self) -> None:
        client_id = uuid4()
        legal_entity_id = uuid4()
        actor_id = uuid4()
        db = _FakeAdjustmentDb()
        payload = AdminStudentQuoteChangeCreateRequest(
            student_id=client_id,
            change_type="COURSE_CANCELLED",
            title="Cours annule non rattrape",
            before_snapshot={"text": "Cours du mercredi maintenu"},
            after_snapshot={"text": "Cours annule sans rattrapage"},
            financial_impact_ttc=Decimal("60.00"),
            currency="EUR",
            billing_action="TO_CREDIT",
            vat_rate=Decimal("20.000"),
            legal_entity_id=legal_entity_id,
            client_visible_note="A deduire de la prochaine facture.",
        )

        with patch(
            "app.api.routes.admin_clients._require_client",
            return_value=SimpleNamespace(id=client_id, preferred_currency="EUR"),
        ), patch(
            "app.api.routes.admin_clients._student_quote_change_allowed_users",
            return_value={client_id: SimpleNamespace(id=client_id)},
        ), patch(
            "app.api.routes.admin_clients._require_active_legal_entity",
        ), patch(
            "app.api.routes.admin_clients._create_client_note",
        ), patch(
            "app.api.routes.admin_clients._require_scoped_student_quote_change_out",
            return_value=SimpleNamespace(id=uuid4()),
        ):
            create_admin_client_quote_change(
                client_id=client_id,
                payload=payload,
                db=db,
                actor=SimpleNamespace(id=actor_id),
            )

        change = next(item for item in db.added if isinstance(item, StudentQuoteChange))
        adjustment = next(item for item in db.added if isinstance(item, ClientBillingAdjustment))
        self.assertEqual(change.billing_action, "TO_CREDIT")
        self.assertEqual(change.financial_impact_ttc, Decimal("-60.00"))
        self.assertEqual(adjustment.status, "READY")
        self.assertEqual(adjustment.adjustment_type, "CREDIT_NOTE")
        self.assertEqual(adjustment.total_incl_vat, Decimal("-60.00"))
        self.assertEqual(adjustment.amount_excl_vat, Decimal("-50.00"))
        self.assertEqual(adjustment.vat_amount, Decimal("-10.00"))
        self.assertEqual(db.flush_calls, 1)
        self.assertEqual(db.commit_calls, 1)

    def test_approve_positive_adjustment_creates_pending_charge(self) -> None:
        client_id = uuid4()
        student_id = uuid4()
        change_id = uuid4()
        legal_entity_id = uuid4()
        adjustment = SimpleNamespace(
            id=uuid4(),
            user_id=client_id,
            student_user_id=student_id,
            change_id=change_id,
            quote_id=uuid4(),
            actor_user_id=None,
            status="READY",
            adjustment_type="INVOICE",
            label="Cours ajoute",
            description="Cours supplementaire valide par la famille",
            amount_excl_vat=Decimal("100.00"),
            vat_rate=Decimal("20.000"),
            vat_amount=Decimal("20.00"),
            total_incl_vat=Decimal("120.00"),
            currency="EUR",
            legal_entity_id=legal_entity_id,
            converted_manual_transaction_id=None,
            dismissed_reason=None,
            decided_at=None,
            created_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
        )
        db = _FakeAdjustmentDb()
        now = datetime(2026, 5, 23, 8, 30, tzinfo=timezone.utc)

        with patch("app.api.routes.admin_clients._require_client", return_value=SimpleNamespace(id=client_id)), patch(
            "app.api.routes.admin_clients._require_scoped_billing_adjustment",
            return_value=adjustment,
        ), patch("app.api.routes.admin_clients._require_active_legal_entity"), patch(
            "app.api.routes.admin_clients._utcnow",
            return_value=now,
        ), patch("app.api.routes.admin_clients._create_client_note"), patch(
            "app.api.routes.admin_clients._build_admin_client_payments",
            side_effect=lambda db, client_id: _payment_out_for_created_manual_transaction(db),
        ):
            response = approve_admin_client_billing_adjustment(
                client_id=client_id,
                adjustment_id=adjustment.id,
                db=db,
                actor=SimpleNamespace(id=uuid4()),
            )

        created = next(item for item in db.added if isinstance(item, ClientManualTransaction))
        self.assertEqual(created.transaction_type, "CHARGE")
        self.assertEqual(created.status, "PENDING")
        self.assertEqual(created.total_incl_vat, Decimal("120.00"))
        self.assertEqual(created.reference, f"CHANGE:{change_id}")
        self.assertEqual(adjustment.status, "CONVERTED")
        self.assertEqual(adjustment.converted_manual_transaction_id, created.id)
        self.assertEqual(response.id, created.id)
        self.assertEqual(db.flush_calls, 1)
        self.assertEqual(db.commit_calls, 1)

    def test_approve_negative_adjustment_creates_completed_discount(self) -> None:
        client_id = uuid4()
        legal_entity_id = uuid4()
        adjustment = SimpleNamespace(
            id=uuid4(),
            user_id=client_id,
            student_user_id=client_id,
            change_id=uuid4(),
            quote_id=None,
            actor_user_id=None,
            status="READY",
            adjustment_type="CREDIT_NOTE",
            label="Cours annule non rattrape",
            description="Deduction validee",
            amount_excl_vat=Decimal("-50.00"),
            vat_rate=Decimal("20.000"),
            vat_amount=Decimal("-10.00"),
            total_incl_vat=Decimal("-60.00"),
            currency="EUR",
            legal_entity_id=legal_entity_id,
            converted_manual_transaction_id=None,
            dismissed_reason=None,
            decided_at=None,
            created_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
        )
        db = _FakeAdjustmentDb()

        with patch("app.api.routes.admin_clients._require_client", return_value=SimpleNamespace(id=client_id)), patch(
            "app.api.routes.admin_clients._require_scoped_billing_adjustment",
            return_value=adjustment,
        ), patch("app.api.routes.admin_clients._require_active_legal_entity"), patch(
            "app.api.routes.admin_clients._utcnow",
            return_value=datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc),
        ), patch("app.api.routes.admin_clients._create_client_note"), patch(
            "app.api.routes.admin_clients._build_admin_client_payments",
            side_effect=lambda db, client_id: _payment_out_for_created_manual_transaction(db),
        ):
            response = approve_admin_client_billing_adjustment(
                client_id=client_id,
                adjustment_id=adjustment.id,
                db=db,
                actor=SimpleNamespace(id=uuid4()),
            )

        created = next(item for item in db.added if isinstance(item, ClientManualTransaction))
        self.assertEqual(created.transaction_type, "DISCOUNT")
        self.assertEqual(created.status, "COMPLETED")
        self.assertEqual(created.total_incl_vat, Decimal("-60.00"))
        self.assertEqual(adjustment.status, "CONVERTED")
        self.assertEqual(response.manual_transaction_type, "DISCOUNT")


if __name__ == "__main__":
    unittest.main()
