from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_ADMIN,
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_PARTICIPANT,
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_TEACHER,
    PREDEFINED_TEMPLATE_BY_CODE,
)
from app.services.session_automation import (
    _effective_auto_cancel_threshold,
    _has_booked_overlapping_rehearsal_studio,
    _is_protected_richelieu_collective,
)


def test_slot_rule_can_be_explicitly_disabled() -> None:
    db = MagicMock()
    slot = SimpleNamespace(
        auto_cancel_rule_enabled_override=False,
        auto_cancel_if_booked_less_than_override=3,
        course_type_id="activity-id",
    )

    assert _effective_auto_cancel_threshold(db, session_obj=slot) is None
    db.scalar.assert_not_called()


def test_slot_custom_rule_takes_priority_over_activity() -> None:
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(
        code="ADULT_GROUP",
        name="Cours collectifs ado/adultes",
        lesson_format="GROUP",
    )
    slot = SimpleNamespace(
        auto_cancel_rule_enabled_override=True,
        auto_cancel_if_booked_less_than_override=4,
        course_type_id="activity-id",
    )

    assert _effective_auto_cancel_threshold(db, session_obj=slot) == 4


def test_protected_core_lesson_cannot_be_auto_cancelled_even_with_slot_override() -> None:
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(
        code="PIANO_GROUP_ONSITE_1H",
        name="Cours de piano collectif en presentiel (1h)",
        lesson_format="GROUP",
    )
    slot = SimpleNamespace(
        auto_cancel_rule_enabled_override=True,
        auto_cancel_if_booked_less_than_override=4,
        course_type_id="activity-id",
    )

    assert _effective_auto_cancel_threshold(db, session_obj=slot) is None


def test_slot_inherits_enabled_activity_rule() -> None:
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(
        auto_cancel_rule_enabled=True,
        auto_cancel_if_booked_less_than_override=3,
    )
    slot = SimpleNamespace(
        auto_cancel_rule_enabled_override=None,
        auto_cancel_if_booked_less_than_override=None,
        course_type_id="activity-id",
    )

    assert _effective_auto_cancel_threshold(db, session_obj=slot) == 3


def test_slot_inherits_disabled_activity_by_default() -> None:
    db = MagicMock()
    db.scalar.return_value = SimpleNamespace(
        auto_cancel_rule_enabled=False,
        auto_cancel_if_booked_less_than_override=3,
    )
    slot = SimpleNamespace(
        auto_cancel_rule_enabled_override=None,
        auto_cancel_if_booked_less_than_override=None,
        course_type_id="activity-id",
    )

    assert _effective_auto_cancel_threshold(db, session_obj=slot) is None


def test_auto_cancellation_email_templates_are_available_in_admin_catalogue() -> None:
    for code in (
        PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_PARTICIPANT,
        PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_TEACHER,
        PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_ADMIN,
    ):
        template = PREDEFINED_TEMPLATE_BY_CODE[code]
        assert template.channel == "EMAIL"
        assert template.body_format == "HTML"


def _richelieu_collective(*, hour_utc: int = 17):
    return SimpleNamespace(
        id=uuid4(),
        course_type_id=uuid4(),
        location_id=uuid4(),
        title="Cours collectif",
        start_at_utc=datetime(2026, 8, 19, hour_utc, tzinfo=timezone.utc),
        end_at_utc=datetime(2026, 8, 19, hour_utc + 1, tzinfo=timezone.utc),
    )


def test_richelieu_19h_collective_is_protected_candidate() -> None:
    slot = _richelieu_collective()
    course_type = SimpleNamespace(name="Cours collectifs ado/adultes")
    location = SimpleNamespace(code="RICHELIEU", timezone="Europe/Paris")

    assert _is_protected_richelieu_collective(
        session_obj=slot,
        course_type=course_type,
        location=location,
    )


def test_richelieu_collective_at_another_hour_is_not_protected() -> None:
    slot = _richelieu_collective(hour_utc=16)
    course_type = SimpleNamespace(name="Cours collectifs ado/adultes")
    location = SimpleNamespace(code="RICHELIEU", timezone="Europe/Paris")

    assert not _is_protected_richelieu_collective(
        session_obj=slot,
        course_type=course_type,
        location=location,
    )


def test_richelieu_children_collective_at_19h_is_not_protected() -> None:
    slot = _richelieu_collective()
    course_type = SimpleNamespace(name="Cours de piano collectif enfants en présentiel (1h)")
    location = SimpleNamespace(code="RICHELIEU", timezone="Europe/Paris")

    assert not _is_protected_richelieu_collective(
        session_obj=slot,
        course_type=course_type,
        location=location,
    )


def test_richelieu_19h_collective_is_exempt_when_a_studio_is_booked() -> None:
    slot = _richelieu_collective()
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (
        SimpleNamespace(name="Cours collectifs ado/adultes"),
        SimpleNamespace(code="RICHELIEU", timezone="Europe/Paris"),
    )
    db.scalar.return_value = 1

    assert _has_booked_overlapping_rehearsal_studio(db, session_obj=slot)


def test_richelieu_19h_collective_is_not_exempt_without_a_booked_studio() -> None:
    slot = _richelieu_collective()
    db = MagicMock()
    db.execute.return_value.one_or_none.return_value = (
        SimpleNamespace(name="Cours collectifs ado/adultes"),
        SimpleNamespace(code="RICHELIEU", timezone="Europe/Paris"),
    )
    db.scalar.return_value = 0

    assert not _has_booked_overlapping_rehearsal_studio(db, session_obj=slot)
