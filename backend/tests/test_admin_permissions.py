from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.deps import BACKOFFICE_PERMISSION_KEYS, normalize_admin_permission_map
from app.services.professor_permissions import DEFAULT_PROFESSOR_PERMISSIONS, PERMISSION_FIELDS


class AdminPermissionTests(unittest.TestCase):
    def test_edit_planning_implies_planning_visibility(self) -> None:
        permissions = normalize_admin_permission_map(
            {
                "can_view_planning": False,
                "can_edit_planning": True,
                "can_view_all_school_sessions": False,
            }
        )

        self.assertTrue(permissions["can_view_planning"])
        self.assertTrue(permissions["can_view_all_school_sessions"])

    def test_planning_visibility_is_not_forced_without_edit_permission(self) -> None:
        permissions = normalize_admin_permission_map(
            {
                "can_view_planning": False,
                "can_edit_planning": False,
            }
        )

        self.assertFalse(permissions["can_view_planning"])

    def test_upcoming_trials_is_a_dedicated_backoffice_permission(self) -> None:
        self.assertIn("can_view_upcoming_trials", BACKOFFICE_PERMISSION_KEYS)
        self.assertIn("can_view_upcoming_trials", PERMISSION_FIELDS)
        self.assertFalse(DEFAULT_PROFESSOR_PERMISSIONS["can_view_upcoming_trials"])

    def test_accounting_permissions_enable_backoffice_access(self) -> None:
        self.assertIn("can_manage_invoices_and_accounts", BACKOFFICE_PERMISSION_KEYS)
        self.assertIn("can_create_and_view_reports", BACKOFFICE_PERMISSION_KEYS)
        self.assertFalse(DEFAULT_PROFESSOR_PERMISSIONS["can_manage_invoices_and_accounts"])
        self.assertFalse(DEFAULT_PROFESSOR_PERMISSIONS["can_create_and_view_reports"])


if __name__ == "__main__":
    unittest.main()
