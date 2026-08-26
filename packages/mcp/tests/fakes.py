from types import SimpleNamespace
from uuid import uuid4

from merchantos_domain import DomainError, TenantContext
from merchantos_mcp.permissions import ToolPermission

ALL_READ = frozenset(ToolPermission)


def session_ctx() -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("read_orders", "read_products", "read_customers", "read_inventory"),
        )
    )


def _store(ctx: TenantContext) -> dict[str, object]:
    return {"store_id": str(ctx.store_id), "shop_domain": "alpha.myshopify.com"}


def _kpis() -> dict[str, object]:
    return {
        "revenue": "100.00",
        "orders": 1,
        "aov": "100.00",
        "customers": 1,
        "new_customers": 1,
        "returning_customers": 0,
        "cancelled_orders": 0,
        "excluded_financial_orders": 0,
        "previous": {"revenue": "50.00", "orders": 1, "aov": "50.00", "customers": 1},
        "growth_pct": {"revenue": "100.00", "orders": "0.00", "customers": "0.00", "aov": "100.00"},
    }


def _health() -> dict[str, object]:
    return {
        "score": 70,
        "status": "watch",
        "summary": "ok",
        "label": "MerchantOS health indicator",
        "components": [],
    }


class FakeAnalyticsService:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.calls: list[str] = []

    def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("overview")
        if self.empty:
            return {
                "request_id": str(ctx.request_id),
                "store": _store(ctx),
                "kpis": {**_kpis(), "revenue": "0.00", "orders": 0, "aov": None, "customers": 0},
                "health": {**_health(), "status": "insufficient_data", "score": None},
                "opportunities": [],
                "inventory": {"tracked_variants": 0, "in_stock_variants": 0},
                "trends": {"revenue": [], "customers": []},
                "products": [],
            }
        return {
            "request_id": str(ctx.request_id),
            "store": _store(ctx),
            "kpis": _kpis(),
            "health": _health(),
            "opportunities": [{"key": "idle", "title": "Follow up", "evidence": []}],
            "inventory": {"tracked_variants": 1, "in_stock_variants": 1, "available_units": 3},
            "trends": {
                "revenue": [{"date": "2026-08-20", "revenue": "100.00", "orders": 1}],
                "customers": [{"date": "2026-08-20", "customers": 1}],
            },
            "products": [
                {
                    "product_gid": "gid://shopify/Product/1",
                    "title": "Mug",
                    "revenue": "100.00",
                }
            ],
        }

    def revenue(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("revenue")
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "kpis": body["kpis"],
            "trend": body["trends"]["revenue"],  # type: ignore[index]
        }

    def orders(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("orders")
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "orders": body["kpis"]["orders"],  # type: ignore[index]
            "trend": body["trends"]["revenue"],  # type: ignore[index]
        }

    def products(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("products")
        body = self.overview(ctx, filters)
        items = [] if self.empty else body["products"]
        return {
            "request_id": str(ctx.request_id),
            "store": _store(ctx),
            "total": len(items),  # type: ignore[arg-type]
            "limit": 25,
            "offset": 0,
            "items": items,
        }

    def inventory(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("inventory")
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "inventory": body["inventory"],
        }

    def customers(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("customers")
        body = self.overview(ctx, filters)
        return {"request_id": body["request_id"], "store": body["store"], "kpis": body["kpis"]}

    def sales_trends(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("sales_trends")
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "revenue": body["trends"]["revenue"],  # type: ignore[index]
            "customers": body["trends"]["customers"],  # type: ignore[index]
        }

    def health(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("health")
        body = self.overview(ctx, filters)
        return {"request_id": body["request_id"], "store": body["store"], "health": body["health"]}

    def opportunities(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        self.calls.append("opportunities")
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "opportunities": [] if self.empty else body["opportunities"],
        }


class FailingAnalyticsService(FakeAnalyticsService):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc

    def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        raise self.exc


class BrokenOutputService(FakeAnalyticsService):
    def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        return {"unexpected": True}


def boom_domain() -> DomainError:
    return DomainError("db down")
