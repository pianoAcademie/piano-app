from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select

from app.api.routes.admin_clients import (
    _allocate_invoice_number_for_seller_entity,
    _append_private_invoice_note,
    _build_invoice_range_note_message,
    _parse_invoice_range_note_entry,
    create_admin_client_range_invoice,
)
from app.db.session import SessionLocal
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry
from app.models.plan import ClientPlanSubscription
from app.models.quote import Quote
from app.models.user import ClientKind, User, UserRole
from app.schemas.admin import AdminRangeInvoiceCreateRequest


BILLING_ID = UUID("31d3b3a9-ab88-4909-84c5-cf3fe9f0e6d3")
MARINE_ID = BILLING_ID
ELSA_ID = UUID("35c102bf-97c4-472e-9f77-e013cdf1ab4c")
MARINE_QUOTE = "DV-20260522102555-1636"
ELSA_QUOTE = "DV-20260826084730-847A"
MARINE_SUBSCRIPTION_ID = UUID("27b16516-76c5-43be-87c2-293e8b1e9854")
ELSA_SUBSCRIPTION_ID = UUID("ed156da2-a8cb-411c-a8eb-0e99c8296e86")
SOURCE_INVOICE_NOTE_IDS = (
    UUID("262b18c2-cb27-49da-9b09-06a1ecff5ee2"),  # PA26-0815
    UUID("fba09e1e-3762-437f-b46b-3518a5c14d99"),  # PA26-0817
)
REFERRAL_TRANSACTION_ID = UUID("af959fd3-8aa4-4861-a220-efeab6f3074a")
EXPECTED_TOTALS = {
    MARINE_QUOTE: Decimal("803.00"),
    ELSA_QUOTE: Decimal("861.00"),
}
INSTALLMENT_AMOUNTS = {
    MARINE_QUOTE: Decimal("80.30"),
    ELSA_QUOTE: Decimal("86.10"),
}
EXPECTED_FAMILY_MONTHLY = Decimal("166.40")
EXPECTED_FIRST_DUE = Decimal("116.40")
INSTALLMENT_MONTHS = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
    (2027, 1),
    (2027, 2),
    (2027, 3),
    (2027, 4),
    (2027, 5),
    (2027, 6),
)


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _credit_source_invoice(
    db,
    *,
    source_note: ClientNoteEntry,
    actor: User,
    issued_date: date,
) -> ClientNoteEntry:
    metadata = _parse_invoice_range_note_entry(source_note)
    assert metadata is not None
    assert str(metadata.get("invoice_status") or "").upper() == "ISSUED"
    assert not metadata.get("payment_provider_reference")
    assert not metadata.get("paid_at")
    assert not metadata.get("credit_note_note_id")
    source_lines = db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.note_id == source_note.id)
    ).all()
    assert source_lines

    seller_ids = {line.seller_legal_entity_id for line in source_lines if line.seller_legal_entity_id is not None}
    assert len(seller_ids) == 1
    seller_id = next(iter(seller_ids))
    credit_number = _allocate_invoice_number_for_seller_entity(
        db,
        seller_legal_entity_id=seller_id,
        issued_at=datetime.combine(issued_date, time.min, tzinfo=timezone.utc),
    )
    source_number = str(metadata.get("invoice_number") or "")
    reason = "Remplacement par une facture familiale unique avec mensualites constantes."
    totals: dict[str, Decimal] = {}
    for line in source_lines:
        currency = (line.currency or "EUR").upper()
        totals[currency] = q2(totals.get(currency, Decimal("0.00")) + Decimal(line.total_incl_vat))

    credit_metadata = dict(metadata)
    for field in (
        "emailed_at",
        "reminded_at",
        "paid_at",
        "payment_url",
        "payment_provider",
        "payment_provider_reference",
        "payment_amount_paid",
        "payment_currency",
        "payment_checkout_status",
        "payment_lookup_status",
        "payment_transaction_id",
        "bank_transfer_order_id",
        "bank_transfer_order_reference",
        "bank_transfer_order_status",
        "bank_transfer_order_expires_at",
        "bank_transfer_order_paid_at",
        "reconciled_manual_payment_ids",
        "applied_payment_totals_by_currency",
        "applied_payment_lines",
        "opening_balance_by_currency",
        "credit_note_note_id",
        "credit_note_number",
        "partial_payment_requests",
    ):
        credit_metadata.pop(field, None)
    credit_metadata.update(
        {
            "document_type": "CREDIT_NOTE",
            "invoice_number": credit_number,
            "invoice_status": "CREDIT_NOTE",
            "issued_date": issued_date.isoformat(),
            "due_date": issued_date.isoformat(),
            "no_due_date": True,
            "included_payment_keys": [],
            "totals_by_currency": {currency: f"{-amount:.2f}" for currency, amount in totals.items()},
            "total_to_pay_by_currency": {currency: "0.00" for currency in totals},
            "original_invoice_note_id": str(source_note.id),
            "original_invoice_number": source_number,
            "credit_note_reason": reason,
            "credited_at": datetime.combine(issued_date, time.min, tzinfo=timezone.utc).isoformat(),
            "public_note": f"Avoir relatif a la facture {source_number}. Motif : {reason}",
            "private_note": _append_private_invoice_note(
                credit_metadata.get("private_note"),
                f"Avoir cree pour annuler la facture {source_number}.",
            ),
        }
    )
    credit_note = ClientNoteEntry(
        user_id=BILLING_ID,
        author_user_id=actor.id,
        entry_type="MANUAL",
        message=_build_invoice_range_note_message(credit_metadata),
    )
    db.add(credit_note)
    db.flush()
    for line in source_lines:
        db.add(
            ClientInvoiceLine(
                note_id=credit_note.id,
                user_id=BILLING_ID,
                source=line.source,
                source_payment_id=line.source_payment_id,
                occurred_at=line.occurred_at,
                label=line.label,
                amount_excl_vat=-q2(Decimal(line.amount_excl_vat)),
                vat_rate=Decimal(line.vat_rate),
                vat_amount=-q2(Decimal(line.vat_amount)),
                total_incl_vat=-q2(Decimal(line.total_incl_vat)),
                currency=line.currency,
                billing_entity=line.billing_entity,
                seller_legal_entity_id=line.seller_legal_entity_id,
            )
        )

    metadata["invoice_status"] = "CANCELLED"
    metadata["credit_note_note_id"] = str(credit_note.id)
    metadata["credit_note_number"] = credit_number
    metadata["credited_at"] = datetime.combine(issued_date, time.min, tzinfo=timezone.utc).isoformat()
    metadata["private_note"] = _append_private_invoice_note(
        metadata.get("private_note"),
        f"Facture annulee par l'avoir {credit_number}. Motif : {reason}",
    )
    source_note.message = _build_invoice_range_note_message(metadata)
    db.add(source_note)
    return credit_note


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    issued_date = date(2026, 9, 4)

    with SessionLocal() as db:
        billing = db.get(User, BILLING_ID)
        marine = db.get(User, MARINE_ID)
        elsa = db.get(User, ELSA_ID)
        actor = db.scalar(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at).limit(1))
        assert billing is not None and billing.email == "marine.pinotie55@gmail.com"
        assert marine is not None and marine.client_kind == ClientKind.ADULT
        assert elsa is not None and elsa.client_kind == ClientKind.CHILD
        assert actor is not None

        quotes = {
            quote.quote_number: quote
            for quote in db.scalars(
                select(Quote).where(Quote.quote_number.in_([MARINE_QUOTE, ELSA_QUOTE])).with_for_update()
            ).all()
        }
        assert set(quotes) == {MARINE_QUOTE, ELSA_QUOTE}
        assert all(quote.status == "approved" for quote in quotes.values())
        assert all(q2(Decimal(quote.total_ttc)) == EXPECTED_TOTALS[number] for number, quote in quotes.items())
        assert len({quote.legal_entity_id for quote in quotes.values()}) == 1

        subscriptions = {
            sub.id: sub
            for sub in db.scalars(
                select(ClientPlanSubscription)
                .where(ClientPlanSubscription.id.in_([MARINE_SUBSCRIPTION_ID, ELSA_SUBSCRIPTION_ID]))
                .with_for_update()
            ).all()
        }
        assert set(subscriptions) == {MARINE_SUBSCRIPTION_ID, ELSA_SUBSCRIPTION_ID}
        assert subscriptions[MARINE_SUBSCRIPTION_ID].user_id == MARINE_ID
        assert subscriptions[ELSA_SUBSCRIPTION_ID].user_id == ELSA_ID

        source_notes = db.scalars(
            select(ClientNoteEntry)
            .where(ClientNoteEntry.id.in_(SOURCE_INVOICE_NOTE_IDS))
            .with_for_update()
        ).all()
        assert {note.id for note in source_notes} == set(SOURCE_INVOICE_NOTE_IDS)
        for note in source_notes:
            metadata = _parse_invoice_range_note_entry(note)
            assert metadata is not None and str(metadata.get("invoice_status") or "").upper() == "ISSUED"
            assert not metadata.get("paid_at") and not metadata.get("payment_provider_reference")

        quote_ids = [quote.id for quote in quotes.values()]
        assert not db.scalar(
            select(ClientManualTransaction.id)
            .where(ClientManualTransaction.reference.like("QUOTE:%:INSTALLMENT:%"))
            .where(ClientManualTransaction.user_id == BILLING_ID)
            .limit(1)
        )
        referral = db.get(ClientManualTransaction, REFERRAL_TRANSACTION_ID)
        assert referral is not None and referral.user_id == BILLING_ID
        assert referral.transaction_type == "DISCOUNT" and q2(Decimal(referral.total_incl_vat)) == Decimal("-50.00")

        old_quote_charges = db.scalars(
            select(ClientManualTransaction)
            .where(
                ClientManualTransaction.user_id == BILLING_ID,
                ClientManualTransaction.transaction_type == "CHARGE",
                ClientManualTransaction.reference.like("QUOTE:%:ROW:%"),
            )
            .with_for_update()
        ).all()
        old_quote_charges = [
            row for row in old_quote_charges
            if any(str(row.reference or "").startswith(f"QUOTE:{quote_id}:ROW:") for quote_id in quote_ids)
        ]
        assert len(old_quote_charges) == 5
        assert q2(sum((Decimal(row.total_incl_vat) for row in old_quote_charges), Decimal("0.00"))) == Decimal("190.00")

        print(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        print("cancel and credit: PA26-0815 (201.00 EUR), PA26-0817 (143.00 EUR)")
        print("fixed family schedule: 10 x 166.40 EUR")
        print("replacement September invoice: 166.40 - 50.00 referral = 116.40 EUR")
        print("notifications: none")
        if not args.apply:
            db.rollback()
            return

        for note in sorted(source_notes, key=lambda item: item.created_at):
            _credit_source_invoice(db, source_note=note, actor=actor, issued_date=issued_date)

        subscriptions[MARINE_SUBSCRIPTION_ID].billing_method_code = "CARD_MONTHLY_FIXED"
        subscriptions[ELSA_SUBSCRIPTION_ID].billing_method_code = "CARD_MONTHLY_FIXED"
        db.add_all(list(subscriptions.values()))
        for row in old_quote_charges:
            row.status = "CANCELLED"
            row.updated_at = now
            db.add(row)

        september_transaction_ids = []
        for quote_number, student_id in ((MARINE_QUOTE, MARINE_ID), (ELSA_QUOTE, ELSA_ID)):
            quote = quotes[quote_number]
            installment_amount = INSTALLMENT_AMOUNTS[quote_number]
            assert q2(installment_amount * 10) == EXPECTED_TOTALS[quote_number]
            vat_rate = Decimal("20.000")
            for index, (year, month) in enumerate(INSTALLMENT_MONTHS, start=1):
                due_date = date(year, month, 1)
                amount_ht = q2(installment_amount / Decimal("1.20"))
                transaction = ClientManualTransaction(
                    user_id=BILLING_ID,
                    student_user_id=student_id,
                    actor_user_id=actor.id,
                    transaction_type="CHARGE",
                    status="PENDING",
                    label=f"Echeance {index}/10 - {quote_number}",
                    description="Echeance mensuelle fixe conforme a la regularisation familiale",
                    category="Forfait annuel - mensualite fixe",
                    occurred_at=datetime.combine(due_date, time(hour=2), tzinfo=timezone.utc),
                    amount_excl_vat=amount_ht,
                    vat_rate=vat_rate,
                    vat_amount=q2(installment_amount - amount_ht),
                    total_incl_vat=installment_amount,
                    currency="EUR",
                    reference=f"QUOTE:{quote.id}:INSTALLMENT:{index}",
                    legal_entity_id=quote.legal_entity_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(transaction)
                db.flush()
                if index == 1:
                    september_transaction_ids.append(transaction.id)

        replacement = create_admin_client_range_invoice(
            client_id=BILLING_ID,
            payload=AdminRangeInvoiceCreateRequest(
                issued_date=issued_date,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 30),
                due_date=date(2026, 9, 7),
                include_pending=True,
                include_cancelled=False,
                layout="COMPILED",
                generation_mode="MANUAL",
                group_adjustments_by_type=False,
                include_discount_adjustments=True,
                include_supplement_adjustments=True,
                auto_include_previous_balance=False,
                selected_payment_keys=[
                    *(f"MANUAL:{transaction_id}" for transaction_id in september_transaction_ids),
                    f"MANUAL:{REFERRAL_TRANSACTION_ID}",
                ],
                public_note="Mensualite familiale septembre 2026 pour Marine Pinotie et Elsa Meyer.",
                private_note=(
                    "Remplace PA26-0815 et PA26-0817 par une facture familiale unique. "
                    "Mensualite brute 166,40 EUR; avoir parrainage 50,00 EUR; net a payer 116,40 EUR. "
                    "Aucun email envoye automatiquement."
                ),
            ),
            db=db,
            actor=actor,
        )
        assert q2(Decimal(str(replacement.total_to_pay_by_currency.get("EUR")))) == EXPECTED_FIRST_DUE
        print(f"applied: yes; replacement invoice: {replacement.invoice_number}; net due: 116.40 EUR")


if __name__ == "__main__":
    main()
