"""add simulation planning foundation

Revision ID: 20260328_0087
Revises: 20260327_0086
Create Date: 2026-03-28 11:10:00.000000
"""

from __future__ import annotations

from datetime import time
from typing import Any, Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260328_0087"
down_revision: Union[str, None] = "20260327_0086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _infer_usage_family(name: str, code: str, mode: str) -> tuple[str, bool]:
    haystack = f"{name} {code}".strip().lower()
    if str(mode or "").strip().upper() == "ONLINE":
        return "ONLINE", False
    if "domicile" in haystack:
        return "HOME", False
    if "masterclass" in haystack or "concours" in haystack:
        return "MASTERCLASS", True
    if "eveil" in haystack:
        return "EARLY_MUSIC", True
    if "adult" in haystack or "adulte" in haystack or "ado" in haystack:
        return "COLLECTIVE_ADULT", True
    if "particul" in haystack or "individ" in haystack or "priv" in haystack:
        return "PRIVATE_LESSON", True
    if "collectif" in haystack or "initiation" in haystack:
        return "COLLECTIVE_CHILD", True
    return "OTHER", True


def _time_with_duration(start_time: time, duration_minutes: int) -> str:
    hours = duration_minutes // 60
    minutes = duration_minutes % 60
    end_hour = start_time.hour + hours + ((start_time.minute + minutes) // 60)
    end_minute = (start_time.minute + minutes) % 60
    end_hour = end_hour % 24
    return f"{end_hour:02d}:{end_minute:02d}"


def _seed_activity_profiles(bind: sa.engine.Connection) -> None:
    course_types = bind.execute(sa.text("SELECT id, code, name, mode FROM course_types")).mappings().all()
    existing_ids = {
        row["course_type_id"]
        for row in bind.execute(sa.text("SELECT course_type_id FROM simulation_activity_profiles")).mappings().all()
    }
    for row in course_types:
        if row["id"] in existing_ids:
            continue
        usage_family, consumes_physical = _infer_usage_family(
            str(row.get("name") or ""),
            str(row.get("code") or ""),
            str(row.get("mode") or ""),
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO simulation_activity_profiles (
                    id, course_type_id, usage_family, consumes_physical_capacity, active, created_at, updated_at
                ) VALUES (
                    :id, :course_type_id, :usage_family, :consumes_physical_capacity, true, now(), now()
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "course_type_id": row["id"],
                "usage_family": usage_family,
                "consumes_physical_capacity": consumes_physical,
            },
        )


def _insert_rule_set(
    bind: sa.engine.Connection,
    *,
    location_id: Any,
    name: str,
    scenarios: list[dict[str, Any]],
) -> None:
    rule_set_id = uuid.uuid4()
    window_id = uuid.uuid4()
    bind.execute(
        sa.text(
            """
            INSERT INTO simulation_capacity_rule_sets (
                id, location_id, name, active, created_at, updated_at
            ) VALUES (
                :id, :location_id, :name, true, now(), now()
            )
            """
        ),
        {"id": rule_set_id, "location_id": location_id, "name": name},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO simulation_capacity_windows (
                id, rule_set_id, weekdays, start_time, end_time, sort_order, active, created_at, updated_at
            ) VALUES (
                :id, :rule_set_id, CAST(:weekdays AS jsonb), '00:00', '23:59', 0, true, now(), now()
            )
            """
        ),
        {"id": window_id, "rule_set_id": rule_set_id, "weekdays": "[0,1,2,3,4,5,6]"},
    )
    for scenario_index, scenario in enumerate(scenarios):
        scenario_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO simulation_capacity_scenarios (
                    id, window_id, code, name, priority, active, created_at, updated_at
                ) VALUES (
                    :id, :window_id, :code, :name, :priority, true, now(), now()
                )
                """
            ),
            {
                "id": scenario_id,
                "window_id": window_id,
                "code": scenario["code"],
                "name": scenario["name"],
                "priority": scenario_index,
            },
        )
        for line in scenario["lines"]:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO simulation_capacity_scenario_lines (
                        id, scenario_id, usage_family, max_concurrent_slots, max_total_seats, notes, created_at, updated_at
                    ) VALUES (
                        :id, :scenario_id, :usage_family, :max_concurrent_slots, :max_total_seats, :notes, now(), now()
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "scenario_id": scenario_id,
                    "usage_family": line["usage_family"],
                    "max_concurrent_slots": line.get("max_concurrent_slots"),
                    "max_total_seats": line.get("max_total_seats"),
                    "notes": line.get("notes"),
                },
            )


