from __future__ import annotations

from pydantic import BaseModel


class ReminderJobResponse(BaseModel):
    created: int
    sent: int
    skipped: int
    failed: int


class AutoCancelJobResponse(BaseModel):
    checked: int
    cancelled_sessions: int
    cancelled_bookings: int


class PayoutJobResponse(BaseModel):
    checked: int
    created: int
    updated: int
    skipped_no_rate: int
    skipped_existing_locked: int


class ProfessorDailyDigestJobResponse(BaseModel):
    checked: int
    sent: int
    skipped_not_due: int
    skipped_no_courses: int
    failed: int


class SubscriptionBillingJobResponse(BaseModel):
    checked: int
    charged: int
    skipped: int
    failed: int
    processed: int | None = None
    first_failures: int | None = None
    final_failures: int | None = None
    job_run_id: str | None = None


class SubscriptionCycleGenerationJobResponse(BaseModel):
    checked: int
    created: int
    skipped: int
    failed: int
    job_run_id: str


class SubscriptionRetryJobResponse(BaseModel):
    checked: int
    recovered: int
    skipped: int
    failed: int
    final_failures: int
    processed: int
    job_run_id: str


class SubscriptionRecoveryReconciliationJobResponse(BaseModel):
    checked: int
    reconciled: int
    skipped: int
    failed: int
    job_run_id: str


class AutoInvoiceBillingJobResponse(BaseModel):
    checked: int
    generated: int
    skipped_empty: int
    skipped_duplicate: int
    failed: int


class NotificationEngineJobResponse(BaseModel):
    checked: int
    processed: int
    sent: int
    skipped: int
    failed: int
    job_run_id: str
