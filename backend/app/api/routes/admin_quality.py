from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.user import User, UserRole
from app.services.quote_planning_audit import audit_quote_planning, repair_safe_quote_planning_mismatches


router = APIRouter(prefix="/admin/quality-control")


@router.get("/quote-planning")
def get_quote_planning_audit(
    school_year: str = Query(default="2026-2027", min_length=4, max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_quotes")),
) -> dict[str, object]:
    return audit_quote_planning(db, school_year=school_year)


@router.post("/quote-planning/repair-safe")
def repair_quote_planning_audit(
    school_year: str = Query(default="2026-2027", min_length=4, max_length=40),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    return repair_safe_quote_planning_mismatches(db, actor=actor, school_year=school_year)
