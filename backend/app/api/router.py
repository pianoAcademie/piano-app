from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, admin_clients, admin_collaborators, admin_config, admin_pricing, auth, bookings, catalogue, clients, internal_jobs, payments_public, plans, professors, reports

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(clients.router, tags=["clients"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_config.router, tags=["admin-config"])
api_router.include_router(admin_clients.router, tags=["admin-clients"])
api_router.include_router(admin_collaborators.router, tags=["admin-collaborators"])
api_router.include_router(admin_pricing.router, tags=["admin-pricing"])
api_router.include_router(reports.router, tags=["admin-reports"])
api_router.include_router(catalogue.router, tags=["catalogue"])
api_router.include_router(plans.router, tags=["plans"])
api_router.include_router(bookings.router, tags=["bookings"])
api_router.include_router(professors.router, tags=["professors"])
api_router.include_router(internal_jobs.router, tags=["internal-jobs"])
api_router.include_router(payments_public.router, tags=["public-payments"])
