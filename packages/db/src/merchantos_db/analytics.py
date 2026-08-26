"""Tenant-scoped aggregated analytics. No full-table loads into Python."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from merchantos_domain import TenantContext
from merchantos_domain.metrics import EXCLUDED_FINANCIAL_STATUSES, ZERO, money
from sqlalchemy import ColumnElement, Select, and_, case, desc, func, select
from sqlalchemy.orm import Session

from merchantos_db.models import (
    Customer,
    InventorySnapshot,
    Order,
    OrderLine,
    Product,
    Store,
    Variant,
)
from merchantos_db.rls import tenant_scope


def _included_order_clause(ctx: TenantContext) -> ColumnElement[bool]:
    excluded = tuple(EXCLUDED_FINANCIAL_STATUSES)
    return and_(
        Order.merchant_id == ctx.merchant_id,
        Order.store_id == ctx.store_id,
        Order.cancelled_at.is_(None),
        Order.processed_at.is_not(None),
        func.upper(Order.financial_status).notin_(excluded),
    )


@dataclass(frozen=True)
class PeriodKpis:
    revenue: Decimal
    orders: int
    aov: Decimal | None
    customers: int
    new_customers: int
    returning_customers: int
    cancelled_orders: int
    excluded_financial_orders: int


@dataclass(frozen=True)
class DailyPoint:
    day: datetime
    revenue: Decimal
    orders: int


@dataclass(frozen=True)
class ProductPerformanceRow:
    product_gid: str
    title: str
    status: str
    units_sold: int
    revenue: Decimal
    available: int | None


@dataclass(frozen=True)
class InventorySummary:
    tracked_variants: int
    in_stock_variants: int
    out_of_stock_variants: int
    available_units: int
    on_hand_units: int
    utilization_pct: Decimal | None


@dataclass(frozen=True)
class StoreAnalyticsMeta:
    store_id: UUID
    shop_domain: str
    timezone: str
    currency: str
    installed: bool
    sync_status: str


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def store_meta(self, ctx: TenantContext) -> StoreAnalyticsMeta | None:
        with tenant_scope(self._session, ctx.merchant_id):
            store = self._session.get(Store, ctx.store_id)
        if store is None or store.merchant_id != ctx.merchant_id:
            return None
        return StoreAnalyticsMeta(
            store_id=store.id,
            shop_domain=store.myshopify_domain,
            timezone=store.iana_timezone,
            currency=store.currency,
            installed=store.uninstalled_at is None,
            sync_status=store.sync_status,
        )

    def period_kpis(self, ctx: TenantContext, start: datetime, end: datetime) -> PeriodKpis:
        included = _included_order_clause(ctx)
        in_range = and_(included, Order.processed_at >= start, Order.processed_at < end)
        with tenant_scope(self._session, ctx.merchant_id):
            revenue, orders, customers = self._session.execute(
                select(
                    func.coalesce(func.sum(Order.total_price), 0),
                    func.count(Order.id),
                    func.count(func.distinct(Order.customer_id)),
                ).where(in_range)
            ).one()
            new_customers = self._session.scalar(
                select(func.count(func.distinct(Customer.id))).where(
                    Customer.merchant_id == ctx.merchant_id,
                    Customer.store_id == ctx.store_id,
                    Customer.deleted_at.is_(None),
                    Customer.first_order_at.is_not(None),
                    Customer.first_order_at >= start,
                    Customer.first_order_at < end,
                )
            )
            returning = self._session.scalar(
                select(func.count(func.distinct(Order.customer_id))).where(
                    in_range,
                    Order.customer_id.is_not(None),
                    Order.customer_id.in_(
                        select(Customer.id).where(
                            Customer.merchant_id == ctx.merchant_id,
                            Customer.store_id == ctx.store_id,
                            Customer.first_order_at.is_not(None),
                            Customer.first_order_at < start,
                        )
                    ),
                )
            )
            cancelled = self._session.scalar(
                select(func.count(Order.id)).where(
                    Order.merchant_id == ctx.merchant_id,
                    Order.store_id == ctx.store_id,
                    Order.cancelled_at.is_not(None),
                    Order.processed_at.is_not(None),
                    Order.processed_at >= start,
                    Order.processed_at < end,
                )
            )
            excluded_fin = self._session.scalar(
                select(func.count(Order.id)).where(
                    Order.merchant_id == ctx.merchant_id,
                    Order.store_id == ctx.store_id,
                    Order.cancelled_at.is_(None),
                    Order.processed_at.is_not(None),
                    Order.processed_at >= start,
                    Order.processed_at < end,
                    func.upper(Order.financial_status).in_(tuple(EXCLUDED_FINANCIAL_STATUSES)),
                )
            )
        from merchantos_domain.metrics import average_order_value

        rev = money(Decimal(revenue or 0))
        order_count = int(orders or 0)
        return PeriodKpis(
            revenue=rev,
            orders=order_count,
            aov=average_order_value(rev, order_count),
            customers=int(customers or 0),
            new_customers=int(new_customers or 0),
            returning_customers=int(returning or 0),
            cancelled_orders=int(cancelled or 0),
            excluded_financial_orders=int(excluded_fin or 0),
        )

    def daily_series(self, ctx: TenantContext, start: datetime, end: datetime) -> list[DailyPoint]:
        day = func.date_trunc("day", Order.processed_at)
        with tenant_scope(self._session, ctx.merchant_id):
            rows = self._session.execute(
                select(
                    day.label("day"),
                    func.coalesce(func.sum(Order.total_price), 0),
                    func.count(Order.id),
                )
                .where(
                    _included_order_clause(ctx),
                    Order.processed_at >= start,
                    Order.processed_at < end,
                )
                .group_by(day)
                .order_by(day)
            ).all()
        return [
            DailyPoint(day=row[0], revenue=money(Decimal(row[1])), orders=int(row[2]))
            for row in rows
        ]

    def _latest_availability(self, ctx: TenantContext) -> Select[tuple[UUID, int, int]]:
        ranked = (
            select(
                InventorySnapshot.variant_id,
                InventorySnapshot.available,
                InventorySnapshot.on_hand,
                func.row_number()
                .over(
                    partition_by=(InventorySnapshot.variant_id, InventorySnapshot.location_id),
                    order_by=InventorySnapshot.captured_at.desc(),
                )
                .label("rn"),
            ).where(
                InventorySnapshot.merchant_id == ctx.merchant_id,
                InventorySnapshot.store_id == ctx.store_id,
            )
        ).subquery()
        return (
            select(
                ranked.c.variant_id,
                func.coalesce(func.sum(ranked.c.available), 0).label("available"),
                func.coalesce(func.sum(ranked.c.on_hand), 0).label("on_hand"),
            )
            .where(ranked.c.rn == 1)
            .group_by(ranked.c.variant_id)
        )

    def product_performance(
        self,
        ctx: TenantContext,
        start: datetime,
        end: datetime,
        *,
        limit: int,
        offset: int,
        sort: str,
    ) -> tuple[list[ProductPerformanceRow], int]:
        latest = self._latest_availability(ctx).subquery()
        line_rev = OrderLine.price * OrderLine.quantity - OrderLine.discount_allocation
        sales = (
            select(
                OrderLine.variant_id.label("variant_id"),
                func.coalesce(func.sum(OrderLine.quantity), 0).label("units_sold"),
                func.coalesce(func.sum(line_rev), 0).label("revenue"),
            )
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                _included_order_clause(ctx),
                OrderLine.merchant_id == ctx.merchant_id,
                Order.processed_at >= start,
                Order.processed_at < end,
            )
            .group_by(OrderLine.variant_id)
        ).subquery()
        units = func.coalesce(func.sum(sales.c.units_sold), 0)
        revenue = func.coalesce(func.sum(sales.c.revenue), 0)
        available = func.coalesce(func.sum(latest.c.available), 0)
        query = (
            select(
                Product.shopify_gid,
                Product.title,
                Product.status,
                units.label("units_sold"),
                revenue.label("revenue"),
                available.label("available"),
            )
            .select_from(Product)
            .outerjoin(
                Variant,
                and_(
                    Variant.product_id == Product.id,
                    Variant.merchant_id == Product.merchant_id,
                ),
            )
            .outerjoin(sales, sales.c.variant_id == Variant.id)
            .outerjoin(latest, latest.c.variant_id == Variant.id)
            .where(
                Product.merchant_id == ctx.merchant_id,
                Product.store_id == ctx.store_id,
                Product.deleted_at.is_(None),
            )
            .group_by(Product.id)
        )
        order_expr = {
            "revenue": desc(revenue),
            "units": desc(units),
            "title": Product.title.asc(),
            "available": desc(available),
        }.get(sort, desc(revenue))
        with tenant_scope(self._session, ctx.merchant_id):
            total = self._session.scalar(
                select(func.count()).select_from(
                    select(Product.id)
                    .where(
                        Product.merchant_id == ctx.merchant_id,
                        Product.store_id == ctx.store_id,
                        Product.deleted_at.is_(None),
                    )
                    .subquery()
                )
            )
            rows = self._session.execute(
                query.order_by(order_expr).limit(limit).offset(offset)
            ).all()
        return (
            [
                ProductPerformanceRow(
                    product_gid=row[0],
                    title=row[1],
                    status=row[2],
                    units_sold=int(row[3] or 0),
                    revenue=money(Decimal(row[4] or 0)),
                    available=int(row[5]) if row[5] is not None else None,
                )
                for row in rows
            ],
            int(total or 0),
        )

    def inventory_summary(self, ctx: TenantContext) -> InventorySummary:
        latest = self._latest_availability(ctx).subquery()
        with tenant_scope(self._session, ctx.merchant_id):
            tracked, in_stock, available, on_hand = self._session.execute(
                select(
                    func.count(latest.c.variant_id),
                    func.coalesce(func.sum(case((latest.c.available > 0, 1), else_=0)), 0),
                    func.coalesce(func.sum(latest.c.available), 0),
                    func.coalesce(func.sum(latest.c.on_hand), 0),
                )
            ).one()
        tracked_n = int(tracked or 0)
        in_stock_n = int(in_stock or 0)
        avail_n = int(available or 0)
        on_hand_n = int(on_hand or 0)
        util = (
            None if on_hand_n <= 0 else money(Decimal(avail_n) / Decimal(on_hand_n) * Decimal(100))
        )
        return InventorySummary(
            tracked_variants=tracked_n,
            in_stock_variants=in_stock_n,
            out_of_stock_variants=max(tracked_n - in_stock_n, 0),
            available_units=avail_n,
            on_hand_units=on_hand_n,
            utilization_pct=util,
        )

    def idle_repeat_customers(self, ctx: TenantContext, start: datetime, end: datetime) -> int:
        ordered_in_period = select(Order.customer_id).where(
            _included_order_clause(ctx),
            Order.processed_at >= start,
            Order.processed_at < end,
            Order.customer_id.is_not(None),
        )
        with tenant_scope(self._session, ctx.merchant_id):
            count = self._session.scalar(
                select(func.count(Customer.id)).where(
                    Customer.merchant_id == ctx.merchant_id,
                    Customer.store_id == ctx.store_id,
                    Customer.deleted_at.is_(None),
                    Customer.orders_count >= 2,
                    Customer.last_order_at.is_not(None),
                    Customer.last_order_at < start,
                    Customer.id.notin_(ordered_in_period),
                )
            )
        return int(count or 0)

    def customer_trend(
        self, ctx: TenantContext, start: datetime, end: datetime
    ) -> list[DailyPoint]:
        day = func.date_trunc("day", Order.processed_at)
        with tenant_scope(self._session, ctx.merchant_id):
            rows = self._session.execute(
                select(day.label("day"), func.count(func.distinct(Order.customer_id)))
                .where(
                    _included_order_clause(ctx),
                    Order.processed_at >= start,
                    Order.processed_at < end,
                    Order.customer_id.is_not(None),
                )
                .group_by(day)
                .order_by(day)
            ).all()
        return [DailyPoint(day=row[0], revenue=ZERO, orders=int(row[1])) for row in rows]
