from __future__ import annotations
import argparse, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from sqlalchemy import func, or_, select
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE, BOOKING_STATUSES_COUNTED_AS_RESERVED
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location, Professor
from app.models.user import User

PARIS = ZoneInfo("Europe/Paris")
START = datetime(2026, 9, 7, 0, 0, tzinfo=PARIS).astimezone(timezone.utc)

def local(row):
    tz = ZoneInfo(row.timezone or "Europe/Paris")
    start, end = row.start_at_utc.astimezone(tz), row.end_at_utc.astimezone(tz)
    return f"{start.date()} {start:%H:%M}-{end:%H:%M}"

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apply", action="store_true"); parser.parse_args()
    with SessionLocal() as db:
        users = db.scalars(select(User).where(func.lower(User.first_name).like("%charlotte%"), func.lower(User.last_name).like("%lavallade%"))).all()
        print(f"[CHARLOTTE_INSPECT] users={[(str(u.id), u.first_name, u.last_name) for u in users]}")
        for user in users:
            rows = db.execute(select(Booking, CourseSession, CourseType, Location, Professor).join(CourseSession, CourseSession.id == Booking.session_id).join(CourseType, CourseType.id == CourseSession.course_type_id).join(Location, Location.id == CourseSession.location_id).outerjoin(Professor, Professor.id == CourseSession.professor_id).where(Booking.user_id == user.id, Booking.status.in_(BOOKING_STATUSES_ACTIVE), CourseSession.start_at_utc >= START).order_by(CourseSession.start_at_utc)).all()
            groups = {}
            for booking, session, course, location, professor in rows:
                key = str(session.recurrence_group_id)
                groups.setdefault(key, []).append((booking, session, course, location, professor))
            for gid, items in groups.items():
                b,s,c,l,p = items[0]
                print(f"[CHARLOTTE_INSPECT] source user={user.id} group={gid} count={len(items)} first_booking={b.id} first_session={s.id} schedule={local(s)} course={c.name!r} location={l.code}/{l.name} professor={(p.first_name+' '+p.last_name) if p else '-'} price={b.total_incl_vat_snapshot} currency={b.currency_snapshot}")
        targets = db.execute(select(CourseSession, CourseType, Location, Professor).join(CourseType, CourseType.id == CourseSession.course_type_id).join(Location, Location.id == CourseSession.location_id).outerjoin(Professor, Professor.id == CourseSession.professor_id).where(or_(func.upper(Location.code) == "SCHEFFER", func.lower(Location.name).like("%scheffer%")), CourseSession.start_at_utc >= START).order_by(CourseSession.start_at_utc)).all()
        by_group = {}
        for session, course, location, professor in targets:
            when = session.start_at_utc.astimezone(ZoneInfo(session.timezone or "Europe/Paris"))
            if when.weekday() == 0 and when.hour == 18 and when.minute == 0:
                by_group.setdefault(str(session.recurrence_group_id), []).append((session,course,location,professor))
        for gid, items in by_group.items():
            s,c,l,p = items[0]
            reserved = db.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == s.id, Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED)))
            print(f"[CHARLOTTE_INSPECT] target group={gid} count={len(items)} first_session={s.id} schedule={local(s)} course={c.name!r} location={l.code}/{l.name} professor={(p.first_name+' '+p.last_name) if p else '-'} capacity={reserved}/{s.capacity_max}")
        db.rollback()

if __name__ == "__main__": main()
