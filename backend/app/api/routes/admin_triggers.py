from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import CourseType, Location
from app.models.plan import Plan
from app.models.user import User, UserRole
from app.schemas.automation import (
    AdminAutomationRuleCreate,
    AdminAutomationRuleOut,
    AdminAutomationRuleUpdate,
)
from app.services.automation_triggers import (
    create_automation_rule,
    delete_automation_rule,
    list_automation_rules,
    update_automation_rule,
)
from app.services.messaging_templates import resolve_messaging_template_ref


router = APIRouter()


def _validate_references(db: Session, payload: AdminAutomationRuleCreate | AdminAutomationRuleUpdate) -> None:
    if payload.plan_id is not None and db.scalar(select(Plan.id).where(Plan.id == payload.plan_id)) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Formula not found")
    if payload.course_type_id is not None and db.scalar(select(CourseType.id).where(CourseType.id == payload.course_type_id)) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Course type not found")
    if payload.location_id is not None and db.scalar(select(Location.id).where(Location.id == payload.location_id)) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Location not found")
    try:
        resolve_messaging_template_ref(
            db,
            template_ref=payload.template_ref,
            default_ref=payload.template_ref,
            channel="EMAIL",
            active_only=True,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/admin/triggers", response_model=list[AdminAutomationRuleOut])
def list_admin_triggers(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[dict[str, object]]:
    return list_automation_rules(db)


@router.post("/admin/triggers", response_model=AdminAutomationRuleOut, status_code=status.HTTP_201_CREATED)
def create_admin_trigger(
    payload: AdminAutomationRuleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    _validate_references(db, payload)
    row = create_automation_rule(db, payload)
    db.commit()
    return row


@router.put("/admin/triggers/{rule_id}", response_model=AdminAutomationRuleOut)
def update_admin_trigger(
    rule_id: UUID,
    payload: AdminAutomationRuleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    _validate_references(db, payload)
    row = update_automation_rule(db, rule_id, payload)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    db.commit()
    return row


@router.delete("/admin/triggers/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_trigger(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    if not delete_automation_rule(db, rule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
