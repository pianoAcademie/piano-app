from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    admin_catalog,
    admin_clients,
    admin_collaborators,
    admin_config,
    admin_notifications,
    admin_subscriptions,
    admin_to_process,
    admin_pricing,
    admin_teacher_invoices,
    auth,
    bookings,
    catalogue,
    clients,
    events,
    internal_jobs,
    notification_webhooks,
    impersonation,
    payments_public,
    plans,
    professor_catalog,
    professors,
    quotes,
    reports,
    teacher_invoicing,
    typeform_intakes,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(clients.router, tags=["clients"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_catalog.router, tags=["admin-catalog"])
api_router.include_router(admin_config.router, tags=["admin-config"])
api_router.include_router(admin_clients.router, tags=["admin-clients"])
api_router.include_router(admin_collaborators.router, tags=["admin-collaborators"])
api_router.include_router(admin_pricing.router, tags=["admin-pricing"])
api_router.include_router(admin_notifications.router, tags=["admin-notifications"])
api_router.include_router(admin_subscriptions.router, tags=["admin-subscriptions"])
api_router.include_router(admin_to_process.router, tags=["admin-to-process"])
api_router.include_router(admin_teacher_invoices.router, tags=["admin-teacher-invoices"])
api_router.include_router(reports.router, tags=["admin-reports"])
api_router.include_router(catalogue.router, tags=["catalogue"])
api_router.include_router(plans.router, tags=["plans"])
api_router.include_router(bookings.router, tags=["bookings"])
api_router.include_router(professors.router, tags=["professors"])
api_router.include_router(teacher_invoicing.router, tags=["teacher-invoicing"])
api_router.include_router(professor_catalog.router, tags=["professor-catalog"])
api_router.include_router(quotes.router, tags=["quotes"])
api_router.include_router(typeform_intakes.router, tags=["typeform-intakes"])
api_router.include_router(internal_jobs.router, tags=["internal-jobs"])
api_router.include_router(notification_webhooks.router, tags=["notification-webhooks"])
api_router.include_router(payments_public.router, tags=["public-payments"])
api_router.include_router(impersonation.router, tags=["impersonation"])
