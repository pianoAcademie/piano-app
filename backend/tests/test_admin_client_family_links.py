from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import delete_admin_client_family_link


class _ScalarListResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeFamilyDeleteSession:
    def __init__(self, *, link: object | None, siblings: list[object]) -> None:
        self._link = link
        self._siblings = siblings
        self.deleted: list[object] = []
        self.commit_calls = 0

    def scalar(self, _query: object) -> object | None:
        return self._link

    def scalars(self, _query: object) -> _ScalarListResult:
        return _ScalarListResult(self._siblings)

    def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    def commit(self) -> None:
        self.commit_calls += 1


class AdminClientFamilyLinkDeleteTests(unittest.TestCase):
    def test_delete_reassigns_billing_recipient_before_removing_current_link(self) -> None:
        child_id = uuid4()
        current_adult_id = uuid4()
        replacement_adult_id = uuid4()
        link = SimpleNamespace(
            id=uuid4(),
            child_user_id=child_id,
            adult_user_id=current_adult_id,
            is_billing_recipient=True,
        )
        replacement = SimpleNamespace(
            id=uuid4(),
            child_user_id=child_id,
            adult_user_id=replacement_adult_id,
            is_billing_recipient=False,
        )
        db = _FakeFamilyDeleteSession(link=link, siblings=[replacement])

        with patch("app.api.routes.admin_clients._set_billing_recipient") as set_billing_recipient:
            response = delete_admin_client_family_link(link.id, db=db, _=SimpleNamespace())

        set_billing_recipient.assert_called_once_with(
            db,
            child_user_id=child_id,
            chosen_adult_user_id=replacement_adult_id,
        )
        self.assertEqual(db.deleted, [link])
        self.assertEqual(db.commit_calls, 1)
        self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
