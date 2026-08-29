from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin import (
    _parse_school_year_bounds,
    _planning_simulation_clean_location_label,
    _planning_simulation_live_slot_key,
    _planning_simulation_location_name_key,
    _planning_simulation_is_online_solfege,
    _planning_simulation_quote_person_key,
    _planning_simulation_quote_capacity_key,
    _planning_simulation_add_quote_capacity,
    _planning_simulation_quote_reserves_capacity,
    _planning_simulation_quote_location_name,
    _planning_simulation_resolve_live_slot_for_quote,
    _planning_simulation_search_text,
    _planning_simulation_select_live_slot_for_quote,
    _planning_simulation_teacher_assignment_warnings,
    _planning_simulation_teacher_needs,
    _safe_zoneinfo,
    update_planning_simulation_teacher_assignment,
)
from app.models.catalog import DeliveryMode
from app.models.planning_simulation import PlanningSimulationTeacherAssignment
from app.schemas.admin import AdminPlanningSimulationTeacherAssignmentUpdateRequest


class _AssignmentSession:
    def __init__(self, scalar_results: list[object | None]) -> None:
        self.scalar_results = list(scalar_results)
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commits = 0

    def scalar(self, _statement: object) -> object | None:
        return self.scalar_results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)

    def delete(self, value: object) -> None:
        self.deleted.append(value)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, _value: object) -> None:
        pass


