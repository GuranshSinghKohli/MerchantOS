from merchantos_domain import AgentResult, AskResult, ClaimKind, ConfidenceBand, Finding
from pydantic import ValidationError


def test_finding_and_agent_result_reject_approval() -> None:
    finding = Finding(
        id="f_1",
        title="Revenue decreased",
        description="Revenue decreased 12.4%.",
        category="revenue",
        severity="watch",
        claim_kind=ClaimKind.FACT,
        evidence_ids=["ev_1"],
        confidence=ConfidenceBand.HIGH,
    )
    AgentResult(
        agent_name="analytics",
        run_id="r",
        summary="Revenue decreased 12.4%.",
        findings=[finding],
        evidence=[],
        confidence=ConfidenceBand.MEDIUM,
    )
    try:
        Finding.model_validate({**finding.model_dump(), "tenant_id": "x", "status": "APPROVED"})
        raise AssertionError("expected validation error")
    except ValidationError:
        pass
    AskResult(answer="ok", findings=[finding], confidence_band=ConfidenceBand.LOW)
