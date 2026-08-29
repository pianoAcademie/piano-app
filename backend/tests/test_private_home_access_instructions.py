from __future__ import annotations

import unittest

from app.models.user import User
from app.schemas.admin import AdminClientCreateRequest, AdminClientOut, AdminClientUpdateRequest
from app.schemas.user import UserOut


class PrivateHomeAccessInstructionsTests(unittest.TestCase):
    def test_private_field_is_supported_by_admin_client_contracts(self) -> None:
        create_payload = AdminClientCreateRequest(
            first_name="Camille",
            last_name="Martin",
            home_access_instructions="Bâtiment B, 3e étage, code 1234",
        )
        update_payload = AdminClientUpdateRequest(home_access_instructions="Interphone Martin")

        self.assertEqual(create_payload.home_access_instructions, "Bâtiment B, 3e étage, code 1234")
        self.assertEqual(update_payload.home_access_instructions, "Interphone Martin")
        self.assertIn("home_access_instructions", AdminClientOut.model_fields)
        self.assertIn("home_access_instructions", User.__table__.columns)

    def test_private_field_is_not_exposed_in_client_profile_contract(self) -> None:
        self.assertNotIn("home_access_instructions", UserOut.model_fields)


if __name__ == "__main__":
    unittest.main()
