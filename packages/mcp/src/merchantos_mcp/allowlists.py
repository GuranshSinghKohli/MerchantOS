"""Per-agent allowlists. Binding the full registry to a node is forbidden."""

from merchantos_mcp.permissions import ToolPermission

READ_TOOLS: frozenset[str] = frozenset(
    {
        "get_store_overview",
        "get_revenue_metrics",
        "get_order_metrics",
        "get_product_performance",
        "get_inventory_health",
        "get_customer_metrics",
        "get_sales_trends",
        "get_merchant_health",
        "get_opportunities",
    }
)

AGENT_TOOLS: dict[str, frozenset[str]] = {
    "orchestrator": frozenset({"get_store_overview"}),
    "analytics": frozenset(
        {
            "get_store_overview",
            "get_revenue_metrics",
            "get_order_metrics",
            "get_product_performance",
            "get_sales_trends",
            "get_merchant_health",
            "get_opportunities",
        }
    ),
    "inventory": frozenset({"get_inventory_health", "get_product_performance"}),
    "customer": frozenset({"get_customer_metrics"}),
}

TOOL_PERMISSION: dict[str, ToolPermission] = {
    "get_store_overview": ToolPermission.ANALYTICS_READ,
    "get_revenue_metrics": ToolPermission.ANALYTICS_READ,
    "get_sales_trends": ToolPermission.ANALYTICS_READ,
    "get_merchant_health": ToolPermission.ANALYTICS_READ,
    "get_opportunities": ToolPermission.ANALYTICS_READ,
    "get_order_metrics": ToolPermission.ORDERS_READ,
    "get_product_performance": ToolPermission.PRODUCTS_READ,
    "get_inventory_health": ToolPermission.INVENTORY_READ,
    "get_customer_metrics": ToolPermission.CUSTOMERS_READ,
}

FORBIDDEN_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "execute_approved_action",
        "execute_sql",
        "raw_shopify_graphql",
        "http_request",
        "run_shell",
    }
)
