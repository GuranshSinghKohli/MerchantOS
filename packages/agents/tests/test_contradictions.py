from merchantos_agents.contradictions import detect_contradictions
from merchantos_domain import EvidenceItem


def test_opposite_growth_signs_are_unresolved() -> None:
    found = detect_contradictions(
        [
            EvidenceItem(id="a:ev_1", source="get_revenue_metrics", fact="revenue_growth_pct=12.4"),
            EvidenceItem(id="i:ev_1", source="get_store_overview", fact="revenue_growth_pct=-8.0"),
        ]
    )
    assert len(found) == 1
    assert found[0].status == "unresolved"
    assert found[0].metric == "revenue_growth_pct"


def test_same_sign_and_non_growth_facts_are_not_conflicts() -> None:
    found = detect_contradictions(
        [
            EvidenceItem(id="a:ev_1", source="get_revenue_metrics", fact="revenue_growth_pct=4.0"),
            EvidenceItem(id="a:ev_2", source="get_store_overview", fact="revenue_growth_pct=1.0"),
            EvidenceItem(id="i:ev_1", source="get_inventory_health", fact="available_units=3"),
        ]
    )
    assert found == []
