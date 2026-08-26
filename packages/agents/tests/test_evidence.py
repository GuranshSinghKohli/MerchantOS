from merchantos_agents.evidence import (
    extract_evidence,
    ground_findings,
    has_conflicting_evidence,
    resolve_confidence,
)
from merchantos_agents.state import ToolResult
from merchantos_domain import ClaimKind, ConfidenceBand, EvidenceItem, Finding


def test_extract_and_conflict_and_grounding() -> None:
    results = [
        ToolResult(
            name="get_revenue_metrics",
            ok=True,
            output={
                "kpis": {
                    "revenue": "80.00",
                    "previous": {"revenue": "100.00"},
                    "growth_pct": {"revenue": "-20.00"},
                }
            },
        ),
        ToolResult(
            name="get_store_overview",
            ok=True,
            output={"kpis": {"growth_pct": {"revenue": "12.00"}}},
        ),
    ]
    evidence = extract_evidence(results)
    assert any(item.fact == "revenue=80.00" for item in evidence)
    assert has_conflicting_evidence(evidence) is True
    draft = Finding(
        id="f_1",
        title="x",
        description="x",
        category="revenue",
        severity="info",
        claim_kind=ClaimKind.FACT,
        evidence_ids=["ev_missing"],
        confidence=ConfidenceBand.HIGH,
    )
    grounded, dropped = ground_findings([draft], evidence)
    assert grounded == []
    assert dropped
    band = resolve_confidence(
        evidence=evidence,
        findings=[],
        tool_errors=False,
        insufficient=False,
        conflicting=True,
        proposed=ConfidenceBand.HIGH,
        assumptions=[],
    )
    assert band is ConfidenceBand.LOW


def test_confidence_cannot_be_raised_by_model() -> None:
    evidence = [
        EvidenceItem(id="ev_1", source="get_customer_metrics", fact="customers=1"),
    ]
    band = resolve_confidence(
        evidence=evidence,
        findings=[],
        tool_errors=False,
        insufficient=False,
        conflicting=False,
        proposed=ConfidenceBand.HIGH,
        assumptions=["guess"],
    )
    assert band is ConfidenceBand.MEDIUM
