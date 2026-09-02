from __future__ import annotations

import logging
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import BACKOFFICE_PERMISSION_KEYS, get_admin_permission_map, get_current_user, get_db, require_roles
from app.models.catalog import Professor
from app.models.user import User, UserRole
from app.schemas.admin import AdminImpersonationEndOut, AdminImpersonationStartOut
from app.services.security import create_access_token

router = APIRouter()
logger = logging.getLogger(__name__)

IMPERSONATION_TOKEN_TTL_MINUTES = 15


def _display_name(first_name: str | None, last_name: str | None, fallback: str) -> str:
    full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return full_name or fallback


def _teacher_impersonation_destination(
    view_mode: Literal["teacher", "manager"],
    *,
    has_teacher_access: bool,
    has_manager_access: bool,
) -> tuple[str, str]:
    if view_mode == "teacher" and not has_teacher_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Collaborator has no teacher access",
        )
    if view_mode == "manager" and not has_manager_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher has no manager access",
        )
    if view_mode == "manager":
        return "manager", "/admin"
    return "teacher", "/prof"


@router.post("/admin/impersonate/client/{client_id}", response_model=AdminImpersonationStartOut)
def start_admin_client_impersonation(
    client_id: UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminImpersonationStartOut:
    target = db.scalar(select(User).where(User.id == client_id))
    if target is None or target.role != UserRole.CLIENT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    access_token = create_access_token(
        subject=str(target.id),
        role=target.role.value,
        expires_delta=timedelta(minutes=IMPERSONATION_TOKEN_TTL_MINUTES),
        extra_claims={
            "imp": True,
            "act": str(actor.id),
            "target_role": "client",
            "preview_read_only": True,
        },
    )
    logger.info("impersonation_started actor=%s target=%s role=client", actor.id, target.id)
    return AdminImpersonationStartOut(
        target_user_id=target.id,
        target_role="client",
        target_display_name=_display_name(target.first_name, target.last_name, target.email),
        access_token=access_token,
        expires_in_seconds=IMPERSONATION_TOKEN_TTL_MINUTES * 60,
        redirect_path="/client?tab=home",
    )


@router.post("/admin/impersonate/teacher/{teacher_id}", response_model=AdminImpersonationStartOut)
def start_admin_teacher_impersonation(
    teacher_id: UUID,
    view_mode: Literal["teacher", "manager"] = "teacher",
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminImpersonationStartOut:
    professor = db.scalar(select(Professor).where(Professor.id == teacher_id))
    if professor is None or not bool(professor.active):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    target = db.scalar(select(User).where(User.email == professor.email))
    if target is None or target.role != UserRole.PROF or not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Teacher user account not found or inactive",
        )

    permission_map = get_admin_permission_map(db, target)
    has_manager_access = any(bool(permission_map.get(field)) for field in BACKOFFICE_PERMISSION_KEYS)
    target_role, redirect_path = _teacher_impersonation_destination(
        view_mode,
        has_teacher_access=bool(professor.is_coach),
        has_manager_access=has_manager_access,
    )

    access_token = create_access_token(
        subject=str(target.id),
        role=target.role.value,
        expires_delta=timedelta(minutes=IMPERSONATION_TOKEN_TTL_MINUTES),
        extra_claims={
            "imp": True,
            "act": str(actor.id),
            "target_role": target_role,
        },
    )
    logger.info("impersonation_started actor=%s target=%s role=%s", actor.id, target.id, target_role)
    return AdminImpersonationStartOut(
        target_user_id=target.id,
        target_role=target_role,
        target_display_name=_display_name(target.first_name, target.last_name, target.email),
        access_token=access_token,
        expires_in_seconds=IMPERSONATION_TOKEN_TTL_MINUTES * 60,
        redirect_path=redirect_path,
    )


@router.post("/impersonation/end", response_model=AdminImpersonationEndOut)
def end_impersonation(
    current_user: User = Depends(get_current_user),
) -> AdminImpersonationEndOut:
    claims = getattr(current_user, "_auth_claims", None)
    if not isinstance(claims, dict) or not claims.get("imp"):
        return AdminImpersonationEndOut(message="No active impersonation")

    actor_id = claims.get("act")
    logger.info("impersonation_ended actor=%s target=%s", actor_id, current_user.id)
    return AdminImpersonationEndOut(message="Impersonation ended")