def _seed_default_rule_sets(bind: sa.engine.Connection) -> None:
    locations = bind.execute(sa.text("SELECT id, code, name FROM locations")).mappings().all()
    by_key: dict[str, Any] = {}
    for row in locations:
        haystack = f"{row.get('code') or ''} {row.get('name') or ''}".strip().lower()
        if "scheffer" in haystack:
            by_key["scheffer"] = row["id"]
        if "pompe" in haystack:
            by_key["pompe"] = row["id"]
        if "assas" in haystack:
            by_key["assas"] = row["id"]
        if "richelieu" in haystack:
            by_key["richelieu"] = row["id"]

    existing = {
        row["location_id"]
        for row in bind.execute(sa.text("SELECT location_id FROM simulation_capacity_rule_sets")).mappings().all()
    }

    if by_key.get("scheffer") and by_key["scheffer"] not in existing:
        _insert_rule_set(
            bind,
            location_id=by_key["scheffer"],
            name="Regles locales - Scheffer",
            scenarios=[
                {
                    "code": "CHILD_PLUS_PRIVATE",
                    "name": "2 collectifs enfants + 1 particulier",
                    "lines": [
                        {"usage_family": "COLLECTIVE_CHILD", "max_concurrent_slots": 2},
                        {"usage_family": "PRIVATE_LESSON", "max_concurrent_slots": 1},
                    ],
                },
                {
                    "code": "ADULT_GROUP",
                    "name": "1 collectif ado/adulte de 10 places",
                    "lines": [
                        {"usage_family": "COLLECTIVE_ADULT", "max_concurrent_slots": 1, "max_total_seats": 10},
                    ],
                },
                {
                    "code": "MASTERCLASS",
                    "name": "1 masterclass de 12 places",
                    "lines": [
                        {"usage_family": "MASTERCLASS", "max_concurrent_slots": 1, "max_total_seats": 12},
                    ],
                },
            ],
        )

    if by_key.get("pompe") and by_key["pompe"] not in existing:
        _insert_rule_set(
            bind,
            location_id=by_key["pompe"],
            name="Regles locales - Pompe",
            scenarios=[
                {
                    "code": "THREE_CHILD_GROUPS",
                    "name": "3 collectifs enfants",
                    "lines": [
                        {"usage_family": "COLLECTIVE_CHILD", "max_concurrent_slots": 3},
                    ],
                },
                {
                    "code": "CHILD_ADULT_EARLY",
                    "name": "1 collectif enfant + 1 collectif ado/adulte + 1 eveil",
                    "lines": [
                        {"usage_family": "COLLECTIVE_CHILD", "max_concurrent_slots": 1, "max_total_seats": 6},
                        {"usage_family": "COLLECTIVE_ADULT", "max_concurrent_slots": 1, "max_total_seats": 10},
                        {"usage_family": "EARLY_MUSIC", "max_concurrent_slots": 1},
                    ],
                },
            ],
        )

    if by_key.get("assas") and by_key["assas"] not in existing:
        _insert_rule_set(
            bind,
            location_id=by_key["assas"],
            name="Regles locales - Assas",
            scenarios=[
                {
                    "code": "CHILD_PLUS_EARLY",
                    "name": "1 collectif enfant de 4 places + 1 eveil",
                    "lines": [
                        {"usage_family": "COLLECTIVE_CHILD", "max_concurrent_slots": 1, "max_total_seats": 4},
                        {"usage_family": "EARLY_MUSIC", "max_concurrent_slots": 1},
                    ],
                },
                {
                    "code": "ADULT_GROUP",
                    "name": "1 collectif ado/adulte de 8 places",
                    "lines": [
                        {"usage_family": "COLLECTIVE_ADULT", "max_concurrent_slots": 1, "max_total_seats": 8},
                    ],
                },
            ],
        )

    if by_key.get("richelieu") and by_key["richelieu"] not in existing:
        _insert_rule_set(
            bind,
            location_id=by_key["richelieu"],
            name="Regles locales - Richelieu",
            scenarios=[
                {
                    "code": "CHILD_PLUS_PRIVATE",
                    "name": "2 collectifs enfants + 1 particulier",
                    "lines": [
                        {"usage_family": "COLLECTIVE_CHILD", "max_concurrent_slots": 2},
                        {"usage_family": "PRIVATE_LESSON", "max_concurrent_slots": 1},
                    ],
                },
                {
                    "code": "ADULT_GROUP",
                    "name": "1 collectif ado/adulte de 10 places",
                    "lines": [
                        {"usage_family": "COLLECTIVE_ADULT", "max_concurrent_slots": 1, "max_total_seats": 10},
                    ],
                },
                {
                    "code": "MASTERCLASS",
                    "name": "1 masterclass de 12 places",
                    "lines": [
                        {"usage_family": "MASTERCLASS", "max_concurrent_slots": 1, "max_total_seats": 12},
                    ],
                },
            ],
        )


