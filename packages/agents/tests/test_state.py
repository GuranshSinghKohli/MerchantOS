from uuid import uuid4

import pytest
from merchantos_agents import AgentState
from merchantos_domain import AgentRunStatus, ForbiddenFactoryError, TenantContext
from pydantic import ValidationError


def test_valid_and_invalid_state() -> None:
    state = AgentState(run_id=str(uuid4()), request_id=str(uuid4()), question="How is revenue?")
    assert state.status is AgentRunStatus.RUNNING
    assert not hasattr(state, "tenant_id")
    with pytest.raises(ValidationError):
        AgentState(
            run_id="r",
            request_id="q",
            question="x",
            tenant_id="nope",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        AgentState.model_validate(
            {
                "run_id": "r",
                "request_id": "q",
                "question": "x",
                "approval": {"status": "APPROVED"},
            }
        )


def test_tenant_cannot_be_constructed_from_state() -> None:
    assert not hasattr(TenantContext, "from_agent_state")
    with pytest.raises(ForbiddenFactoryError):
        TenantContext.model_validate({"merchant_id": str(uuid4()), "store_id": str(uuid4())})
