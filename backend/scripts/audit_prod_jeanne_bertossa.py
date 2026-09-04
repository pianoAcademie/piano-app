from __future__ import annotations
import os,sys,unicodedata
from sqlalchemy import select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db.session import SessionLocal
from app.models.user import User
from app.models.plan import ClientPlanSubscription,Plan
from app.models.catalog import Booking,CourseSession,CourseType,Location
from app.models.client_record import ClientManualTransaction,ClientNoteEntry
def n(v):return ''.join(c for c in unicodedata.normalize('NFKD',str(v or '')) if not unicodedata.combining(c)).casefold().strip()
with SessionLocal() as db:
 users=[u for u in db.scalars(select(User)).all() if n(u.first_name)=='jeanne' and n(u.last_name)=='bertossa']
 print('USERS',[(u.id,u.first_name,u.last_name,u.email,u.is_active,u.client_kind,u.created_at) for u in users])
 for u in users:
  subs=db.execute(select(ClientPlanSubscription,Plan).join(Plan).where(ClientPlanSubscription.user_id==u.id).order_by(ClientPlanSubscription.started_at)).all()
  print('SUBS',u.id,[(s.id,p.name,p.kind,s.status,s.started_at,s.ends_at,s.migration_source_code,s.billing_method_code,s.payment_method_type,s.payment_provider_code,s.payment_provider_customer_ref,s.payment_provider_subscription_ref,s.last_payment_status,s.next_payment_at,s.bookings_blocked,s.initial_total_incl_vat) for s,p in subs])
  bookings=db.execute(select(Booking,CourseSession,CourseType,Location).join(CourseSession,CourseSession.id==Booking.session_id).join(CourseType,CourseType.id==CourseSession.course_type_id).join(Location,Location.id==CourseSession.location_id).where(Booking.user_id==u.id).order_by(CourseSession.start_at_utc.desc()).limit(30)).all()
  print('BOOKINGS',[(b.status,s.start_at_utc,ct.name,l.name,b.client_plan_subscription_id,str(b.total_incl_vat_snapshot)) for b,s,ct,l in bookings])
  tx=list(db.scalars(select(ClientManualTransaction).where(ClientManualTransaction.user_id==u.id).order_by(ClientManualTransaction.occurred_at.desc()).limit(30)).all())
  print('TX',[(x.id,x.occurred_at,x.transaction_type,x.status,str(x.total_incl_vat),x.label,x.reference,x.description) for x in tx])
  notes=list(db.scalars(select(ClientNoteEntry).where(ClientNoteEntry.user_id==u.id).order_by(ClientNoteEntry.created_at.desc()).limit(20)).all())
  print('NOTES',[(x.created_at,x.entry_type,(x.message or '')[:500]) for x in notes])
