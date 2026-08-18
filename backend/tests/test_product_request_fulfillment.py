from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.admin_catalog import create_admin_catalog_request
from app.models.product_catalog import ProductReorderStatus, ProductRequestStatus
from app.schemas.catalog_admin import AdminCatalogRequestCreateRequest
from app.services.product_catalog import (
    _assign_request_to_next_session,
    find_next_in_person_delivery_session,
    prepare_product_request_fulfillment,
)


NOW = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)


def _request(*, location_id=None, should_bill=False):
    return SimpleNamespace(
        id=uuid4(),
        student_user_id=uuid4(),
        product_id=uuid4(),
        location_id=location_id or uuid4(),
        quantity=1,
        should_bill=should_bill,
        status=ProductRequestStatus.PROCESSING,
        stock_transfer_id=None,
        stock_reserved_quantity=0,
        ready_at=None,
        assigned_session_id=None,
        assigned_professor_id=None,
        updated_at=NOW,
    )


def _product(request_row):
    return SimpleNamespace(
        id=request_row.product_id,
        is_virtual=False,
        primary_location_id=uuid4(),
        reorder_status=ProductReorderStatus.NORMAL,
        reorder_status_updated_at=NOW,
        updated_at=NOW,
    )


def _stock(request_row, *, real=0, estimated=0):
    return SimpleNamespace(
        product_id=request_row.product_id,
        location_id=request_row.location_id,
        real_quantity=real,
        estimated_quantity=estimated,
        estimated_updated_at=NOW,
        updated_at=NOW,
    )


def test_request_becomes_deliverable_only_when_physical_stock_is_available() -> None:
    request_row = _request()
    product = _product(request_row)
    stock = _stock(request_row, real=1, estimated=1)
    db = SimpleNamespace(scalar=MagicMock(return_value=product), add=MagicMock())

    with (
        patch("app.services.product_catalog._assign_request_to_next_session"),
        patch("app.services.product_catalog.get_or_create_stock_row", return_value=stock),
        patch("app.services.product_catalog._available_physical_quantity", return_value=1),
        patch("app.services.product_catalog.create_stock_transfer") as create_transfer,
    ):
        prepare_product_request_fulfillment(
            db,
            request_row=request_row,
            actor_user_id=uuid4(),
            now=NOW,
            reserve_estimated_demand=True,
        )

    assert request_row.status == ProductRequestStatus.TO_DELIVER
    assert request_row.stock_reserved_quantity == 1
    assert request_row.ready_at == NOW
    assert stock.estimated_quantity == 0
    create_transfer.assert_not_called()


def test_missing_local_stock_creates_transfer_and_keeps_request_hidden_from_teacher() -> None:
    request_row = _request()
    product = _product(request_row)
    target_stock = _stock(request_row, real=0, estimated=0)
    source_stock = SimpleNamespace(location_id=uuid4())
    transfer = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(scalar=MagicMock(return_value=product), add=MagicMock())

    with (
        patch("app.services.product_catalog._assign_request_to_next_session"),
        patch("app.services.product_catalog.get_or_create_stock_row", return_value=target_stock),
        patch("app.services.product_catalog._available_physical_quantity", return_value=0),
        patch("app.services.product_catalog._find_stock_transfer_source", return_value=source_stock),
        patch("app.services.product_catalog.create_stock_transfer", return_value=transfer) as create_transfer,
        patch("app.services.product_catalog.recalculate_product_global_stock"),
    ):
        prepare_product_request_fulfillment(
            db,
            request_row=request_row,
            actor_user_id=uuid4(),
            now=NOW,
            reserve_estimated_demand=True,
        )

    assert request_row.status == ProductRequestStatus.WAITING_STOCK
    assert request_row.stock_reserved_quantity == 0
    assert request_row.ready_at is None
    assert request_row.stock_transfer_id == transfer.id
    create_transfer.assert_called_once()


def test_missing_stock_everywhere_creates_reorder_need() -> None:
    request_row = _request()
    product = _product(request_row)
    target_stock = _stock(request_row, real=0, estimated=0)
    db = SimpleNamespace(scalar=MagicMock(return_value=product), add=MagicMock())

    with (
        patch("app.services.product_catalog._assign_request_to_next_session"),
        patch("app.services.product_catalog.get_or_create_stock_row", return_value=target_stock),
        patch("app.services.product_catalog._available_physical_quantity", return_value=0),
        patch("app.services.product_catalog._find_stock_transfer_source", return_value=None),
        patch("app.services.product_catalog.create_stock_transfer") as create_transfer,
        patch("app.services.product_catalog.recalculate_product_global_stock"),
    ):
        prepare_product_request_fulfillment(
            db,
            request_row=request_row,
            actor_user_id=uuid4(),
            now=NOW,
            reserve_estimated_demand=True,
        )

    assert request_row.status == ProductRequestStatus.WAITING_STOCK
    assert product.reorder_status == ProductReorderStatus.TO_ORDER
    create_transfer.assert_not_called()


