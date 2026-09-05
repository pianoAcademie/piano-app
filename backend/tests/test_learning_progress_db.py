"""Uses the same isolated PostgreSQL fixture as physical distribution tests."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from tests.test_partition_distribution import scenario  # noqa: F401
from app.api.routes.repertoire import LearningChange, professor_change_learning, professor_learning
from app.models.learning_progress import StudentLearningEvent
from app.models.partition_distribution import PartitionMovement
from app.models.product_catalog import CatalogProduct
from app.models.repertoire import SheetMusicPiece


def setup(scenario):
    db, admin, actor, prof, student, product, stock, assignment, session, week = scenario
    pieces = [SheetMusicPiece(product_id=product.id, title=f"Morceau {i}", position=i, active=True) for i in range(1, 4)]
    db.add_all(pieces); db.flush()
    assignment.status = "IN_PROGRESS"
    assignment.delivered_at = datetime.now(timezone.utc)
    assignment.current_piece_id = pieces[1].id
    db.flush()
    return db, actor, student, product, assignment, session, pieces


def test_persistent_history_complete_undo_and_reload(scenario):
    db, actor, student, product, assignment, session, pieces = setup(scenario)
    initial = professor_learning(student.id, session.id, db, actor)
    assert initial["revision"] == 0
    history = professor_change_learning(student.id, LearningChange(revision=0, session_id=session.id, action="HISTORY",
        product_id=product.id, piece_id=pieces[1].id, statuses={pieces[2].id: "COMPLETED", pieces[0].id: "REVIEW"}), db, actor)
    result = professor_change_learning(student.id, LearningChange(revision=1, session_id=session.id, action="COMPLETE_PIECE", piece_id=pieces[0].id), db, actor)
    db.expire_all()
    loaded = professor_learning(student.id, session.id, db, actor)
    assert loaded["revision"] == 2
    assert loaded["state"]["books"][str(product.id)]["current_piece_id"] == str(pieces[0].id)
    assert loaded["history"][0]["piece_id"] == str(pieces[1].id)
    assert len(loaded["history"]) == 2
    undone = professor_change_learning(student.id, LearningChange(revision=2, session_id=session.id, action="UNDO", undo_event_id=result["undo_event_id"]), db, actor)
    assert undone["state"] == history["state"]
    assert db.scalar(select(func.count()).select_from(StudentLearningEvent).where(StudentLearningEvent.student_id == student.id)) == 3


def test_correct_delivered_book_preserves_delivery_and_stock(scenario):
    db, actor, student, product, assignment, session, pieces = setup(scenario)
    other = CatalogProduct(title="Partition réellement travaillée", active=True, is_virtual=False)
    db.add(other); db.flush()
    new_piece = SheetMusicPiece(product_id=other.id, title="Un autre morceau", position=1, active=True)
    db.add(new_piece); db.flush()
    delivered_at = assignment.delivered_at
    count = db.scalar(select(func.count()).select_from(PartitionMovement))
    result = professor_change_learning(student.id, LearningChange(revision=0, session_id=session.id, action="CORRECT", product_id=other.id, piece_id=new_piece.id), db, actor)
    db.refresh(assignment)
    assert result["state"]["product_id"] == str(other.id)
    assert assignment.product_id == product.id
    assert assignment.delivered_at == delivered_at
    assert db.scalar(select(func.count()).select_from(PartitionMovement)) == count


def test_older_screen_cannot_write_twice(scenario):
    db, actor, student, product, assignment, session, pieces = setup(scenario)
    command = LearningChange(revision=0, session_id=session.id, action="CONTINUE")
    professor_change_learning(student.id, command, db, actor)
    with pytest.raises(HTTPException) as exc:
        professor_change_learning(student.id, command, db, actor)
    assert exc.value.status_code == 409
