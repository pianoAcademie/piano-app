from __future__ import annotations
import os,sys
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db.session import SessionLocal
from app.models.catalog import CourseSession,CourseType,Location,Professor
P=ZoneInfo('Europe/Paris'); START=datetime(2026,9,7,tzinfo=P).astimezone(timezone.utc); END=datetime(2026,10,18,tzinfo=P).astimezone(timezone.utc)
with SessionLocal() as db:
 locs=list(db.scalars(select(Location).where(Location.city.ilike('Bar-le-Duc'))).all());print('LOCS',[(x.id,x.name,x.timezone) for x in locs])
 profs=list(db.scalars(select(Professor).where((Professor.first_name.ilike('%Estela%'))|(Professor.last_name.ilike('%Estela%')))).all());print('PROFS',[(x.id,x.first_name,x.last_name,x.is_active) for x in profs])
 types=list(db.scalars(select(CourseType).where((CourseType.name.ilike('%essai%'))|(CourseType.code.ilike('%TRIAL%')))).all());print('TYPES',[(x.id,x.code,x.name,x.duration_minutes,x.lesson_format,x.default_course_rate_ttc,x.trial_course_enabled,x.trial_course_price_ttc,x.allows_student_bookings,x.active) for x in types])
 rows=db.execute(select(CourseSession,CourseType,Location,Professor).join(CourseType).join(Location).outerjoin(Professor).where(CourseSession.start_at_utc>=START,CourseSession.start_at_utc<END,Location.city.ilike('Bar-le-Duc')).order_by(CourseSession.start_at_utc)).all()
 for s,ct,l,p in rows:
  local=s.start_at_utc.astimezone(P)
  if local.weekday() in {2,3,5}: print('SESSION',s.id,s.recurrence_group_id,local.isoformat(),s.end_at_utc.astimezone(P).isoformat(),s.status,ct.code,ct.name,l.name,(f'{p.first_name} {p.last_name}' if p else None),s.capacity_max)
