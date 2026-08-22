from decimal import Decimal
from types import SimpleNamespace
import unittest

from app.api.routes.admin_clients import _is_non_billable_free_trial_booking


class AdminClientFreeTrialBillingTests(unittest.TestCase):
    def test_zero_total_trial_booking_is_non_billable(self) -> None:
        booking = SimpleNamespace(is_trial_course=True, total_incl_vat_snapshot=Decimal("0.00"))

        self.assertTrue(_is_non_billable_free_trial_booking(booking))

    def test_paid_standard_booking_remains_billable(self) -> None:
        booking = SimpleNamespace(is_trial_course=False, total_incl_vat_snapshot=Decimal("35.00"))

        self.assertFalse(_is_non_billable_free_trial_booking(booking))
