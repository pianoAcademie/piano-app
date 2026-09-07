from __future__ import annotations
import argparse, os, sys
from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from sqlalchemy import func, select
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE, BOOKING_STATUSES_COUNTED_AS_RESERVED, _move_planning_reorganization_booking_occurrence
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, Location, Professor, SessionStatus
from app.models.client_record import ClientNoteEntry
from app.models.user import User

SCRIPT = "MOVE_CHARLOTTE_DE_LAVALLADE_SCHEFFER_17_TO_18_20260907"
STUDENT_ID = UUID("f3b42693-777f-4132-b303-8e5bab8f866b")
SOURCE_GROUP_ID = UUID("489c3a8a-3012-517d-9187-18d5b89e6ae6")
TARGET_GROUP_ID = UUID("d8211818-9b36-579f-80b7-4e5d1f711db0")
START_DATE, EXPECTED_COUNT = date(2026, 9, 14), 30
PARIS = ZoneInfo("Europe/Paris")

def parts(row):
    tz = ZoneInfo(row.timezone or "Europe/Paris"); a=row.start_at_utc.astimezone(tz); b=row.end_at_utc.astimezone(tz)
    return a.date(), a.time().replace(tzinfo=None), b.time().replace(tzinfo=None)

def guard_slot(db, row, expected_time, expected_professor):
    loc=db.get(Location,row.location_id); prof=db.get(Professor,row.professor_id) if row.professor_id else None
    if loc is None or str(loc.code).upper() != "SCHEFFER" or "scheffer" not in str(loc.name).casefold(): raise SystemExit(f"[{SCRIPT}] location_guard_failed")
    if parts(row) != (START_DATE, expected_time, time(expected_time.hour+1)): raise SystemExit(f"[{SCRIPT}] schedule_guard_failed actual={parts(row)}")
    full=f"{prof.first_name} {prof.last_name}".casefold() if prof else ""
    if expected_professor not in full: raise SystemExit(f"[{SCRIPT}] professor_guard_failed actual={full}")

def count_group(db, group_id):
    return db.scalar(select(func.count()).select_from(Booking).join(CourseSession,CourseSession.id==Booking.session_id).where(Booking.user_id==STUDENT_ID,Booking.status.in_(BOOKING_STATUSES_ACTIVE),CourseSession.recurrence_group_id==group_id,CourseSession.start_at_utc>=datetime(2026,9,14,tzinfo=PARIS).astimezone(timezone.utc)))

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--apply",action="store_true"); args=parser.parse_args(); now=datetime.now(timezone.utc); start=datetime(2026,9,14,tzinfo=PARIS).astimezone(timezone.utc)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.id==STUDENT_ID).with_for_update())
        if user is None or user.first_name.strip().casefold()!="charlotte" or user.last_name.strip().casefold()!="de lavallade": raise SystemExit(f"[{SCRIPT}] student_guard_failed")
        sources=db.execute(select(Booking,CourseSession).join(CourseSession,CourseSession.id==Booking.session_id).where(Booking.user_id==STUDENT_ID,Booking.status.in_(BOOKING_STATUSES_ACTIVE),CourseSession.recurrence_group_id==SOURCE_GROUP_ID,CourseSession.start_at_utc>=start,CourseSession.status==SessionStatus.SCHEDULED).order_by(CourseSession.start_at_utc).with_for_update()).all()
        targets=db.scalars(select(CourseSession).where(CourseSession.recurrence_group_id==TARGET_GROUP_ID,CourseSession.start_at_utc>=start,CourseSession.status==SessionStatus.SCHEDULED).order_by(CourseSession.start_at_utc).with_for_update()).all()
        if len(sources)!=EXPECTED_COUNT or len(targets)!=EXPECTED_COUNT: raise SystemExit(f"[{SCRIPT}] count_guard_failed source={len(sources)} target={len(targets)}")
        guard_slot(db,sources[0][1],time(17),"rosana"); guard_slot(db,targets[0],time(18),"rym")
        sb={parts(s)[0]:(b,s) for b,s in sources}; tb={parts(s)[0]:s for s in targets}
        if len(sb)!=EXPECTED_COUNT or len(tb)!=EXPECTED_COUNT or set(sb)!=set(tb): raise SystemExit(f"[{SCRIPT}] calendar_guard_failed source={sorted(sb)} target={sorted(tb)}")
        if int(count_group(db,TARGET_GROUP_ID) or 0): raise SystemExit(f"[{SCRIPT}] target_already_booked")
        for target in targets:
            occupied=db.scalar(select(func.count()).select_from(Booking).where(Booking.session_id==target.id,Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED)))
            if int(occupied or 0)>=int(target.capacity_max): raise SystemExit(f"[{SCRIPT}] target_full session={target.id} occupied={occupied}")
        days=sorted(sb); print(f"[{SCRIPT}] mode={'apply' if args.apply else 'dry-run'} move=30 first={days[0]} last={days[-1]} source=Mon_17_Scheffer_Rosana target=Mon_18_Scheffer_Rym price=keep_source notifications=none")
        if not args.apply: db.rollback(); print(f"[{SCRIPT}] committed=false"); return
        for day in days:
            booking,source=sb[day]; ok,detail=_move_planning_reorganization_booking_occurrence(db,booking=booking,source_session=source,target_session=tb[day],now=now,target_price_snapshot=None,lock_price_snapshot=True)
            if not ok: raise SystemExit(f"[{SCRIPT}] move_failed day={day} detail={detail}")
        db.add(ClientNoteEntry(user_id=STUDENT_ID,author_user_id=None,entry_type="AUTO",message=f"{SCRIPT} - 30 reservations futures transferees a compter du 14/09/2026 : lundi 17h Rue Scheffer (Rosana) vers lundi 18h Rue Scheffer (Rym). La seance du 07/09/2026 etait deja terminee et reste inchangee. Tarifs et rattachements financiers conserves. Aucune notification envoyee.")); db.flush()
        source_after=count_group(db,SOURCE_GROUP_ID); target_after=count_group(db,TARGET_GROUP_ID)
        if int(source_after or 0)!=0 or int(target_after or 0)!=EXPECTED_COUNT: raise SystemExit(f"[{SCRIPT}] postcheck_failed source={source_after} target={target_after}")
        db.commit(); print(f"[{SCRIPT}] committed=true moved=30 source_after=0 target_after={target_after}")

if __name__=="__main__": main()
