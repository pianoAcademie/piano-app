from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.user import User, UserRole
from app.schemas.jobs import (
    AutoInvoiceBillingJobResponse,
    AutoCancelJobResponse,
    InvoiceReminderJobResponse,
    NotificationEngineJobResponse,
    PayoutJobResponse,
    ProfessorDailyDigestJobResponse,
    ReminderJobResponse,
    SubscriptionBillingJobResponse,
    SubscriptionCycleGenerationJobResponse,
    SubscriptionRecoveryReconciliationJobResponse,
    SubscriptionRetryJobResponse,
)
from app.services.auto_invoice_billing import run_auto_invoice_billing_job
from app.services.invoice_reminders import run_invoice_due_reminder_job
from app.services.jobs.application.notification_jobs import (
    run_delivery_feedback_job,
    run_immediate_notification_dispatch_job,
    run_reminder_generation_job,
    run_scheduled_notification_dispatch_job,
)
from app.services.professor_daily_digest import run_send_professor_daily_digest_job
from app.services.payouts import run_calc_professor_payouts_job
from app.services.subscription_billing import (
    run_subscription_billing_job,
    run_subscription_cycle_generation_job,
    run_subscription_recovery_reconciliation_job,
    run_subscription_retry_job,
)
from app.services.session_automation import run_auto_cancel_empty_sessions_job

router = APIRouter(prefix="/internal/jobs")


@router.post("/send-reminders", response_model=ReminderJobResponse)
def send_reminders(
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ReminderJobResponse:
    now = datetime.now(timezone.utc)
    generation = run_reminder_generation_job(db, now=now, limit=limit)
    dispatch = run_scheduled_notification_dispatch_job(db, now=now, limit=limit)
    db.commit()
    return ReminderJobResponse(
        created=generation.sent,
        sent=dispatch.sent,
        skipped=generation.skipped + dispatch.skipped,
        failed=generation.failed + dispatch.failed,
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
        processed=result.processed,
        first_failures=result.first_failures,
        final_failures=result.final_failures,
        job_run_id=str(result.job_run_id),
    )


@router.post("/run-subscription-cycle-generation", response_model=SubscriptionCycleGenerationJobResponse)
def run_subscription_cycle_generation(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SubscriptionCycleGenerationJobResponse:
    now = datetime.now(timezone.utc)
    result = run_subscription_cycle_generation_job(db, now=now, limit=limit)
    db.commit()
    return SubscriptionCycleGenerationJobResponse(
        checked=result.checked,
        created=result.created,
        skipped=result.skipped,
        failed=result.failed,
        job_run_id=str(result.job_run_id),
    )


@router.post("/run-subscription-retry", response_model=SubscriptionRetryJobResponse)
def run_subscription_retry(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SubscriptionRetryJobResponse:
    now = datetime.now(timezone.utc)
    result = run_subscription_retry_job(db, now=now, limit=limit)
    db.commit()
    return SubscriptionRetryJobResponse(
        checked=result.checked,
        recovered=result.recovered,
        skipped=result.skipped,
        failed=result.failed,
        final_failures=result.final_failures,
        processed=result.processed,
        job_run_id=str(result.job_run_id),
    )


@router.post("/run-subscription-recovery-reconciliation", response_model=SubscriptionRecoveryReconciliationJobResponse)
def run_subscription_recovery_reconciliation(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SubscriptionRecoveryReconciliationJobResponse:
    now = datetime.now(timezone.utc)
    result = run_subscription_recovery_reconciliation_job(db, now=now, limit=limit)
    db.commit()
    return SubscriptionRecoveryReconciliationJobResponse(
        checked=result.checked,
        reconciled=result.reconciled,
        skipped=result.skipped,
        failed=result.failed,
        job_run_id=str(result.job_run_id),
    )


@router.post("/run-auto-invoice-billing", response_model=AutoInvoiceBillingJobResponse)
def run_auto_invoice_billing(
    limit: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AutoInvoiceBillingJobResponse:
    now = datetime.now(timezone.utc)
    result = run_auto_invoice_billing_job(db, now=now, limit=limit)
    db.commit()
    return AutoInvoiceBillingJobResponse(
        checked=result.checked,
        generated=result.generated,
        skipped_empty=result.skipped_empty,
        skipped_duplicate=result.skipped_duplicate,
        failed=result.failed,
    )


@router.post("/run-invoice-reminders", response_model=InvoiceReminderJobResponse)
def run_invoice_reminders(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> InvoiceReminderJobResponse:
    now = datetime.now(timezone.utc)
    result = run_invoice_due_reminder_job(db, now=now, limit=limit)
    db.commit()
    return InvoiceReminderJobResponse(
        checked=result.checked,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
    )


@router.post("/notifications/reminder-generation", response_model=NotificationEngineJobResponse)
def run_notifications_reminder_generation(
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationEngineJobResponse:
    now = datetime.now(timezone.utc)
    result = run_reminder_generation_job(db, now=now, limit=limit)
    db.commit()
    return NotificationEngineJobResponse(
        checked=result.checked,
        processed=result.processed,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
        job_run_id=str(result.job_run_id),
    )


@router.post("/notifications/dispatch-scheduled", response_model=NotificationEngineJobResponse)
def run_notifications_dispatch_scheduled(
    limit: int = Query(default=500, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationEngineJobResponse:
    now = datetime.now(timezone.utc)
    result = run_scheduled_notification_dispatch_job(db, now=now, limit=limit)
    db.commit()
    return NotificationEngineJobResponse(
        checked=result.checked,
        processed=result.processed,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
        job_run_id=str(result.job_run_id),
    )


@router.post("/notifications/dispatch-immediate", response_model=NotificationEngineJobResponse)
def run_notifications_dispatch_immediate(
    limit: int = Query(default=500, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationEngineJobResponse:
    now = datetime.now(timezone.utc)
    result = run_immediate_notification_dispatch_job(db, now=now, limit=limit)
    db.commit()
    return NotificationEngineJobResponse(
        checked=result.checked,
        processed=result.processed,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
        job_run_id=str(result.job_run_id),
    )


@router.post("/notifications/delivery-feedback", response_model=NotificationEngineJobResponse)
def run_notifications_delivery_feedback(
    limit: int = Query(default=500, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationEngineJobResponse:
    now = datetime.now(timezone.utc)
    result = run_delivery_feedback_job(db, now=now, limit=limit)
    db.commit()
    return NotificationEngineJobResponse(
        checked=result.checked,
        processed=result.processed,
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
        job_run_id=str(result.job_run_id),
    )
