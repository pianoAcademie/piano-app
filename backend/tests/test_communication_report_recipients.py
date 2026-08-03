from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.reports import (
    _communication_recipient_names,
    _communication_recipient_user_id,
)


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(self, users: list[object]) -> None:
        self._users = users

    def scalars(self, _query: object) -> _ScalarRows:
        return _ScalarRows(self._users)


class CommunicationReportRecipientTests(unittest.TestCase):
    def test_legacy_client_reference_resolves_user_id(self) -> None:
        user_id = uuid4()
        row = SimpleNamespace(recipient_user_id=None, recipient=f"client:{user_id}")

        self.assertEqual(_communication_recipient_user_id(row), user_id)

    def test_names_resolve_from_user_id_and_historical_email(self) -> None:
        linked_user_id = uuid4()
        email_user_id = uuid4()
        linked_user = SimpleNamespace(
            id=linked_user_id,
            first_name="Sienna",
            last_name="Stiebert Ambroise",
            email="child@example.test",
        )
        email_user = SimpleNamespace(
            id=email_user_id,
            first_name="Agnès",
            last_name="Ambroise",
            email="ambroisea@example.test",
        )
        linked_log_id = uuid4()
        historical_log_id = uuid4()
        rows = [
            SimpleNamespace(
                id=linked_log_id,
                recipient_user_id=linked_user_id,
                recipient="+33600000000",
            ),
            SimpleNamespace(
                id=historical_log_id,
                recipient_user_id=None,
                recipient="AMBROISEA@example.test",
            ),
        ]

        names = _communication_recipient_names(
            _FakeSession([linked_user, email_user]),
            rows,
        )

        self.assertEqual(names[linked_log_id], "Sienna Stiebert Ambroise")
        self.assertEqual(names[historical_log_id], "Agnès Ambroise")


if __name__ == "__main__":
    unittest.main()
