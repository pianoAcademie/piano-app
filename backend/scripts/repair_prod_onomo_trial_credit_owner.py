from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseType
from app.models.client_record import ClientNoteEntry
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription, Plan, PlanEntitlement, SubscriptionStatus
from app.models.subscription_engine import SubscriptionBillingCycle, SubscriptionPaymentAttempt
from app.models.user import ClientKind, User, UserRole
from app.services.client_status import promote_client_to_active_student, refresh_responsable_status

SCRIPT_PREFIX = "PROD_REPAIR_ONOMO_TRIAL_CREDIT_OWNER"
MOTHER_ID = UUID("07ae43cc-1db2-45e8-ba8f-155443efe533")
CHILD_ID = UUID("7a286966-b40e-4bf3-a1a8-464f94a9da66")
SUBSCRIPTION_ID = UUID("95bd30ee-e218-4c5c-9091-971e2fa2c36c")
PAYMENT_REFERENCE = "pay_3HVzQ0br9XR37w3U4XeHbo"
COLLECTIVE_TRIAL_COURSE_TYPE_ID = UUID("2e69344f-ddaa-4e98-937a-2ca1635c1d58")
ONSITE_CREDIT_TYPE_ID = UUID("0657a7b7-0856-4229-b37f-58180c89ee19")
AUDIT_MESSAGE = (
    "Correction bénéficiaire : carnet « Cours d'essai de piano en présentiel » "
    "transféré de Régine Onomo vers Noah Roisier-Onomo ; Régine reste la payeuse."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_label(user: User) -> str:
    name = " ".join(part for part in [user.first_name or "", user.last_name or ""] if part).strip()
    return f"{user.id}|{name or user.email}|{user.email}|{user.client_kind.value}|{user.client_status.value}"


def _assert_target_rows(db) -> tuple[User, User, ClientPlanSubscription, Plan, CourseType]:
    mother = db.scalar(select(User).where(User.id == MOTHER_ID).with_for_update())
    child = db.scalar(select(User).where(User.id == CHILD_ID).with_for_update())
    subscription_row = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(ClientPlanSubscription.id == SUBSCRIPTION_ID)
        .with_for_update()
    ).first()
    if mother is None or child is None or subscription_row is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target rows are missing")
    subscription, plan = subscription_row
    collective_trial = db.scalar(
        select(CourseType).where(CourseType.id == COLLECTIVE_TRIAL_COURSE_TYPE_ID).with_for_update()
    )
    if collective_trial is None or collective_trial.name.strip() != "Cours d'essai collectif":
        raise SystemExit(f"[{SCRIPT_PREFIX}] collective trial course type is missing or unexpected")

    if mother.role != UserRole.CLIENT or mother.client_kind != ClientKind.ADULT:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected mother row: {_user_label(mother)}")
    if mother.email.strip().lower() != "regine.onomo@hotmail.fr":
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected mother email: {mother.email}")
    if child.role != UserRole.CLIENT or child.client_kind != ClientKind.CHILD:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected child row: {_user_label(child)}")
    if (child.first_name or "").strip().casefold() != "noah" or "roisier-onomo" not in (child.last_name or "").strip().casefold():
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected child identity: {_user_label(child)}")
    family_link = db.scalar(
        select(ClientFamilyLink.id).where(
            ClientFamilyLink.adult_user_id == mother.id,
            ClientFamilyLink.child_user_id == child.id,
            ClientFamilyLink.is_billing_recipient.is_(True),
        )
    )
    if family_link is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] billing family link is missing")
    if plan.name.strip() != "Cours d'essai de piano en présentiel":
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected plan: {plan.name}")
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected status: {subscription.status.value}")
    if subscription.credits_initial != 1 or subscription.credits_remaining != 1:
        raise SystemExit(
            f"[{SCRIPT_PREFIX}] unexpected credits: {subscription.credits_remaining}/{subscription.credits_initial}"
        )
    if (subscription.payment_provider_subscription_ref or "").strip() != PAYMENT_REFERENCE:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected payment reference")
    if subscription.user_id not in {mother.id, child.id}:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected subscription owner: {subscription.user_id}")

    dependent_counts = {
        "bookings": db.scalar(
            select(func.count()).select_from(Booking).where(Booking.client_plan_subscription_id == subscription.id)
        )
        or 0,
        "billing_cycles": db.scalar(
            select(func.count()).select_from(SubscriptionBillingCycle).where(
                SubscriptionBillingCycle.subscription_id == subscription.id
            )
        )
        or 0,
        "payment_attempts": db.scalar(
            select(func.count()).select_from(SubscriptionPaymentAttempt).where(
                SubscriptionPaymentAttempt.subscription_id == subscription.id
            )
        )
        or 0,
    }
    if any(dependent_counts.values()):
        raise SystemExit(f"[{SCRIPT_PREFIX}] dependent rows prevent transfer: {dependent_counts}")
    print(f"[{SCRIPT_PREFIX}] mother={_user_label(mother)}")
    print(f"[{SCRIPT_PREFIX}] child={_user_label(child)}")
    print(
        f"[{SCRIPT_PREFIX}] subscription={subscription.id}|owner={subscription.user_id}|"
        f"payer={subscription.payer_contact_id}|credits={subscription.credits_remaining}/{subscription.credits_initial}"
    )
    print(f"[{SCRIPT_PREFIX}] dependencies={dependent_counts}")
    print(
        f"[{SCRIPT_PREFIX}] collective_trial={collective_trial.id}|"
        f"enabled={collective_trial.trial_course_enabled}|price={collective_trial.trial_course_price_ttc}|"
        f"credit_type={collective_trial.credit_type_id}"
    )
    return mother, child, subscription, plan, collective_trial


