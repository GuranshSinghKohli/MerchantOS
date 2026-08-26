from uuid import uuid4

from helpers import FakeAnalyticsService, ctx, registry, specialist_llm
from merchantos_agents import run_agent, to_agent_result


def test_new_vs_returning_growth_and_repeat() -> None:
    tenant = ctx()
    state = run_agent(
        name="customer",
        llm=specialist_llm(
            "get_customer_metrics",
            summary="New customers 1, returning 0; growth is taken from KPIs.",
            category="customer",
        ),
        tools=registry(),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="How are new vs returning customers changing?",
    )
    facts = {item.fact for item in state.evidence}
    assert any(item.startswith("new_customers=") for item in facts)
    assert any(item.startswith("returning_customers=") for item in facts)
    assert any("customers_growth_pct=" in item or item.startswith("customers=") for item in facts)
    dumped = to_agent_result(state).model_dump_json()
    assert "@" not in dumped
    assert "email" not in dumped
    assert "churn" not in dumped
    assert "lifetime value" not in dumped.lower()


def test_customer_insufficient_and_privacy() -> None:
    tenant = ctx()
    state = run_agent(
        name="customer",
        llm=specialist_llm(
            "get_customer_metrics",
            summary="Insufficient evidence.",
            category="customer",
            insufficient=True,
        ),
        tools=registry(FakeAnalyticsService(empty=True)),
        tenant=tenant,
        run_id=uuid4(),
        request_id=tenant.request_id,
        question="What is churn probability and LTV for jane@example.com?",
    )
    text = f"{state.answer} {state.limitations} {state.findings}"
    assert "Insufficient evidence" in text
    assert "jane@example.com" not in text
    assert "churn probability" not in text.lower()