def test_course_change_moves_demand_and_uses_substitute_teacher() -> None:
    old_location_id = uuid4()
    new_location_id = uuid4()
    substitute_id = uuid4()
    request_row = _request(location_id=old_location_id)
    request_row.assigned_session_id = uuid4()
    request_row.stock_reserved_quantity = 1
    session_obj = SimpleNamespace(
        id=uuid4(),
        location_id=new_location_id,
        professor_id=uuid4(),
        substitute_teacher_id=substitute_id,
    )
    old_stock = SimpleNamespace(estimated_quantity=0, estimated_updated_at=NOW, updated_at=NOW)
    new_stock = SimpleNamespace(estimated_quantity=2, estimated_updated_at=NOW, updated_at=NOW)
    db = SimpleNamespace(add=MagicMock())

    with (
        patch("app.services.product_catalog.find_next_in_person_delivery_session", return_value=session_obj),
        patch("app.services.product_catalog.get_or_create_stock_row", side_effect=[old_stock, new_stock]),
    ):
        _assign_request_to_next_session(
            db,
            request_row=request_row,
            now=NOW,
            move_estimated_demand=True,
        )

    assert old_stock.estimated_quantity == 1
    assert new_stock.estimated_quantity == 1
    assert request_row.location_id == new_location_id
    assert request_row.assigned_session_id == session_obj.id
    assert request_row.assigned_professor_id == substitute_id
    assert request_row.stock_reserved_quantity == 0


def test_next_delivery_course_skips_a_day_whose_morning_email_was_already_sent() -> None:
    student_id = uuid4()
    professor_id = uuid4()
    today_session = SimpleNamespace(
        professor_id=professor_id,
        substitute_teacher_id=None,
        start_at_utc=datetime(2026, 8, 18, 17, 0, tzinfo=timezone.utc),
    )
    future_session = SimpleNamespace(
        professor_id=professor_id,
        substitute_teacher_id=None,
        start_at_utc=datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc),
    )
    professor = SimpleNamespace(
        active=True,
        daily_schedule_email_enabled=True,
        last_daily_schedule_sent_on=datetime(2026, 8, 18, tzinfo=timezone.utc).date(),
    )
    db = SimpleNamespace(
        scalars=MagicMock(return_value=SimpleNamespace(all=lambda: [today_session, future_session])),
        scalar=MagicMock(return_value=professor),
    )

    selected = find_next_in_person_delivery_session(
        db,
        student_user_id=student_id,
        now=NOW,
    )

    assert selected is future_session


def test_admin_request_uses_location_from_next_delivery_session() -> None:
    student_id = uuid4()
    product_id = uuid4()
    next_location_id = uuid4()
    actor = SimpleNamespace(id=uuid4())
    payload = AdminCatalogRequestCreateRequest(
        student_user_id=student_id,
        product_id=product_id,
    )
    db = SimpleNamespace(
        add=MagicMock(),
        flush=MagicMock(),
        commit=MagicMock(),
        refresh=MagicMock(),
    )

    with (
        patch("app.api.routes.admin_catalog._require_student_client"),
        patch("app.api.routes.admin_catalog._require_product"),
        patch("app.api.routes.admin_catalog._require_location") as require_location,
        patch(
            "app.api.routes.admin_catalog.find_next_in_person_delivery_session",
            return_value=SimpleNamespace(location_id=next_location_id),
        ),
        patch("app.api.routes.admin_catalog.apply_request_acceptance"),
        patch("app.api.routes.admin_catalog._request_out", side_effect=lambda _db, row: row),
    ):
        created = create_admin_catalog_request(payload=payload, db=db, actor=actor)

    assert created.location_id == next_location_id
    require_location.assert_called_once_with(db, next_location_id)


def test_admin_request_without_future_lesson_requires_a_fallback_location() -> None:
    payload = AdminCatalogRequestCreateRequest(
        student_user_id=uuid4(),
        product_id=uuid4(),
    )
    db = SimpleNamespace()

    with (
        patch("app.api.routes.admin_catalog._require_student_client"),
        patch("app.api.routes.admin_catalog._require_product"),
        patch("app.api.routes.admin_catalog.find_next_in_person_delivery_session", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            create_admin_catalog_request(payload=payload, db=db, actor=SimpleNamespace(id=uuid4()))

    assert exc_info.value.status_code == 409
