"""Real PostgreSQL round trips, never production; all rows rolled back by case."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from tests.test_annual_pricing_postgres import case, setup_move, URL
from app.models.catalog import Booking, BookingStatus, CourseType, DeliveryMode, LessonFormat, SessionStatus
from app.models.plan import ClientPlanSubscription, Plan, SubscriptionStatus
from app.models.product_catalog import CatalogProduct
from app.models.makeup import MakeupPassPurchase, MakeupRequest, MakeupRequestStatus
from app.services.makeup_accounting import mark_original, makeup_role
from app.services.makeup_booking import program, options, compatible_activity, release_replacement
from app.services.makeup_passes import consume_pass_and_create_makeup, revoke_pending_makeup_for_corrected_absence

pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


@pytest.fixture
def recovery(case):
    db, actor, sources, targets, bookings = setup_move(case)
    now = datetime.now(timezone.utc)
    original = bookings[0]
    from app.models.family import ClientFamilyLink
    link = db.scalar(select(ClientFamilyLink).where(ClientFamilyLink.adult_user_id == actor.id,
        ClientFamilyLink.child_user_id == original.user_id))
    link.is_billing_recipient = True
    source = sources[0]
    source.start_at_utc = now - timedelta(days=1)
    source.end_at_utc = source.start_at_utc + timedelta(hours=1)
    original.status = BookingStatus.EXCUSED_ABSENCE
    sub = db.get(ClientPlanSubscription, original.client_plan_subscription_id)
    sub.started_at = now - timedelta(days=60)
    db.get(Plan, sub.plan_id).name = "Année 2026-2027"
    sub.annual_pricing_terms = [{"activity_id": str(source.course_type_id), "location_id": str(source.location_id),
        "duration_minutes": 60, "session_ids": [str(source.id)]}]
    product = CatalogProduct(title="Pass Récup", is_makeup_pass=True)
    db.add(product); db.flush()
    purchase = MakeupPassPurchase(user_id=original.user_id, product_id=product.id, forfait_subscription_id=sub.id,
        credits_initial=4, credits_remaining=4)
    db.add(purchase); db.flush()
    request = consume_pass_and_create_makeup(db, booking=original, subscription=sub, actor_user_id=actor.id, now=now)
    db.commit()
    return db, actor, original, sub, product, purchase, request, targets, now


def book(r, target=None):
    db, actor, original, _, _, _, request, targets, now = r
    return program(db, request_id=request.id, student_id=original.user_id, target_id=(target or targets[0]).id,
        actor_id=actor.id, now=now)


def test_preview_read_only_and_program_zero_extra_without_changing_contract(recovery):
    db, actor, original, sub, _, purchase, request, targets, now = recovery
    contract = list(sub.annual_pricing_terms)
    price = (original.price_excl_vat_snapshot, original.vat_amount_snapshot, original.total_incl_vat_snapshot)
    preview = options(db, request, now=now, start=now, end=now+timedelta(days=60))
    assert targets[0].id in [o["id"] for o in preview["options"]]
    assert request.status == MakeupRequestStatus.PROPOSED and purchase.credits_remaining == 3
    booking = book(recovery)
    db.commit(); db.expire_all()
    assert booking.status == BookingStatus.BOOKED
    assert booking.total_incl_vat_snapshot == booking.price_excl_vat_snapshot == booking.vat_amount_snapshot == 0
    assert booking.pricing_snapshot_locked and makeup_role(booking) == "replacement"
    assert request.reserved_booking_id == booking.id and request.status == MakeupRequestStatus.BOOKED
    assert sub.annual_pricing_terms == contract
    assert (original.price_excl_vat_snapshot, original.vat_amount_snapshot, original.total_incl_vat_snapshot) == price
    assert original.status == BookingStatus.EXCUSED_ABSENCE
    assert purchase.credits_remaining == 3


def test_double_submit_idempotent_and_different_second_target_rejected(recovery):
    db, _, original, _, _, purchase, request, targets, _ = recovery
    first = book(recovery)
    assert book(recovery).id == first.id
    with pytest.raises(HTTPException, match="déjà programmé"):
        book(recovery, targets[1])
    assert db.scalar(select(func.count()).select_from(Booking).where(Booking.makeup_request_id == request.id)) == 2  # source and replacement
    assert purchase.credits_remaining == 3


@pytest.mark.parametrize("change", ["full", "cancelled", "expired", "longer", "past", "overlap", "adult_only", "no_pass", "present", "wrong_product", "inactive", "other_activity", "missing_validity", "custom_time"])
def test_ineligible_or_stale_preview_never_consumes_or_books(recovery, change):
    db, actor, original, sub, product, purchase, request, targets, now = recovery
    target = targets[0]
    if change == "full": target.capacity_max = 0
    elif change == "cancelled": target.status = SessionStatus.CANCELLED
    elif change == "expired": sub.ends_at = now - timedelta(hours=1)
    elif change == "longer": target.end_at_utc += timedelta(minutes=30)
    elif change == "past": target.start_at_utc = now - timedelta(hours=2); target.end_at_utc = now - timedelta(hours=1)
    elif change == "overlap":
        from app.models.catalog import CourseSession
        conflict = CourseSession(course_type_id=target.course_type_id, location_id=target.location_id, title="Overlap",
            start_at_utc=target.start_at_utc, end_at_utc=target.end_at_utc, capacity_max=6, timezone=target.timezone,
            auto_cancel_deadline_utc=target.start_at_utc)
        db.add(conflict); db.flush()
        db.add(Booking(session_id=conflict.id, user_id=original.user_id, status=BookingStatus.BOOKED))
    elif change == "adult_only": target.child_bookings_enabled = False
    elif change == "no_pass": request.used_pass_purchase_id = None
    elif change == "present": original.status = BookingStatus.ATTENDED
    elif change == "wrong_product": product.is_makeup_pass = False
    elif change == "inactive": sub.status = SubscriptionStatus.CANCELLED
    elif change == "missing_validity": sub.ends_at = None
    elif change == "custom_time": original.student_start_at_utc = now
    elif change == "other_activity":
        activity = CourseType(code=str(uuid4()), name="Cours particulier", service_code="PIANO", mode=DeliveryMode.ONSITE,
            duration_minutes=60, default_capacity=1, lesson_format=LessonFormat.INDIVIDUAL)
        db.add(activity); db.flush(); target.course_type_id = activity.id
    db.flush()
    with pytest.raises(HTTPException): book(recovery)
    assert request.status == MakeupRequestStatus.PROPOSED and request.reserved_booking_id is None
    assert purchase.credits_remaining == 3
    assert not db.scalar(select(Booking.id).where(Booking.session_id == target.id, Booking.user_id == original.user_id))


def test_online_pass_never_offers_onsite(recovery):
    db, _, _, _, product, _, request, _, now = recovery
    product.title = "Pass Récup Online"; db.flush()
    assert options(db, request, now=now, start=now, end=now+timedelta(days=60))["options"] == []
    with pytest.raises(HTTPException, match="compatible"): book(recovery)


def test_remaining_zero_is_ok_when_request_already_consumed_last_credit(recovery):
    recovery[5].credits_remaining = 0
    assert book(recovery).id
    assert recovery[5].credits_remaining == 0


def test_wrong_student_is_not_found(recovery):
    db, actor, _, _, _, _, request, targets, now = recovery
    with pytest.raises(HTTPException) as exc:
        program(db, request_id=request.id, student_id=actor.id, target_id=targets[0].id, actor_id=actor.id, now=now)
    assert exc.value.status_code == 404


def test_account_has_one_original_charge_and_no_replacement_or_credit(recovery):
    from app.api.routes.admin_clients import _build_admin_client_payments
    db, actor, original, _, _, _, request, _, _ = recovery
    booking = book(recovery); db.flush()
    rows = _build_admin_client_payments(db, client_id=actor.id)
    original_rows = [row for row in rows if row.id == original.id]
    assert len(original_rows) == 1
    assert original_rows[0].source == "BOOKING" and original_rows[0].total_incl_vat == 34
    assert not any(row.id == booking.id for row in rows)
    assert not any(row.id == original.id and row.source == "BOOKING_CREDIT" for row in rows)


def test_existing_invoice_coverage_and_original_amount_unchanged(recovery):
    from app.api.routes.admin_clients import _build_admin_client_payments
    db, actor, original, _, _, _, _, _, _ = recovery
    lock = ("ISSUED", "TEST-001", None, "UNPAID", None)
    with patch("app.api.routes.admin_clients._active_invoice_lock_by_payment_key", return_value={f"BOOKING:{original.id}": lock}):
        booking = book(recovery)
        rows = _build_admin_client_payments(db, client_id=actor.id)
    assert not any(row.source == "BOOKING_CREDIT" and row.id == original.id for row in rows)
    assert not any(row.id == booking.id for row in rows)
    assert original.total_incl_vat_snapshot == Decimal("34.00")


def test_already_invoiced_cancellation_credit_requires_accountant(recovery):
    original = recovery[2]
    with patch("app.api.routes.admin_clients._active_invoice_lock_by_payment_key", return_value={f"BOOKING_CREDIT:{original.id}": ("ISSUED", "TEST", None, "UNPAID", None)}):
        with pytest.raises(HTTPException, match="avoir a déjà été émis"): book(recovery)
    assert recovery[6].status == MakeupRequestStatus.PROPOSED


def test_cancel_replacement_releases_same_request_without_debit(recovery):
    db, _, original, _, _, purchase, request, targets, now = recovery
    first = book(recovery)
    first.status = BookingStatus.CANCELLED
    release_replacement(db, first, now=now)
    db.flush()
    second = book(recovery, targets[1])
    assert second.id != first.id and request.reserved_booking_id == second.id
    assert purchase.credits_remaining == 3


def test_cannot_revoke_absence_with_booked_replacement(recovery):
    book(recovery)
    with pytest.raises(HTTPException, match="déjà réservé"):
        revoke_pending_makeup_for_corrected_absence(recovery[0], booking=recovery[2], now=recovery[-1])


def test_client_pricing_uses_pass_before_contract_whitelist(recovery):
    from app.api.routes.bookings import _resolve_booking_pricing
    from app.models.user import User
    db, _, original, sub, _, _, _, targets, now = recovery
    price = _resolve_booking_pricing(db, session_obj=targets[0], user=db.get(User, original.user_id), now=now,
        subscription=sub, plan=db.get(Plan, sub.plan_id), use_makeup=True)
    assert price.total_incl_vat == 0 and price.source.startswith("makeup:")


def test_no_immediate_email_notification(recovery):
    with patch("app.services.notifications.application.orchestrator.enqueue_notifications") as notify:
        book(recovery)
    notify.assert_not_called()


def test_quote_pricing_does_not_use_unrelated_pending_makeup(recovery):
    from app.api.routes.bookings import _resolve_booking_pricing
    from app.models.user import User
    db, _, original, sub, _, _, _, targets, now = recovery
    with pytest.raises(HTTPException, match="cours contractuel"):
        _resolve_booking_pricing(db, session_obj=targets[0], user=db.get(User, original.user_id), now=now,
            subscription=sub, plan=db.get(Plan, sub.plan_id))


@pytest.mark.parametrize("allowed", [False, True])
def test_endpoint_checks_edit_planning_permission(recovery, allowed):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes.admin_makeups import router
    from app.api.deps import get_current_user, get_db
    from app.models.user import UserRole
    from types import SimpleNamespace
    db, actor, original, sub, product, _, request, targets, _ = recovery
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=actor.id, role=UserRole.PROF)
    with patch("app.api.deps.get_admin_permission_map", return_value={"can_view_clients": True, "can_edit_planning": allowed}), TestClient(app) as client:
        from app.services.makeup_booking import preview_version
        response = client.post(f"/admin/clients/{original.user_id}/makeups/{request.id}/program", json={"session_id": str(targets[0].id),
            "expected_version": preview_version(request, original, sub, product, targets[0])})
    assert response.status_code == (200 if allowed else 403)
    assert (request.reserved_booking_id is not None) == allowed


@pytest.mark.parametrize("source", ["BOOKING", "BOOKING_CREDIT"])
def test_real_issued_invoice_is_immutable(recovery, source):
    from app.api.routes.admin_clients import _build_invoice_range_note_message, _build_admin_client_payments
    from app.models.client_record import ClientNoteEntry, ClientInvoiceLine
    db, actor, original, _, _, _, _, _, now = recovery
    metadata = {"kind": "INVOICE_RANGE", "layout": "DETAILED", "invoice_number": "TEST-MAKEUP", "invoice_status": "ISSUED", "start_date": "2026-01-01",
        "end_date": "2027-07-31", "issued_date": now.date().isoformat(), "due_date": now.date().isoformat(),
        "included_payment_keys": [f"{source}:{original.id}"], "totals_by_currency": {"EUR": "34.00"},
        "sent_at": now.isoformat()}
    note = ClientNoteEntry(user_id=actor.id, message=_build_invoice_range_note_message(metadata))
    db.add(note); db.flush()
    line = ClientInvoiceLine(note_id=note.id, user_id=original.user_id, source=source, source_payment_id=original.id,
        occurred_at=now, label="Original invoice", amount_excl_vat=Decimal("28.33"), vat_rate=20,
        vat_amount=Decimal("5.67"), total_incl_vat=34, currency="EUR")
    db.add(line); db.commit()
    before_message = note.message
    before_amount = line.total_incl_vat
    if source == "BOOKING_CREDIT":
        with pytest.raises(HTTPException, match="avoir a déjà été émis"): book(recovery)
    else:
        replacement = book(recovery)
        rows = _build_admin_client_payments(db, client_id=actor.id)
        row = next(r for r in rows if r.id == original.id)
        assert row.invoice_number == "TEST-MAKEUP" and row.invoice_status == "ISSUED"
        assert not any(r.id == replacement.id or (r.id == original.id and r.source == "BOOKING_CREDIT") for r in rows)
    db.flush(); db.expire_all()
    assert note.message == before_message and line.total_incl_vat == before_amount


def test_automatic_cancellation_releases_same_pass_right(recovery):
    from app.services.session_automation import restore_cancelled_booking_credit
    replacement = book(recovery)
    assert restore_cancelled_booking_credit(recovery[0], booking=replacement)
    assert recovery[6].status == MakeupRequestStatus.PROPOSED
    assert recovery[5].credits_remaining == 3


def test_changed_slot_after_preview_requires_new_confirmation(recovery):
    from app.services.makeup_booking import preview_version
    db, actor, original, sub, product, purchase, request, targets, now = recovery
    expected = preview_version(request, original, sub, product, targets[0])
    targets[0].start_at_utc += timedelta(hours=1)
    targets[0].end_at_utc += timedelta(hours=1)
    db.flush()
    with pytest.raises(HTTPException, match="depuis l'aperçu"):
        program(db, request_id=request.id, student_id=original.user_id, target_id=targets[0].id,
            actor_id=actor.id, expected_version=expected, now=now)
    assert purchase.credits_remaining == 3 and request.status == MakeupRequestStatus.PROPOSED
