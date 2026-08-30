from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.api.deps import get_db, require_roles
from app.models.user import User, UserRole
from app.models.quote import QuoteEvent
from app.models.annual_pricing import AnnualFamilyReference
from app.services.annual_pricing_review import (
    AnnualReviewRequest, KEY, quote_students, family_members, reviewed_lines, prepare_review, apply_review,
)

router = APIRouter()


@router.get("/quotes/{quote_id}/annual-pricing")
def context(quote_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    from app.api.routes.quotes import _load_quote, _load_quote_lines
    quote = _load_quote(db, quote_id)
    students = quote_students(db, quote)
    families = {}
    references = {}
    primary_courses = {}
    for student in students:
        children, guardians = family_members(db, student.id)
        families[str(student.id)] = [{"id": str(u.id), "label": f"{u.first_name or ''} {u.last_name or ''}".strip()}
                                    for child_id in sorted(children, key=str) if (u := db.get(User, child_id))]
        refs = [db.get(AnnualFamilyReference, (guardian, quote.school_year_label)) for guardian in guardians]
        references[str(student.id)] = next((str(r.child_id) for r in refs if r), None)
        subscriptions = db.scalars(select(ClientPlanSubscription).join(Plan).where(
            ClientPlanSubscription.user_id == student.id, Plan.kind == PlanKind.FORFAIT,
            ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPlanSubscription.started_at < datetime(2027, 8, 1, tzinfo=timezone.utc),
            ClientPlanSubscription.ends_at >= datetime(2026, 9, 1, tzinfo=timezone.utc),
        )).all()
        primary_courses[str(student.id)] = [{"id": t["course_key"], "label": t["title"]}
            for sub in subscriptions for t in (sub.annual_pricing_terms or []) if t.get("primary")]
    return {"students": [{"id": str(s.id), "label": f"{s.first_name or ''} {s.last_name or ''}".strip()} for s in students],
        "families": families, "references": references, "primary_courses": primary_courses, "review": (quote.meta or {}).get(KEY),
        "lines": [{"id": str(l.id), "title": l.title, "quantity": str(l.quantity)} for l, _, _ in reviewed_lines(db, quote, _load_quote_lines(db, quote_id))]}


@router.post("/quotes/{quote_id}/annual-pricing/preview")
def preview(quote_id: UUID, payload: AnnualReviewRequest, db: Session = Depends(get_db),
            _: User = Depends(require_roles(UserRole.ADMIN))):
    from app.api.routes.quotes import _load_quote, _load_quote_lines
    return prepare_review(db, _load_quote(db, quote_id, lock=True), _load_quote_lines(db, quote_id), payload)


@router.post("/quotes/{quote_id}/annual-pricing/apply")
def apply(quote_id: UUID, payload: AnnualReviewRequest, db: Session = Depends(get_db),
          actor: User = Depends(require_roles(UserRole.ADMIN))):
    from app.api.routes.quotes import _load_quote, _load_quote_lines, _build_payment_terms_snapshot_for_quote
    quote = _load_quote(db, quote_id, lock=True)
    review = apply_review(db, quote, _load_quote_lines(db, quote_id), payload, actor)
    quote.payment_terms_snapshot = _build_payment_terms_snapshot_for_quote(db, quote, total_ttc=quote.total_ttc)
    quote.price_snapshot = {**(quote.price_snapshot or {}), "total_ttc": str(quote.total_ttc), "annual_decisions": review["decisions"]}
    quote.document_status = "stale"
    quote.document_hash = None
    quote.document_generated_at = None
    quote.document_snapshot_id = None
    quote.updated_at = datetime.now(timezone.utc)
    db.add(QuoteEvent(quote_id=quote.id, event_type="annual_pricing_reviewed", actor_type="admin", actor_id=actor.id, payload=review))
    db.commit()
    return {"ok": True, "total": str(quote.total_ttc)}