def _seed_evening_templates(bind: sa.engine.Connection) -> None:
    locations = bind.execute(sa.text("SELECT id, code, name FROM locations")).mappings().all()
    course_types = bind.execute(sa.text("SELECT id, code, name, duration_minutes FROM course_types WHERE active = true")).mappings().all()
    by_key: dict[str, Any] = {}
    for row in locations:
        haystack = f"{row.get('code') or ''} {row.get('name') or ''}".strip().lower()
        if "scheffer" in haystack:
            by_key["scheffer"] = row
        if "pompe" in haystack:
            by_key["pompe"] = row
        if "richelieu" in haystack:
            by_key["richelieu"] = row

    adult_collective = None
    for row in course_types:
        haystack = f"{row.get('code') or ''} {row.get('name') or ''}".strip().lower()
        if ("ado" in haystack or "adult" in haystack or "adulte" in haystack) and ("collectif" in haystack or "groupe" in haystack):
            adult_collective = row
            break
    if adult_collective is None:
        return

    existing_scopes = {
        (row["location_id"], row["course_type_id"], row["name"])
        for row in bind.execute(sa.text("SELECT location_id, course_type_id, name FROM simulation_templates")).mappings().all()
    }
    duration = int(adult_collective.get("duration_minutes") or 60)
    end_time = _time_with_duration(time(hour=19, minute=0), duration)

    for key in ("scheffer", "richelieu", "pompe"):
        location = by_key.get(key)
        if location is None:
            continue
        name = f"Collectif ado/adulte soir - {location['name']}"
        scope = (location["id"], adult_collective["id"], name)
        if scope in existing_scopes:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO simulation_templates (
                    id, name, location_id, course_type_id, weekdays, start_time, end_time,
                    recurrence_frequency, effective_from, effective_to, capacity_override, active, created_at, updated_at
                ) VALUES (
                    :id, :name, :location_id, :course_type_id, CAST(:weekdays AS jsonb), '19:00', :end_time,
                    'weekly', NULL, NULL, 10, true, now(), now()
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "name": name,
                "location_id": location["id"],
                "course_type_id": adult_collective["id"],
                "weekdays": "[0,1,2,3,4]",
                "end_time": end_time,
            },
        )


