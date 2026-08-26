"""Deterministic opportunity rules. No causal claims, no invented $ impact."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from merchantos_domain.metrics import growth_pct


@dataclass(frozen=True)
class OpportunityEvidence:
    metric: str
    value: str


@dataclass(frozen=True)
class Opportunity:
    key: str
    title: str
    explanation: str
    metric: str
    severity: str
    evidence: tuple[OpportunityEvidence, ...]
    detected_at: datetime


@dataclass(frozen=True)
class ProductSignal:
    product_gid: str
    title: str
    units_sold: int
    revenue: Decimal
    available: int | None


def build_opportunities(
    *,
    now: datetime,
    revenue: Decimal,
    previous_revenue: Decimal,
    orders: int,
    previous_orders: int,
    top_products: tuple[ProductSignal, ...],
    repeat_customers_idle: int,
) -> tuple[Opportunity, ...]:
    found: list[Opportunity] = []
    rev_growth = growth_pct(revenue, previous_revenue)
    if previous_revenue > 0 and rev_growth is not None and rev_growth <= Decimal("-10.00"):
        found.append(
            Opportunity(
                key="revenue_declining",
                title="Revenue is down versus the comparison period",
                explanation=(
                    "Included order revenue is at least 10% lower than the comparison "
                    "period. This is a period-over-period observation, not a cause."
                ),
                metric="revenue_growth_pct",
                severity="high" if rev_growth <= Decimal("-25.00") else "medium",
                evidence=(
                    OpportunityEvidence("revenue", str(revenue)),
                    OpportunityEvidence("previous_revenue", str(previous_revenue)),
                    OpportunityEvidence("revenue_growth_pct", str(rev_growth)),
                ),
                detected_at=now,
            )
        )
    order_growth = growth_pct(orders, previous_orders)
    if previous_orders > 0 and order_growth is not None and order_growth <= Decimal("-10.00"):
        found.append(
            Opportunity(
                key="orders_declining",
                title="Order count is down versus the comparison period",
                explanation=(
                    "Included orders fell at least 10% versus the comparison period. "
                    "Revenue impact is not estimated separately."
                ),
                metric="order_growth_pct",
                severity="medium",
                evidence=(
                    OpportunityEvidence("orders", str(orders)),
                    OpportunityEvidence("previous_orders", str(previous_orders)),
                    OpportunityEvidence("order_growth_pct", str(order_growth)),
                ),
                detected_at=now,
            )
        )
    if top_products:
        leader = top_products[0]
        if leader.units_sold > 0 and leader.available is not None and leader.available <= 5:
            found.append(
                Opportunity(
                    key="low_stock_high_seller",
                    title="A top seller has low available inventory",
                    explanation=(
                        f"{leader.title} led units sold in this period and currently "
                        f"shows available inventory of {leader.available}. "
                        "Available is the latest snapshot total across locations."
                    ),
                    metric="inventory_available",
                    severity="high" if leader.available <= 0 else "medium",
                    evidence=(
                        OpportunityEvidence("product", leader.title),
                        OpportunityEvidence("units_sold", str(leader.units_sold)),
                        OpportunityEvidence("available", str(leader.available)),
                    ),
                    detected_at=now,
                )
            )
        for row in top_products[:5]:
            if (
                row.units_sold >= 3
                and row.available is not None
                and 0 < row.available <= 10
                and row.product_gid != leader.product_gid
            ):
                found.append(
                    Opportunity(
                        key=f"high_seller_low_cover:{row.product_gid}",
                        title="A high-performing product has limited cover",
                        explanation=(
                            f"{row.title} sold {row.units_sold} units in this period "
                            f"with {row.available} available. No expected revenue is inferred."
                        ),
                        metric="inventory_available",
                        severity="low",
                        evidence=(
                            OpportunityEvidence("product", row.title),
                            OpportunityEvidence("units_sold", str(row.units_sold)),
                            OpportunityEvidence("available", str(row.available)),
                        ),
                        detected_at=now,
                    )
                )
                break
    if repeat_customers_idle >= 3:
        found.append(
            Opportunity(
                key="idle_repeat_customers",
                title="Repeat customers did not order in this period",
                explanation=(
                    f"{repeat_customers_idle} customers with two or more lifetime orders "
                    "and a prior last-order timestamp placed no included order in this "
                    "period. This counts customers only; it does not estimate spend."
                ),
                metric="idle_repeat_customers",
                severity="low",
                evidence=(
                    OpportunityEvidence("idle_repeat_customers", str(repeat_customers_idle)),
                ),
                detected_at=now,
            )
        )
    return tuple(found)
