from datetime import datetime, timezone
from sqlalchemy import select
from app.models.annual_pricing import AnnualStudentEnrollment
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus


def enrollment_context(db, student_id, season):
    saved = db.get(AnnualStudentEnrollment, (student_id, season))
    year = int(season[:4])
    subscription = db.scalar(select(ClientPlanSubscription.id).join(Plan).where(
        ClientPlanSubscription.user_id == student_id, Plan.kind == PlanKind.FORFAIT,
        ClientPlanSubscription.started_at < datetime(year, 8, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.ends_at >= datetime(year - 1, 9, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
    ).limit(1))
    return {"status": saved.status if saved else "AUTO", "evidence": saved.evidence if saved else None,
            "history_found": bool(subscription), "subscription_id": str(subscription) if subscription else None}


def resolve_enrollment(context, status, note):
    if status == "AUTO" and context["status"] != "AUTO":
        status = context["status"]
        note = (context["evidence"] or {}).get("note", "")
    if status == "RETURNING_MANUAL" and len(note.strip()) < 10:
        raise ValueError("Justifiez la réinscription confirmée par l'administration (10 caractères minimum).")
    returning = status == "RETURNING_MANUAL" or (status == "AUTO" and context["history_found"])
    source = "ADMIN" if status == "RETURNING_MANUAL" else "HISTORY" if returning else "NEW" if status == "NEW" else "UNVERIFIED"
    return {"status": status, "returning": returning, "source": source, "note": note.strip(),
            "subscription_id": context["subscription_id"] if source == "HISTORY" else None}
