from uuid import uuid4

from helpers import ConfigurableAnalytics, ctx, plan_turn, registry, specialist_llm, synth_turn
from merchantos_agents import run_agent, to_agent_result
from merchantos_llm import FakeLLM, FakeTurn


def test_revenue_orders_aov_and_product_contribution() -> None:
    tenant = ctx()
    state = run_agent(
        name="analytics",
        llm=specialist_llm(
            "get_revenue_metrics",
            "get_order_metrics",
            "get_product_performance",
            summary="Revenue, orders, AOV, and product contribution are taken from tools.",
            category="revenue",
        ),
        tools=registry(),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="Why did revenue change and which products contributed?",
    )
    facts = {item.fact for item in state.evidence}
    assert any(item.startswith("revenue=") for item in facts)
    assert any(item.startswith("orders=") or item.startswith("previous_orders=") for item in facts)
    assert any("aov=" in item or item.startswith("aov_growth_pct=") for item in facts)
    assert any(item.startswith("product[") for item in facts)
    result = to_agent_result(state)
    assert result.findings[0].claim_kind.value == "FACT"
    assert result.findings[0].evidence_ids


def test_conflicting_growth_lowers_confidence() -> None:
    tenant = ctx()
    service = ConfigurableAnalytics(growth_override={"revenue": "12.40"})
    state = run_agent(
        name="analytics",
        llm=FakeLLM(
            [
                plan_turn("get_store_overview", "get_revenue_metrics"),
                synth_turn(
                    summary="Revenue signals conflict.",
                    category="anomaly",
                    proposed="HIGH",
                ),
            ]
        ),
        tools=registry(service),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="Why did revenue change?",
    )
    assert state.confidence_band is not None
    assert state.confidence_band.value == "LOW"
    assert any("conflict" in item.lower() for item in state.limitations)


def test_invalid_tool_arguments_are_recorded() -> None:
    tenant = ctx()
    state = run_agent(
        name="analytics",
        llm=FakeLLM(
            [
                FakeTurn(
                    {
                        "plan": "bad args",
                        "tools": [{"name": "get_product_performance", "arguments": {"limit": 0}}],
                        "insufficient_data": False,
                    }
                ),
                synth_turn(
                    summary="Insufficient evidence.",
                    category="product",
                    insufficient=True,
                ),
            ]
        ),
        tools=registry(),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="products",
    )
    assert state.tool_results[0].ok is False
    assert state.insufficient_data is True
