from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from pypdf import PdfReader

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.teacher_invoicing import ComputedMissingSession, ComputedStatement
from app.services.teacher_statement_notifications import (
    TeacherPeriodCandidate,
    add_french_business_days,
    build_available_email,
    build_blocked_email,
    expected_payment_date,
    invoice_deadline,
    render_accounting_digest_pdf,
    run_teacher_statement_notification_job,
)


def _professor(*, vat: bool = False, vat_rate: Decimal | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        first_name="Rym" if vat else "Marie",
        last_name="Dupont",
        email="prof@example.com",
        teacher_is_vat_applicable=vat,
        teacher_vat_rate=vat_rate,
    )


def _computed(
    professor: SimpleNamespace,
    *,
    complete: bool = True,
    payor_name: str = "PIANO ACADEMIE",
) -> ComputedStatement:
    missing = []
    if not complete:
        missing = [
            ComputedMissingSession(
                session_id=uuid4(),
                title="Cours collectif enfants",
                start_at_utc=datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc),
                end_at_utc=datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc),
                pending_students_count=2,
                total_students_count=4,
            )
        ]
    vat_amount = Decimal("20.00") if professor.teacher_is_vat_applicable else Decimal("0.00")
    return ComputedStatement(
        teacher_id=professor.id,
        payor_legal_entity_id=uuid4(),
        payor_legal_entity_name=payor_name,
        year=2026,
        month=8,
        attendance_complete=complete,
        currency="EUR",
        totals_ht=Decimal("100.00"),
        totals_vat=vat_amount,
        totals_ttc=Decimal("100.00") + vat_amount,
        lines=[],
        missing_sessions=missing,
        vat_applicable=professor.teacher_is_vat_applicable,
        vat_rate=professor.teacher_vat_rate,
    )


class TeacherStatementNotificationTests(unittest.TestCase):
    def test_regular_deadline_and_payment_date(self) -> None:
        deadline = invoice_deadline(period_year=2026, period_month=8, notification_date=date(2026, 8, 21))

        self.assertEqual(deadline, date(2026, 9, 1))
        self.assertEqual(expected_payment_date(deadline), date(2026, 9, 4))

    def test_late_notification_keeps_two_business_days(self) -> None:
        deadline = invoice_deadline(period_year=2026, period_month=8, notification_date=date(2026, 9, 1))

        self.assertEqual(deadline, date(2026, 9, 3))
        self.assertEqual(expected_payment_date(deadline), date(2026, 9, 8))

    def test_business_days_exclude_weekends_and_french_holidays(self) -> None:
        self.assertEqual(add_french_business_days(date(2026, 4, 30), 1), date(2026, 5, 4))

    @patch("app.services.teacher_statement_notifications.resolve_frontend_base_url", return_value="https://app.piano-academie.com")
    def test_non_vat_email_uses_article_293_b_and_no_home_paragraph(self, _: MagicMock) -> None:
        professor = _professor()
        subject, body = build_available_email(
            MagicMock(),
            professor=professor,
            statements=[_computed(professor)],
            year=2026,
            month=8,
            notification_date=date(2026, 8, 21),
            language="fr",
        )

        self.assertIn("relevé de prestations", subject)
        self.assertIn("TVA non applicable, article 293 B du CGI", body)
        self.assertIn("01/09/2026", body)
        self.assertIn("04/09/2026", body)
        self.assertNotIn("Cours à domicile", body)

    @patch("app.services.teacher_statement_notifications.resolve_frontend_base_url", return_value="https://app.piano-academie.com")
    def test_vat_email_uses_configured_rate_and_home_paragraph(self, _: MagicMock) -> None:
        professor = _professor(vat=True, vat_rate=Decimal("20.00"))
        _, body = build_available_email(
            MagicMock(),
            professor=professor,
            statements=[_computed(professor, payor_name="PIANO ACADEMIE SERVICES")],
            year=2026,
            month=8,
            notification_date=date(2026, 8, 21),
            language="fr",
        )

        self.assertIn("TVA au taux configuré de 20.00 %", body)
        self.assertIn("Cours à domicile", body)
        self.assertIn("Piano Académie Services", body)

    @patch("app.services.teacher_statement_notifications.resolve_frontend_base_url", return_value="https://app.piano-academie.com")
    def test_blocked_email_lists_missing_attendance_and_explains_lock(self, _: MagicMock) -> None:
        professor = _professor()
        subject, body = build_blocked_email(
            MagicMock(),
            professor=professor,
            statements=[_computed(professor, complete=False)],
            year=2026,
            month=8,
            language="fr",
        )

        self.assertIn("bloqué", subject)
        self.assertIn("Cours collectif enfants", body)
        self.assertIn("2 présence(s) à compléter", body)
        self.assertIn("automatiquement débloqué", body)

    def test_accounting_pdf_distinguishes_non_vat_and_vat_amounts(self) -> None:
        no_vat_professor = _professor()
        vat_professor = _professor(vat=True, vat_rate=Decimal("20.00"))
        rows = []
        for professor, computed in (
            (no_vat_professor, _computed(no_vat_professor)),
            (vat_professor, _computed(vat_professor)),
        ):
            statement = SimpleNamespace(id=uuid4(), status="to_verify")
            rows.append((professor, statement, computed, "Attendue"))

        content = render_accounting_digest_pdf(
            year=2026,
            month=8,
            rows=rows,
            generated_at=datetime(2026, 9, 1, 5, 0, tzinfo=timezone.utc),
        )

        extracted = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        self.assertIn("Non applicable", extracted)
        self.assertIn("100.00 EUR", extracted)
        self.assertIn("120.00 EUR", extracted)
        self.assertIn("présences à compléter", extracted)

    @patch("app.services.teacher_statement_notifications._send_accounting_digest_if_due", return_value=0)
    @patch("app.services.teacher_statement_notifications._invoice_status", return_value="Attendue")
    @patch("app.services.teacher_statement_notifications.build_available_email", return_value=("Sujet", "Corps"))
    @patch("app.services.teacher_statement_notifications._professor_language", return_value="fr")
    @patch("app.services.teacher_statement_notifications._period_event_exists", return_value=False)
    @patch("app.services.teacher_statement_notifications.sync_teacher_monthly_statements")
    @patch("app.services.teacher_statement_notifications._period_candidates")
    @patch("app.services.teacher_statement_notifications.send_email")
    def test_dry_run_never_calls_email_provider(
        self,
        send_email_mock: MagicMock,
        candidates_mock: MagicMock,
        sync_mock: MagicMock,
        *_: MagicMock,
    ) -> None:
        professor = _professor()
        computed = _computed(professor)
        statement = SimpleNamespace(id=uuid4(), status="to_verify")
        candidate = TeacherPeriodCandidate(
            professor=professor,
            year=2026,
            month=8,
            last_course_end_at_utc=datetime(2026, 8, 20, 16, 0, tzinfo=timezone.utc),
        )
        candidates_mock.side_effect = lambda db, period, limit: [candidate] if period.month == 8 else []
        sync_mock.return_value = [(statement, computed)]

        before = run_teacher_statement_notification_job(
            MagicMock(),
            now=datetime(2026, 8, 20, 17, 59, tzinfo=timezone.utc),
            dry_run=True,
        )
        result = run_teacher_statement_notification_job(
            MagicMock(),
            now=datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc),
            dry_run=True,
        )

        self.assertEqual(before.available_sent, 0)
        self.assertEqual(before.skipped_not_due, 1)
        self.assertEqual(result.available_sent, 1)
        self.assertTrue(result.dry_run)
        send_email_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
