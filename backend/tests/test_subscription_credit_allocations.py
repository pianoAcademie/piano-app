from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.plan import PlanCreditGrantsRelation, PlanKind
from app.services.subscription_credit_allocations import subscription_credit_allocations


def test_and_pack_exposes_remaining_credits_by_type() -> None:
    subscription_id = uuid4()
    plan_id = uuid4()
    studio_credit_type_id = uuid4()
    piano_credit_type_id = uuid4()
    subscription = SimpleNamespace(id=subscription_id)
    plan = SimpleNamespace(
        id=plan_id,
        kind=PlanKind.PACK,
        credit_grants_relation=PlanCreditGrantsRelation.AND,
    )
    grants_result = MagicMock()
    grants_result.all.return_value = [
        (plan_id, studio_credit_type_id, "CREDIT_STUDIO", "Credit reservation studio", 6),
        (plan_id, piano_credit_type_id, "CREDIT_PIANO_ONSITE", "Credit cours de piano en presentiel", 6),
    ]
    usage_result = MagicMock()
    usage_result.all.return_value = [(subscription_id, studio_credit_type_id, 2)]
    db = MagicMock()
    db.execute.side_effect = [grants_result, usage_result]

    result = subscription_credit_allocations(db, subscriptions=[(subscription, plan)])

    assert result[subscription_id][0]["credits_remaining"] == 4
    assert result[subscription_id][1]["credits_remaining"] == 6


def test_or_pack_keeps_shared_credit_pool_without_fake_breakdown() -> None:
    subscription = SimpleNamespace(id=uuid4())
    plan = SimpleNamespace(
        id=uuid4(),
        kind=PlanKind.PACK,
        credit_grants_relation=PlanCreditGrantsRelation.OR,
    )
    db = MagicMock()

    assert subscription_credit_allocations(db, subscriptions=[(subscription, plan)]) == {}
    db.execute.assert_not_called()
