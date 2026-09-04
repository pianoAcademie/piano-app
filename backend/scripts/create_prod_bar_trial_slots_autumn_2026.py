from __future__ import annotations
import argparse,os,sys
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import or_,select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db.session import SessionLocal
from app.models.catalog import CourseSession,CourseSessionProfessor,CourseType,Location,Professor,SessionStatus
from app.services.billing_entities import normalize_billing_entity

LOCATION=UUID('26132519-8dfe-446a-91e7-82ea3172cec7'); PROFESSOR=UUID('a58909e3-e7f4-4e56-bb9b-624669946f80')
PARIS=ZoneInfo('Europe/Paris'); END=date(2026,10,17)
STARTS={3:[time(8,30),time(10),time(10,30)],5:[time(9),time(9,30),time(16),time(16,30),time(17),time(17,30)]}
def wanted():
 out=[]
 d=date(2026,9,7)
 while d<=END:
  for t in STARTS.get(d.weekday(),[]):
   s=datetime.combine(d,t,tzinfo=PARIS).astimezone(timezone.utc);out.append((s,s+timedelta(minutes=30),d.weekday(),t))
  d+=timedelta(days=1)
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');a=ap.parse_args(); expected=wanted()
 if len(expected)!=54:raise RuntimeError(f'expected_count_{len(expected)}')
 with SessionLocal() as db:
  course_types=list(db.scalars(select(CourseType).where(CourseType.name=="Cours d'essai individuel",CourseType.duration_minutes==30,CourseType.active.is_(True))).all())
  loc=db.get(Location,LOCATION);prof=db.get(Professor,PROFESSOR)
  if len(course_types)!=1 or not loc or loc.name!='Bar-le-Duc' or not prof or (prof.first_name,prof.last_name)!=('Estela','Oliviero') or not prof.active:raise RuntimeError('identity_guard')
  ct=course_types[0];course_id=ct.id
  starts={s for s,_,_,_ in expected}; existing=list(db.scalars(select(CourseSession).where(CourseSession.start_at_utc.in_(starts),CourseSession.location_id==LOCATION,CourseSession.status==SessionStatus.SCHEDULED)).all())
  exact={(s.start_at_utc,s.end_at_utc,s.course_type_id,s.professor_id) for s in existing}
  desired={(s,e,course_id,PROFESSOR) for s,e,_,_ in expected}
  if exact==desired and len(existing)==54: print('BAR_TRIAL_CREATE|already_created|count=54');return
  if existing:raise RuntimeError(f'existing_exact_start_count_{len(existing)}')
  overlaps=list(db.scalars(select(CourseSession).where(CourseSession.professor_id==PROFESSOR,CourseSession.status==SessionStatus.SCHEDULED,or_(*[((CourseSession.start_at_utc<e)&(CourseSession.end_at_utc>s)) for s,e,_,_ in expected]))).all())
  if overlaps:raise RuntimeError('professor_overlap_'+','.join(str(x.id) for x in overlaps))
  print(f'BAR_TRIAL_CREATE|audit|count=54|first={expected[0][0].astimezone(PARIS).isoformat()}|last={expected[-1][0].astimezone(PARIS).isoformat()}|free=true|children=true|adults=true|apply={a.apply}')
  if not a.apply:return
  groups={(weekday,t):uuid4() for weekday,times in STARTS.items() for t in times}
  rows=[]
  for start,end,weekday,t in expected:
   row=CourseSession(course_type_id=course_id,billing_entity_snapshot=normalize_billing_entity(ct.billing_entity_code),snapshot_seller_legal_entity_id=ct.seller_legal_entity_id,snapshot_payor_legal_entity_id=ct.payor_legal_entity_id,location_id=LOCATION,professor_id=PROFESSOR,title="Cours d'essai individuel",description="Cours d'essai individuel gratuit de 30 minutes",private_description="Créneaux temporaires Bar-le-Duc jusqu'aux vacances de la Toussaint 2026",start_at_utc=start,end_at_utc=end,is_all_day=False,capacity_max=1,child_bookings_enabled=True,adult_bookings_enabled=True,adult_capacity_max=1,child_trial_bookings_enabled=True,adult_trial_bookings_enabled=True,status=SessionStatus.SCHEDULED,auto_cancel_deadline_utc=start-timedelta(hours=12),auto_cancel_rule_enabled_override=False,is_private=False,allow_online_booking=True,visibility_scope='EXTERNAL',booking_scope='EXTERNAL',external_booking_price_ttc=Decimal('0.00'),external_booking_price_unit='PER_SESSION',show_external_remaining_seats=True,timezone='Europe/Paris',recurrence_group_id=groups[(weekday,t)],recurrence_rule='WEEKLY',recurrence_until_date=END)
   db.add(row);rows.append(row)
  db.flush()
  db.add_all([CourseSessionProfessor(session_id=r.id,professor_id=PROFESSOR,position=1) for r in rows]);db.commit()
 with SessionLocal() as verify:
  made=list(verify.scalars(select(CourseSession).where(CourseSession.start_at_utc.in_(starts),CourseSession.location_id==LOCATION,CourseSession.course_type_id==course_id,CourseSession.professor_id==PROFESSOR,CourseSession.status==SessionStatus.SCHEDULED)).all())
  if len(made)!=54 or any(x.external_booking_price_ttc!=Decimal('0.00') or not x.child_trial_bookings_enabled or not x.adult_trial_bookings_enabled for x in made):raise RuntimeError('postcheck')
 print('BAR_TRIAL_CREATE|summary|result=applied|created=54|weekly_series=9|price=0.00|children=true|adults=true')
if __name__=='__main__':main()
