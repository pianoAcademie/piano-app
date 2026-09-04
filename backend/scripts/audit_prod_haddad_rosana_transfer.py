from __future__ import annotations
import os,sys,unicodedata
from collections import defaultdict
from zoneinfo import ZoneInfo
from sqlalchemy import func,select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db.session import SessionLocal
from app.models.user import User
from app.models.catalog import Booking,CourseSession,CourseType,Location,Professor
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE,BOOKING_STATUSES_COUNTED_AS_RESERVED
P=ZoneInfo('Europe/Paris')
def n(v): return ''.join(c for c in unicodedata.normalize('NFKD',str(v or '')) if not unicodedata.combining(c)).casefold().strip()
with SessionLocal() as db:
 users=list(db.scalars(select(User).where(User.role=='client')).all())
 girls=[u for u in users if n(u.last_name)=='haddad' and n(u.first_name) in {'gaelle','zoe'}]
 print('GIRLS',[(u.id,u.first_name,u.last_name,u.client_kind) for u in girls])
 for u in girls:
  rows=db.execute(select(Booking,CourseSession,CourseType,Location,Professor).join(CourseSession,CourseSession.id==Booking.session_id).join(CourseType,CourseType.id==CourseSession.course_type_id).join(Location,Location.id==CourseSession.location_id).outerjoin(Professor,Professor.id==CourseSession.professor_id).where(Booking.user_id==u.id,Booking.status.in_(BOOKING_STATUSES_ACTIVE)).order_by(CourseSession.start_at_utc)).all()
  groups=defaultdict(list)
  for r in rows: groups[r[1].recurrence_group_id].append(r)
  for gid,rs in groups.items():
   b,s,ct,l,p=rs[0]; print('SOURCE',u.first_name,gid,len(rs),s.start_at_utc.astimezone(P).isoformat(),ct.name,l.name,(p.first_name+' '+p.last_name if p else None),sorted({str(x[0].total_incl_vat_snapshot) for x in rs}))
 targets=db.execute(select(CourseSession,CourseType,Location,Professor).join(CourseType,CourseType.id==CourseSession.course_type_id).join(Location,Location.id==CourseSession.location_id).join(Professor,Professor.id==CourseSession.professor_id).where(func.lower(Professor.first_name).contains('rosana')).order_by(CourseSession.start_at_utc)).all()
 groups=defaultdict(list)
 for r in targets:
  local=r[0].start_at_utc.astimezone(P)
  if local.weekday()==2 and local.hour==15: groups[r[0].recurrence_group_id].append(r)
 for gid,rs in groups.items():
  active=[r for r in rs if str(getattr(r[0].status,'value',r[0].status))=='SCHEDULED']
  caps=[]
  for s,*_ in active:
   reserved=int(db.scalar(select(func.count(Booking.id)).where(Booking.session_id==s.id,Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED))) or 0); caps.append(s.capacity_max-reserved)
  s,ct,l,p=rs[0]; print('TARGET',gid,'raw',len(rs),'scheduled',len(active),'first',active[0][0].start_at_utc.astimezone(P).isoformat() if active else None,'last',active[-1][0].start_at_utc.astimezone(P).isoformat() if active else None,'course',ct.name,'location',l.name,'prof',p.first_name,p.last_name,'free_min',min(caps) if caps else None)
