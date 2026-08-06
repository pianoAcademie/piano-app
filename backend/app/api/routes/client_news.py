from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.client_news import ClientNewsArticle
from app.models.user import User, UserRole
from app.schemas.client_news import (
    AdminClientNewsCreate,
    AdminClientNewsOut,
    AdminClientNewsUpdate,
    ClientNewsOut,
)


router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _admin_out(row: ClientNewsArticle) -> AdminClientNewsOut:
    return AdminClientNewsOut.model_validate(row, from_attributes=True)


def _client_out(row: ClientNewsArticle, language: str) -> ClientNewsOut:
    english = language.strip().lower().startswith("en")
    return ClientNewsOut(
        id=row.id,
        title=(row.title_en if english and row.title_en else row.title_fr),
        summary=(row.summary_en if english and row.summary_en else row.summary_fr),
        body=(row.body_en if english and row.body_en else row.body_fr),
        link_url=row.link_url,
        link_label=(row.link_label_en if english and row.link_label_en else row.link_label_fr),
        is_pinned=row.is_pinned,
        published_at=row.published_at or row.created_at,
    )


def _normalized_values(payload: AdminClientNewsCreate | AdminClientNewsUpdate) -> dict[str, object]:
    values = payload.model_dump()
    if values["status"] == "PUBLISHED" and values["published_at"] is None:
        values["published_at"] = _utcnow()
    published_at = values.get("published_at")
    expires_at = values.get("expires_at")
    if isinstance(published_at, datetime) and isinstance(expires_at, datetime) and expires_at <= published_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La date d'expiration doit être postérieure à la publication",
        )
    return values


@router.get("/admin/client-news", response_model=list[AdminClientNewsOut])
def list_admin_client_news(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> list[AdminClientNewsOut]:
    rows = db.scalars(
        select(ClientNewsArticle).order_by(
            ClientNewsArticle.is_pinned.desc(),
            ClientNewsArticle.published_at.desc().nulls_last(),
            ClientNewsArticle.created_at.desc(),
        )
    ).all()
    return [_admin_out(row) for row in rows]


@router.post("/admin/client-news", response_model=AdminClientNewsOut, status_code=status.HTTP_201_CREATED)
def create_admin_client_news(
    payload: AdminClientNewsCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> AdminClientNewsOut:
    values = _normalized_values(payload)
    row = ClientNewsArticle(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _admin_out(row)


@router.put("/admin/client-news/{article_id}", response_model=AdminClientNewsOut)
def update_admin_client_news(
    article_id: UUID,
    payload: AdminClientNewsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> AdminClientNewsOut:
    row = db.get(ClientNewsArticle, article_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable")
    values = _normalized_values(payload)
    if values["status"] == "DRAFT":
        values["published_at"] = None
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _admin_out(row)


@router.delete("/admin/client-news/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_client_news(
    article_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> Response:
    row = db.get(ClientNewsArticle, article_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/clients/me/news", response_model=list[ClientNewsOut])
def list_client_news(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientNewsOut]:
    now = _utcnow()
    rows = db.scalars(
        select(ClientNewsArticle)
        .where(
            ClientNewsArticle.status == "PUBLISHED",
            ClientNewsArticle.published_at.is_not(None),
            ClientNewsArticle.published_at <= now,
            or_(ClientNewsArticle.expires_at.is_(None), ClientNewsArticle.expires_at > now),
        )
        .order_by(ClientNewsArticle.is_pinned.desc(), ClientNewsArticle.published_at.desc())
        .limit(50)
    ).all()
    return [_client_out(row, current_user.preferred_language or "fr") for row in rows]
