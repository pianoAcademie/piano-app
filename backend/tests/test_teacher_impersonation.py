from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.impersonation import _teacher_impersonation_destination


def test_teacher_view_always_opens_teacher_portal_for_manager() -> None:
    assert _teacher_impersonation_destination(
        "teacher",
        has_teacher_access=True,
        has_manager_access=True,
    ) == ("teacher", "/prof")


def test_teacher_view_is_rejected_for_non_teacher_collaborator() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _teacher_impersonation_destination(
            "teacher",
            has_teacher_access=False,
            has_manager_access=True,
        )

    assert exc_info.value.status_code == 403


def test_manager_view_opens_backoffice_when_allowed() -> None:
    assert _teacher_impersonation_destination(
        "manager",
        has_teacher_access=False,
        has_manager_access=True,
    ) == ("manager", "/admin")


def test_manager_view_is_rejected_without_manager_permissions() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _teacher_impersonation_destination(
            "manager",
            has_teacher_access=True,
            has_manager_access=False,
        )

    assert exc_info.value.status_code == 403
