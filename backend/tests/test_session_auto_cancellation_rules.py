from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_ADMIN,
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_PARTICIPANT,
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_TEACHER,
    PREDEFINED_TEMPLATE_BY_CODE,
)
from app.services.session_automation import _effective_auto_cancel_threshold


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
    slot = SimpleNamespace(
        auto_cancel_rule_enabled_override=True,
        auto_cancel_if_booked_less_than_override=4,
        course_type_id="activity-id",
    )

    assert _effective_auto_cancel_threshold(db, session_obj=slot) == 4
    db.scalar.assert_not_called()


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