class AdminPlanningSimulationTests(unittest.TestCase):
    def test_change_request_revision_draft_releases_capacity_until_sent(self) -> None:
        released_draft = SimpleNamespace(status="created", meta={"planning_hold_released": True})
        sent_revision = SimpleNamespace(status="sent", meta={"planning_hold_released": True})
        regular_draft = SimpleNamespace(status="created", meta={})
        replaced_source = SimpleNamespace(status="replaced", meta={"planning_hold_released": True})

        self.assertFalse(_planning_simulation_quote_reserves_capacity(released_draft))
        self.assertTrue(_planning_simulation_quote_reserves_capacity(sent_revision))
        self.assertTrue(_planning_simulation_quote_reserves_capacity(regular_draft))
        self.assertFalse(_planning_simulation_quote_reserves_capacity(replaced_source))

    def test_quote_variants_share_one_capacity_key(self) -> None:
        group_id = str(uuid4())
        first = SimpleNamespace(id=uuid4(), meta={"variant_group_id": group_id})
        second = SimpleNamespace(id=uuid4(), meta={"variant_group_id": group_id})
        independent = SimpleNamespace(id=uuid4(), meta={})

        self.assertEqual(
            _planning_simulation_quote_capacity_key(first),
            _planning_simulation_quote_capacity_key(second),
        )
        self.assertNotEqual(
            _planning_simulation_quote_capacity_key(first),
            _planning_simulation_quote_capacity_key(independent),
        )

    def test_quote_variant_capacity_uses_highest_status_once(self) -> None:
        entry = {
            "_draft_quote_ids": set(),
            "_draft_quote_students": {},
            "_pending_quote_ids": set(),
            "_pending_quote_students": {},
            "_approved_quote_ids": set(),
            "_approved_quote_students": {},
        }
        capacity_key = f"variant:{uuid4()}"

        _planning_simulation_add_quote_capacity(
            entry,
            bucket_name="_draft_quote_ids",
            bucket_people_name="_draft_quote_students",
            capacity_key=capacity_key,
            student_name="Eleve",
        )
        _planning_simulation_add_quote_capacity(
            entry,
            bucket_name="_pending_quote_ids",
            bucket_people_name="_pending_quote_students",
            capacity_key=capacity_key,
            student_name="Eleve",
        )

        self.assertEqual(entry["_draft_quote_ids"], set())
        self.assertEqual(entry["_pending_quote_ids"], {capacity_key})
        self.assertEqual(entry["_approved_quote_ids"], set())

    @staticmethod
    def _teacher_need_slot(
        *,
        activity_id: object,
        activity_name: str,
        weekday: int,
        weekday_label: str,
        start_time: str,
        end_time: str,
        location_id: object | None = None,
        location_name: str = "Site principal",
        occurrence_dates: list[date] | None = None,
        slot_key: str | None = None,
        teacher_assignment_professor_id: object | None = None,
        teacher_assignment_label: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            slot_key=slot_key or f"slot-{uuid4()}",
            course_type_id=activity_id,
            course_type_name=activity_name,
            course_type_color_hex="#94C973",
            location_id=location_id,
            location_name=location_name,
            weekday=weekday,
            weekday_label=weekday_label,
            start_time=start_time,
            end_time=end_time,
            occurrence_dates=occurrence_dates or [],
            teacher_assignment_professor_id=teacher_assignment_professor_id,
            teacher_assignment_label=teacher_assignment_label,
        )

    def test_parse_school_year_bounds_accepts_standard_label(self) -> None:
        self.assertEqual(
            _parse_school_year_bounds("2026-2027"),
            (date(2026, 9, 1), date(2027, 8, 31)),
        )

    def test_parse_school_year_bounds_rejects_invalid_label(self) -> None:
        self.assertIsNone(_parse_school_year_bounds(""))
        self.assertIsNone(_parse_school_year_bounds("2027-2026"))
        self.assertIsNone(_parse_school_year_bounds("saison"))

    def test_safe_zoneinfo_falls_back_for_missing_or_invalid_timezone(self) -> None:
        self.assertEqual(_safe_zoneinfo(None).key, "Europe/Paris")
        self.assertEqual(_safe_zoneinfo("not-a-timezone").key, "Europe/Paris")
        self.assertEqual(_safe_zoneinfo("UTC").key, "UTC")

    def test_planning_simulation_hides_uuid_location_labels(self) -> None:
        self.assertEqual(
            _planning_simulation_clean_location_label("1be3c4dc-2f55-4712-bcf9-32a4624ff1ad"),
            "",
        )

    def test_planning_simulation_search_text_strips_accents(self) -> None:
        self.assertEqual(
            _planning_simulation_search_text("Cours collectif Éveil musical - Répétition"),
            "cours collectif eveil musical - repetition",
        )

    def test_planning_simulation_location_name_key_matches_bar_le_duc_variants(self) -> None:
        self.assertEqual(_planning_simulation_location_name_key("Bar-le-Duc"), "bar le duc")
        self.assertEqual(_planning_simulation_location_name_key("  BAR LE DUC  "), "bar le duc")

    def test_planning_simulation_excludes_only_online_solfege(self) -> None:
        self.assertTrue(
            _planning_simulation_is_online_solfege(
                SimpleNamespace(mode=DeliveryMode.ONLINE, code="SOLFEGE_ONLINE", name="Solfège en ligne")
            )
        )
        self.assertFalse(
            _planning_simulation_is_online_solfege(
                SimpleNamespace(mode=DeliveryMode.ONSITE, code="SOLFEGE", name="Solfège en présentiel")
            )
        )
        self.assertFalse(
            _planning_simulation_is_online_solfege(
                SimpleNamespace(mode=DeliveryMode.ONLINE, code="PIANO_ONLINE", name="Piano en ligne")
            )
        )
        self.assertTrue(
            _planning_simulation_is_online_solfege(
                SimpleNamespace(mode=DeliveryMode.ANY, code="SOLFEGE_3", name="Solfège niveau 3"),
                location_name="Online",
            )
        )
        self.assertFalse(
            _planning_simulation_is_online_solfege(
                SimpleNamespace(mode=DeliveryMode.ANY, code="SOLFEGE", name="Solfège en présentiel"),
                location_name="Rue Scheffer",
            )
        )

    def test_planning_simulation_groups_recurrent_orphan_sessions_by_signature(self) -> None:
        signature = "richelieu|solfege|2|18:05|18:35"

        self.assertEqual(
            _planning_simulation_live_slot_key(
                session_id=uuid4(),
                recurrence_group_id=None,
                signature=signature,
            ),
            _planning_simulation_live_slot_key(
                session_id=uuid4(),
                recurrence_group_id=None,
                signature=signature,
            ),
        )

    def test_planning_simulation_selects_least_loaded_live_slot_for_quote(self) -> None:
        slot_entries = {
            "series:full": {
                "capacity_max": 6,
                "_booked_user_ids": {"1", "2", "3", "4", "5", "6"},
                "_approved_quote_ids": set(),
                "_pending_quote_ids": set(),
                "_draft_quote_ids": set(),
            },
            "series:available": {
                "capacity_max": 6,
                "_booked_user_ids": {"1", "2"},
                "_approved_quote_ids": {"quote-1"},
                "_pending_quote_ids": set(),
                "_draft_quote_ids": set(),
            },
        }

        self.assertEqual(
            _planning_simulation_select_live_slot_for_quote(slot_entries, ["series:full", "series:available"]),
            "series:available",
        )

    def test_planning_simulation_rebalances_parallel_slots_even_with_series_key(self) -> None:
        slot_entries = {
            "series::scheffer-tue-17-a": {
                "capacity_max": 6,
                "_booked_user_ids": {"1", "2", "3", "4", "5", "6"},
                "_approved_quote_ids": {"quote-1", "quote-2"},
                "_pending_quote_ids": set(),
                "_draft_quote_ids": set(),
            },
            "series::scheffer-tue-17-b": {
                "capacity_max": 6,
                "_booked_user_ids": {"7", "8"},
                "_approved_quote_ids": set(),
                "_pending_quote_ids": set(),
                "_draft_quote_ids": set(),
            },
        }
        live_slot_keys_by_signature = {
            "scheffer|piano|1|17:00|18:00": {"series::scheffer-tue-17-a", "series::scheffer-tue-17-b"}
        }

        self.assertEqual(
            _planning_simulation_resolve_live_slot_for_quote(
                slot_entries=slot_entries,
                live_slot_keys_by_signature=live_slot_keys_by_signature,
                signature="scheffer|piano|1|17:00|18:00",
                block_series_key="scheffer-tue-17-a",
            ),
            "series::scheffer-tue-17-b",
        )

    def test_planning_simulation_labels_online_quote_slots(self) -> None:
        label = _planning_simulation_quote_location_name(
            {"activity_label": "Cours de solfege - Niveau 1"},
            course_type=SimpleNamespace(mode=DeliveryMode.ONLINE),
        )

        self.assertEqual(label, "En ligne")

    def test_planning_simulation_falls_back_to_unknown_location_label(self) -> None:
        self.assertEqual(_planning_simulation_quote_location_name({}), "Lieu non defini")

    def test_planning_simulation_quote_person_key_prefers_client(self) -> None:
        quote = SimpleNamespace(client_id="client-id", prospect_id="prospect-id")
        prospect = SimpleNamespace(linked_client_id="linked-client-id")

        self.assertEqual(_planning_simulation_quote_person_key(quote, prospect), "client:client-id")

    def test_planning_simulation_quote_person_key_uses_linked_prospect_client(self) -> None:
        quote = SimpleNamespace(client_id=None, prospect_id="prospect-id")
        prospect = SimpleNamespace(linked_client_id="linked-client-id")

        self.assertEqual(_planning_simulation_quote_person_key(quote, prospect), "client:linked-client-id")

    def test_teacher_needs_include_daily_global_and_activity_peaks(self) -> None:
        piano_id = uuid4()
        solfege_id = uuid4()
        slots = [
            self._teacher_need_slot(
                activity_id=piano_id,
                activity_name="Piano collectif",
                weekday=0,
                weekday_label="Lundi",
                start_time="16:00",
                end_time="17:00",
            ),
            self._teacher_need_slot(
                activity_id=piano_id,
                activity_name="Piano collectif",
                weekday=0,
                weekday_label="Lundi",
                start_time="16:30",
                end_time="17:30",
            ),
            self._teacher_need_slot(
                activity_id=solfege_id,
                activity_name="Solfège",
                weekday=0,
                weekday_label="Lundi",
                start_time="17:00",
                end_time="18:00",
            ),
            self._teacher_need_slot(
                activity_id=piano_id,
                activity_name="Piano collectif",
                weekday=1,
                weekday_label="Mardi",
                start_time="16:00",
                end_time="17:00",
            ),
        ]

        needs = _planning_simulation_teacher_needs(slots)  # type: ignore[arg-type]

        self.assertEqual(needs.summary.active_day_count, 2)
        self.assertEqual(needs.summary.slot_count, 4)
        self.assertEqual(needs.summary.teaching_minutes, 240)
        self.assertEqual(needs.summary.peak_concurrent_teachers, 2)
        self.assertEqual(needs.summary.mobilized_teachers, 3)
        self.assertEqual(needs.days[0].weekday_label, "Lundi")
        self.assertEqual(needs.days[0].peak_concurrent_teachers, 2)
        self.assertEqual(needs.days[0].first_start_time, "16:00")
        self.assertEqual(needs.days[0].last_end_time, "18:00")
        self.assertEqual(needs.activities[0].course_type_name, "Piano collectif")
        self.assertEqual(needs.activities[0].slot_count, 3)
        self.assertEqual(needs.activities[0].peak_concurrent_teachers, 2)
        self.assertEqual(needs.days[0].time_buckets[0].start_time, "16:00")
        self.assertEqual(needs.days[0].time_buckets[0].total_teachers, 2)

    def test_teacher_needs_do_not_overlap_adjacent_courses(self) -> None:
        activity_id = uuid4()
        needs = _planning_simulation_teacher_needs(  # type: ignore[arg-type]
            [
                self._teacher_need_slot(
                    activity_id=activity_id,
                    activity_name="Cours particulier",
                    weekday=2,
                    weekday_label="Mercredi",
                    start_time="14:00",
                    end_time="14:30",
                ),
                self._teacher_need_slot(
                    activity_id=activity_id,
                    activity_name="Cours particulier",
                    weekday=2,
                    weekday_label="Mercredi",
                    start_time="14:30",
                    end_time="15:00",
                ),
            ]
        )

        self.assertEqual(needs.summary.peak_concurrent_teachers, 1)
        self.assertEqual(needs.summary.teaching_minutes, 60)
        self.assertEqual(needs.summary.mobilized_teachers, 1)

    def test_teacher_needs_keep_same_activity_on_separate_sites_during_half_day(self) -> None:
        activity_id = uuid4()
        first_location_id = uuid4()
        second_location_id = uuid4()
        needs = _planning_simulation_teacher_needs(  # type: ignore[arg-type]
            [
                self._teacher_need_slot(
                    activity_id=activity_id,
                    activity_name="Piano collectif",
                    weekday=5,
                    weekday_label="Samedi",
                    start_time="09:00",
                    end_time="10:00",
                    location_id=first_location_id,
                    location_name="Site A",
                ),
                self._teacher_need_slot(
                    activity_id=activity_id,
                    activity_name="Piano collectif",
                    weekday=5,
                    weekday_label="Samedi",
                    start_time="10:00",
                    end_time="11:00",
                    location_id=second_location_id,
                    location_name="Site B",
                ),
            ]
        )

        self.assertEqual(needs.summary.peak_concurrent_teachers, 1)
        self.assertEqual(needs.summary.mobilized_teachers, 2)
        self.assertEqual(needs.days[0].mobilized_teachers, 2)
        self.assertEqual(len(needs.days[0].timeline_rows), 2)
        self.assertEqual(
            [bucket.total_teachers for bucket in needs.days[0].time_buckets],
            [1, 1],
        )

    def test_teacher_needs_do_not_overlap_successive_series_at_same_time(self) -> None:
        activity_id = uuid4()
        common = {
            "activity_id": activity_id,
            "activity_name": "Cours collectifs ado/adultes",
            "weekday": 1,
            "weekday_label": "Mardi",
            "start_time": "19:00",
            "end_time": "20:00",
            "location_name": "Rue d'Assas",
        }
        needs = _planning_simulation_teacher_needs(  # type: ignore[arg-type]
            [
                self._teacher_need_slot(
                    **common,
                    occurrence_dates=[date(2026, 9, 1)],
                ),
                self._teacher_need_slot(
                    **common,
                    occurrence_dates=[date(2026, 9, 8), date(2026, 9, 15)],
                ),
            ]
        )

        self.assertEqual(needs.summary.peak_concurrent_teachers, 1)
        self.assertEqual(needs.summary.mobilized_teachers, 1)
        self.assertEqual(needs.days[0].time_buckets[0].total_teachers, 1)
        self.assertEqual(needs.days[0].timeline_rows[0].bucket_teachers, [1])

    def test_teacher_needs_count_series_that_really_overlap(self) -> None:
        activity_id = uuid4()
        overlap_date = date(2026, 9, 8)
        slots = [
            self._teacher_need_slot(
                activity_id=activity_id,
                activity_name="Cours collectifs ado/adultes",
                weekday=1,
                weekday_label="Mardi",
                start_time="19:00",
                end_time="20:00",
                location_name="Rue d'Assas",
                occurrence_dates=[overlap_date],
            )
            for _ in range(2)
        ]

        needs = _planning_simulation_teacher_needs(slots)  # type: ignore[arg-type]

        self.assertEqual(needs.summary.peak_concurrent_teachers, 2)
        self.assertEqual(needs.summary.mobilized_teachers, 2)

    def test_teacher_assignment_warnings_detect_overlap_for_same_placeholder(self) -> None:
        common = {
            "activity_id": uuid4(),
            "activity_name": "Piano collectif",
            "weekday": 2,
            "weekday_label": "Mercredi",
            "location_name": "Rue Scheffer",
            "occurrence_dates": [date(2026, 9, 9)],
            "teacher_assignment_label": "Prof à confirmer 1",
        }
        first = self._teacher_need_slot(
            **common,
            slot_key="first",
            start_time="14:00",
            end_time="15:00",
        )
        second = self._teacher_need_slot(
            **common,
            slot_key="second",
            start_time="14:30",
            end_time="15:30",
        )

        warnings = _planning_simulation_teacher_assignment_warnings([first, second])  # type: ignore[arg-type]

        self.assertEqual(warnings["first"], ["TIME_OVERLAP"])
        self.assertEqual(warnings["second"], ["TIME_OVERLAP"])

    def test_teacher_assignment_warnings_flag_multi_site_half_day_without_false_overlap(self) -> None:
        professor_id = uuid4()
        common = {
            "activity_id": uuid4(),
            "activity_name": "Piano collectif",
            "weekday": 5,
            "weekday_label": "Samedi",
            "occurrence_dates": [date(2026, 9, 12)],
            "teacher_assignment_professor_id": professor_id,
            "teacher_assignment_label": "Camille Martin",
        }
        first = self._teacher_need_slot(
            **common,
            slot_key="assas",
            location_id=uuid4(),
            location_name="Rue d'Assas",
            start_time="09:00",
            end_time="10:00",
        )
        second = self._teacher_need_slot(
            **common,
            slot_key="pompe",
            location_id=uuid4(),
            location_name="Rue de la Pompe",
            start_time="10:00",
            end_time="11:00",
        )

        warnings = _planning_simulation_teacher_assignment_warnings([first, second])  # type: ignore[arg-type]

        self.assertEqual(warnings["assas"], ["MULTI_SITE_HALF_DAY"])
        self.assertEqual(warnings["pompe"], ["MULTI_SITE_HALF_DAY"])

    def test_teacher_assignment_warnings_include_secondary_masterclass_professors(self) -> None:
        shared_professor_id = uuid4()
        common = {
            "activity_id": uuid4(),
            "activity_name": "Masterclass piano",
            "weekday": 6,
            "weekday_label": "Dimanche",
            "location_name": "Rue de Richelieu",
            "occurrence_dates": [date(2026, 10, 4)],
        }
        first = self._teacher_need_slot(
            **common,
            slot_key="masterclass-first",
            start_time="14:00",
            end_time="16:00",
        )
        second = self._teacher_need_slot(
            **common,
            slot_key="masterclass-second",
            start_time="15:00",
            end_time="17:00",
        )
        first.teacher_assignment_professor_ids = [uuid4(), shared_professor_id]
        first.teacher_assignment_labels = ["Premier professeur", "Professeur partagé"]
        second.teacher_assignment_professor_ids = [uuid4(), uuid4(), shared_professor_id]
        second.teacher_assignment_labels = ["Autre professeur", "Troisième professeur", "Professeur partagé"]

        warnings = _planning_simulation_teacher_assignment_warnings([first, second])  # type: ignore[arg-type]

        self.assertEqual(warnings["masterclass-first"], ["TIME_OVERLAP"])
        self.assertEqual(warnings["masterclass-second"], ["TIME_OVERLAP"])

    def test_teacher_assignment_update_resolves_professor_label(self) -> None:
        professor_id = uuid4()
        current_user_id = uuid4()
        professor = SimpleNamespace(
            id=professor_id,
            first_name="Camille",
            last_name="Martin",
            active=True,
        )
        db = _AssignmentSession([professor, None])

        result = update_planning_simulation_teacher_assignment(
            AdminPlanningSimulationTeacherAssignmentUpdateRequest(
                school_year_label="2026-2027",
                slot_key="live:test-slot",
                professor_id=professor_id,
                teacher_label="Ignored placeholder",
                status="CONFIRMED",
            ),
            db,  # type: ignore[arg-type]
            SimpleNamespace(id=current_user_id),  # type: ignore[arg-type]
        )

        self.assertEqual(len(db.added), 1)
        assignment = db.added[0]
        self.assertIsInstance(assignment, PlanningSimulationTeacherAssignment)
        self.assertEqual(assignment.professor_id, professor_id)  # type: ignore[attr-defined]
        self.assertEqual(assignment.teacher_label, "Camille Martin")  # type: ignore[attr-defined]
        self.assertEqual(assignment.status, "CONFIRMED")  # type: ignore[attr-defined]
        self.assertEqual(result.teacher_label, "Camille Martin")
        self.assertEqual(db.commits, 1)

    def test_teacher_assignment_update_rejects_inactive_professor(self) -> None:
        professor_id = uuid4()
        db = _AssignmentSession([
            SimpleNamespace(
                id=professor_id,
                first_name="Ancien",
                last_name="Professeur",
                active=False,
            ),
        ])

        with self.assertRaises(HTTPException) as raised:
            update_planning_simulation_teacher_assignment(
                AdminPlanningSimulationTeacherAssignmentUpdateRequest(
                    school_year_label="2026-2027",
                    slot_key="live:test-slot",
                    professor_id=professor_id,
                ),
                db,  # type: ignore[arg-type]
                SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail, "Professor is inactive")
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 0)

    def test_teacher_assignment_update_clears_existing_assignment(self) -> None:
        assignment = PlanningSimulationTeacherAssignment(
            id=uuid4(),
            school_year_label="2026-2027",
            slot_key="live:test-slot",
            teacher_label="Prof à confirmer 1",
            status="PREVISIONAL",
        )
        db = _AssignmentSession([assignment])

        result = update_planning_simulation_teacher_assignment(
            AdminPlanningSimulationTeacherAssignmentUpdateRequest(
                school_year_label="2026-2027",
                slot_key="live:test-slot",
            ),
            db,  # type: ignore[arg-type]
            SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
        )

        self.assertEqual(db.deleted, [assignment])
        self.assertTrue(result.deleted)
        self.assertEqual(db.commits, 1)


if __name__ == "__main__":
    unittest.main()
