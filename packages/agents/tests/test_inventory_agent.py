from uuid import uuid4

import pytest
from helpers import (
    ConfigurableAnalytics,
    FakeAnalyticsService,
    ctx,
    plan_turn,
    registry,
    specialist_llm,
)
from merchantos_agents import run_agent
from merchantos_llm import FakeLLM
from merchantos_mcp import ToolError

LOW_STOCK = [
    {
        "product_gid": "gid://shopify/Product/1",
        "title": "Hero Mug",
        "revenue": "400.00",
        "units_sold": 40,
        "available": 0,
    },
    {
        "product_gid": "gid://shopify/Product/2",
        "title": "Slow Hat",
        "revenue": "5.00",
        "units_sold": 1,
        "available": 80,
    },
]


def test_low_inventory_and_high_performing_relationship() -> None:
    tenant = ctx()
    service = ConfigurableAnalytics(
        products=LOW_STOCK,
        inventory={
            "tracked_variants": 2,
            "in_stock_variants": 1,
            "out_of_stock_variants": 1,
            "available_units": 80,
            "on_hand_units": 80,
            "utilization_pct": "50.00",
        },
    )
    state = run_agent(
        name="inventory",
        llm=specialist_llm(
            "get_inventory_health",
            "get_product_performance",
            summary="Hero Mug is out of stock while selling; Slow Hat looks overstocked.",
            category="inventory",
        ),
        tools=registry(service),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="Which high-performing products have low inventory?",
    )
    facts = " ".join(item.fact for item in state.evidence)
    assert "out_of_stock_variants=1" in facts
    assert "available=0" in facts
    assert "available=80" in facts
    assert state.tool_results[0].name == "get_inventory_health"


def test_inventory_insufficient_and_no_invented_lead_time() -> None:
    tenant = ctx()
    state = run_agent(
        name="inventory",
        llm=specialist_llm(
            "get_inventory_health",
            summary="Insufficient evidence.",
            category="inventory",
            insufficient=True,
        ),
        tools=registry(FakeAnalyticsService(empty=True)),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="What reorder quantity should I use given a 21-day lead time?",
    )
    text = (state.answer or "") + " ".join(state.limitations)
    assert "Insufficient evidence" in text
    assert "21-day" not in (state.answer or "")


def test_inventory_cannot_use_customer_tool() -> None:
    tenant = ctx()
    with pytest.raises(ToolError):
        run_agent(
            name="inventory",
            llm=FakeLLM([plan_turn("get_customer_metrics")]),
            tools=registry(),
            tenant=tenant,
            run_id=uuid4(),
            request_id=tenant.request_id,
            question="customers?",
        )
