from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.catalog import Professor
from app.models.professor_access import ProfessorPermission
from app.models.user import User, UserRole
from app.services.professor_permissions import permissions_dict

bearer_scheme = HTTPBearer(auto_error=False)

READ_ONLY_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}

BACKOFFICE_PERMISSION_KEYS = {
    "can_view_planning",
    "can_edit_planning",
    "can_view_planning_simulation",
    "can_manage_check_deposits",
    "can_view_clients",
    "can_access_collaborators",
    "can_view_intakes",
    "can_view_quotes",
    "can_view_upcoming_trials",
    "can_manage_events",
    "can_manage_mobile_news",
    "can_manage_website_and_news",
}


def normalize_admin_permission_map(permission_map: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(permission_map)
    if normalized.get("can_edit_planning"):
        normalized["can_view_planning"] = True
        normalized["can_view_all_school_sessions"] = True
    return normalized


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_read_only_client_preview(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("imp")
        and payload.get("preview_read_only")
        and payload.get("target_role") == "client"
        and payload.get("act")
    )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    if payload.get("imp") and request.url.path.startswith("/api/v1/admin") and payload.get("target_role") != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Impersonation token cannot access admin endpoints",
        )

    read_only_client_preview = is_read_only_client_preview(payload)
    if read_only_client_preview and request.method.upper() not in READ_ONLY_HTTP_METHODS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client preview is read-only",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_uuid = UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        ) from exc

    user = db.scalar(select(User).where(User.id == user_uuid))
    if user is None or (not user.is_active and not read_only_client_preview):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    setattr(user, "_auth_claims", payload)
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    def _require_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _require_role


def get_admin_permission_map(db: Session, user: User) -> dict[str, Any]:
    if user.role == UserRole.ADMIN:
        return {}
    if user.role != UserRole.PROF:
        return {}
    email = (user.email or "").strip().lower()
    if not email:
        return {}
    professor = db.scalar(select(Professor).where(func.lower(Professor.email) == email).limit(1))
    if professor is None:
        return {}
    row = db.scalar(select(ProfessorPermission).where(ProfessorPermission.professor_id == professor.id).limit(1))
    return normalize_admin_permission_map(permissions_dict(row, legacy_if_missing=False))


def require_admin_or_permissions(*permission_fields: str) -> Callable[..., User]:
    def _require_permission(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role == UserRole.ADMIN:
            return current_user
        permission_map = get_admin_permission_map(db, current_user)
        has_backoffice_profile = any(bool(permission_map.get(field)) for field in BACKOFFICE_PERMISSION_KEYS)
        if has_backoffice_profile and any(bool(permission_map.get(field)) for field in permission_fields):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return _require_permission
