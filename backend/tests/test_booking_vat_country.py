from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes.admin_clients import _booking_vat_country as admin_booking_vat_country
from app.api.routes.bookings import _booking_vat_country as checkout_booking_vat_country
from app.api.routes.clients import _booking_vat_country as client_booking_vat_country
from app.models.catalog import DeliveryMode


class _LocationDb:
    def __init__(self, location: object) -> None:
        self.location = location

    def scalar(self, _query: object) -> object:
        return self.location


class BookingVatCountryTests(unittest.TestCase):
    def test_online_location_overrides_legacy_onsite_course_mode(self) -> None:
        session = SimpleNamespace(location_id=uuid4())
        course_type = SimpleNamespace(mode=DeliveryMode.ONSITE)
        location = SimpleNamespace(is_online=True, country_code="FR")
        billing_profile = SimpleNamespace(residence_country="SA")

        self.assertEqual(
            admin_booking_vat_country(
                session_obj=session,
                course_type=course_type,
                location=location,
                billing_profile=billing_profile,
            ),
            "SA",
        )
        self.assertEqual(
            client_booking_vat_country(
                session_obj=session,
                course_type=course_type,
                location=location,
                billing_profile=billing_profile,
            ),
            "SA",
        )
        self.assertEqual(
            checkout_booking_vat_country(
                session_obj=session,
                course_type=course_type,
                billing_profile=billing_profile,
                db=_LocationDb(location),
            ),
            "SA",
        )

    def test_physical_location_keeps_location_country(self) -> None:
        country = admin_booking_vat_country(
            session_obj=SimpleNamespace(location_id=uuid4()),
            course_type=SimpleNamespace(mode=DeliveryMode.ONSITE),
            location=SimpleNamespace(is_online=False, country_code="FR"),
            billing_profile=SimpleNamespace(residence_country="SA"),
        )

        self.assertEqual(country, "FR")


if __name__ == "__main__":
    unittest.main()
