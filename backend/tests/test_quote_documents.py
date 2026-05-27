from __future__ import annotations

from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import sys
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.quotes.quote_documents import (
    _calendar_snapshot_with_line_recommendation_keys,
    _calendar_snapshot_with_planning_sessions,
    _calendar_snapshot_with_current_solfege_block,
    _check_payment_instruction_lines,
    _current_solfege_document_info,
    _line_groups,
    _line_matches_end_year_concert,
    _pass_recup_compact_notice_markup,
    _planning_block_pdf_row,
    _planning_blocks_table_html,
    _normalise_check_schedule_deposit_months,
    _quote_template_disables_pass_recup,
    _quote_template_allows_end_year_concert,
    _resolve_prospect_data,
    _session_blocked_by_quote_school_calendar,
    _solfege_pending_block_info,
)
from app.services.quotes.calendar_engine import CalendarGenerationInput, generate_calendar_snapshot
from app.api.routes.quotes import _resolve_quote_pdf_bytes


class QuoteDocumentMarkupTests(unittest.TestCase):
    def test_session_blocked_by_quote_school_calendar_honors_vacation_periods(self) -> None:
        session = {
            "date": "2026-10-20",
            "activity_id": str(uuid4()),
            "location_id": str(uuid4()),
        }
        calendar_rows = [
            {
                "is_active": True,
                "location_id": session["location_id"],
                "school_year_label": "2026-2027",
                "holiday_dates": [],
                "closure_dates": [],
                "vacation_periods": [{"start_date": "2026-10-18", "end_date": "2026-11-02"}],
            }
        ]

        blocked = _session_blocked_by_quote_school_calendar(
            session=session,
            calendar_rows=calendar_rows,
            activity_exclusion_flags={session["activity_id"]: (True, True)},
        )

        self.assertTrue(blocked)

    def test_session_blocked_by_quote_school_calendar_honors_activity_flags(self) -> None:
        activity_id = str(uuid4())
        session = {
            "date": "2026-10-20",
            "activity_id": activity_id,
            "location_id": str(uuid4()),
        }
        calendar_rows = [
            {
                "is_active": True,
                "location_id": session["location_id"],
                "school_year_label": "2026-2027",
                "holiday_dates": ["2026-10-20"],
                "closure_dates": [],
                "vacation_periods": [{"start_date": "2026-10-18", "end_date": "2026-11-02"}],
            }
        ]

        blocked = _session_blocked_by_quote_school_calendar(
            session=session,
            calendar_rows=calendar_rows,
            activity_exclusion_flags={activity_id: (False, False)},
        )

        self.assertFalse(blocked)

    def test_adult_pdf_identity_uses_typeform_contact_details_when_prospect_is_incomplete(self) -> None:
        prospect_id = uuid4()
        quote = SimpleNamespace(
            prospect_id=prospect_id,
            client_id=None,
            meta={
                "typeform_intake": {
                    "normalized_payload": {
                        "parent_phone": "+33674473945",
                        "parent_address_line_1": "11 rue Landry Gillon",
                        "parent_city": "Bar-le-Duc",
                        "parent_postal_code": "55000",
                        "parent_country": "FR",
                    }
                }
            },
        )
        prospect = SimpleNamespace(
            first_name="Perrine",
            last_name="Vacher",
            email="perrine.vacher@gmail.com",
            phone="",
            meta={"prospect_type": "adult"},
        )
        db = SimpleNamespace(scalar=lambda _query: prospect)

        prospect_data = _resolve_prospect_data(db=db, quote=quote)  # type: ignore[arg-type]

        self.assertEqual(prospect_data["adult_phone"], "+33674473945")
        self.assertEqual(prospect_data["adult_address"], "11 rue Landry Gillon, 55000 Bar-le-Duc, FR")

    def test_active_adult_quote_pdf_identity_uses_typeform_contact_details_without_prospect(self) -> None:
        quote = SimpleNamespace(
            prospect_id=None,
            client_id=None,
            meta={
                "typeform_intake": {
                    "normalized_payload": {
                        "customer_type": "adult",
                        "parent_first_name": "Perrine",
                        "parent_last_name": "Vacher",
                        "parent_email": "perrine.vacher@gmail.com",
                        "parent_phone": "+33674473945",
                        "parent_address_line_1": "11 rue Landry Gillon",
                        "parent_city": "Bar-le-Duc",
                    }
                }
            },
        )

        prospect_data = _resolve_prospect_data(db=None, quote=quote)  # type: ignore[arg-type]

        self.assertEqual(prospect_data["prospect_type"], "adult")
        self.assertEqual(prospect_data["adult_full_name"], "Perrine Vacher")
        self.assertEqual(prospect_data["adult_email"], "perrine.vacher@gmail.com")
        self.assertEqual(prospect_data["adult_phone"], "+33674473945")
        self.assertEqual(prospect_data["adult_address"], "11 rue Landry Gillon, Bar-le-Duc")

    def test_public_pdf_regenerates_when_quote_document_is_not_frozen(self) -> None:
        quote = SimpleNamespace(
            id=uuid4(),
            document_status="generated",
            document_snapshot_id=uuid4(),
        )
        db = SimpleNamespace(scalar=lambda _query: (_ for _ in ()).throw(AssertionError("stale snapshot reused")))

        with patch(
            "app.api.routes.quotes._freeze_quote_document_snapshot",
            return_value=SimpleNamespace(combined_html_snapshot="<html>fresh</html>"),
        ) as freeze_mock, patch(
            "app.api.routes.quotes.render_quote_pdf_from_combined_html",
            return_value=b"%PDF fresh",
        ) as render_mock:
            pdf_bytes = _resolve_quote_pdf_bytes(
                db,
                quote=quote,
                lines=[],
                freeze_state="frozen",
            )

        self.assertEqual(pdf_bytes, b"%PDF fresh")
        freeze_mock.assert_called_once()
        render_mock.assert_called_once()

    def test_calendar_snapshot_hydrates_missing_block_sessions_from_planning(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        session_id = uuid4()
        recurrence_id = uuid4()
        fake_db = SimpleNamespace(
            scalar=lambda _query: None,
            execute=lambda _query: SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=session_id,
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 10, 7, 16, 5, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 10, 7, 16, 35, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours de solfège - Niveau 1", mode="ONLINE"),
                        SimpleNamespace(id=location_id, name="Online", timezone="Europe/Paris", is_online=True),
                    )
                ]
            )
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours de solfège - Niveau 1",
                    "location_label": "En ligne",
                    "weekday": 2,
                    "weekday_label": "Mercredi",
                    "start_date": "2026-09-01",
                    "end_date": "2027-08-31",
                    "start_time": "18:05",
                    "end_time": "18:35",
                    "modality": "ONLINE",
                    "selection_pending": False,
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual(hydrated["sessions_count"], 1)
        self.assertEqual(hydrated["sessions"][0]["date"], "2026-10-07")
        self.assertEqual(hydrated["sessions"][0]["activity_label"], "Cours de solfège - Niveau 1")
        self.assertEqual(hydrated["sessions"][0]["modality"], "ONLINE")

    def test_calendar_snapshot_hydration_keeps_block_excluded_dates_out_of_planning_sessions(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        fake_db = SimpleNamespace(
            scalar=lambda _query: None,
            execute=lambda _query: SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectifs ado/adultes", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Rue de Richelieu", timezone="Europe/Paris", is_online=False),
                    ),
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectifs ado/adultes", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Rue de Richelieu", timezone="Europe/Paris", is_online=False),
                    ),
                ]
            )
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectifs ado/adultes",
                    "location_id": str(location_id),
                    "location_label": "Rue de Richelieu",
                    "weekday": 2,
                    "weekday_label": "Mercredi",
                    "start_date": "2026-09-09",
                    "end_date": "2027-06-16",
                    "start_time": "19:00",
                    "end_time": "20:00",
                    "holiday_dates": ["2026-11-11"],
                    "selection_pending": False,
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual(hydrated["sessions_count"], 1)
        self.assertEqual([item["date"] for item in hydrated["sessions"]], ["2026-11-04"])

    def test_calendar_snapshot_applies_session_limit_after_school_calendar_filtering(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        calendar_value = json.dumps(
            [
                {
                    "is_active": True,
                    "location_id": str(location_id),
                    "school_year_label": "2026-2027",
                    "holiday_dates": [],
                    "closure_dates": [],
                    "vacation_periods": [{"start_date": "2026-09-16", "end_date": "2026-09-16"}],
                }
            ]
        )
        rows = [
            (
                SimpleNamespace(
                    id=uuid4(),
                    course_type_id=activity_id,
                    location_id=location_id,
                    status="SCHEDULED",
                    start_at_utc=start_at,
                    end_at_utc=end_at,
                    timezone="Europe/Paris",
                    recurrence_group_id=recurrence_id,
                ),
                SimpleNamespace(id=activity_id, name="Cours collectif", mode="ONSITE"),
                SimpleNamespace(id=location_id, name="Rue de la Pompe", timezone="Europe/Paris", is_online=False),
            )
            for start_at, end_at in [
                (datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc), datetime(2026, 9, 9, 9, 0, tzinfo=timezone.utc)),
                (datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc), datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)),
                (datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc), datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc)),
                (datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc), datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)),
                (datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc), datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)),
                (datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc), datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)),
            ]
        ]
        fake_db = SimpleNamespace(
            scalar=lambda _query: SimpleNamespace(value=calendar_value),
            scalars=lambda _query: SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=activity_id,
                        exclude_holidays_in_recurrence=True,
                        exclude_school_vacations_in_recurrence=True,
                    )
                ]
            ),
            execute=lambda _query: SimpleNamespace(all=lambda: rows),
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectif",
                    "location_id": str(location_id),
                    "location_label": "Rue de la Pompe",
                    "weekday": 2,
                    "weekday_label": "Mercredi",
                    "start_date": "2026-09-09",
                    "end_date": "2026-09-23",
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "series_key": str(recurrence_id),
                    "planning_session_limit": 3,
                    "selection_pending": False,
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual([item["date"] for item in hydrated["sessions"]], ["2026-09-09", "2026-09-23", "2026-09-30"])
        self.assertEqual(hydrated["sessions_count"], 3)
        self.assertEqual(hydrated["blocks"][0]["end_date"], "2026-09-30")

    def test_calendar_snapshot_uses_expected_block_sessions_when_live_series_is_shorter(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        expected_dates = [
            "2026-09-09",
            "2026-09-16",
            "2026-09-23",
            "2026-09-30",
            "2026-10-07",
            "2026-10-14",
            "2026-11-04",
            "2026-11-18",
            "2026-11-25",
            "2026-12-02",
            "2026-12-09",
            "2026-12-16",
            "2027-01-06",
            "2027-01-13",
            "2027-01-20",
            "2027-01-27",
            "2027-02-03",
            "2027-02-24",
            "2027-03-03",
            "2027-03-10",
            "2027-03-17",
            "2027-03-24",
            "2027-03-31",
            "2027-04-21",
            "2027-04-28",
            "2027-05-05",
            "2027-05-12",
            "2027-05-19",
            "2027-05-26",
            "2027-06-02",
            "2027-06-09",
            "2027-06-16",
        ]
        paris = ZoneInfo("Europe/Paris")

        def live_row(iso_date: str) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
            local_day = date.fromisoformat(iso_date)
            local_start = datetime.combine(local_day, time(14, 0), tzinfo=paris)
            local_end = datetime.combine(local_day, time(15, 0), tzinfo=paris)
            return (
                SimpleNamespace(
                    id=uuid4(),
                    course_type_id=activity_id,
                    location_id=location_id,
                    status="SCHEDULED",
                    start_at_utc=local_start.astimezone(timezone.utc),
                    end_at_utc=local_end.astimezone(timezone.utc),
                    timezone="Europe/Paris",
                    recurrence_group_id=recurrence_id,
                ),
                SimpleNamespace(id=activity_id, name="Cours de piano collectif en presentiel (1h)", mode="ONSITE"),
                SimpleNamespace(id=location_id, name="Rue de la Pompe", timezone="Europe/Paris", is_online=False),
            )

        rows = [live_row(item) for item in expected_dates[:23]]
        fake_db = SimpleNamespace(
            scalar=lambda _query: None,
            execute=lambda _query: SimpleNamespace(all=lambda: rows),
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours de piano collectif en presentiel (1h)",
                    "location_id": str(location_id),
                    "location_label": "Rue de la Pompe",
                    "weekday": 2,
                    "weekday_label": "Mercredi",
                    "start_date": "2026-09-09",
                    "end_date": "2027-03-31",
                    "start_time": "14:00",
                    "end_time": "15:00",
                    "series_key": str(recurrence_id),
                    "calendar_school_year": "2026-2027",
                    "planning_session_limit": 32,
                    "holiday_dates": ["2026-11-11"],
                    "closure_dates": [
                        "2026-10-21",
                        "2026-10-28",
                        "2026-12-23",
                        "2026-12-30",
                        "2027-02-10",
                        "2027-02-17",
                        "2027-04-07",
                        "2027-04-14",
                    ],
                    "selection_pending": False,
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual(hydrated["sessions_count"], 32)
        self.assertEqual([item["date"] for item in hydrated["sessions"]], expected_dates)
        self.assertEqual(hydrated["blocks"][0]["end_date"], "2027-06-16")

    def test_line_recommendation_keys_copy_planning_session_limit_from_quote_line(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            id=uuid4(),
            activity_id=activity_id,
            sort_order=0,
            created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            meta={
                "typeform_automatic_line": "collective_course",
                "planning_session_limit": 32,
            },
        )
        recommendation_key = f"{activity_id}:collective_course"
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "recommendation_key": recommendation_key,
                    "start_date": "2026-09-09",
                    "end_date": "2027-04-14",
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_line_recommendation_keys(None, snapshot, lines=[line])

        self.assertEqual(hydrated["blocks"][0]["planning_session_limit"], 32)

    def test_line_recommendation_keys_copy_single_activity_session_limit(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            id=uuid4(),
            activity_id=activity_id,
            sort_order=0,
            created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            meta={"planning_session_limit": 32},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "start_date": "2026-09-09",
                    "end_date": "2027-04-14",
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_line_recommendation_keys(None, snapshot, lines=[line])

        self.assertEqual(hydrated["blocks"][0]["planning_session_limit"], 32)

    def test_line_recommendation_keys_infer_session_limit_from_service_quantity(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            id=uuid4(),
            activity_id=activity_id,
            line_category="service",
            pricing_unit="session",
            quantity=Decimal("31.00"),
            sort_order=0,
            created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "start_date": "2026-09-12",
                    "end_date": "2027-04-10",
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_line_recommendation_keys(None, snapshot, lines=[line])

        self.assertEqual(hydrated["blocks"][0]["planning_session_limit"], 31)

    def test_calendar_generation_truncates_to_session_limit_after_exclusions(self) -> None:
        snapshot = generate_calendar_snapshot(
            CalendarGenerationInput(
                start_date=date(2026, 9, 9),
                end_date=date(2027, 8, 31),
                weekdays=[2],
                start_time=time(10, 0),
                end_time=time(11, 0),
                holiday_dates=[date(2026, 11, 11)],
                closure_dates=[date(2026, 10, 21), date(2026, 10, 28)],
                session_limit=3,
            )
        )

        self.assertEqual([row["date"] for row in snapshot["sessions"]], ["2026-09-09", "2026-09-16", "2026-09-23"])
        self.assertEqual(snapshot["sessions_count"], 3)

    def test_calendar_snapshot_hydrates_partial_block_sessions_from_planning(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        fake_db = SimpleNamespace(
            scalar=lambda _query: None,
            execute=lambda _query: SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectif", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Rue de la Pompe", timezone="Europe/Paris", is_online=False),
                    ),
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectif", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Rue de la Pompe", timezone="Europe/Paris", is_online=False),
                    ),
                ]
            )
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectif",
                    "location_id": str(location_id),
                    "location_label": "Rue de la Pompe",
                    "weekday": 1,
                    "weekday_label": "Mardi",
                    "start_date": "2026-09-08",
                    "end_date": "2026-09-22",
                    "start_time": "12:00",
                    "end_time": "13:00",
                    "selection_pending": False,
                }
            ],
            "sessions": [
                {
                    "date": "2026-09-08",
                    "start_time": "12:00",
                    "end_time": "13:00",
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectif",
                    "location_id": str(location_id),
                    "location_label": "Rue de la Pompe",
                    "weekday": 1,
                    "weekday_label": "Mardi",
                }
            ],
            "sessions_count": 1,
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual([item["date"] for item in hydrated["sessions"]], ["2026-09-08", "2026-09-15"])
        self.assertEqual(hydrated["sessions_count"], 2)

    def test_calendar_snapshot_hydration_respects_block_series_key(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        expected_recurrence_id = uuid4()
        other_recurrence_id = uuid4()
        fake_db = SimpleNamespace(
            scalar=lambda _query: None,
            execute=lambda _query: SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=expected_recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectif - enfants - Bar-le-Duc", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Bar-le-Duc", timezone="Europe/Paris", is_online=False),
                    ),
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 9, 17, 16, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=other_recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectif - enfants - Bar-le-Duc", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Bar-le-Duc", timezone="Europe/Paris", is_online=False),
                    ),
                ]
            )
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectif - enfants - Bar-le-Duc",
                    "location_id": str(location_id),
                    "location_label": "Bar-le-Duc",
                    "weekday": 3,
                    "weekday_label": "Jeudi",
                    "start_date": "2026-09-10",
                    "end_date": "2026-09-17",
                    "start_time": "17:00",
                    "end_time": "18:00",
                    "series_key": str(expected_recurrence_id),
                    "selection_pending": False,
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual(hydrated["sessions_count"], 1)
        self.assertEqual(hydrated["sessions"][0]["series_key"], str(expected_recurrence_id))

    def test_calendar_snapshot_hydration_replaces_shifted_legacy_session_times(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        fake_db = SimpleNamespace(
            scalar=lambda _query: None,
            execute=lambda _query: SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=uuid4(),
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 11, 3, 18, 0, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours collectifs ado/adultes", mode="ONSITE"),
                        SimpleNamespace(id=location_id, name="Rue de la Pompe", timezone="Europe/Paris", is_online=False),
                    )
                ]
            )
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectifs ado/adultes",
                    "location_id": str(location_id),
                    "location_label": "Rue de la Pompe",
                    "weekday": 1,
                    "weekday_label": "Mardi",
                    "start_date": "2026-11-03",
                    "end_date": "2026-11-03",
                    "start_time": "19:00",
                    "end_time": "20:00",
                    "series_key": str(recurrence_id),
                    "selection_pending": False,
                }
            ],
            "sessions": [
                {
                    "date": "2026-11-03",
                    "start_time": "18:00",
                    "end_time": "19:00",
                    "activity_id": str(activity_id),
                    "activity_label": "Cours collectifs ado/adultes",
                    "location_id": str(location_id),
                    "location_label": "Rue de la Pompe",
                    "series_key": str(recurrence_id),
                    "weekday": 1,
                    "weekday_label": "Mardi",
                }
            ],
            "sessions_count": 1,
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual(hydrated["sessions_count"], 1)
        self.assertEqual(hydrated["sessions"][0]["date"], "2026-11-03")
        self.assertEqual(hydrated["sessions"][0]["start_time"], "19:00")
        self.assertEqual(hydrated["sessions"][0]["end_time"], "20:00")

    def test_pass_recup_compact_pdf_markup_is_reportlab_compatible(self) -> None:
        markup = _pass_recup_compact_notice_markup(language="fr", pdf_compatible=True)
        markup = markup.replace("<p>", "").replace("</p>", "")

        paragraph = Paragraph(markup, getSampleStyleSheet()["BodyText"])

        self.assertIsNotNone(paragraph)
        self.assertIn("<font", markup)
        self.assertNotIn("<span", markup)

    def test_bar_le_duc_quote_templates_disable_pass_recup_pdf_option(self) -> None:
        child_quote = SimpleNamespace(
            meta={"quote_template_code": "TEMPLATE_BAR_LE_DUC_ENFANT"},
            quote_template_id=None,
            quote_template_version_id=None,
        )
        adult_quote = SimpleNamespace(
            meta={"quote_template_code": "TEMPLATE_BLD_ADULTES"},
            quote_template_id=None,
            quote_template_version_id=None,
        )

        self.assertTrue(_quote_template_disables_pass_recup(db=None, quote=child_quote))
        self.assertTrue(_quote_template_disables_pass_recup(db=None, quote=adult_quote))

    def test_end_year_concert_line_match_detects_billed_option(self) -> None:
        line = SimpleNamespace(
            title="Concert de fin d’année",
            code="CONCERT_FIN_ANNEE",
            line_type="item",
            line_category="product",
            master_item_type="product",
        )

        self.assertTrue(_line_matches_end_year_concert(line))

    def test_end_year_concert_template_gate_uses_meta(self) -> None:
        enabled_quote = SimpleNamespace(
            meta={"end_year_concert_option_mode": "enabled"},
            quote_template_id=None,
            quote_template_version_id=None,
        )
        regular_quote = SimpleNamespace(meta={}, quote_template_id=None, quote_template_version_id=None)

        self.assertTrue(_quote_template_allows_end_year_concert(db=None, quote=enabled_quote))
        self.assertFalse(_quote_template_allows_end_year_concert(db=None, quote=regular_quote))

    def test_solfege_pending_info_detects_accented_labels_and_keeps_slot_proposals(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 2",
                    "location_label": "Online",
                    "weekday": -1,
                    "selection_pending": True,
                    "pending_slot_options": [
                        {
                            "weekday_label": "Mercredi",
                            "start_time": "17:15",
                            "end_time": "18:00",
                            "location_label": "Online",
                            "modality": "ONLINE",
                        },
                        {
                            "weekday_label": "Samedi",
                            "start_time": "10:15",
                            "end_time": "11:00",
                            "location_label": "Online",
                            "modality": "ONLINE",
                        },
                    ],
                }
            ]
        }

        info = _solfege_pending_block_info(snapshot, language="fr")

        self.assertTrue(info["has_pending_selection"])
        self.assertEqual(info["level_code"], "2")
        self.assertGreaterEqual(len(info["slot_labels"]), 2)
        self.assertTrue(any("Mercredi" in label for label in info["slot_labels"]))
        self.assertTrue(any("Samedi" in label for label in info["slot_labels"]))

    def test_solfege_pending_info_falls_back_to_rule_slots_when_snapshot_has_none(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 2",
                    "location_label": "Online",
                    "location_id": None,
                    "weekday": -1,
                    "selection_pending": True,
                    "pending_solfege_level": "2",
                    "modality": "ONLINE",
                    "pending_slot_options": [],
                }
            ]
        }
        fake_rule = SimpleNamespace(
            allowed_time_slots=[
                {"weekday": 2, "start_time": "17:15", "end_time": "18:00"},
                {"weekday": 5, "start_time": "10:15", "end_time": "11:00"},
            ],
            allowed_weekdays=[],
            location_id=None,
            modality="ONLINE",
            created_at=None,
        )

        with patch(
            "app.services.quotes.quote_documents._matching_solfege_rule_for_pending_block",
            return_value=fake_rule,
        ):
            info = _solfege_pending_block_info(snapshot, db=object(), language="fr")

        self.assertTrue(info["has_pending_selection"])
        self.assertTrue(any("Mercredi 17:15-18:00" in label for label in info["slot_labels"]))
        self.assertTrue(any("Samedi 10:15-11:00" in label for label in info["slot_labels"]))

    def test_planning_blocks_table_uses_selected_solfege_slot_when_pending_block_was_chosen(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 1",
                    "location_label": "Online",
                    "weekday": -1,
                    "weekday_label": "Selection a faire",
                    "start_time": "",
                    "end_time": "",
                    "duration_minutes": 30,
                    "selection_pending": True,
                    "pending_solfege_level": "1",
                    "pending_slot_options": [
                        {
                            "weekday_label": "Mardi",
                            "start_time": "17:05",
                            "end_time": "17:35",
                            "location_label": "Online",
                        }
                    ],
                }
            ]
        }
        selected_slot = {
            "weekday": 1,
            "weekday_label": "Mardi",
            "start_time": "17:05",
            "end_time": "17:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "label": "Mardi 17:05-17:35 · Online",
        }

        html, count = _planning_blocks_table_html(
            snapshot,
            selected_solfege_slot=selected_slot,
            language="fr",
        )

        self.assertEqual(count, 1)
        self.assertIn("Mardi", html)
        self.assertIn("17:05 - 17:35", html)
        self.assertNotIn("à choisir", html)

    def test_pdf_planning_row_uses_selected_solfege_slot_when_pending_block_was_chosen(self) -> None:
        block = {
            "activity_label": "Cours de solfège en ligne - niveau 4",
            "location_label": "Online",
            "weekday": -1,
            "weekday_label": "Selection a faire",
            "start_time": "",
            "end_time": "",
            "duration_minutes": 45,
            "selection_pending": True,
            "pending_solfege_level": "4",
            "modality": "ONLINE",
        }
        selected_slot = {
            "weekday": 3,
            "weekday_label": "Jeudi",
            "start_time": "18:50",
            "end_time": "19:35",
            "duration_minutes": 45,
            "location_label": "Online",
            "level_code": "4",
        }

        row = _planning_block_pdf_row(block, selected_solfege_slot=selected_slot, language="fr")

        self.assertEqual(row[1], "Online")
        self.assertEqual(row[2], "Jeudi")
        self.assertEqual(row[3], "18:50 - 19:35")
        self.assertEqual(row[4], "45 min")
        self.assertNotIn("à choisir", " ".join(row))

    def test_current_solfege_document_info_prefers_saved_line_and_planning_over_stale_quote_fields(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=activity_id,
            title="Solfège - Niveau 2",
            description="Cours de solfège en ligne",
            code="SOLFEGE_NIVEAU_2",
            duration_minutes=45,
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours de solfège - Niveau 2",
                    "location_label": "Online",
                    "weekday": 3,
                    "weekday_label": "Jeudi",
                    "start_time": "18:50",
                    "end_time": "19:35",
                    "duration_minutes": 45,
                    "selection_pending": False,
                    "pending_solfege_level": "2",
                    "modality": "ONLINE",
                }
            ]
        }
        stale_selected_slot = {
            "weekday": 2,
            "weekday_label": "Mercredi",
            "start_time": "18:05",
            "end_time": "18:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "level_code": "1",
        }

        info = _current_solfege_document_info(
            lines=[line],
            calendar_snapshot=snapshot,
            quote_selected_slot=stale_selected_slot,
            quote_level="1",
            quote_duration_minutes=30,
            language="fr",
        )

        self.assertEqual(info["level_code"], "2")
        self.assertEqual(info["duration_minutes"], 45)
        self.assertEqual(info["selected_slot"]["weekday_label"], "Jeudi")
        self.assertEqual(info["selected_slot"]["start_time"], "18:50")
        self.assertIn("cours en ligne", info["selected_slot"]["label"].lower())

    def test_current_solfege_document_info_matches_same_level_when_activity_ids_differ(self) -> None:
        line_activity_id = uuid4()
        planning_activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=line_activity_id,
            title="Cours de solfège en ligne - niveau 4",
            description="Cours de solfège en ligne",
            code="SOLFEGE_NIVEAU_4",
            duration_minutes=45,
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(planning_activity_id),
                    "activity_label": "Solfège niveau 4",
                    "location_label": "Online",
                    "weekday": 3,
                    "weekday_label": "Jeudi",
                    "start_time": "18:50",
                    "end_time": "19:35",
                    "duration_minutes": 45,
                    "selection_pending": False,
                    "pending_solfege_level": "4",
                    "modality": "ONLINE",
                }
            ]
        }

        info = _current_solfege_document_info(
            lines=[line],
            calendar_snapshot=snapshot,
            quote_selected_slot={},
            quote_level="4",
            quote_duration_minutes=45,
            language="fr",
        )

        self.assertTrue(info["has_current_solfege"])
        self.assertEqual(info["level_code"], "4")
        self.assertEqual(info["selected_slot"]["weekday_label"], "Jeudi")
        self.assertEqual(info["selected_slot"]["start_time"], "18:50")

    def test_current_solfege_document_info_ignores_stale_quote_fields_without_current_solfege(self) -> None:
        stale_selected_slot = {
            "weekday": 2,
            "weekday_label": "Mercredi",
            "start_time": "18:05",
            "end_time": "18:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "level_code": "1",
        }

        info = _current_solfege_document_info(
            lines=[],
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de piano collectif en présentiel (1h)",
                        "location_label": "Rue de Richelieu",
                        "weekday": 5,
                        "weekday_label": "Samedi",
                        "start_time": "11:00",
                        "end_time": "12:00",
                        "duration_minutes": 60,
                    }
                ]
            },
            quote_selected_slot=stale_selected_slot,
            quote_level="1",
            quote_duration_minutes=30,
            language="fr",
        )

        self.assertFalse(info["has_current_solfege"])
        self.assertEqual(info["level_code"], "")
        self.assertIsNone(info["duration_minutes"])
        self.assertEqual(info["selected_slot"], {})

    def test_current_solfege_block_is_added_to_planning_table_when_snapshot_lacks_it(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=activity_id,
            title="Solfège - Niveau 1",
            description="Cours de solfège en ligne",
            code="SOLFEGE_NIVEAU_1",
            duration_minutes=30,
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(uuid4()),
                    "activity_label": "Cours de piano collectif en présentiel (1h)",
                    "location_label": "Rue d Assas",
                    "weekday": 1,
                    "weekday_label": "Mardi",
                    "start_time": "17:00",
                    "end_time": "18:00",
                    "duration_minutes": 60,
                    "selection_pending": False,
                }
            ]
        }
        selected_slot = {
            "weekday": 1,
            "weekday_label": "Mardi",
            "start_time": "17:05",
            "end_time": "17:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "level_code": "1",
            "modality": "ONLINE",
        }

        snapshot = _calendar_snapshot_with_current_solfege_block(
            snapshot,
            lines=[line],
            selected_solfege_slot=selected_slot,
            language="fr",
        )
        html, count = _planning_blocks_table_html(snapshot, language="fr")

        self.assertEqual(count, 2)
        self.assertIn("Cours de piano collectif", html)
        self.assertIn("Cours de solfège en ligne - niveau 1", html)
        self.assertIn("à choisir", html)

    def test_line_groups_route_service_products_to_other_fees(self) -> None:
        product_id = uuid4()
        line = SimpleNamespace(
            line_type="item",
            master_item_type="product",
            title="Frais de coordination",
            code="FEE_COORDINATION",
            line_category="product",
            product_id=product_id,
            kit_id=None,
        )

        services, products, kits, adjustments, other_fees = _line_groups([line], service_product_ids={product_id})

        self.assertEqual(services, [])
        self.assertEqual(products, [])
        self.assertEqual(kits, [])
        self.assertEqual(adjustments, [])
        self.assertEqual(other_fees, [line])

    def test_check_payment_instructions_use_piano_academie_payee(self) -> None:
        lines = _check_payment_instruction_lines(
            payment_method_label="Cheque",
            schedule=[],
            legal_entity_name="Piano Academie SAS",
            has_deposit=False,
            language="fr",
        )

        self.assertIn("à l’ordre de PIANO ACADEMIE", " ".join(lines))
        self.assertTrue(any("signer vos chèques" in line or "signez vos chèques" in line.lower() for line in lines))
        self.assertTrue(any("1 rue de Richelieu, 75001 PARIS" in line for line in lines))
        self.assertFalse(any("acompte" in line.lower() for line in lines))
        self.assertFalse(any("l’ensemble des chèques" in line for line in lines))

    def test_check_payment_instructions_use_services_payee_and_deposit_card_notice(self) -> None:
        lines = _check_payment_instruction_lines(
            payment_method_label="",
            schedule=[{"payment_method": "Chèque"}, {"payment_method": "Chèque"}],
            legal_entity_name="Piano Academie Services SAS",
            has_deposit=True,
            deposit_amount_ttc=Decimal("200.00"),
            currency="EUR",
            language="fr",
        )

        joined = " ".join(lines)
        self.assertIn("à l’ordre de PIANO ACADEMIE SERVICES", joined)
        self.assertIn("L’acompte de 200,00 EUR", joined)
        self.assertIn("doit être réglé par carte bancaire", joined)
        self.assertIn("avec le lien de paiement", joined)
        self.assertIn("l’ensemble des chèques doit être envoyé avant le démarrage des cours", joined)
        self.assertNotIn("Lorsqu’un acompte est demandé", joined)

    def test_check_schedule_normalisation_keeps_configured_second_check_month(self) -> None:
        schedule = _normalise_check_schedule_deposit_months(
            [
                {"label": "1er cheque", "payment_method": "Cheque"},
                {"label": "2e cheque", "payment_method": "Cheque", "due_month": 2, "due_label": "fevrier"},
            ],
            language="fr",
        )

        self.assertEqual(schedule[0]["due_label"], "avant le démarrage du 1er cours")
        self.assertEqual(schedule[1]["due_month"], 2)
        self.assertEqual(schedule[1]["due_label"], "fevrier")


if __name__ == "__main__":
    unittest.main()