def upgrade() -> None:
    op.create_table(
        "simulation_activity_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_family", sa.String(length=40), nullable=False),
        sa.Column("consumes_physical_capacity", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_capacity_override", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("course_type_id", name="uq_simulation_activity_profiles_course_type"),
        sa.CheckConstraint(
            "default_capacity_override IS NULL OR default_capacity_override >= 0",
            name="ck_simulation_activity_profiles_capacity_non_negative",
        ),
    )

    op.create_table(
        "simulation_capacity_rule_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "simulation_capacity_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "rule_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("simulation_capacity_rule_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weekdays", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("sort_order >= 0", name="ck_simulation_capacity_windows_sort_order_non_negative"),
    )

    op.create_table(
        "simulation_capacity_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "window_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("simulation_capacity_windows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("window_id", "code", name="uq_simulation_capacity_scenarios_window_code"),
        sa.CheckConstraint("priority >= 0", name="ck_simulation_capacity_scenarios_priority_non_negative"),
    )

    op.create_table(
        "simulation_capacity_scenario_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("simulation_capacity_scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("usage_family", sa.String(length=40), nullable=False),
        sa.Column("max_concurrent_slots", sa.Integer(), nullable=True),
        sa.Column("max_total_seats", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("scenario_id", "usage_family", name="uq_simulation_capacity_scenario_lines_scenario_usage"),
        sa.CheckConstraint(
            "(max_concurrent_slots IS NOT NULL) OR (max_total_seats IS NOT NULL)",
            name="ck_simulation_capacity_scenario_lines_has_limit",
        ),
        sa.CheckConstraint(
            "max_concurrent_slots IS NULL OR max_concurrent_slots >= 0",
            name="ck_simulation_capacity_scenario_lines_concurrent_non_negative",
        ),
        sa.CheckConstraint(
            "max_total_seats IS NULL OR max_total_seats >= 0",
            name="ck_simulation_capacity_scenario_lines_seats_non_negative",
        ),
    )

    op.create_table(
        "simulation_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("professors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("weekdays", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("recurrence_frequency", sa.String(length=20), nullable=False, server_default=sa.text("'weekly'")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("capacity_override", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("capacity_override IS NULL OR capacity_override >= 0", name="ck_simulation_templates_capacity_non_negative"),
    )

    op.create_table(
        "simulation_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("simulation_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("professors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("starts_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PROJECTED'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("template_id", "starts_at_utc", name="uq_simulation_slots_template_start"),
        sa.CheckConstraint("capacity >= 0", name="ck_simulation_slots_capacity_non_negative"),
        sa.CheckConstraint("ends_at_utc > starts_at_utc", name="ck_simulation_slots_time_range"),
    )

    op.create_table(
        "planned_needs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default=sa.text("'QUOTE'")),
        sa.Column("source_quote_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("quote_status_snapshot", sa.String(length=40), nullable=False, server_default=sa.text("'created'")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("starts_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seat_demand", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("usage_family_snapshot", sa.String(length=40), nullable=False, server_default=sa.text("'OTHER'")),
        sa.Column("consumes_physical_capacity", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allocation_status", sa.String(length=20), nullable=False, server_default=sa.text("'UNALLOCATED'")),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_projected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_type", "source_key", name="uq_planned_needs_source"),
        sa.CheckConstraint("seat_demand > 0", name="ck_planned_needs_seat_demand_positive"),
        sa.CheckConstraint("ends_at_utc > starts_at_utc", name="ck_planned_needs_time_range"),
    )

    op.create_table(
        "simulation_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("planned_need_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("planned_needs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("simulation_slot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("simulation_slots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allocated_seats", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ALLOCATED'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("planned_need_id", name="uq_simulation_allocations_planned_need"),
        sa.CheckConstraint("allocated_seats > 0", name="ck_simulation_allocations_allocated_seats_positive"),
    )

    op.create_table(
        "simulation_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_simulation_rule_sets_location_active", "simulation_capacity_rule_sets", ["location_id", "active"])
    op.create_index("ix_simulation_windows_rule_set", "simulation_capacity_windows", ["rule_set_id"])
    op.create_index("ix_simulation_scenarios_window", "simulation_capacity_scenarios", ["window_id"])
    op.create_index("ix_simulation_lines_scenario", "simulation_capacity_scenario_lines", ["scenario_id"])
    op.create_index("ix_simulation_templates_location_active", "simulation_templates", ["location_id", "active"])
    op.create_index("ix_simulation_slots_location_start", "simulation_slots", ["location_id", "starts_at_utc"])
    op.create_index("ix_planned_needs_active_start", "planned_needs", ["active", "starts_at_utc"])
    op.create_index("ix_planned_needs_quote", "planned_needs", ["source_quote_id"])
    op.create_index("ix_planned_needs_location", "planned_needs", ["location_id", "starts_at_utc"])
    op.create_index("ix_simulation_allocations_slot", "simulation_allocations", ["simulation_slot_id"])
    op.create_index("ix_simulation_audit_entity", "simulation_audit_events", ["entity_type", "entity_id"])

    bind = op.get_bind()
    _seed_activity_profiles(bind)
    _seed_default_rule_sets(bind)
    _seed_evening_templates(bind)


def downgrade() -> None:
    op.drop_index("ix_simulation_audit_entity", table_name="simulation_audit_events")
    op.drop_index("ix_simulation_allocations_slot", table_name="simulation_allocations")
    op.drop_index("ix_planned_needs_location", table_name="planned_needs")
    op.drop_index("ix_planned_needs_quote", table_name="planned_needs")
    op.drop_index("ix_planned_needs_active_start", table_name="planned_needs")
    op.drop_index("ix_simulation_slots_location_start", table_name="simulation_slots")
    op.drop_index("ix_simulation_templates_location_active", table_name="simulation_templates")
    op.drop_index("ix_simulation_lines_scenario", table_name="simulation_capacity_scenario_lines")
    op.drop_index("ix_simulation_scenarios_window", table_name="simulation_capacity_scenarios")
    op.drop_index("ix_simulation_windows_rule_set", table_name="simulation_capacity_windows")
    op.drop_index("ix_simulation_rule_sets_location_active", table_name="simulation_capacity_rule_sets")

    op.drop_table("simulation_audit_events")
    op.drop_table("simulation_allocations")
    op.drop_table("planned_needs")
    op.drop_table("simulation_slots")
    op.drop_table("simulation_templates")
    op.drop_table("simulation_capacity_scenario_lines")
    op.drop_table("simulation_capacity_scenarios")
    op.drop_table("simulation_capacity_windows")
    op.drop_table("simulation_capacity_rule_sets")
    op.drop_table("simulation_activity_profiles")
