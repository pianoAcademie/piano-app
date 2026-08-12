from __future__ import annotations

from collections import defaultdict
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, CreditType
from app.models.plan import ClientPlanSubscription, Plan, PlanCreditGrant, PlanCreditGrantsRelation, PlanKind


def subscription_credit_allocations(
    db: Session,
    *,
    subscriptions: Iterable[tuple[ClientPlanSubscription, Plan]],
) -> dict[UUID, list[dict[str, object]]]:
    """Return the per-credit-type balance represented by a multi-credit pack."""
    rows = list(subscriptions)
    pack_rows = [
        (subscription, plan)
        for subscription, plan in rows
        if plan.kind == PlanKind.PACK and plan.credit_grants_relation == PlanCreditGrantsRelation.AND
    ]
    if not pack_rows:
        return {}

    plan_ids = {plan.id for _, plan in pack_rows}
    subscription_ids = {subscription.id for subscription, _ in pack_rows}
    grants = db.execute(
        select(
            PlanCreditGrant.plan_id,
            PlanCreditGrant.credit_type_id,
            CreditType.code,
            CreditType.name,
            PlanCreditGrant.credits_count,
        )
        .join(CreditType, CreditType.id == PlanCreditGrant.credit_type_id)
        .where(PlanCreditGrant.plan_id.in_(plan_ids))
        .order_by(PlanCreditGrant.plan_id.asc(), CreditType.name.asc())
    ).all()

    used_by_subscription_and_type: dict[tuple[UUID, UUID], int] = defaultdict(int)
    usage_rows = db.execute(
        select(
            Booking.client_plan_subscription_id,
            CourseType.credit_type_id,
            func.count(Booking.id),
        )
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            Booking.client_plan_subscription_id.in_(subscription_ids),
            Booking.status.in_([BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW]),
            CourseType.credit_type_id.is_not(None),
        )
        .group_by(Booking.client_plan_subscription_id, CourseType.credit_type_id)
    ).all()
    for subscription_id, credit_type_id, used_count in usage_rows:
        if subscription_id is not None and credit_type_id is not None:
            used_by_subscription_and_type[(subscription_id, credit_type_id)] = int(used_count or 0)

    grants_by_plan: dict[UUID, list[tuple[UUID, str, str, int]]] = defaultdict(list)
    for plan_id, credit_type_id, code, name, credits_count in grants:
        grants_by_plan[plan_id].append((credit_type_id, code, name, int(credits_count or 0)))

    result: dict[UUID, list[dict[str, object]]] = {}
    for subscription, plan in pack_rows:
        allocations: list[dict[str, object]] = []
        for credit_type_id, code, name, initial in grants_by_plan.get(plan.id, []):
            used = used_by_subscription_and_type.get((subscription.id, credit_type_id), 0)
            allocations.append(
                {
                    "credit_type_id": credit_type_id,
                    "credit_type_code": code,
                    "credit_type_name": name,
                    "credits_initial": initial,
                    "credits_remaining": max(0, initial - used),
                }
            )
        result[subscription.id] = allocations
    return result
