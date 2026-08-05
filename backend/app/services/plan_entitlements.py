from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import CourseType
from app.models.plan import Plan, PlanCreditGrant, PlanEntitlement, PlanKind


def effective_entitlements_by_plan(
    db: Session,
    *,
    plan_ids: list[UUID],
) -> tuple[dict[UUID, list[UUID]], dict[UUID, list[str]]]:
    """Return explicit entitlements plus PACK access implied by credit grants."""
    if not plan_ids:
        return {}, {}

    explicit_rows = db.execute(
        select(PlanEntitlement.plan_id, PlanEntitlement.course_type_id, CourseType.name)
        .join(CourseType, CourseType.id == PlanEntitlement.course_type_id)
        .where(PlanEntitlement.plan_id.in_(plan_ids))
    ).all()
    credit_grant_rows = db.execute(
        select(PlanCreditGrant.plan_id, CourseType.id, CourseType.name)
        .join(Plan, Plan.id == PlanCreditGrant.plan_id)
        .join(CourseType, CourseType.credit_type_id == PlanCreditGrant.credit_type_id)
        .where(
            PlanCreditGrant.plan_id.in_(plan_ids),
            Plan.kind == PlanKind.PACK,
            CourseType.active.is_(True),
        )
    ).all()

    rows_by_plan: dict[UUID, dict[UUID, str]] = defaultdict(dict)
    for plan_id, course_type_id, course_type_name in [*explicit_rows, *credit_grant_rows]:
        rows_by_plan[plan_id][course_type_id] = course_type_name

    ids_map: dict[UUID, list[UUID]] = {}
    names_map: dict[UUID, list[str]] = {}
    for plan_id, course_types in rows_by_plan.items():
        ordered = sorted(course_types.items(), key=lambda item: (item[1].casefold(), str(item[0])))
        ids_map[plan_id] = [course_type_id for course_type_id, _ in ordered]
        names_map[plan_id] = [course_type_name for _, course_type_name in ordered]

    return ids_map, names_map
