"""Deterministic analytics. MCP and HTTP both call this; they do not recompute metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from merchantos_db import AnalyticsRepository, session_scope
from merchantos_domain import (
    CompareMode,
    DatePreset,
    ProductSignal,
    TenantContext,
    UnauthorizedError,
    build_opportunities,
    compute_health_score,
    growth_pct,
    resolve_compared_windows,
)
from sqlalchemy import Engine


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _window_payload(window: Any) -> dict[str, object]:
    return {
        "preset": window.preset.value,
        "timezone": window.timezone,
        "start": window.start_utc.isoformat(),
        "end": window.end_utc.isoformat(),
        "start_local": window.start_local.isoformat(),
        "end_local_exclusive": window.end_local_exclusive.isoformat(),
    }


def _kpi_payload(current: Any, previous: Any) -> dict[str, object]:
    return {
        "revenue": _dec(current.revenue),
        "orders": current.orders,
        "aov": _dec(current.aov),
        "customers": current.customers,
        "new_customers": current.new_customers,
        "returning_customers": current.returning_customers,
        "cancelled_orders": current.cancelled_orders,
        "excluded_financial_orders": current.excluded_financial_orders,
        "previous": {
            "revenue": _dec(previous.revenue),
            "orders": previous.orders,
            "aov": _dec(previous.aov),
            "customers": previous.customers,
            "new_customers": previous.new_customers,
            "returning_customers": previous.returning_customers,
        },
        "growth_pct": {
            "revenue": _dec(growth_pct(current.revenue, previous.revenue)),
            "orders": _dec(growth_pct(current.orders, previous.orders)),
            "customers": _dec(growth_pct(current.customers, previous.customers)),
            "aov": (
                _dec(growth_pct(current.aov, previous.aov))
                if current.aov is not None and previous.aov is not None
                else None
            ),
        },
    }


@dataclass(frozen=True)
class AnalyticsFilters:
    """Date/page filters. Never includes tenant identity."""

    request_id: UUID
    preset: DatePreset
    compare: CompareMode
    date_from: date | None
    date_to: date | None
    now: datetime
    limit: int = 25
    offset: int = 0
    sort: str = "revenue"


class AnalyticsService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _windows(self, ctx: TenantContext, filters: AnalyticsFilters) -> tuple[Any, Any, Any]:
        with session_scope(self._engine) as db:
            meta = AnalyticsRepository(db).store_meta(ctx)
        if meta is None:
            raise UnauthorizedError("store is missing")
        compared = resolve_compared_windows(
            preset=filters.preset,
            compare=filters.compare,
            timezone=meta.timezone,
            now=filters.now,
            custom_from=filters.date_from,
            custom_to=filters.date_to,
        )
        return meta, compared.current, compared

    def overview(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        meta, current, compared = self._windows(ctx, filters)
        with session_scope(self._engine) as db:
            repo = AnalyticsRepository(db)
            current_kpis = repo.period_kpis(ctx, current.start_utc, current.end_utc)
            previous_kpis = repo.period_kpis(
                ctx, compared.previous.start_utc, compared.previous.end_utc
            )
            trend = repo.daily_series(ctx, current.start_utc, current.end_utc)
            products, _total = repo.product_performance(
                ctx, current.start_utc, current.end_utc, limit=8, offset=0, sort="revenue"
            )
            inventory = repo.inventory_summary(ctx)
            customer_trend = repo.customer_trend(ctx, current.start_utc, current.end_utc)
            idle = repo.idle_repeat_customers(ctx, current.start_utc, current.end_utc)
        health = compute_health_score(
            revenue=current_kpis.revenue,
            previous_revenue=previous_kpis.revenue,
            orders=current_kpis.orders,
            previous_orders=previous_kpis.orders,
            tracked_variants=inventory.tracked_variants,
            in_stock_variants=inventory.in_stock_variants,
            ordering_customers=current_kpis.customers,
            previous_ordering_customers=previous_kpis.customers,
        )
        opportunities = build_opportunities(
            now=filters.now,
            revenue=current_kpis.revenue,
            previous_revenue=previous_kpis.revenue,
            orders=current_kpis.orders,
            previous_orders=previous_kpis.orders,
            top_products=tuple(
                ProductSignal(
                    product_gid=row.product_gid,
                    title=row.title,
                    units_sold=row.units_sold,
                    revenue=row.revenue,
                    available=row.available,
                )
                for row in products
            ),
            repeat_customers_idle=idle,
        )
        return {
            "request_id": str(filters.request_id),
            "store": {
                "store_id": str(meta.store_id),
                "shop_domain": meta.shop_domain,
                "timezone": meta.timezone,
                "currency": meta.currency,
                "installed": meta.installed,
                "sync_status": meta.sync_status,
            },
            "range": {
                "current": _window_payload(current),
                "previous": _window_payload(compared.previous),
                "compare": compared.compare.value,
            },
            "kpis": _kpi_payload(current_kpis, previous_kpis),
            "trends": {
                "revenue": [
                    {
                        "date": point.day.date().isoformat(),
                        "revenue": _dec(point.revenue),
                        "orders": point.orders,
                    }
                    for point in trend
                ],
                "customers": [
                    {"date": point.day.date().isoformat(), "customers": point.orders}
                    for point in customer_trend
                ],
            },
            "products": [
                {
                    "product_gid": row.product_gid,
                    "title": row.title,
                    "status": row.status,
                    "units_sold": row.units_sold,
                    "revenue": _dec(row.revenue),
                    "available": row.available,
                }
                for row in products
            ],
            "inventory": {
                "tracked_variants": inventory.tracked_variants,
                "in_stock_variants": inventory.in_stock_variants,
                "out_of_stock_variants": inventory.out_of_stock_variants,
                "available_units": inventory.available_units,
                "on_hand_units": inventory.on_hand_units,
                "utilization_pct": _dec(inventory.utilization_pct),
            },
            "health": {
                "score": health.score,
                "status": health.status,
                "summary": health.summary,
                "label": "MerchantOS health indicator",
                "components": [
                    {
                        "key": row.key,
                        "label": row.label,
                        "weight": str(row.weight),
                        "score": row.score,
                        "explanation": row.explanation,
                    }
                    for row in health.components
                ],
            },
            "opportunities": [
                {
                    "key": row.key,
                    "title": row.title,
                    "explanation": row.explanation,
                    "metric": row.metric,
                    "severity": row.severity,
                    "detected_at": row.detected_at.isoformat(),
                    "evidence": [
                        {"metric": item.metric, "value": item.value} for item in row.evidence
                    ],
                }
                for row in opportunities
            ],
        }

    def revenue(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "range": body["range"],
            "kpis": body["kpis"],
            "trend": body["trends"]["revenue"],  # type: ignore[index]
        }

    def orders(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        kpis = body["kpis"]
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "range": body["range"],
            "orders": kpis["orders"],  # type: ignore[index]
            "previous_orders": kpis["previous"]["orders"],  # type: ignore[index]
            "growth_pct": kpis["growth_pct"]["orders"],  # type: ignore[index]
            "cancelled_orders": kpis["cancelled_orders"],  # type: ignore[index]
            "excluded_financial_orders": kpis["excluded_financial_orders"],  # type: ignore[index]
            "trend": body["trends"]["revenue"],  # type: ignore[index]
        }

    def products(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        meta, current, compared = self._windows(ctx, filters)
        with session_scope(self._engine) as db:
            rows, total = AnalyticsRepository(db).product_performance(
                ctx,
                current.start_utc,
                current.end_utc,
                limit=filters.limit,
                offset=filters.offset,
                sort=filters.sort,
            )
        return {
            "request_id": str(filters.request_id),
            "store": {
                "store_id": str(meta.store_id),
                "shop_domain": meta.shop_domain,
                "currency": meta.currency,
            },
            "range": {"current": _window_payload(current), "compare": compared.compare.value},
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset,
            "items": [
                {
                    "product_gid": row.product_gid,
                    "title": row.title,
                    "status": row.status,
                    "units_sold": row.units_sold,
                    "revenue": _dec(row.revenue),
                    "available": row.available,
                }
                for row in rows
            ],
        }

    def inventory(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "range": body["range"],
            "inventory": body["inventory"],
            "products": body["products"],
        }

    def customers(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "range": body["range"],
            "kpis": {
                "customers": body["kpis"]["customers"],  # type: ignore[index]
                "new_customers": body["kpis"]["new_customers"],  # type: ignore[index]
                "returning_customers": body["kpis"]["returning_customers"],  # type: ignore[index]
                "growth_pct": body["kpis"]["growth_pct"],  # type: ignore[index]
                "previous": body["kpis"]["previous"],  # type: ignore[index]
            },
            "trend": body["trends"]["customers"],  # type: ignore[index]
        }

    def health(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {"request_id": body["request_id"], "store": body["store"], "health": body["health"]}

    def opportunities(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "opportunities": body["opportunities"],
        }

    def sales_trends(self, ctx: TenantContext, filters: AnalyticsFilters) -> dict[str, object]:
        body = self.overview(ctx, filters)
        return {
            "request_id": body["request_id"],
            "store": body["store"],
            "range": body["range"],
            "revenue": body["trends"]["revenue"],  # type: ignore[index]
            "customers": body["trends"]["customers"],  # type: ignore[index]
        }
