"""Round-trip regression on an isolated database; all changes rolled back."""
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import pytest
from sqlalchemy import select
from app.models.quote import QuoteLine
from app.schemas.quote import QuoteLineIn
from app.api.routes.quotes import (
    _materialize_quote_lines, _sync_typeform_planned_quote_line_quantities,
    _quote_monthly_service_amounts_ttc_for_schedule,
)
from tests.test_annual_pricing_postgres import case, URL

pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


def test_editor_recreates_lines_without_losing_planning_links(case):
    db, quote, lines, _, _, _ = case
    quote.pricing_catalog_id = None
    first, second = lines
    old_key = f"{first.activity_id}:line:{uuid4()}"
    second_key = f"{first.activity_id}:second_piano_course"
    first.quantity = 63
    second.quantity = 31
    first.meta = {"typeform_planned_quantity_applied": True}
    second.meta = {"typeform_planned_quantity_applied": True, "typeform_automatic_line": "second_piano_course"}
    second.unit_price_ttc = Decimal(32)
    second.unit_price_ht, second.unit_vat_amount = Decimal('26.67'), Decimal('5.33')
    quote.calendar_snapshot = {'sessions': [
        {'activity_id':str(first.activity_id), 'recommendation_key':key, 'date':date}
        for key,count,date in ((old_key,32,'2026-09-09'),(second_key,31,'2026-10-03'))
        for _ in range(count)
    ]}
    snapshot = deepcopy(quote.calendar_snapshot)
    db.flush()
    for _ in range(3):
        previous_ids = {line.id for line in lines}
        inputs = [QuoteLineIn(line_category='service', activity_id=line.activity_id, title=line.title,
                             pricing_unit='session', quantity=line.quantity, vat_rate=line.vat_rate,
                             unit_price_ttc=line.unit_price_ttc, sort_order=line.sort_order, meta=deepcopy(line.meta))
                  for line in lines]
        _materialize_quote_lines(db,quote=quote,lines_in=inputs)
        db.flush()
        lines = list(db.scalars(select(QuoteLine).where(QuoteLine.quote_id==quote.id).order_by(QuoteLine.sort_order)))
        assert not previous_ids.intersection(line.id for line in lines)
        _sync_typeform_planned_quote_line_quantities(lines,calendar_snapshot=quote.calendar_snapshot)
        db.flush(); db.expire_all()
        lines = list(db.scalars(select(QuoteLine).where(QuoteLine.quote_id==quote.id).order_by(QuoteLine.sort_order)))
        assert [line.quantity for line in lines] == [32,31]
        assert [line.unit_price_ttc for line in lines] == [38,32]
        assert sum(line.amount_ttc for line in lines) == Decimal(2208)
        assert lines[0].meta['recommendation_key'] == old_key
        assert quote.calendar_snapshot == snapshot
    # Distinct months prove monthly billing uses each line's own sessions, not
    # the 63-course activity pool. Hydration is not under test in this assertion.
    with patch('app.api.routes.quotes._calendar_snapshot_with_line_recommendation_keys',return_value=snapshot), \
         patch('app.api.routes.quotes._calendar_snapshot_with_planning_sessions',return_value=snapshot):
        assert _quote_monthly_service_amounts_ttc_for_schedule(db,quote) == {
            '2026-09': Decimal(1216), '2026-10': Decimal(992)}
