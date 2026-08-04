from types import SimpleNamespace
from uuid import uuid4

from app.services.intake_local_confirmation import (
    LOCAL_CONFIRMATION_CONFIRMED,
    LOCAL_CONFIRMATION_PENDING,
    ensure_local_confirmation_assignment,
    is_bar_le_duc,
)


class _FakeDb:
    def __init__(self, professor: object) -> None:
        self.professor = professor
        self.added: list[object] = []

    def scalar(self, _statement: object) -> object:
        return self.professor

    def add(self, value: object) -> None:
        self.added.append(value)


def _intake(status: str = "NOT_REQUIRED") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        detected_location="Bar-le-Duc",
        local_confirmation_status=status,
        local_confirmation_requested_at=None,
        local_confirmation_assignee_professor_id=None,
        local_confirmation_assignee_name=None,
    )


def test_bar_le_duc_location_matching_accepts_code_and_display_name() -> None:
    assert is_bar_le_duc("BAR_LE_DUC")
    assert is_bar_le_duc("École à Bar-le-Duc")
    assert not is_bar_le_duc("Rue de Richelieu")


def test_bld_intake_is_assigned_and_marked_pending() -> None:
    professor = SimpleNamespace(
        id=uuid4(),
        first_name="Estela",
        last_name="Oliviero",
        email="estela.oliviero@piano-academie.com",
        active=True,
    )
    intake = _intake()
    db = _FakeDb(professor)
    config = SimpleNamespace(
        location_code="BAR_LE_DUC",
        configuration_json={"local_confirmation_professor_email": professor.email},
    )

    result = ensure_local_confirmation_assignment(db, intake=intake, config=config)

    assert result is professor
    assert intake.local_confirmation_status == LOCAL_CONFIRMATION_PENDING
    assert intake.local_confirmation_assignee_professor_id == professor.id
    assert intake.local_confirmation_assignee_name == "Estela Oliviero"
    assert intake.local_confirmation_requested_at is not None
    assert db.added == [intake]


def test_reingestion_does_not_reopen_a_confirmed_intake() -> None:
    professor = SimpleNamespace(
        id=uuid4(),
        first_name="Estela",
        last_name="Oliviero",
        email="estela.oliviero@piano-academie.com",
        active=True,
    )
    intake = _intake(LOCAL_CONFIRMATION_CONFIRMED)
    db = _FakeDb(professor)

    ensure_local_confirmation_assignment(
        db,
        intake=intake,
        config=SimpleNamespace(location_code="BAR_LE_DUC", configuration_json={}),
    )

    assert intake.local_confirmation_status == LOCAL_CONFIRMATION_CONFIRMED
    assert intake.local_confirmation_requested_at is None
