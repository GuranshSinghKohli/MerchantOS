from datetime import UTC, datetime

from merchantos_domain import (
    ConfidenceBand,
    IntelligenceReport,
    Recommendation,
    RecommendationPriority,
)
from pydantic import ValidationError


def test_report_and_recommendation_reject_execution_fields() -> None:
    rec = Recommendation(
        id="rec_1",
        title="Review inventory",
        recommendation="Investigate availability for the top product.",
        rationale="Units remaining are low relative to recent sales.",
        evidence_ids=["analytics:ev_1"],
        expected_objective="Avoid a stockout on a contributing SKU",
        priority=RecommendationPriority.HIGH,
        confidence=ConfidenceBand.MEDIUM,
    )
    try:
        Recommendation.model_validate({**rec.model_dump(), "approved_action": {}})
        raise AssertionError("expected validation error")
    except ValidationError:
        pass
    report = IntelligenceReport(
        report_id="r1",
        run_id="run1",
        question="Why is revenue down?",
        executive_summary="Revenue declined while inventory is tight.",
        recommendations=[rec],
        confidence=ConfidenceBand.MEDIUM,
        selected_agents=["analytics", "inventory"],
        generated_at=datetime.now(UTC),
    )
    dumped = report.model_dump()
    assert "tenant_id" not in dumped
    assert "approved_action" not in dumped
    try:
        IntelligenceReport.model_validate({**dumped, "tenant_id": "x"})
        raise AssertionError("expected validation error")
    except ValidationError:
        pass
