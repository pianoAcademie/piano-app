from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client_record import ClientManualTransaction, ClientNoteEntry
from app.models.plan import ClientPlanSubscription
from app.models.quote import Quote
from app.models.user import User, UserRole


QUOTE_NUMBER = "DV-20260706091430-83B0"
STUDENT_ID = "64413093-2e9a-4903-8d53-97603ff9c0d5"
BILLING_ID = "133250f9-2a68-4574-8ad5-be902a247617"
SUBSCRIPTION_ID = "fc07d723-32f1-4cf7-ae7a-acee675728b9"
PAID_TOTAL = Decimal("213.00")
EXPECTED_TOTAL = Decimal("851.00")
OVERPAYMENT = Decimal("15.40")


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).with_for_update())
        subscription = db.scalar(
            select(ClientPlanSubscription)
            .where(ClientPlanSubscription.id == SUBSCRIPTION_ID)
            .with_for_update()
        )
        billing = db.get(User, BILLING_ID)
        actor = db.scalar(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at).limit(1))
        assert quote is not None and quote.status == "approved" and Decimal(quote.total_ttc) == EXPECTED_TOTAL
        assert subscription is not None and str(subscription.user_id) == STUDENT_ID
        assert billing is not None and billing.email == "marine.adolphe@gmail.com"
        assert actor is not None

        schedule = list((quote.payment_terms_snapshot or {}).get("schedule") or [])
        assert len(schedule) == 10
        assert q2(sum(Decimal(str(item["amount_ttc"])) for item in schedule)) == EXPECTED_TOTAL
        future = schedule[1:]
        assert all(Decimal(str(item["amount_ttc"])) == Decimal("72.60") for item in future)

        existing = db.scalars(
            select(ClientManualTransaction).where(
                ClientManualTransaction.reference.like(f"QUOTE:{quote.id}:FIXED_INSTALLMENT:%")
            )
        ).all()
        assert not existing, "Rose Jeanson fixed installments already materialized"

        print(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"subscription: {subscription.id} {subscription.billing_method_code} -> CARD_MONTHLY_FIXED")
        print("2026-10: 72.60 - 15.40 credit = 57.20 EUR")
        print("2026-11 through 2027-06: 8 x 72.60 EUR")
        print(f"control: {PAID_TOTAL} + 57.20 + 8 x 72.60 = {EXPECTED_TOTAL}")
        if not args.apply:
            db.rollback()
            return

        subscription.billing_method_code = "CARD_MONTHLY_FIXED"
        db.add(subscription)
        vat_rate = Decimal("20.000")
        for index, item in enumerate(future, start=2):
            amount_ttc = Decimal(str(item["amount_ttc"]))
            due_date = datetime.fromisoformat(str(item["due_date"])).date()
            amount_ht = q2(amount_ttc / Decimal("1.20"))
            tx = ClientManualTransaction(
                user_id=billing.id,
                student_user_id=subscription.user_id,
                actor_user_id=actor.id,
                transaction_type="CHARGE",
                status="PENDING",
                label=f"Echeance {index}/10 - {QUOTE_NUMBER}",
                description="Echeance mensuelle fixe conforme au devis accepte",
                category="Forfait annuel - mensualite fixe",
                occurred_at=datetime.combine(due_date, time(hour=2), tzinfo=timezone.utc),
                amount_excl_vat=amount_ht,
                vat_rate=vat_rate,
                vat_amount=q2(amount_ttc - amount_ht),
                total_incl_vat=amount_ttc,
                currency="EUR",
                reference=f"QUOTE:{quote.id}:FIXED_INSTALLMENT:{index}",
                legal_entity_id=quote.legal_entity_id,
                created_at=now,
                updated_at=now,
            )
            db.add(tx)

        october_date = datetime.fromisoformat(str(future[0]["due_date"])).date()
        credit_ht = q2(OVERPAYMENT / Decimal("1.20"))
        db.add(
            ClientManualTransaction(
                user_id=billing.id,
                student_user_id=subscription.user_id,
                actor_user_id=actor.id,
                transaction_type="DISCOUNT",
                status="COMPLETED",
                label="Regularisation paiement septembre - Rose Jeanson",
                description="Imputation des 15,40 EUR payes en trop sur PA26-0828",
                category="Regularisation echeancier",
                occurred_at=datetime.combine(october_date, time(hour=2), tzinfo=timezone.utc),
                amount_excl_vat=-credit_ht,
                vat_rate=vat_rate,
                vat_amount=-q2(OVERPAYMENT - credit_ht),
                total_incl_vat=-OVERPAYMENT,
                currency="EUR",
                reference=f"QUOTE:{quote.id}:FIXED_INSTALLMENT:CREDIT:PA26-0828",
                legal_entity_id=quote.legal_entity_id,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ClientNoteEntry(
                user_id=billing.id,
                author_user_id=actor.id,
                entry_type="AUTO",
                message=(
                    "REGULARISATION ECHEANCIER ROSE JEANSON | PA26-0828 payee 213,00 EUR | "
                    "devis accepte 851,00 EUR | octobre 57,20 EUR apres imputation de 15,40 EUR | "
                    "novembre 2026 a juin 2027: 72,60 EUR/mois | aucune notification envoyee"
                ),
                created_at=now,
            )
        )
        db.commit()
        print("applied: yes; notifications: none")


if __name__ == "__main__":
    main()
