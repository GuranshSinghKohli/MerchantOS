from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_domain import ForbiddenFactoryError, QueueMessage, TenantContext
from merchantos_domain.actions import ActionType, AgentActionProposal
from merchantos_domain.queue_message import JobKind
from pydantic import ValidationError


def _session() -> SimpleNamespace:
    return SimpleNamespace(
        merchant_id=uuid4(),
        store_id=uuid4(),
        user_id=uuid4(),
        request_id=uuid4(),
        scopes=("read_products",),
    )


def test_from_session_and_job_row() -> None:
    session = _session()
    ctx = TenantContext.from_session(session)
    assert ctx.merchant_id == session.merchant_id
    job = SimpleNamespace(
        merchant_id=session.merchant_id,
        store_id=session.store_id,
        user_id=None,
        request_id=session.request_id,
        scopes=(),
    )
    from_job = TenantContext.from_job_row(job)
    assert from_job.user_id is None
    assert from_job.merchant_id == session.merchant_id


def test_constructor_and_dict_validation_are_forbidden() -> None:
    session = _session()
    with pytest.raises(ForbiddenFactoryError):
        TenantContext(
            merchant_id=session.merchant_id,
            store_id=session.store_id,
            user_id=session.user_id,
            request_id=session.request_id,
            scopes=session.scopes,
        )
    with pytest.raises(ForbiddenFactoryError):
        TenantContext.model_validate(
            {
                "merchant_id": str(session.merchant_id),
                "store_id": str(session.store_id),
                "user_id": None,
                "request_id": str(session.request_id),
                "scopes": [],
            }
        )


def test_no_queue_message_factory() -> None:
    assert not hasattr(TenantContext, "from_queue_message")
    assert not hasattr(TenantContext, "from_tool_args")


def test_queue_message_rejects_tenant_fields() -> None:
    with pytest.raises(ValidationError):
        QueueMessage.model_validate(
            {
                "job_kind": JobKind.AGENT_RUN,
                "job_id": str(uuid4()),
                "merchant_id": str(uuid4()),
            }
        )


def test_proposal_rejects_approval_fields() -> None:
    with pytest.raises(ValidationError):
        AgentActionProposal.model_validate(
            {
                "action_type": ActionType.UPDATE_VARIANT_PRICE,
                "resource_ids": [str(uuid4())],
                "rationale": "x",
                "status": "APPROVED",
            }
        )
