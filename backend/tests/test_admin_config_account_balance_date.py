from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, call, patch

from fastapi import HTTPException

from app.api.routes import admin_config
from app.schemas.admin import AdminConfigAccountUpdateRequest


class AdminConfigAccountBalanceDateTests(unittest.TestCase):
    def test_fixed_date_mode_requires_a_date(self) -> None:
        payload = AdminConfigAccountUpdateRequest(
            client_balance_default_date_mode="FIXED_DATE",
            client_balance_default_date=None,
        )

        with self.assertRaises(HTTPException) as raised:
            admin_config.update_admin_config_account(
                payload=payload,
                db=MagicMock(),
                current_user=MagicMock(),
            )

        self.assertEqual(raised.exception.status_code, 422)

    @patch.object(admin_config, "get_admin_config_account")
    @patch.object(admin_config, "_set_setting")
    def test_fixed_date_is_persisted_as_iso_date(self, set_setting: MagicMock, get_account: MagicMock) -> None:
        payload = AdminConfigAccountUpdateRequest(
            client_balance_default_date_mode="FIXED_DATE",
            client_balance_default_date=date(2027, 7, 31),
        )
        db = MagicMock()
        expected = MagicMock()
        get_account.return_value = expected

        result = admin_config.update_admin_config_account(
            payload=payload,
            db=db,
            current_user=MagicMock(),
        )

        self.assertIs(result, expected)
        self.assertIn(
            call(db, admin_config.ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_MODE_KEY, "FIXED_DATE"),
            set_setting.call_args_list,
        )
        self.assertIn(
            call(db, admin_config.ACCOUNT_CLIENT_BALANCE_DEFAULT_DATE_KEY, "2027-07-31"),
            set_setting.call_args_list,
        )
        db.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
