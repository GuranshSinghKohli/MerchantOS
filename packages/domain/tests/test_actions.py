from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_domain import (
    ActionType,
    AgentActionProposal,
    ApprovedAction,
    ForbiddenFactoryError,
    NotApprovedError,
    TenantContext,
)
from pydantic import ValidationError


def _ctx():
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("write_products",),
        )
    )


def test_proposal_rejects_approval_and_payload_fields() -> None:
    with pytest.raises(ValidationError):
        AgentActionProposal.model_validate(
            {
                "action_type": ActionType.UPDATE_PRODUCT_TITLE,
                "resource_ids": [str(uuid4())],
                "rationale": "rename",
                "status": "APPROVED",
                "payload": {"title": "x"},
            }
        )


def test_approved_action_cannot_be_built_from_llm_dict() -> None:
    with pytest.raises(ForbiddenFactoryError):
        ApprovedAction.model_validate(
            {
                "action_id": str(uuid4()),
                "approval_id": str(uuid4()),
                "merchant_id": str(uuid4()),
                "store_id": str(uuid4()),
                "action_type": "update_product_title",
                "payload": {},
                "payload_hash": "x",
                "mutation": "update_product_title",
                "status": "APPROVED",
            }
        )


def test_load_rejects_proposed_rejected_expired_and_hash_mismatch() -> None:
    ctx = _ctx()
    now = datetime.now(UTC)
    kwargs = {
        "action_id": uuid4(),
        "approval_id": uuid4(),
        "action_merchant_id": ctx.merchant_id,
        "action_store_id": ctx.store_id,
        "action_type": ActionType.UPDATE_PRODUCT_TITLE.value,
        "payload": {"shopify_gid": "gid://shopify/Product/1", "title": "N"},
        "payload_hash": "abc",
        "frozen_payload_hash": "abc",
        "expires_at": now + timedelta(hours=1),
        "now": now,
    }
    with pytest.raises(NotApprovedError):
        ApprovedAction.load(ctx, action_status="PROPOSED", approval_status="APPROVED", **kwargs)
    with pytest.raises(NotApprovedError):
        ApprovedAction.load(ctx, action_status="APPROVED", approval_status="REJECTED", **kwargs)
    with pytest.raises(NotApprovedError):
        ApprovedAction.load(
            ctx,
            action_status="APPROVED",
            approval_status="APPROVED",
            **{**kwargs, "frozen_payload_hash": "other"},
        )
    with pytest.raises(NotApprovedError):
        ApprovedAction.load(
            ctx,
            action_status="APPROVED",
            approval_status="APPROVED",
            **{**kwargs, "expires_at": now - timedelta(seconds=1)},
        )
    loaded = ApprovedAction.load(
        ctx, action_status="APPROVED", approval_status="APPROVED", **kwargs
    )
    assert loaded.action_type is ActionType.UPDATE_PRODUCT_TITLE
    foreign = TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("write_products",),
        )
    )
    with pytest.raises(NotApprovedError):
        ApprovedAction.load(foreign, action_status="APPROVED", approval_status="APPROVED", **kwargs)
    with pytest.raises(NotApprovedError):
        ApprovedAction.load(
            ctx,
            action_status="APPROVED",
            approval_status="APPROVED",
            **{**kwargs, "action_type": "delete_product"},
        )
