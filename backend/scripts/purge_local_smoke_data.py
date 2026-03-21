from __future__ import annotations

import argparse
import os
import sys
from collections import OrderedDict
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import bindparam, text

from app.core.config import settings
from app.db.session import SessionLocal


TEST_EMAIL_PATTERNS = ("%@example.com", "%@piano-academie.test")


def _require_local_like_context(*, force: bool) -> None:
    local_markers = ("localhost", "127.0.0.1", "piano-app", "piano_academie")
    current = " ".join(
        [
            settings.frontend_base_url,
            settings.database_url,
        ]
    ).lower()
    if force or any(marker in current for marker in local_markers):
        return
    raise SystemExit(
        "Refus de lancer la purge hors contexte local detecte. "
        "Utilisez --force si vous savez exactement ce que vous faites."
    )


def _select_ids(db, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    return [row[0] for row in db.execute(text(sql), params or {}).all()]


def _delete_ids(db, *, table: str, column: str, ids: list[Any]) -> int:
    if not ids:
        return 0
    stmt = text(f"delete from {table} where {column} in :ids").bindparams(bindparam("ids", expanding=True))
    return db.execute(stmt, {"ids": ids}).rowcount or 0


def _delete_by_conditions(
    db,
    *,
    table: str,
    conditions: list[tuple[str, list[Any]]],
) -> int:
    active = [(column, ids) for column, ids in conditions if ids]
    if not active:
        return 0
    clauses = [f"{column} in :{column}" for column, _ in active]
    stmt = text(f"delete from {table} where {' or '.join(clauses)}")
    for column, _ in active:
        stmt = stmt.bindparams(bindparam(column, expanding=True))
    params = {column: ids for column, ids in active}
    return db.execute(stmt, params).rowcount or 0


def _collect_targets(db) -> dict[str, list[Any]]:
    test_user_ids = _select_ids(
        db,
        """
        select id
        from users
        where lower(email) like any(:patterns)
        """,
        {"patterns": list(TEST_EMAIL_PATTERNS)},
    )
    test_prospect_ids = _select_ids(
        db,
        """
        select id
        from prospects
        where lower(email) like any(:patterns)
        """,
        {"patterns": list(TEST_EMAIL_PATTERNS)},
    )
    smoke_course_type_ids = _select_ids(
        db,
        """
        select id
        from course_types
        where service_code = 'TYPEFORM_DEMO'
           or code like 'SMK_%'
           or lower(coalesce(code, '')) like '%smoke%'
           or lower(coalesce(name, '')) like '%smoke%'
           or lower(coalesce(description, '')) like '%smoke%'
        """,
    )
    smoke_session_ids = _select_ids(
        db,
        """
        select id
        from course_sessions
        where course_type_id = any(:course_type_ids)
           or coalesce(private_description, '') like 'TYPEFORM_DEMO|%'
           or lower(coalesce(title, '')) like '%smoke%'
           or lower(coalesce(description, '')) like '%smoke%'
           or lower(coalesce(group_note, '')) like '%smoke%'
           or lower(coalesce(professor_reminder_note, '')) like '%smoke%'
           or lower(coalesce(zoom_link, '')) like '%smoke%'
        """,
        {"course_type_ids": smoke_course_type_ids or [None]},
    )
    smoke_plan_ids = _select_ids(
        db,
        """
        select id
        from plans
        where lower(coalesce(code, '')) like 'smk_%'
           or lower(coalesce(code, '')) like '%smoke%'
           or lower(coalesce(name, '')) like '%smoke%'
           or lower(coalesce(description, '')) like '%smoke%'
        """,
    )
    demo_form_config_ids = _select_ids(
        db,
        """
        select id
        from typeform_form_configs
        where configuration_json::text like '%TF_DEMO_%'
        """,
    )
    demo_quote_ids = _select_ids(
        db,
        """
        select id
        from quotes
        where prospect_id = any(:prospect_ids)
           or client_id = any(:user_ids)
           or coalesce(meta->>'demo_case_key', '') <> ''
           or coalesce(meta->>'demo_seed', '') in ('true', 'True')
        """,
        {
            "prospect_ids": test_prospect_ids or [None],
            "user_ids": test_user_ids or [None],
        },
    )
    demo_intake_ids = _select_ids(
        db,
        """
        select id
        from typeform_intakes
        where source_response_id like 'demo_%'
           or source_response_id like 'demo_quote_case_%'
           or form_config_id = any(:form_config_ids)
           or related_quote_id = any(:quote_ids)
        """,
        {
            "form_config_ids": demo_form_config_ids or [None],
            "quote_ids": demo_quote_ids or [None],
        },
    )
    demo_communication_ids = _select_ids(
        db,
        """
        select id
        from communication_logs
        where lower(coalesce(recipient, '')) like any(:patterns)
           or recipient_user_id = any(:user_ids)
           or sender_user_id = any(:user_ids)
           or lower(coalesce(subject, '')) like '%smoke%'
           or lower(coalesce(subject, '')) like '%demo%'
           or lower(coalesce(content, '')) like '%smoke%'
           or lower(coalesce(content, '')) like '%demo%'
        """,
        {
            "patterns": list(TEST_EMAIL_PATTERNS),
            "user_ids": test_user_ids or [None],
        },
    )
    demo_subscription_ids = _select_ids(
        db,
        """
        select id
        from client_plan_subscriptions
        where user_id = any(:user_ids)
           or payer_contact_id = any(:user_ids)
           or plan_id = any(:plan_ids)
        """,
        {
            "user_ids": test_user_ids or [None],
            "plan_ids": smoke_plan_ids or [None],
        },
    )
    smoke_professor_ids = _select_ids(
        db,
        """
        select id
        from professors
        where lower(coalesce(email, '')) like '%@example.com'
        """,
    )
    return {
        "test_user_ids": test_user_ids,
        "test_prospect_ids": test_prospect_ids,
        "smoke_course_type_ids": smoke_course_type_ids,
        "smoke_session_ids": smoke_session_ids,
        "smoke_plan_ids": smoke_plan_ids,
        "demo_form_config_ids": demo_form_config_ids,
        "demo_quote_ids": demo_quote_ids,
        "demo_intake_ids": demo_intake_ids,
        "demo_communication_ids": demo_communication_ids,
        "demo_subscription_ids": demo_subscription_ids,
        "smoke_professor_ids": smoke_professor_ids,
    }


def _summarize_targets(targets: dict[str, list[Any]]) -> OrderedDict[str, int]:
    return OrderedDict((label, len(values)) for label, values in targets.items())


def _purge(db, targets: dict[str, list[Any]]) -> OrderedDict[str, int]:
    deleted: OrderedDict[str, int] = OrderedDict()
    quote_ids = targets["demo_quote_ids"]
    intake_ids = targets["demo_intake_ids"]
    form_config_ids = targets["demo_form_config_ids"]
    communication_ids = targets["demo_communication_ids"]
    session_ids = targets["smoke_session_ids"]
    activity_ids = targets["smoke_course_type_ids"]
    plan_ids = targets["smoke_plan_ids"]
    subscription_ids = targets["demo_subscription_ids"]
    prospect_ids = targets["test_prospect_ids"]
    user_ids = targets["test_user_ids"]
    professor_ids = targets["smoke_professor_ids"]

    deleted["typeform_intakes"] = _delete_ids(db, table="typeform_intakes", column="id", ids=intake_ids)
    deleted["quote_acceptance_followups"] = _delete_ids(
        db, table="quote_acceptance_followups", column="quote_id", ids=quote_ids
    )
    deleted["quote_document_snapshots"] = _delete_ids(
        db, table="quote_document_snapshots", column="quote_id", ids=quote_ids
    )
    deleted["quote_email_outbox"] = _delete_ids(db, table="quote_email_outbox", column="quote_id", ids=quote_ids)
    deleted["quote_events"] = _delete_ids(db, table="quote_events", column="quote_id", ids=quote_ids)
    deleted["quote_lines"] = _delete_ids(db, table="quote_lines", column="quote_id", ids=quote_ids)
    deleted["quotes"] = _delete_ids(db, table="quotes", column="id", ids=quote_ids)

    deleted["communication_logs"] = _delete_ids(
        db, table="communication_logs", column="id", ids=communication_ids
    )

    deleted["bookings"] = _delete_by_conditions(
        db,
        table="bookings",
        conditions=[
            ("session_id", session_ids),
            ("user_id", user_ids),
            ("client_plan_subscription_id", subscription_ids),
        ],
    )
    deleted["notifications"] = _delete_ids(db, table="notifications", column="slot_id", ids=session_ids)
    deleted["professor_session_messages"] = _delete_ids(
        db, table="professor_session_messages", column="session_id", ids=session_ids
    )
    deleted["professor_session_payouts"] = _delete_ids(
        db, table="professor_session_payouts", column="session_id", ids=session_ids
    )
    deleted["course_sessions"] = _delete_ids(db, table="course_sessions", column="id", ids=session_ids)

    deleted["client_forfait_activity_pricing"] = _delete_by_conditions(
        db,
        table="client_forfait_activity_pricing",
        conditions=[
            ("subscription_id", subscription_ids),
            ("course_type_id", activity_ids),
        ],
    )
    deleted["client_plan_subscriptions"] = _delete_by_conditions(
        db,
        table="client_plan_subscriptions",
        conditions=[
            ("id", subscription_ids),
            ("plan_id", plan_ids),
            ("user_id", user_ids),
            ("payer_contact_id", user_ids),
        ],
    )

    deleted["professor_contract_grid_lines"] = _delete_ids(
        db, table="professor_contract_grid_lines", column="course_type_id", ids=activity_ids
    )
    deleted["teacher_invoice_lines"] = _delete_ids(
        db, table="teacher_invoice_lines", column="course_type_id", ids=activity_ids
    )
    deleted["teacher_statement_messages"] = _delete_ids(
        db, table="teacher_statement_messages", column="teacher_id", ids=professor_ids
    )
    deleted["teacher_invoice_audit_events"] = _delete_ids(
        db, table="teacher_invoice_audit_events", column="teacher_id", ids=professor_ids
    )
    deleted["teacher_invoices"] = _delete_ids(db, table="teacher_invoices", column="teacher_id", ids=professor_ids)
    deleted["teacher_monthly_statements"] = _delete_ids(
        db, table="teacher_monthly_statements", column="teacher_id", ids=professor_ids
    )
    deleted["professor_salary_payments"] = _delete_ids(
        db, table="professor_salary_payments", column="professor_id", ids=professor_ids
    )
    deleted["professor_session_messages_by_professor"] = _delete_ids(
        db, table="professor_session_messages", column="professor_id", ids=professor_ids
    )
    deleted["professor_session_payouts_by_professor"] = _delete_ids(
        db, table="professor_session_payouts", column="professor_id", ids=professor_ids
    )
    deleted["professor_hourly_rates"] = _delete_ids(
        db, table="professor_hourly_rates", column="professor_id", ids=professor_ids
    )
    deleted["professor_permissions"] = _delete_ids(
        db, table="professor_permissions", column="professor_id", ids=professor_ids
    )
    deleted["professor_contract_grids"] = _delete_ids(
        db, table="professor_contract_grids", column="professor_id", ids=professor_ids
    )
    deleted["plans"] = _delete_ids(db, table="plans", column="id", ids=plan_ids)
    deleted["course_types"] = _delete_ids(db, table="course_types", column="id", ids=activity_ids)
    deleted["professors"] = _delete_ids(db, table="professors", column="id", ids=professor_ids)

    deleted["typeform_form_configs"] = _delete_ids(
        db, table="typeform_form_configs", column="id", ids=form_config_ids
    )
    deleted["prospects"] = _delete_ids(db, table="prospects", column="id", ids=prospect_ids)
    deleted["users"] = _delete_ids(db, table="users", column="id", ids=user_ids)

    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Supprime localement les donnees smoke/demo/test sans toucher aux activites metier."
    )
    parser.add_argument("--apply", action="store_true", help="Execute effectivement la purge.")
    parser.add_argument("--force", action="store_true", help="Bypass la garde anti-prod.")
    args = parser.parse_args()

    _require_local_like_context(force=args.force)

    with SessionLocal() as db:
        targets = _collect_targets(db)
        summary = _summarize_targets(targets)
        print("Cibles detectees :")
        for label, count in summary.items():
            print(f"- {label}: {count}")

        if not args.apply:
            print("\nDry-run termine. Relancez avec --apply pour supprimer.")
            return

        deleted = _purge(db, targets)
        db.commit()

        print("\nSuppression executee :")
        for label, count in deleted.items():
            print(f"- {label}: {count}")

        remaining = _summarize_targets(_collect_targets(db))
        print("\nReste apres purge :")
        for label, count in remaining.items():
            print(f"- {label}: {count}")


if __name__ == "__main__":
    main()
