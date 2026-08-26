"""Explainable MerchantOS health indicator. Not a scientific forecast."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from merchantos_domain.metrics import ZERO, growth_pct, money


@dataclass(frozen=True)
class HealthComponent:
    key: str
    label: str
    weight: Decimal
    score: int
    explanation: str


@dataclass(frozen=True)
class HealthScore:
    """Internal MerchantOS indicator on 0–100. None when data is insufficient."""

    score: int | None
    status: str
    components: tuple[HealthComponent, ...]
    summary: str


WEIGHT_REVENUE = Decimal("0.40")
WEIGHT_ORDERS = Decimal("0.20")
WEIGHT_INVENTORY = Decimal("0.25")
WEIGHT_CUSTOMERS = Decimal("0.15")


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _revenue_score(growth: Decimal | None, previous_revenue: Decimal) -> tuple[int, str]:
    if previous_revenue <= 0 and growth is None:
        return 50, "No prior-period revenue; treated as a neutral baseline."
    if growth is None:
        return 50, "Prior-period revenue is zero, so growth is undefined."
    # Map −20% → 0, 0% → 50, +20% → 100, linear, clamped.
    mapped = int(money(Decimal("50") + (growth * Decimal("2.5"))))
    return _clamp(mapped), f"Revenue changed {growth}% versus the comparison period."


def _order_score(orders: int, previous_orders: int) -> tuple[int, str]:
    if orders == 0 and previous_orders == 0:
        return 0, "No included orders in either period."
    if previous_orders == 0:
        return 70, "Orders exist in the current period with no prior-period baseline."
    change = growth_pct(orders, previous_orders)
    assert change is not None
    mapped = int(money(Decimal("50") + (change * Decimal("2.5"))))
    return _clamp(mapped), f"Order count changed {change}% versus the comparison period."


def _inventory_score(tracked: int, in_stock: int) -> tuple[int, str]:
    if tracked <= 0:
        return 50, "No inventory snapshots are available; treated as a neutral baseline."
    ratio = money(Decimal(in_stock) / Decimal(tracked) * Decimal(100))
    return _clamp(int(ratio)), (
        f"{in_stock} of {tracked} tracked selling variants have available > 0."
    )


def _customer_score(current: int, previous: int) -> tuple[int, str]:
    if current == 0 and previous == 0:
        return 0, "No customers placed an included order in either period."
    if previous == 0:
        return 70, "Customers ordered in the current period with no prior-period baseline."
    change = growth_pct(current, previous)
    assert change is not None
    mapped = int(money(Decimal("50") + (change * Decimal("2.5"))))
    return _clamp(mapped), f"Ordering customers changed {change}% versus the comparison period."


def compute_health_score(
    *,
    revenue: Decimal,
    previous_revenue: Decimal,
    orders: int,
    previous_orders: int,
    tracked_variants: int,
    in_stock_variants: int,
    ordering_customers: int,
    previous_ordering_customers: int,
) -> HealthScore:
    if (
        revenue == ZERO
        and previous_revenue == ZERO
        and orders == 0
        and previous_orders == 0
        and tracked_variants == 0
        and ordering_customers == 0
    ):
        return HealthScore(
            score=None,
            status="insufficient_data",
            components=(),
            summary="Not enough store activity to compute a MerchantOS health indicator.",
        )
    rev_s, rev_x = _revenue_score(growth_pct(revenue, previous_revenue), previous_revenue)
    ord_s, ord_x = _order_score(orders, previous_orders)
    inv_s, inv_x = _inventory_score(tracked_variants, in_stock_variants)
    cus_s, cus_x = _customer_score(ordering_customers, previous_ordering_customers)
    components = (
        HealthComponent("revenue_trend", "Revenue trend", WEIGHT_REVENUE, rev_s, rev_x),
        HealthComponent("order_volume", "Order volume", WEIGHT_ORDERS, ord_s, ord_x),
        HealthComponent("inventory_coverage", "Inventory coverage", WEIGHT_INVENTORY, inv_s, inv_x),
        HealthComponent("customer_activity", "Customer activity", WEIGHT_CUSTOMERS, cus_s, cus_x),
    )
    weighted = (
        Decimal(rev_s) * WEIGHT_REVENUE
        + Decimal(ord_s) * WEIGHT_ORDERS
        + Decimal(inv_s) * WEIGHT_INVENTORY
        + Decimal(cus_s) * WEIGHT_CUSTOMERS
    )
    score = _clamp(int(money(weighted)))
    if score >= 75:
        status = "healthy"
    elif score >= 50:
        status = "watch"
    else:
        status = "attention"
    return HealthScore(
        score=score,
        status=status,
        components=components,
        summary=(
            f"MerchantOS health indicator is {score}/100 ({status}). "
            "This is an internal weighted blend of revenue trend, orders, "
            "inventory coverage, and customer activity — not a forecast."
        ),
    )
