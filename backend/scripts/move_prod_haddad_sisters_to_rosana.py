from __future__ import annotations
import argparse,os,sys
from uuid import UUID
from sqlalchemy import select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.db.session import SessionLocal
from app.models.catalog import Booking,CourseSession
from app.models.user import User,UserRole
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE,preview_planning_reorganization_booking_move,move_planning_reorganization_booking
from app.schemas.admin import AdminPlanningReorganizationMovePreviewRequest,AdminPlanningReorganizationMoveRequest

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
  target_first=db.scalar(select(CourseSession).where(CourseSession.recurrence_group_id==TARGET).order_by(CourseSession.start_at_utc).limit(1))
  if not actor or not target_first: raise RuntimeError('identity_guard')
  for student,source_group in STUDENTS.items():
   source=group_bookings(db,student,source_group); target=group_bookings(db,student,TARGET)
   if not source and len(target)==32:
    print(f'HADDAD_MOVE|already_moved|student={student}');continue
   if len(source)!=32 or target: raise RuntimeError(f'count_guard_{student}_{len(source)}_{len(target)}')
   preview=preview_planning_reorganization_booking_move(AdminPlanningReorganizationMovePreviewRequest(booking_id=source[0].id,target_session_id=target_first.id,scope='series_future'),db=db,_=actor)
   if preview.affected_bookings!=32: raise RuntimeError(f'preview_count_{student}_{preview.affected_bookings}')
   print(f'HADDAD_MOVE|audit|student={student}|count=32|price_change={preview.price_change}|apply={a.apply}')
   if a.apply:
    out=move_planning_reorganization_booking(AdminPlanningReorganizationMoveRequest(booking_id=source[0].id,target_session_id=target_first.id,scope='series_future',price_policy='keep_source',expected_version=preview.version),db=db,actor=actor)
    if out.moved_count!=32: raise RuntimeError(f'move_count_{student}_{out.moved_count}')
  if not a.apply: db.rollback();return
 with SessionLocal() as verify:
  for student,source_group in STUDENTS.items():
   if group_bookings(verify,student,source_group) or len(group_bookings(verify,student,TARGET))!=32: raise RuntimeError(f'postcheck_{student}')
 print('HADDAD_MOVE|summary|result=applied|gaelle=32|zoe=32|invoices_created=0|email_sent=False')
if __name__=='__main__':main()
