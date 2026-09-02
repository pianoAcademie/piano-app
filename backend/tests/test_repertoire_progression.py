from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.product_catalog import CatalogProduct
from app.models.repertoire import SheetMusicPiece, StudentSheetMusic, StudentSheetMusicEvent
from app.api.routes.repertoire import AssignmentUpdate, _update_assignment, _validated_piece_for_product
from app.services.repertoire_progression import (
    ensure_previous_partition_for_reenrollment,
    partition_degree,
    start_next_partition_after_completion,
)


def test_partition_degree_supports_accents_and_excludes_non_degree_books():
    assert partition_degree("Partition degré 8") == 8
    assert partition_degree("Partition Degre 10") == 10
    assert partition_degree("Partition Ados") is None


def test_reenrollment_creates_previous_degree_in_progress():
    db = MagicMock()
    db.scalar.return_value = None
    next_product = CatalogProduct(id=uuid4(), title="Partition degré 8", active=True, is_virtual=False)
    previous_product = CatalogProduct(id=uuid4(), title="Partition degré 7", active=True, is_virtual=False)

    with patch(
        "app.services.repertoire_progression.previous_partition_product",
        return_value=previous_product,
    ):
        assignment = ensure_previous_partition_for_reenrollment(
            db,
            student_id=uuid4(),
            next_product=next_product,
            actor_user_id=uuid4(),
        )

    assert assignment is not None
    assert assignment.product_id == previous_product.id
    assert assignment.title_snapshot == "Partition degré 7"
    assert assignment.status == "IN_PROGRESS"
    assert assignment.started_at is not None
    assert db.add.call_count == 2


def test_completing_current_partition_starts_quote_partition_at_first_piece():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    student_id = uuid4()
    current = StudentSheetMusic(
        id=uuid4(),
        student_id=student_id,
        product_id=uuid4(),
        title_snapshot="Partition degré 7",
        status="COMPLETED",
    )
    next_product_id = uuid4()
    next_assignment = StudentSheetMusic(
        id=uuid4(),
        student_id=student_id,
        product_id=next_product_id,
        title_snapshot="Partition degré 8",
        status="STANDBY",
        source_quote_line_id=uuid4(),
    )
    first_piece = SheetMusicPiece(
        id=uuid4(),
        product_id=next_product_id,
        title="Dans l’antre du roi de la montagne – E. Grieg",
        position=1,
        active=True,
    )
    db = MagicMock()
    db.scalar.side_effect = [next_assignment, first_piece]

    started = start_next_partition_after_completion(
        db,
        completed_assignment=current,
        actor_user_id=uuid4(),
        now=now,
    )

    assert started is next_assignment
    assert next_assignment.status == "IN_PROGRESS"
    assert next_assignment.current_piece_id == first_piece.id
    assert next_assignment.started_at == now
    assert next_assignment.delivered_at == now


def test_professor_authorized_product_correction_is_audited_without_touching_quote():
    db = MagicMock()
    old_product_id = uuid4()
    corrected_product = CatalogProduct(
        id=uuid4(),
        title="Partition degré 7",
        active=True,
        is_virtual=False,
    )
    assignment = StudentSheetMusic(
        id=uuid4(),
        student_id=uuid4(),
        product_id=old_product_id,
        title_snapshot="Partition degré 8",
        status="IN_PROGRESS",
        current_piece_id=uuid4(),
        source_quote_line_id=uuid4(),
    )
    source_quote_line_id = assignment.source_quote_line_id
    actor = MagicMock()
    actor.id = uuid4()

    with (
        patch("app.api.routes.repertoire._partition_product", return_value=corrected_product),
        patch("app.api.routes.repertoire._assignment_out", return_value=assignment),
    ):
        result = _update_assignment(
            db,
            assignment,
            AssignmentUpdate(product_id=corrected_product.id),
            actor,
            allow_product_change=True,
        )

    assert result is assignment
    assert assignment.product_id == corrected_product.id
    assert assignment.title_snapshot == corrected_product.title
    assert assignment.current_piece_id is None
    assert assignment.source_quote_line_id == source_quote_line_id
    events = [
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], StudentSheetMusicEvent)
    ]
    correction = next(event for event in events if event.event_type == "PARTITION_CORRECTED")
    assert correction.actor_user_id == actor.id
    assert correction.note == "Correction de partition : Partition degré 8 → Partition degré 7"


def test_product_correction_accepts_a_piece_from_the_new_partition():
    db = MagicMock()
    corrected_product = CatalogProduct(
        id=uuid4(),
        title="Partitions Ados",
        active=True,
        is_virtual=False,
    )
    selected_piece = SheetMusicPiece(
        id=uuid4(),
        product_id=corrected_product.id,
        title="I Will Survive - Gloria Gaynor",
        position=1,
        active=True,
    )
    assignment = StudentSheetMusic(
        id=uuid4(),
        student_id=uuid4(),
        product_id=uuid4(),
        title_snapshot="Partition degré 6 Adulte",
        status="IN_PROGRESS",
        current_piece_id=None,
    )
    actor = MagicMock()
    actor.id = uuid4()
    db.get.return_value = selected_piece

    with (
        patch("app.api.routes.repertoire._partition_product", return_value=corrected_product),
        patch("app.api.routes.repertoire._assignment_out", return_value=assignment),
    ):
        _update_assignment(
            db,
            assignment,
            AssignmentUpdate(product_id=corrected_product.id, current_piece_id=selected_piece.id),
            actor,
            allow_product_change=True,
        )

    assert assignment.product_id == corrected_product.id
    assert assignment.title_snapshot == "Partitions Ados"
    assert assignment.current_piece_id == selected_piece.id


def test_new_assignment_piece_must_belong_to_selected_partition():
    db = MagicMock()
    product_id = uuid4()
    selected_piece = SheetMusicPiece(
        id=uuid4(),
        product_id=product_id,
        title="Dernière Danse",
        position=7,
        active=True,
    )
    db.get.return_value = selected_piece

    result = _validated_piece_for_product(db, product_id=product_id, piece_id=selected_piece.id)

    assert result is selected_piece
