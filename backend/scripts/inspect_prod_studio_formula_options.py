from __future__ import annotations

import os
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseType, Location
from app.models.ops import AppSetting
from app.services.quotes.quote_documents import (
    QUOTE_SCHOOL_CALENDARS_SETTING_KEY,
    _calendar_row_applies_to_session,
    _expand_calendar_vacation_dates,
    _is_true,
    _json_list,
    _json_object,
    _parse_iso_date_set,
)

PREFIX="PROD_ONLINE_CALENDAR_BLOCKER_INSPECT"
DATES=[date(2027,3,30), date(2027,5,18)]
COURSE_NAME="Cours de piano collectif en ligne - enfants (1h)"


def p(line): print(f"[{PREFIX}] {line}")


def main():
    with SessionLocal() as db:
        location = db.scalar(select(Location).where(Location.code == "ONLINE").limit(1))
        if location is None:
            location = db.scalar(select(Location).where(Location.is_online.is_(True)).limit(1))
        course = db.scalar(select(CourseType).where(CourseType.name == COURSE_NAME).limit(1))
        p(f"location={location.id if location else '-'}|code={location.code if location else '-'}|name={location.name if location else '-'}")
        p(f"course={course.id if course else '-'}|name={course.name if course else '-'}|exclude_holidays={getattr(course,'exclude_holidays_in_recurrence',None)}|exclude_vacations={getattr(course,'exclude_school_vacations_in_recurrence',None)}")
        setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
        rows = _json_list(__import__('json').loads(setting.value or '[]')) if setting else []
        for target in DATES:
            p(f"date={target.isoformat()}")
            for idx, raw in enumerate(rows, start=1):
                row = _json_object(raw)
                if not _is_true(row.get('is_active', True)):
                    continue
                applies = _calendar_row_applies_to_session(row, location_id=str(location.id), session_date=target) if location else False
                holidays = target in _parse_iso_date_set(row.get('holiday_dates'))
                closures = target in _parse_iso_date_set(row.get('closure_dates'))
                vacations = target in _expand_calendar_vacation_dates(row)
                if applies and (holidays or closures or vacations):
                    p(
                        f"blocker idx={idx}|id={row.get('id')}|name={row.get('name')}|school_year={row.get('school_year_label')}|"
                        f"location_id={row.get('location_id')}|location_ids={row.get('location_ids')}|holiday={holidays}|closure={closures}|vacation={vacations}|"
                        f"vacation_periods={row.get('vacation_periods')}|holiday_dates={row.get('holiday_dates')}|closure_dates={row.get('closure_dates')}"
                    )

if __name__ == '__main__': main()
