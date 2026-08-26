from merchantos_domain import (
    MAX_QUESTION_CHARS,
    TERMINAL_STATUSES,
    AgentRunStatus,
    AskResult,
    EvidenceItem,
)
from pydantic import ValidationError


def test_lifecycle_values() -> None:
    assert AgentRunStatus.PENDING.value == "PENDING"
    assert AgentRunStatus.RUNNING.value == "RUNNING"
    terminal = {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}
    assert terminal <= TERMINAL_STATUSES


def test_ask_result_rejects_approval_and_tenant() -> None:
    AskResult(answer="ok")
    try:
        AskResult.model_validate({"answer": "ok", "status": "APPROVED", "tenant_id": "x"})
        raise AssertionError("expected validation error")
    except ValidationError:
        pass


def test_evidence_is_bounded() -> None:
    EvidenceItem(source="get_store_overview", fact="orders=1")
    try:
        EvidenceItem(source="x", fact="f" * 501)
        raise AssertionError("expected validation error")
    except ValidationError:
        pass
    assert MAX_QUESTION_CHARS == 4000
