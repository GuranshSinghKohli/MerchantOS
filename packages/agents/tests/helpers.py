from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from merchantos_domain import TenantContext
from merchantos_llm import FakeLLM, FakeTurn
from merchantos_mcp import build_commerce_registry


def ctx() -> TenantContext:
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


class FakeAnalyticsService:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty

    def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        if self.empty:
            return {
                "request_id": str(ctx.request_id),
                "store": _store(ctx),
                "kpis": {**_kpis(), "revenue": "0.00", "orders": 0, "aov": None, "customers": 0},
                "health": {"status": "insufficient_data", "score": None},
                "opportunities": [],
                "inventory": {"tracked_variants": 0, "in_stock_variants": 0, "available_units": 0},
                "trends": {"revenue": [], "customers": []},
                "products": [],
            }
        return {
            "request_id": str(ctx.request_id),
            "store": _store(ctx),
            "kpis": _kpis(),
            "health": {"status": "watch", "score": 70},
            "opportunities": [],
            "inventory": {
                "tracked_variants": 1,
                "in_stock_variants": 1,
                "out_of_stock_variants": 0,
                "available_units": 3,
            },
            "trends": {"revenue": [{"date": "2026-08-20", "revenue": "100.00", "orders": 1}]},
            "products": [
                {
                    "product_gid": "gid://shopify/Product/1",
                    "title": "Mug",
                    "revenue": "100.00",
                    "units_sold": 1,
                    "available": 3,
                }
            ],
        }

    def revenue(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "kpis": body["kpis"],
            "trend": body["trends"]["revenue"],  # type: ignore[index]
        }

    def orders(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "orders": body["kpis"]["orders"],  # type: ignore[index]
            "trend": body["trends"]["revenue"],  # type: ignore[index]
        }

    def products(self, ctx: TenantContext, filters: object) -> dict[str, object]:
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
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "inventory": body["inventory"],
        }

    def customers(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {"request_id": body["request_id"], "store": body["store"], "kpis": body["kpis"]}

    def sales_trends(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "revenue": body["trends"]["revenue"],  # type: ignore[index]
            "customers": body["trends"]["customers"],  # type: ignore[index]
        }

    def health(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {"request_id": body["request_id"], "store": body["store"], "health": body["health"]}

    def opportunities(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "opportunities": [] if self.empty else body["opportunities"],
        }


class ConfigurableAnalytics(FakeAnalyticsService):
    def __init__(
        self,
        *,
        empty: bool = False,
        products: list[dict[str, Any]] | None = None,
        inventory: dict[str, Any] | None = None,
        kpis: dict[str, Any] | None = None,
        growth_override: dict[str, str] | None = None,
        inject_title: str | None = None,
    ) -> None:
        super().__init__(empty=empty)
        self._products = products
        self._inventory = inventory
        self._kpis = kpis
        self._growth_override = growth_override
        self._inject_title = inject_title

    def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = super().overview(ctx, filters)
        if self._kpis is not None:
            body["kpis"] = self._kpis
        if self._growth_override and isinstance(body["kpis"], dict):
            growth = dict(body["kpis"].get("growth_pct") or {})  # type: ignore[union-attr]
            growth.update(self._growth_override)
            body["kpis"]["growth_pct"] = growth  # type: ignore[index]
        if self._inventory is not None:
            body["inventory"] = self._inventory
        if self._products is not None:
            body["products"] = self._products
        elif self._inject_title and isinstance(body.get("products"), list) and body["products"]:
            row = dict(body["products"][0])  # type: ignore[index]
            row["title"] = self._inject_title
            body["products"] = [row]
        return body

    def revenue(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        body = super().revenue(ctx, filters)
        if self._growth_override and isinstance(body.get("kpis"), dict):
            growth = dict(body["kpis"].get("growth_pct") or {})
            flipped = {key: f"-{value.lstrip('-')}" for key, value in self._growth_override.items()}
            growth.update(flipped)
            body["kpis"]["growth_pct"] = growth
        return body


def registry(service: FakeAnalyticsService | None = None):
    return build_commerce_registry(service or FakeAnalyticsService())  # type: ignore[arg-type]


def plan_turn(*names: str, insufficient: bool = False) -> FakeTurn:
    return FakeTurn(
        {
            "plan": "collect evidence",
            "tools": [{"name": name, "arguments": {"preset": "last_30"}} for name in names],
            "insufficient_data": insufficient,
        }
    )


def synth_turn(
    *,
    summary: str,
    category: str,
    evidence_ids: list[str] | None = None,
    claim_kind: str = "FACT",
    insufficient: bool = False,
    proposed: str = "HIGH",
    extra_findings: list[dict[str, object]] | None = None,
) -> FakeTurn:
    finding = {
        "title": summary[:160],
        "description": summary,
        "category": category,
        "severity": "watch",
        "claim_kind": claim_kind,
        "evidence_ids": evidence_ids or ["ev_1"],
        "limitations": [],
    }
    findings = [finding, *(extra_findings or [])]
    return FakeTurn(
        {
            "summary": summary,
            "findings": [] if insufficient else findings,
            "assumptions": [],
            "limitations": ["Insufficient evidence."] if insufficient else [],
            "next_steps": ["review the next period"],
            "uncertainty": "short history" if insufficient else "",
            "insufficient_data": insufficient,
            "proposed_confidence": "LOW" if insufficient else proposed,
        }
    )


def specialist_llm(*tool_names: str, summary: str, category: str, **kwargs: Any) -> FakeLLM:
    return FakeLLM(
        [plan_turn(*tool_names), synth_turn(summary=summary, category=category, **kwargs)]
    )
