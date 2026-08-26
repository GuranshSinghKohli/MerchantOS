from datetime import UTC, datetime
from typing import Any

from merchantos_app import AnalyticsFilters, AnalyticsService
from merchantos_domain import CompareMode, DatePreset, TenantContext
from pydantic import BaseModel, ConfigDict

from merchantos_mcp.permissions import RiskLevel, ToolPermission
from merchantos_mcp.registry import ToolRegistry
from merchantos_mcp.schemas import DateRangeInput, ProductPerformanceInput, ToolEnvelope
from merchantos_mcp.spec import ToolSpec


class OverviewOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    kpis: dict[str, Any]
    health: dict[str, Any]
    trends: dict[str, Any]
    opportunities: list[dict[str, Any]]


class RevenueOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    kpis: dict[str, Any]
    trend: list[dict[str, Any]]


class OrdersOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    orders: int
    trend: list[dict[str, Any]]


class ProductsOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]


class InventoryOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    inventory: dict[str, Any]


class CustomersOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    kpis: dict[str, Any]


class TrendsOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    revenue: list[dict[str, Any]]
    customers: list[dict[str, Any]]


class HealthOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    health: dict[str, Any]


class OpportunitiesOutput(ToolEnvelope):
    model_config = ConfigDict(extra="ignore")
    opportunities: list[dict[str, Any]]


def _as_preset(value: object) -> DatePreset:
    return value if isinstance(value, DatePreset) else DatePreset(str(value))


def _as_compare(value: object) -> CompareMode:
    return value if isinstance(value, CompareMode) else CompareMode(str(value))


def _filters(ctx: TenantContext, args: dict[str, Any]) -> AnalyticsFilters:
    return AnalyticsFilters(
        request_id=ctx.request_id,
        preset=_as_preset(args["preset"]),
        compare=_as_compare(args["compare"]),
        date_from=args.get("date_from"),
        date_to=args.get("date_to"),
        now=datetime.now(UTC),
        limit=int(args.get("limit", 25)),
        offset=int(args.get("offset", 0)),
        sort=str(args.get("sort", "revenue")),
    )


def _spec(
    *,
    name: str,
    description: str,
    permission: ToolPermission,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
    handler: Any,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        input_model=input_model,
        output_model=output_model,
        permission=permission,
        risk_level=RiskLevel.LOW,
        tenant_required=True,
        timeout_seconds=5.0,
        read_only=True,
        handler=handler,
    )


def build_commerce_registry(service: AnalyticsService) -> ToolRegistry:
    """Explicit read-only commerce tools. No SQL, HTTP, or Shopify mutations."""

    def overview(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.overview(ctx, _filters(ctx, args))

    def revenue(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.revenue(ctx, _filters(ctx, args))

    def orders(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.orders(ctx, _filters(ctx, args))

    def products(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.products(ctx, _filters(ctx, args))

    def inventory(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.inventory(ctx, _filters(ctx, args))

    def customers(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.customers(ctx, _filters(ctx, args))

    def trends(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.sales_trends(ctx, _filters(ctx, args))

    def health(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.health(ctx, _filters(ctx, args))

    def opportunities(ctx: TenantContext, args: dict[str, Any]) -> dict[str, object]:
        return service.opportunities(ctx, _filters(ctx, args))

    return ToolRegistry(
        (
            _spec(
                name="get_store_overview",
                description="Store KPIs, trends, health, and deterministic opportunities.",
                permission=ToolPermission.ANALYTICS_READ,
                input_model=DateRangeInput,
                output_model=OverviewOutput,
                handler=overview,
            ),
            _spec(
                name="get_revenue_metrics",
                description="Included-order revenue, AOV, and daily revenue trend.",
                permission=ToolPermission.ANALYTICS_READ,
                input_model=DateRangeInput,
                output_model=RevenueOutput,
                handler=revenue,
            ),
            _spec(
                name="get_order_metrics",
                description="Included order counts, exclusions, and daily order trend.",
                permission=ToolPermission.ORDERS_READ,
                input_model=DateRangeInput,
                output_model=OrdersOutput,
                handler=orders,
            ),
            _spec(
                name="get_product_performance",
                description="Paginated product units, revenue, and availability.",
                permission=ToolPermission.PRODUCTS_READ,
                input_model=ProductPerformanceInput,
                output_model=ProductsOutput,
                handler=products,
            ),
            _spec(
                name="get_inventory_health",
                description="Latest inventory coverage and utilization.",
                permission=ToolPermission.INVENTORY_READ,
                input_model=DateRangeInput,
                output_model=InventoryOutput,
                handler=inventory,
            ),
            _spec(
                name="get_customer_metrics",
                description="New and returning ordering customers. Emails are never returned.",
                permission=ToolPermission.CUSTOMERS_READ,
                input_model=DateRangeInput,
                output_model=CustomersOutput,
                handler=customers,
            ),
            _spec(
                name="get_sales_trends",
                description="Daily revenue and ordering-customer series.",
                permission=ToolPermission.ANALYTICS_READ,
                input_model=DateRangeInput,
                output_model=TrendsOutput,
                handler=trends,
            ),
            _spec(
                name="get_merchant_health",
                description="Explainable MerchantOS health indicator and components.",
                permission=ToolPermission.ANALYTICS_READ,
                input_model=DateRangeInput,
                output_model=HealthOutput,
                handler=health,
            ),
            _spec(
                name="get_opportunities",
                description="Deterministic rule-based opportunities with evidence.",
                permission=ToolPermission.ANALYTICS_READ,
                input_model=DateRangeInput,
                output_model=OpportunitiesOutput,
                handler=opportunities,
            ),
        )
    )
