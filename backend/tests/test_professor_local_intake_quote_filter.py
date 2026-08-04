from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.api.routes.professors import list_my_local_intake_confirmations


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
