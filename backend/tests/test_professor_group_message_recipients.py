import unittest

from app.api.routes.professors import _deliverable_client_email
from app.models.user import User


def _user(*, email: str, contact_email: str | None = None) -> User:
    return User(email=email, contact_email=contact_email)


class ProfessorGroupMessageRecipientTests(unittest.TestCase):
    def test_keeps_real_child_address(self) -> None:
        self.assertEqual(_deliverable_client_email(_user(email="Child@Example.com")), "child@example.com")

    def test_uses_real_contact_before_synthetic_login(self) -> None:
        user = _user(email="child@piano-academie.invalid", contact_email="Parent.Child@example.com")
        self.assertEqual(_deliverable_client_email(user), "parent.child@example.com")

    def test_rejects_synthetic_addresses(self) -> None:
        self.assertIsNone(_deliverable_client_email(_user(email="child@piano-academie.invalid")))
        self.assertIsNone(_deliverable_client_email(_user(email="mms-child-123@no-email.local")))
