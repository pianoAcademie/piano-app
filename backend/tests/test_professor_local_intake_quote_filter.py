from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.api.routes.professors import _require_assigned_local_intake, list_my_local_intake_confirmations


def test_pending_local_confirmation_query_excludes_processed_quotes() -> None:
    professor = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        scalars=MagicMock(return_value=SimpleNamespace(all=lambda: [])),
    )

    with patch("app.api.routes.professors._resolve_professor_profile", return_value=professor):
        list_my_local_intake_confirmations(
            status_filter="PENDING",
            limit=100,
            db=db,
            current_user=SimpleNamespace(),
        )

    statement = str(db.scalars.call_args.args[0])
    assert "LEFT OUTER JOIN quotes" in statement
    assert "quotes.sent_at IS NULL" in statement
    assert "quotes.approved_at IS NULL" in statement
    assert "quotes.rejected_at IS NULL" in statement


def test_confirm_local_intake_locks_only_the_intake_table() -> None:
    intake = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(scalar=MagicMock(return_value=intake))

    result = _require_assigned_local_intake(
        db,
        intake_id=intake.id,
        professor_id=uuid4(),
        lock=True,
    )

    statement = db.scalar.call_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert result is intake
    assert "LEFT OUTER JOIN quotes" in compiled
    assert "FOR UPDATE OF typeform_intakes" in compiled
