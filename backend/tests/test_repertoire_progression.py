from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.product_catalog import CatalogProduct
from app.models.repertoire import SheetMusicPiece, StudentSheetMusic
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
