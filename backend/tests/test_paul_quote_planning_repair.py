from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from uuid import uuid4
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.repair_prod_paul_quote_planning_20260831 import (
    ACTIVITY, LOCATION, NEW_SERIES, OLD_SERIES, SessionStatus, repair_calendar,
)


class PaulQuotePlanningRepairTests(unittest.TestCase):
    def setUp(self):
        excluded = {"2026-10-21", "2026-10-28", "2026-11-11", "2026-12-23", "2026-12-30", "2027-02-10", "2027-02-17", "2027-04-07", "2027-04-14"}
        common = {"series_key": str(OLD_SERIES), "activity_id": str(ACTIVITY), "location_id": str(LOCATION), "weekday": 2, "start_time": "19:00", "end_time": "20:00"}
        rows, live = [], []
        cursor = date(2026, 9, 2)
        while cursor <= date(2027, 6, 16):
            start = datetime.combine(cursor, time(19), ZoneInfo("Europe/Paris"))
            live.append(SimpleNamespace(id=uuid4(), status=SessionStatus.SCHEDULED, recurrence_group_id=NEW_SERIES, course_type_id=ACTIVITY, location_id=LOCATION, timezone="Europe/Paris", start_at_utc=start.astimezone(timezone.utc), end_at_utc=(start + timedelta(hours=1)).astimezone(timezone.utc)))
            if cursor >= date(2026, 9, 9) and cursor.isoformat() not in excluded:
                rows.append({**common, "session_id": str(uuid4()), "date": cursor.isoformat()})
            cursor += timedelta(days=7)
        self.snapshot = {"sessions": rows, "sessions_count": 32, "blocks": [{**common, "start_date": "2026-09-09", "end_date": "2027-06-16", "holiday_dates": sorted(excluded)}], "generated_at": "2026-05-18T19:44:22.170Z"}
        self.live = live

    def test_preserves_all_approved_content_and_excludes_extra_live_dates(self):
        before = deepcopy(self.snapshot)
        result = repair_calendar(self.snapshot, self.live)
        self.assertEqual(self.snapshot, before)
        self.assertEqual(len(self.live), 42)
        self.assertEqual(len(result["sessions"]), 32)
        self.assertEqual([r["date"] for r in result["sessions"]], [r["date"] for r in before["sessions"]])
        self.assertEqual(result["blocks"][0]["holiday_dates"], before["blocks"][0]["holiday_dates"])
        self.assertTrue(all(r["series_key"] == str(NEW_SERIES) for r in result["sessions"]))
        self.assertEqual(result["generated_at"], before["generated_at"])

    def test_rejects_missing_and_ambiguous_replacements(self):
        for live in [self.live[:1] + self.live[2:], self.live + [self.live[1]]]:
            with self.subTest(count=len(live)), self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
                repair_calendar(self.snapshot, live)

    def test_rejects_wrong_location_activity_series_time_or_status(self):
        changes = [{"location_id": uuid4()}, {"course_type_id": uuid4()}, {"recurrence_group_id": uuid4()}, {"status": SessionStatus.CANCELLED}, {"start_at_utc": self.live[1].start_at_utc + timedelta(hours=1)}]
        for change in changes:
            live = deepcopy(self.live)
            live[1].__dict__.update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
                repair_calendar(self.snapshot, live)

    def test_rejects_duplicate_approved_dates(self):
        self.snapshot["sessions"][1]["date"] = self.snapshot["sessions"][0]["date"]
        with self.assertRaisesRegex(ValueError, "Duplicate approved"):
            repair_calendar(self.snapshot, self.live)


if __name__ == "__main__":
    unittest.main()
