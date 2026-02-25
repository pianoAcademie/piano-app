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
