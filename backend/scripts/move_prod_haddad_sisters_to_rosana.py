from __future__ import annotations
import argparse,os,sys
from uuid import UUID
from sqlalchemy import select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db.session import SessionLocal
from app.models.catalog import Booking,CourseSession
from app.models.user import User,UserRole
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE,_checked_move_version,_bind_moved_contract,_move_planning_reorganization_booking_occurrence
from app.models.client_record import StudentQuoteChange
from datetime import datetime,timezone
from decimal import Decimal

TARGET=UUID('0933a274-a0a2-56d5-a050-8ec12bbafd01')
STUDENTS={
 UUID('26f54af4-16c6-4fbc-96c3-6f4959f54eaf'):UUID('4331d4b3-c4f4-5920-b289-a8819f4673ba'),
 UUID('71156c56-a179-4120-98bc-9bf2d49f2e0d'):UUID('2616c15b-fa1a-508a-96a6-694d52cc6a1f'),
}
def group_bookings(db,student,group):
 return list(db.scalars(select(Booking).join(CourseSession).where(Booking.user_id==student,Booking.status.in_(BOOKING_STATUSES_ACTIVE),CourseSession.recurrence_group_id==group).order_by(CourseSession.start_at_utc)).all())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');a=ap.parse_args()
 with SessionLocal() as db:
  actor=db.scalar(select(User).where(User.role==UserRole.ADMIN).order_by(User.created_at).limit(1))
  target_sessions=list(db.scalars(select(CourseSession).where(CourseSession.recurrence_group_id==TARGET).order_by(CourseSession.start_at_utc)).all())
  if not actor or len(target_sessions)!=32: raise RuntimeError('identity_guard')
  for student,source_group in STUDENTS.items():
   source=group_bookings(db,student,source_group); target=group_bookings(db,student,TARGET)
   if not source and len(target)==32:
    print(f'HADDAD_MOVE|already_moved|student={student}');continue
   if len(source)!=32 or target: raise RuntimeError(f'count_guard_{student}_{len(source)}_{len(target)}')
   source_sessions=[db.get(CourseSession,b.session_id) for b in source]
   pairs=list(zip(source,source_sessions,target_sessions,strict=True))
   version,occurrences=_checked_move_version(db,pairs,0,[],datetime.now(timezone.utc))
   print(f'HADDAD_MOVE|audit|student={student}|count=32|version={version}|apply={a.apply}')
   if a.apply:
    now=datetime.now(timezone.utc)
    for booking,source_session,target_session in pairs:
     _bind_moved_contract(db,booking,target_session,'series_future')
     moved,detail=_move_planning_reorganization_booking_occurrence(db,booking=booking,source_session=source_session,target_session=target_session,now=now,target_price_snapshot=None,lock_price_snapshot=True)
     if not moved: raise RuntimeError(f'move_failed_{student}_{detail}')
    db.add(StudentQuoteChange(user_id=student,student_user_id=student,actor_user_id=actor.id,change_type='SLOT_CHANGE',status='VALIDATED',effective_date=target_sessions[0].start_at_utc.date(),title='Déplacement de 32 séances vers le cours de Rosana — tarif conservé',description='Transfert annuel vers mercredi 15 h, rue Scheffer, sans notification ni modification de facture.',before_snapshot={'occurrences':occurrences},after_snapshot={'target_sessions':[str(s.id) for s in target_sessions]},financial_impact_ttc=Decimal('0.00'),currency=str(source[0].currency_snapshot),billing_action='NONE'))
    db.commit()
  if not a.apply: db.rollback();return
 with SessionLocal() as verify:
  for student,source_group in STUDENTS.items():
   if group_bookings(verify,student,source_group) or len(group_bookings(verify,student,TARGET))!=32: raise RuntimeError(f'postcheck_{student}')
 print('HADDAD_MOVE|summary|result=applied|gaelle=32|zoe=32|invoices_created=0|email_sent=False')
if __name__=='__main__':main()
