from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from app.db.session import SessionLocal
from app.models.product_catalog import CatalogProduct, ProductCategory
from app.models.quote import Quote, QuoteLine
from app.models.repertoire import StudentSheetMusic, StudentSheetMusicEvent
from app.services.repertoire_progression import (
    ensure_previous_partition_for_reenrollment,
    first_active_piece,
    previous_partition_product,
)


SCRIPT_PREFIX = "reenrollment-repertoire-20260902"


def _is_true(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "oui"}


def _is_reenrollment(quote: Quote) -> bool:
    meta = quote.meta if isinstance(quote.meta, dict) else {}
    intake = meta.get("typeform_intake") if isinstance(meta.get("typeform_intake"), dict) else {}
    normalized = intake.get("normalized_payload") if isinstance(intake.get("normalized_payload"), dict) else {}
    for key in ("is_reenrollment", "reenrollment", "re_enrollment", "is_reinscription", "reinscription"):
        if key in normalized:
            return _is_true(normalized.get(key))
    return False


def _partition_lines(db, quote: Quote) -> list[tuple[QuoteLine, CatalogProduct]]:
    return list(
        db.execute(
            select(QuoteLine, CatalogProduct)
            .join(CatalogProduct, CatalogProduct.id == QuoteLine.product_id)
            .outerjoin(ProductCategory, ProductCategory.id == CatalogProduct.category_id)
            .where(
                QuoteLine.quote_id == quote.id,
                or_(
                    func.lower(QuoteLine.title).contains("partition"),
                    func.lower(CatalogProduct.title).contains("partition"),
                    func.lower(func.coalesce(ProductCategory.name, "")).contains("partition"),
                ),
            )
            .order_by(QuoteLine.sort_order, QuoteLine.id)
        ).all()
    )


def run(*, apply: bool) -> None:
    with SessionLocal() as db:
        quotes = db.scalars(
            select(Quote)
            .where(Quote.status == "approved", Quote.client_id.is_not(None))
            .order_by(Quote.approved_at, Quote.created_at, Quote.id)
        ).all()
        created_next = 0
        reused_next = 0
        created_previous = 0
        promoted_next = 0
        reenrollment_quotes = 0

        for quote in quotes:
            reenrollment = _is_reenrollment(quote)
            if reenrollment:
                reenrollment_quotes += 1
            for line, product in _partition_lines(db, quote):
                assignment = db.scalar(
                    select(StudentSheetMusic).where(StudentSheetMusic.source_quote_line_id == line.id)
                )
                if assignment is None:
                    assignment = db.scalar(
                        select(StudentSheetMusic)
                        .where(
                            StudentSheetMusic.student_id == quote.client_id,
                            StudentSheetMusic.product_id == product.id,
                            StudentSheetMusic.status != "COMPLETED",
                        )
                        .order_by(StudentSheetMusic.created_at.desc())
                        .limit(1)
                    )
                    if assignment is not None:
                        reused_next += 1
                    else:
                        assignment = StudentSheetMusic(
                            student_id=quote.client_id,
                            product_id=product.id,
                            title_snapshot=product.title,
                            status="STANDBY" if reenrollment else "TO_DELIVER",
                            source_quote_line_id=line.id,
                        )
                        db.add(assignment)
                        db.flush()
                        db.add(
                            StudentSheetMusicEvent(
                                assignment_id=assignment.id,
                                event_type="BACKFILLED_FROM_APPROVED_QUOTE",
                                new_status=assignment.status,
                            )
                        )
                        created_next += 1

                if not reenrollment:
                    continue
                previous_product = previous_partition_product(db, product)
                previous_existed = (
                    db.scalar(
                        select(StudentSheetMusic.id)
                        .where(
                            StudentSheetMusic.student_id == quote.client_id,
                            StudentSheetMusic.product_id == previous_product.id,
                        )
                        .limit(1)
                    )
                    is not None
                    if previous_product is not None
                    else False
                )
                previous = ensure_previous_partition_for_reenrollment(
                    db,
                    student_id=quote.client_id,
                    next_product=product,
                    actor_user_id=None,
                )
                if previous is None:
                    continue
                if not previous_existed:
                    created_previous += 1
                if previous.status == "COMPLETED" and assignment.status in {"STANDBY", "TO_DELIVER", "DELIVERED"}:
                    transition_at = previous.completed_at or datetime.now(timezone.utc)
                    first_piece = first_active_piece(db, assignment.product_id)
                    old_status = assignment.status
                    assignment.status = "IN_PROGRESS"
                    assignment.current_piece_id = first_piece.id if first_piece is not None else None
                    assignment.started_at = transition_at
                    assignment.delivered_at = assignment.delivered_at or transition_at
                    db.add(
                        StudentSheetMusicEvent(
                            assignment_id=assignment.id,
                            event_type="BACKFILL_AUTO_STARTED_AFTER_COMPLETION",
                            old_status=old_status,
                            new_status=assignment.status,
                            piece_id=assignment.current_piece_id,
                        )
                    )
                    promoted_next += 1

        print(
            f"[{SCRIPT_PREFIX}] mode={'apply' if apply else 'dry-run'}|"
            f"approved_quotes={len(quotes)}|reenrollment_quotes={reenrollment_quotes}|"
            f"created_next={created_next}|reused_next={reused_next}|"
            f"created_previous={created_previous}|promoted_next={promoted_next}"
        )
        if apply:
            db.commit()
            print(f"[{SCRIPT_PREFIX}] committed=true")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
