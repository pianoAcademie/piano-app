from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminTeacherInvoiceTemplateOut,
    AdminTeacherInvoiceTemplatePreviewRequest,
    AdminTeacherInvoiceTemplateUpdateRequest,
)
from app.services.teacher_invoice_documents import (
    TEACHER_INVOICE_TEMPLATE_KEY,
    TEACHER_INVOICE_TEMPLATE_VARIABLES,
    default_teacher_invoice_context,
    get_teacher_invoice_template,
    render_teacher_invoice_html,
    render_teacher_invoice_pdf_from_html,
    save_teacher_invoice_template,
)

router = APIRouter(prefix="/admin")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/teacher-invoice-template", response_model=AdminTeacherInvoiceTemplateOut)
def get_admin_teacher_invoice_template(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminTeacherInvoiceTemplateOut:
    html_template, version, updated_at = get_teacher_invoice_template(db)
    return AdminTeacherInvoiceTemplateOut(
        key=TEACHER_INVOICE_TEMPLATE_KEY,
        html_template=html_template,
        version=version,
        updated_at=updated_at,
        variables=list(TEACHER_INVOICE_TEMPLATE_VARIABLES),
    )


@router.put("/teacher-invoice-template", response_model=AdminTeacherInvoiceTemplateOut)
def update_admin_teacher_invoice_template(
    payload: AdminTeacherInvoiceTemplateUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminTeacherInvoiceTemplateOut:
    html_template, version, updated_at = save_teacher_invoice_template(db, html_template=payload.html_template)
    db.commit()
    return AdminTeacherInvoiceTemplateOut(
        key=TEACHER_INVOICE_TEMPLATE_KEY,
        html_template=html_template,
        version=version,
        updated_at=updated_at or _utcnow(),
        variables=list(TEACHER_INVOICE_TEMPLATE_VARIABLES),
    )


@router.post("/teacher-invoice-template/preview")
def preview_admin_teacher_invoice_template(
    payload: AdminTeacherInvoiceTemplatePreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    stored_template, _, _ = get_teacher_invoice_template(db)
    html_template = (payload.html_template or "").strip() or stored_template
    rendered_html = render_teacher_invoice_html(
        html_template=html_template,
        context=default_teacher_invoice_context(),
    )
    pdf_content = render_teacher_invoice_pdf_from_html(rendered_html)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="teacher-invoice-preview.pdf"',
            "Cache-Control": "no-store",
        },
    )
