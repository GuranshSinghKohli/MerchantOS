from inspect import signature
from types import SimpleNamespace
from uuid import uuid4

from merchantos_app.policy import PolicyService
from merchantos_domain import (
    ActionSnapshot,
    ActionType,
    AgentActionProposal,
    TenantContext,
)


def _ctx() -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("write_products",),
        )
    )


def test_policy_has_no_llm_and_requires_approval_for_title() -> None:
    assert "llm" not in signature(PolicyService.evaluate).parameters
    snapshot = ActionSnapshot(
        before_state={},
        after_state={},
        payload={},
        payload_hash="x",
        affected_count=1,
    )
    decision = PolicyService().evaluate(
        _ctx(),
        AgentActionProposal(
            action_type=ActionType.UPDATE_PRODUCT_TITLE,
            resource_ids=(uuid4(),),
            rationale="clearer title",
        ),
        snapshot,
    )
    assert decision.verdict == "require_approval"
    assert decision.risk_level.value == "MEDIUM"


def test_price_and_bulk_are_blocked() -> None:
    service = PolicyService()
    ctx = _ctx()
    snap = ActionSnapshot(
        before_state={}, after_state={}, payload={}, payload_hash="x", affected_count=1
    )
    price = service.evaluate(
        ctx,
        AgentActionProposal(
            action_type=ActionType.UPDATE_VARIANT_PRICE,
            resource_ids=(uuid4(),),
            rationale="price",
        ),
        snap,
    )
    assert price.verdict == "block"
    bulk = ActionSnapshot(
        before_state={}, after_state={}, payload={}, payload_hash="x", affected_count=6
    )
    many = service.evaluate(
        ctx,
        AgentActionProposal(
            action_type=ActionType.UPDATE_PRODUCT_TITLE,
            resource_ids=tuple(uuid4() for _ in range(5)),
            rationale="bulk",
        ),
        bulk,
    )
    assert many.verdict == "block"
    assert many.risk_level.value == "CRITICAL"


def test_missing_write_scope_is_blocked() -> None:
    ctx = TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("read_products",),
        )
    )
    decision = PolicyService().evaluate(
        ctx,
        AgentActionProposal(
            action_type=ActionType.UPDATE_PRODUCT_TITLE,
            resource_ids=(uuid4(),),
            rationale="clearer title",
        ),
        ActionSnapshot(
            before_state={}, after_state={}, payload={}, payload_hash="x", affected_count=1
        ),
    )
    assert decision.verdict == "block"
