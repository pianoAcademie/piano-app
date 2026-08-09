from datetime import datetime, timezone
import unittest
from uuid import uuid4

from app.api.routes.admin_collaborators import _to_detail
from app.models.catalog import Professor
from app.models.user import User, UserRole


class AdminProfessorLastLoginTests(unittest.TestCase):
    def professor(self, *, now: datetime) -> Professor:
        return Professor(
            id=uuid4(),
            first_name="Ana",
            last_name="Martin",
            email="ana@example.com",
            payout_currency="EUR",
            is_coach=True,
            active=True,
            daily_schedule_email_enabled=False,
            daily_schedule_email_time="07:00",
            daily_schedule_skip_if_no_course=True,
            created_at=now,
            updated_at=now,
        )

    def test_professor_detail_exposes_linked_user_last_login(self) -> None:
        now = datetime(2026, 8, 9, 8, 30, tzinfo=timezone.utc)
        linked_user = User(
            email="ana@example.com",
            hashed_password="hashed",
            role=UserRole.PROF,
            is_active=True,
            last_login_at=now,
        )

        detail = _to_detail(self.professor(now=now), linked_user=linked_user, permission_row=None)

        self.assertEqual(detail.last_login_at, now)

    def test_professor_detail_has_no_last_login_without_linked_user(self) -> None:
        now = datetime(2026, 8, 9, 8, 30, tzinfo=timezone.utc)

        detail = _to_detail(self.professor(now=now), linked_user=None, permission_row=None)

        self.assertIsNone(detail.last_login_at)
