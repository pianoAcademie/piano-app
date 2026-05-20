from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import false, func, or_, select

from app.api.routes.clients import _active_formula_options_for_course_type, _session_purchase_catalog
from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, CreditType, Location
from app.models.plan import Plan, PlanCreditGrant, PlanEntitlement, PlanKind
from app.services.session_audience import resolve_session_booking_scopes

SCRIPT_PREFIX = "PROD_STUDIO_FORMULA_INSPECT"


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def main() -> None:
    from scripts.fix_prod_breethany_quote_f72c_booking_rates import main as fix_breethany_rates

    original_argv = sys.argv[:]
    sys.argv = [sys.argv[0], "--apply"]
    try:
        fix_breethany_rates()
    finally:
        sys.argv = original_argv
    return

    with SessionLocal() as db:
        studio_course_types = db.execute(
            select(
                CourseType.id,
                CourseType.name,
                CourseType.service_code,
                CourseType.credit_type_id,
                CreditType.code,
                CreditType.name,
            )
            .join(CreditType, CreditType.id == CourseType.credit_type_id, isouter=True)
            .where(func.lower(CourseType.name).like("%studio%"))
            .order_by(CourseType.name.asc())
        ).all()

        if not studio_course_types:
            _print("no studio course types found")
            return

        _print(f"studio_course_types={len(studio_course_types)}")
        for row in studio_course_types:
            course_type_id, name, service_code, credit_type_id, credit_code, credit_name = row
            _print(
                "course_type="
                f"{course_type_id}|name={name}|service_code={service_code or '-'}|"
                f"credit_type_id={credit_type_id or '-'}|credit_type_code={credit_code or '-'}|credit_type_name={credit_name or '-'}"
            )

            exact_public_plans = db.execute(
                select(
                    Plan.id,
                    Plan.code,
                    Plan.name,
                    Plan.kind,
                    Plan.active,
                    Plan.is_private,
                )
                .select_from(Plan)
                .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
                .where(
                    PlanEntitlement.course_type_id == course_type_id,
                    Plan.active.is_(True),
                    Plan.is_private.is_(False),
                )
                .order_by(Plan.name.asc())
            ).all()
            _print(f"exact_public_plans_for_{name}={len(exact_public_plans)}")
            for plan_id, plan_code, plan_name, kind, active, is_private in exact_public_plans:
                _print(
                    "exact_public_plan="
                    f"{plan_id}|code={plan_code}|name={plan_name}|kind={getattr(kind, 'value', kind)}|"
                    f"active={active}|private={is_private}"
                )

            entitlement_rows = db.execute(
                select(
                    Plan.id,
                    Plan.code,
                    Plan.name,
                    Plan.kind,
                    Plan.active,
                    Plan.is_private,
                    Plan.options_json,
                    PlanEntitlement.course_type_id,
                    PlanCreditGrant.credit_type_id,
                    PlanCreditGrant.credits_count,
                )
                .select_from(Plan)
                .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id, isouter=True)
                .join(PlanCreditGrant, PlanCreditGrant.plan_id == Plan.id, isouter=True)
                .where(
                    or_(
                        PlanEntitlement.course_type_id == course_type_id,
                        PlanCreditGrant.credit_type_id == credit_type_id if credit_type_id is not None else false(),
                        func.lower(Plan.name).like("%studio%"),
                        func.lower(Plan.code).like("%studio%"),
                    )
                )
                .order_by(Plan.name.asc())
            ).all()
            _print(f"matching_plan_rows_for_{name}={len(entitlement_rows)}")
            for prow in entitlement_rows:
                (
                    plan_id,
                    plan_code,
                    plan_name,
                    kind,
                    active,
                    is_private,
                    options_json,
                    entitlement_course_type_id,
                    grant_credit_type_id,
                    grant_credits_count,
                ) = prow
                _print(
                    "plan_row="
                    f"{plan_id}|code={plan_code}|name={plan_name}|kind={getattr(kind, 'value', kind)}|"
                    f"active={active}|private={is_private}|options={options_json}|"
                    f"entitlement_course_type_id={entitlement_course_type_id or '-'}|"
                    f"grant_credit_type_id={grant_credit_type_id or '-'}|grant_credits_count={grant_credits_count or 0}"
                )

            formula_options = _active_formula_options_for_course_type(
                db,
                course_type_id=course_type_id,
                course_type_name=name,
                course_type_service_code=service_code,
                credit_type_id=credit_type_id,
                allowed_plan_kinds={PlanKind.PACK, PlanKind.SUBSCRIPTION, PlanKind.FORFAIT},
            )
            _print(
                f"formula_options_for_{name}="
                + (
                    ",".join(
                        f"{option.formula_code}:{option.name}:{getattr(option.formula_type, 'value', option.formula_type)}"
                        for option in formula_options
                    )
                    or "-"
                )
            )

        now = datetime.now(timezone.utc)
        upcoming_sessions = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                func.lower(CourseType.name).like("%studio%"),
                CourseSession.start_at_utc >= now - timedelta(days=3),
                CourseSession.start_at_utc <= now + timedelta(days=30),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
        _print(f"upcoming_studio_sessions={len(upcoming_sessions)}")
        for session_obj, course_type, location in upcoming_sessions:
            formula_options, direct_payment_amount, direct_payment_currency, session_booking_scopes = _session_purchase_catalog(
                db,
                session_obj=session_obj,
                course_type=course_type,
            )
            _print(
                "session="
                f"{session_obj.id}|start_at_utc={session_obj.start_at_utc.isoformat()}|location={location.name}|"
                f"course_type={course_type.name}|course_type_id={course_type.id}|"
                f"credit_type_id={course_type.credit_type_id or '-'}|status={getattr(session_obj.status, 'value', session_obj.status)}|"
                f"price={session_obj.external_booking_price_ttc or '-'} EUR|"
                f"booking_scopes={','.join(scope.value for scope in resolve_session_booking_scopes(session_obj, allows_student_bookings=bool(course_type.allows_student_bookings)))}|"
                f"catalog_scopes={','.join(scope.value for scope in session_booking_scopes)}|"
                f"catalog_direct_payment={direct_payment_amount or '-'} {direct_payment_currency or '-'}|"
                f"catalog_formulas={(','.join(option.formula_code for option in formula_options) or '-')}"
            )


if __name__ == "__main__":
    main()
