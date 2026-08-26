import pytest
from merchantos_mcp import ToolError, ToolErrorCode, ToolPermission, build_commerce_registry
from merchantos_mcp.allowlists import AGENT_TOOLS, TOOL_PERMISSION
from merchantos_mcp.tools import (
    CustomersOutput,
    HealthOutput,
    InventoryOutput,
    OpportunitiesOutput,
    OrdersOutput,
    OverviewOutput,
    ProductsOutput,
    RevenueOutput,
    TrendsOutput,
)

from .fakes import ALL_READ, FailingAnalyticsService, FakeAnalyticsService, boom_domain, session_ctx

TOOLS = (
    ("get_store_overview", OverviewOutput, "overview"),
    ("get_revenue_metrics", RevenueOutput, "revenue"),
    ("get_order_metrics", OrdersOutput, "orders"),
    ("get_product_performance", ProductsOutput, "products"),
    ("get_inventory_health", InventoryOutput, "inventory"),
    ("get_customer_metrics", CustomersOutput, "customers"),
    ("get_sales_trends", TrendsOutput, "sales_trends"),
    ("get_merchant_health", HealthOutput, "health"),
    ("get_opportunities", OpportunitiesOutput, "opportunities"),
)


def test_every_tool_valid_invocation_and_output_schema() -> None:
    service = FakeAnalyticsService()
    registry = build_commerce_registry(service)  # type: ignore[arg-type]
    ctx = session_ctx()
    for name, model, method in TOOLS:
        out = registry.invoke(name, {"preset": "last_30"}, ctx, permissions=ALL_READ)
        parsed = model.model_validate(out)
        assert parsed.request_id == str(ctx.request_id)
        assert parsed.store.store_id == str(ctx.store_id)
        assert method in service.calls
        assert TOOL_PERMISSION[name] is registry.get(name).permission


def test_empty_data_is_structured() -> None:
    registry = build_commerce_registry(FakeAnalyticsService(empty=True))  # type: ignore[arg-type]
    ctx = session_ctx()
    overview = registry.invoke("get_store_overview", {}, ctx, permissions=ALL_READ)
    assert overview["kpis"]["orders"] == 0
    products = registry.invoke("get_product_performance", {"limit": 10}, ctx, permissions=ALL_READ)
    assert products["items"] == []
    opportunities = registry.invoke("get_opportunities", {}, ctx, permissions=ALL_READ)
    assert opportunities["opportunities"] == []


def test_wrong_permission_is_unauthorized() -> None:
    registry = build_commerce_registry(FakeAnalyticsService())  # type: ignore[arg-type]
    ctx = session_ctx()
    with pytest.raises(ToolError) as err:
        registry.invoke(
            "get_order_metrics",
            {},
            ctx,
            permissions=frozenset({ToolPermission.ANALYTICS_READ}),
        )
    assert err.value.code == ToolErrorCode.UNAUTHORIZED


def test_dependency_failure_is_typed() -> None:
    registry = build_commerce_registry(FailingAnalyticsService(boom_domain()))  # type: ignore[arg-type]
    with pytest.raises(ToolError) as err:
        registry.invoke("get_store_overview", {}, session_ctx(), permissions=ALL_READ)
    assert err.value.code == ToolErrorCode.DEPENDENCY_FAILURE
    assert "Traceback" not in str(err.value)
    assert "db down" not in str(err.value)


def test_agent_ports_only_see_allowlisted_tools() -> None:
    registry = build_commerce_registry(FakeAnalyticsService())  # type: ignore[arg-type]
    analytics = registry.for_agent("analytics")
    names = {spec.name for spec in analytics.list_tools()}
    assert names == AGENT_TOOLS["analytics"]
    out = analytics.invoke("get_revenue_metrics", {}, session_ctx())
    assert "kpis" in out
    with pytest.raises(ToolError):
        analytics.invoke("get_customer_metrics", {}, session_ctx())
