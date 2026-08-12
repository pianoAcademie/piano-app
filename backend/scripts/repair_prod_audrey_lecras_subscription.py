from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client_record import ClientLegacyInvoice, ClientNoteEntry
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.user import User, UserRole


SCRIPT_PREFIX = "PROD_REPAIR_AUDREY_LECRAS_SUBSCRIPTION"
TARGET_EMAIL = "audrey.lallart@gmail.com"
TARGET_SPORTIGO_ID = "708650"
TARGET_MIGRATION_SOURCE = "SPORTIGO_2026_OPENING_BALANCE"
TARGET_INVOICE_REFERENCE = "FA-PIANO-2026-803"
SUSPENSION_START_DATE = date(2026, 7, 12)
SUSPENSION_END_DATE = date(2026, 8, 12)
TARGET_NEXT_PAYMENT_DATE = date(2026, 9, 15)
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
NOTE_MARKER = "PROD_REPAIR_AUDREY_LECRAS_SUBSCRIPTION_20260812"


def _local_midnight_utc(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=PARIS_TIMEZONE).astimezone(timezone.utc)


def _assert_target_state(
    *,
    user: User | None,
    subscriptions: list[tuple[ClientPlanSubscription, Plan]],
    target_invoice: ClientLegacyInvoice | None,
) -> tuple[ClientPlanSubscription, Plan]:
    if user is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target_user_missing email={TARGET_EMAIL}")
    if user.role != UserRole.CLIENT:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target_user_not_client user={user.id} role={user.role}")
    if TARGET_SPORTIGO_ID not in (user.private_note or ""):
        raise SystemExit(f"[{SCRIPT_PREFIX}] sportigo_marker_missing user={user.id}")
    if len(subscriptions) != 1:
        raise SystemExit(
            f"[{SCRIPT_PREFIX}] expected_one_migrated_subscription user={user.id} found={len(subscriptions)}"
        )
    subscription, plan = subscriptions[0]
    if plan.kind != PlanKind.SUBSCRIPTION:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target_plan_not_subscription plan={plan.code}")
    if subscription.migration_source_code != TARGET_MIGRATION_SOURCE:
        raise SystemExit(
            f"[{SCRIPT_PREFIX}] migration_source_mismatch subscription={subscription.id} "
            f"source={subscription.migration_source_code or '-'}"
        )
    if target_invoice is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] july_invoice_missing reference={TARGET_INVOICE_REFERENCE}")
    if target_invoice.source_customer_id != TARGET_SPORTIGO_ID:
        raise SystemExit(
            f"[{SCRIPT_PREFIX}] july_invoice_customer_mismatch invoice={target_invoice.id} "
            f"customer={target_invoice.source_customer_id or '-'}"
        )
    if target_invoice.total_incl_vat != 125:
        raise SystemExit(
            f"[{SCRIPT_PREFIX}] july_invoice_amount_mismatch invoice={target_invoice.id} "
            f"amount={target_invoice.total_incl_vat}"
        )
    return subscription, plan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair Audrey Lecras/Lallart's migrated subscription after the July-August suspension omission."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    args = parser.parse_args()

    target_next_payment_at = _local_midnight_utc(TARGET_NEXT_PAYMENT_DATE)
    suspension_starts_at = _local_midnight_utc(SUSPENSION_START_DATE)
    suspension_ends_at = _local_midnight_utc(SUSPENSION_END_DATE)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .where(func.lower(User.email) == TARGET_EMAIL)
            .with_for_update()
            .limit(1)
        )
        subscriptions = []
        if user is not None:
            subscriptions = db.execute(
                select(ClientPlanSubscription, Plan)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .where(
                    ClientPlanSubscription.user_id == user.id,
                    ClientPlanSubscription.migration_source_code == TARGET_MIGRATION_SOURCE,
                    Plan.kind == PlanKind.SUBSCRIPTION,
                )
                .with_for_update()
            ).all()
        target_invoice = None
        if user is not None:
            target_invoice = db.scalar(
                select(ClientLegacyInvoice)
                .where(
                    ClientLegacyInvoice.user_id == user.id,
                    ClientLegacyInvoice.source == "SPORTIGO",
                    ClientLegacyInvoice.external_reference == TARGET_INVOICE_REFERENCE,
                )
                .limit(1)
            )

        subscription, plan = _assert_target_state(
            user=user,
            subscriptions=list(subscriptions),
            target_invoice=target_invoice,
        )
        assert user is not None
        assert target_invoice is not None

        existing_note = db.scalar(
            select(ClientNoteEntry.id)
            .where(
                ClientNoteEntry.user_id == user.id,
                ClientNoteEntry.message.contains(NOTE_MARKER),
            )
            .limit(1)
        )
        legacy_invoice_count = int(
            db.scalar(
                select(func.count(ClientLegacyInvoice.id)).where(
                    ClientLegacyInvoice.user_id == user.id,
                    ClientLegacyInvoice.source == "SPORTIGO",
                    ClientLegacyInvoice.source_customer_id == TARGET_SPORTIGO_ID,
                )
            )
            or 0
        )

        before = {
            "status": subscription.status.value,
            "ends_at": subscription.ends_at,
            "next_payment_at": subscription.next_payment_at,
            "current_period_end": subscription.current_period_end,
            "suspension_starts_at": subscription.suspension_starts_at,
            "suspension_ends_at": subscription.suspension_ends_at,
        }
        changed = any(
            [
                subscription.ends_at != target_next_payment_at,
                subscription.next_payment_at != target_next_payment_at,
                subscription.current_period_end != target_next_payment_at,
                subscription.suspension_start_date != SUSPENSION_START_DATE,
                subscription.suspension_end_date != SUSPENSION_END_DATE,
                subscription.suspension_starts_at != suspension_starts_at,
                subscription.suspension_ends_at != suspension_ends_at,
                subscription.suspension_duration_unit != "MONTH",
                subscription.suspension_duration_value != 1,
            ]
        )

        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}")
        print(
            f"[{SCRIPT_PREFIX}] user={user.id}|name={user.first_name or '-'} {user.last_name or '-'}|"
            f"email={user.email}|sportigo_id={TARGET_SPORTIGO_ID}"
        )
        print(
            f"[{SCRIPT_PREFIX}] subscription={subscription.id}|plan={plan.code}|"
            f"migration_source={subscription.migration_source_code}|status={subscription.status.value}"
        )
        print(
            f"[{SCRIPT_PREFIX}] july_invoice={target_invoice.external_reference}|"
            f"issued_at={target_invoice.issued_at.isoformat()}|amount={target_invoice.total_incl_vat} "
            f"{target_invoice.currency}|legacy_invoice_count={legacy_invoice_count}"
        )
        print(
            f"[{SCRIPT_PREFIX}] before=next:{before['next_payment_at']}|end:{before['ends_at']}|"
            f"period_end:{before['current_period_end']}|suspension:{before['suspension_starts_at']}->{before['suspension_ends_at']}"
        )
        print(
            f"[{SCRIPT_PREFIX}] target=next:{target_next_payment_at}|end:{target_next_payment_at}|"
            f"period_end:{target_next_payment_at}|suspension:{suspension_starts_at}->{suspension_ends_at}"
        )
        print(f"[{SCRIPT_PREFIX}] changed={str(changed).lower()}|note_exists={str(existing_note is not None).lower()}")

        if args.apply:
            subscription.ends_at = target_next_payment_at
            subscription.next_payment_at = target_next_payment_at
            subscription.current_period_end = target_next_payment_at
            subscription.suspension_start_date = SUSPENSION_START_DATE
            subscription.suspension_end_date = SUSPENSION_END_DATE
            subscription.suspension_starts_at = suspension_starts_at
            subscription.suspension_ends_at = suspension_ends_at
            subscription.suspension_duration_unit = "MONTH"
            subscription.suspension_duration_value = 1
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.updated_at = now
            db.add(subscription)

            if existing_note is None:
                db.add(
                    ClientNoteEntry(
                        user_id=user.id,
                        author_user_id=None,
                        entry_type="AUTO",
                        message=(
                            f"{NOTE_MARKER} - Correction administrative : suspension historique du "
                            "12/07/2026 au 12/08/2026 et prochaine echeance decalee du 15/08/2026 "
                            "au 15/09/2026 apres le prelevement Sportigo du 15/07/2026 "
                            f"({TARGET_INVOICE_REFERENCE}, 125 EUR)."
                        ),
                    )
                )
            db.commit()
            print(f"[{SCRIPT_PREFIX}] committed=true")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")


if __name__ == "__main__":
    main()
