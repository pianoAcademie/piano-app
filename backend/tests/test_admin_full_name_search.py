from __future__ import annotations

import unittest

from app.api.routes.admin_clients import _filtered_clients_stmt
from app.api.routes.admin_collaborators import list_collaborators
from app.api.routes.admin_subscriptions import list_admin_subscriptions
from app.api.routes.admin_to_process import list_admin_to_process_messages
from app.api.routes.quotes import list_prospects
from app.api.routes.typeform_intakes import list_typeform_intakes


class _Rows:
    def all(self) -> list[object]:
        return []


class _CaptureDb:
    def __init__(self) -> None:
        self.statements: list[object] = []

    def scalars(self, statement: object) -> _Rows:
        self.statements.append(statement)
        return _Rows()

    def execute(self, statement: object) -> _Rows:
        self.statements.append(statement)
        return _Rows()

    def scalar(self, statement: object) -> int:
        self.statements.append(statement)
        return 0


def _parameter_values(statement: object) -> set[object]:
    return set(statement.compile().params.values())


class AdminFullNameSearchTests(unittest.TestCase):
    def assert_full_name_tokens(self, statement: object) -> None:
        values = _parameter_values(statement)
        self.assertIn("%Maxine%", values)
        self.assertIn("%Lafon%", values)

    def test_clients_require_every_full_name_token(self) -> None:
        statement = _filtered_clients_stmt(
            search=" Maxine   Lafon ",
            client_status=None,
            student_site=None,
            group_id=None,
            include_archived=True,
            active_only=False,
        )
        self.assert_full_name_tokens(statement)

    def test_collaborators_require_every_full_name_token(self) -> None:
        db = _CaptureDb()
        list_collaborators(
            search="Maxine Lafon",
            active_only=False,
            payout_as_of=None,
            limit=200,
            db=db,
            _=object(),
        )
        self.assert_full_name_tokens(db.statements[0])

    def test_prospects_require_every_full_name_token(self) -> None:
        db = _CaptureDb()
        list_prospects(
            q="Maxine Lafon",
            status_filter=None,
            prospect_type_filter=None,
            limit=200,
            db=db,
            _=object(),
        )
        self.assert_full_name_tokens(db.statements[0])

    def test_subscriptions_require_every_full_name_token(self) -> None:
        db = _CaptureDb()
        list_admin_subscriptions(
            status_filter=None,
            q="Maxine Lafon",
            only_retry_due=False,
            limit=200,
            db=db,
            _=object(),
        )
        self.assert_full_name_tokens(db.statements[0])

    def test_to_process_requires_every_full_name_token(self) -> None:
        db = _CaptureDb()
        list_admin_to_process_messages(
            status_filter=None,
            source=None,
            message_type=None,
            q="Maxine Lafon",
            limit=200,
            db=db,
            _=object(),
        )
        self.assert_full_name_tokens(db.statements[0])

    def test_intakes_require_every_full_name_token(self) -> None:
        db = _CaptureDb()
        list_typeform_intakes(
            status_filter=None,
            include_ignored=False,
            exclude_processed=True,
            q="Maxine Lafon",
            page=1,
            page_size=50,
            db=db,
            _=object(),
        )
        self.assert_full_name_tokens(db.statements[0])


if __name__ == "__main__":
    unittest.main()
