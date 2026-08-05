from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import CreditType
from app.models.plan import Plan, PlanKind
from app.models.user import User, UserRole
from app.schemas.sportigo import SportigoCatalogItem, SportigoImportCatalogOut, SportigoImportOut
from app.services.sportigo_import import parse_sportigo_manifest, run_sportigo_import


router = APIRouter(prefix="/admin/sportigo-import")


@router.get("/catalog", response_model=SportigoImportCatalogOut)
def get_sportigo_import_catalog(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SportigoImportCatalogOut:
    plans = db.scalars(
        select(Plan)
        .where(Plan.active.is_(True), Plan.kind == PlanKind.SUBSCRIPTION)
        .order_by(Plan.name.asc())
    ).all()
    credit_types = db.scalars(
        select(CreditType).where(CreditType.active.is_(True)).order_by(CreditType.name.asc())
    ).all()
    return SportigoImportCatalogOut(
        subscription_plans=[SportigoCatalogItem(code=plan.code, name=plan.name, kind=plan.kind.value) for plan in plans],
        credit_types=[SportigoCatalogItem(code=item.code, name=item.name) for item in credit_types],
    )


@router.post("", response_model=SportigoImportOut)
async def import_sportigo_manifest(
    file: UploadFile = File(...),
    dry_run: bool = Form(True),
    activate: bool = Form(False),
    batch_reference: str = Form(..., min_length=3, max_length=120),
    template_plan_code: str = Form(..., min_length=1, max_length=80),
    studio_credit_type_code: str = Form(..., min_length=1, max_length=80),
    collective_credit_type_code: str = Form(..., min_length=1, max_length=80),
    online_credit_type_code: str = Form(..., min_length=1, max_length=80),
    solfege_credit_type_code: str = Form(..., min_length=1, max_length=80),
    confirm_apply: str = Form("", max_length=120),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SportigoImportOut:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Fichier CSV requis")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Fichier CSV vide")
    if not dry_run and confirm_apply.strip() != batch_reference.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pour appliquer l'import, recopiez exactement la référence du lot.",
        )
    rows, parse_errors = parse_sportigo_manifest(content)
    if parse_errors:
        return SportigoImportOut(
            dry_run=dry_run,
            activate=activate,
            batch_reference=batch_reference,
            rows_seen=len(rows),
            rows_valid=len(rows),
            errors=parse_errors,
        )
    result = run_sportigo_import(
        db,
        rows,
        dry_run=dry_run,
        activate=activate,
        batch_reference=batch_reference.strip(),
        template_plan_code=template_plan_code.strip(),
        credit_type_codes={
            "studio": studio_credit_type_code.strip(),
            "collective": collective_credit_type_code.strip(),
            "online": online_credit_type_code.strip(),
            "solfege": solfege_credit_type_code.strip(),
        },
    )
    if result.errors and not dry_run:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(result.errors[:10]))
    return result
