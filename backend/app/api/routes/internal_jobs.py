from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.user import User, UserRole
from app.schemas.jobs import (
    AutoCancelJobResponse,
    PayoutJobResponse,
    ProfessorDailyDigestJobResponse,
    ReminderJobResponse,
    SubscriptionBillingJobResponse,
)
from app.services.professor_daily_digest import run_send_professor_daily_digest_job
from app.services.payouts import run_calc_professor_payouts_job
from app.services.reminders import run_send_reminders_job
from app.services.subscription_billing import run_subscription_billing_job
from app.services.session_automation import run_auto_cancel_empty_sessions_job

router = APIRouter(prefix="/internal/jobs")


@router.post("/send-reminders", response_model=ReminderJobResponse)
def send_reminders(
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ReminderJobResponse:
    now = datetime.now(timezone.utc)
    result = run_send_reminders_job(db, now=now, limit=limit)
    db.commit()
    return ReminderJobResponse(
        created=result.created,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
    )


@router.post("/auto-cancel-empty-sessions", response_model=AutoCancelJobResponse)
def auto_cancel_empty_sessions(
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AutoCancelJobResponse:
    now = datetime.now(timezone.utc)
    result = run_auto_cancel_empty_sessions_job(db, now=now, limit=limit)
    db.commit()
    return AutoCancelJobResponse(
        checked=result.checked,
        cancelled_sessions=result.cancelled_sessions,
        cancelled_bookings=result.cancelled_bookings,
    )


@router.post("/calc-professor-payouts", response_model=PayoutJobResponse)
def calc_professor_payouts(
    limit: int = Query(default=200, ge=1, le=2000),
    force_recompute: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PayoutJobResponse:
    now = datetime.now(timezone.utc)
    result = run_calc_professor_payouts_job(
        db,
        now=now,
        limit=limit,
        force_recompute=force_recompute,
    )
    db.commit()
    return PayoutJobResponse(
        checked=result.checked,
        created=result.created,
        updated=result.updated,
        skipped_no_rate=result.skipped_no_rate,
        skipped_existing_locked=result.skipped_existing_locked,
    )


@router.post("/send-professor-daily-digests", response_model=ProfessorDailyDigestJobResponse)
def send_professor_daily_digests(
    limit: int = Query(default=300, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProfessorDailyDigestJobResponse:
    now = datetime.now(timezone.utc)
    result = run_send_professor_daily_digest_job(db, now=now, limit=limit)
    db.commit()
    return ProfessorDailyDigestJobResponse(
        checked=result.checked,
        sent=result.sent,
        skipped_not_due=result.skipped_not_due,
        skipped_no_courses=result.skipped_no_courses,
        failed=result.failed,
    )


@router.post("/run-subscription-billing", response_model=SubscriptionBillingJobResponse)
def run_subscription_billing(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SubscriptionBillingJobResponse:
    now = datetime.now(timezone.utc)
    result = run_subscription_billing_job(db, now=now, limit=limit)
    db.commit()
    return SubscriptionBillingJobResponse(
        checked=result.checked,
        charged=result.charged,
        skipped=result.skipped,
        failed=result.failed,
    )