def run(*, apply: bool) -> None:
    with SessionLocal() as db:
        mother, child, subscription, plan, collective_trial = _assert_target_rows(db)
        changes: list[str] = []
        if subscription.user_id != child.id:
            changes.append(f"subscription.owner:{subscription.user_id}->{child.id}")
            if apply:
                subscription.user_id = child.id
        if subscription.payer_contact_id != mother.id:
            changes.append(f"subscription.payer:{subscription.payer_contact_id}->{mother.id}")
            if apply:
                subscription.payer_contact_id = mother.id
        if child.client_status.value != "ACTIVE" or not child.is_active:
            changes.append(f"child.status:{child.client_status.value}/active={child.is_active}->ACTIVE/active=True")
            if apply:
                promote_client_to_active_student(child)

        if not collective_trial.trial_course_enabled:
            changes.append("collective_trial.enabled:False->True")
            if apply:
                collective_trial.trial_course_enabled = True
        if collective_trial.trial_course_price_ttc != 20:
            changes.append(f"collective_trial.price:{collective_trial.trial_course_price_ttc}->20.00")
            if apply:
                collective_trial.trial_course_price_ttc = 20
        if collective_trial.credit_type_id != ONSITE_CREDIT_TYPE_ID:
            changes.append(f"collective_trial.credit_type:{collective_trial.credit_type_id}->{ONSITE_CREDIT_TYPE_ID}")
            if apply:
                collective_trial.credit_type_id = ONSITE_CREDIT_TYPE_ID

        entitlement_id = db.scalar(
            select(PlanEntitlement.id).where(
                PlanEntitlement.plan_id == plan.id,
                PlanEntitlement.course_type_id == collective_trial.id,
            )
        )
        if entitlement_id is None:
            changes.append("collective_trial.plan_entitlement:create")
            if apply:
                db.add(PlanEntitlement(plan_id=plan.id, course_type_id=collective_trial.id))

        existing_note = db.scalar(
            select(ClientNoteEntry.id).where(
                ClientNoteEntry.user_id == child.id,
                ClientNoteEntry.message == AUDIT_MESSAGE,
            )
        )
        if existing_note is None:
            changes.append("child.audit_note:create")
            if apply:
                db.add(
                    ClientNoteEntry(
                        user_id=child.id,
                        author_user_id=None,
                        entry_type="AUTO",
                        message=AUDIT_MESSAGE,
                        created_at=_utcnow(),
                    )
                )

        if apply:
            subscription.updated_at = _utcnow()
            db.add(subscription)
            db.add(child)
            db.add(collective_trial)
            db.flush()
            refresh_responsable_status(db, mother)
            db.add(mother)
            db.commit()
        else:
            db.rollback()

        print(f"[{SCRIPT_PREFIX}] mode={'APPLY' if apply else 'DRY_RUN'}")
        print(f"[{SCRIPT_PREFIX}] changes={changes or ['none']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(apply=args.apply)
