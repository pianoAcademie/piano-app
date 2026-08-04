from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.api.routes.admin_clients import _check_deposit_transaction_ids_for_location


def test_bar_le_duc_scope_keeps_check_for_explicit_bld_student() -> None:
    location_id = uuid4()
    student_id = uuid4()
    transaction = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        student_user_id=student_id,
    )
    db = SimpleNamespace(
        scalar=MagicMock(return_value=SimpleNamespace(id=location_id, code="BAR_LE_DUC")),
        scalars=MagicMock(
            side_effect=[
                SimpleNamespace(all=lambda: [student_id]),
                SimpleNamespace(all=lambda: []),
            ]
        ),
    )

    allowed = _check_deposit_transaction_ids_for_location(
        db,
        rows=[transaction],
        location_id=location_id,
    )

    assert allowed == {transaction.id}


def test_bar_le_duc_scope_hides_check_without_bld_student_or_booking() -> None:
    location_id = uuid4()
    transaction = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        student_user_id=uuid4(),
    )
    db = SimpleNamespace(
        scalar=MagicMock(return_value=SimpleNamespace(id=location_id, code="BAR_LE_DUC")),
        scalars=MagicMock(
            side_effect=[
                SimpleNamespace(all=lambda: []),
                SimpleNamespace(all=lambda: []),
            ]
        ),
    )

    allowed = _check_deposit_transaction_ids_for_location(
        db,
        rows=[transaction],
        location_id=location_id,
    )

    assert allowed == set()
