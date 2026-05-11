from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.deps import normalize_admin_permission_map


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


if __name__ == "__main__":
    unittest.main()
