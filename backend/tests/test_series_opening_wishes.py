import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from app.api.routes import admin
from app.schemas.admin import AdminAnnualSeriesTransferRequestCreate, AdminAnnualSeriesTransferStatusUpdate


class OpeningWishTests(unittest.TestCase):
    def test_invalid_day_and_time(self):
        for day, time in [(7, '09:00'), (2, '24:00'), (2, '9:00')]:
            with self.assertRaises(ValidationError):
                AdminAnnualSeriesTransferRequestCreate(student_user_id=uuid4(), source_booking_id=uuid4(), desired_weekday=day, desired_time=time)

    def test_missing_wish_rejected_before_write(self):
        db = MagicMock()
        with self.assertRaises(HTTPException) as error:
            admin.create_annual_series_transfer(AdminAnnualSeriesTransferRequestCreate(student_user_id=uuid4(), source_booking_id=uuid4()), db=db, actor=NS(id=uuid4()))
        self.assertEqual(error.exception.status_code, 422)
        db.commit.assert_not_called()

    def test_unbound_wish_cannot_be_completed(self):
        db = MagicMock()
        db.scalar.return_value = NS(target_session_id=None)
        with self.assertRaises(HTTPException):
            admin.update_annual_series_transfer_status(uuid4(), AdminAnnualSeriesTransferStatusUpdate(status='COMPLETED'), db=db, actor=NS(id=uuid4()))
        db.commit.assert_not_called()

    def test_incompatible_series_cannot_be_attached(self):
        request = NS(id=uuid4(), student_user_id=uuid4(), status='WAITING_OPENING', target_session_id=None)
        db = MagicMock()
        db.scalar.return_value = request
        with patch.object(admin, 'list_annual_series_transfers', return_value=NS(requests=[NS(id=request.id, matching_series=[])])):
            with self.assertRaises(HTTPException):
                admin.update_annual_series_transfer_status(request.id, AdminAnnualSeriesTransferStatusUpdate(status='WAITING', target_session_id=uuid4()), db=db, actor=NS(id=uuid4()))
        db.commit.assert_not_called()

    def test_attach_keeps_original_priority_date_and_source(self):
        requested_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        source = uuid4()
        request = NS(id=uuid4(), student_user_id=uuid4(), status='WAITING_OPENING', target_session_id=None, requested_at=requested_at, source_booking_id=source)
        option = NS(session_id=uuid4(), recurrence_group_id=uuid4())
        db = MagicMock()
        db.scalar.side_effect = [request, None]
        with patch.object(admin, 'list_annual_series_transfers', return_value=NS(requests=[NS(id=request.id, matching_series=[option])])):
            admin.update_annual_series_transfer_status(request.id, AdminAnnualSeriesTransferStatusUpdate(status='WAITING', target_session_id=option.session_id), db=db, actor=NS(id=uuid4()))
        self.assertEqual(request.target_session_id, option.session_id)
        self.assertEqual(request.source_booking_id, source)
        self.assertEqual(request.requested_at, requested_at)
        self.assertEqual(request.status, 'WAITING')

if __name__ == '__main__':
    unittest.main()
