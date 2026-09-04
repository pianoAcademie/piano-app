from __future__ import annotations

import os, sys
from uuid import UUID
from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.plan import ClientPlanSubscription, Plan
from app.models.quote import Quote, QuoteLine

STUDENT_ID = UUID("8442aea7-6395-49c7-8150-57a0e1bb29c8")
TARGET_GROUP_ID = UUID("3c0f8f87-70d5-4e1d-bc41-74c53859e317")

with SessionLocal() as db:
    rows = db.execute(select(Booking, CourseSession).join(CourseSession).where(
        Booking.user_id == STUDENT_ID,
        CourseSession.recurrence_group_id == TARGET_GROUP_ID,
    ).order_by(CourseSession.start_at_utc)).all()
    print("BOOKINGS", len(rows), [(str(b.total_incl_vat_snapshot), b.price_book_version_snapshot, s.start_at_utc.isoformat()) for b,s in rows])
    sub_ids = {b.client_plan_subscription_id for b,_ in rows if b.client_plan_subscription_id}
    for sid in sub_ids:
        sub, plan = db.execute(select(ClientPlanSubscription, Plan).join(Plan).where(ClientPlanSubscription.id == sid)).one()
        print("SUB", sid, plan.name, sub.initial_total_incl_vat, sub.annual_pricing_terms)
    lines = db.execute(select(ClientInvoiceLine, ClientNoteEntry).join(ClientNoteEntry).where(
        ClientInvoiceLine.source_payment_id.in_([b.id for b,_ in rows])
    ).order_by(ClientInvoiceLine.occurred_at)).all()
    print("INVOICE_LINES", [(n.id, l.source_payment_id, str(l.total_incl_vat), l.label, n.message[:300]) for l,n in lines])
    quotes = db.execute(select(Quote, QuoteLine).join(QuoteLine).where(
        (Quote.client_user_id == STUDENT_ID) | (Quote.prospect_user_id == STUDENT_ID)
    )).all()
    print("QUOTES", [(q.quote_number, str(q.total_ttc), l.label, str(l.quantity), str(l.unit_price_ttc), str(l.amount_ttc)) for q,l in quotes])
