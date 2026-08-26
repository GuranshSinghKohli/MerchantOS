"""Deterministic commerce metrics. The LLM is never the calculator of record."""

from decimal import ROUND_HALF_UP, Decimal

QUANT = Decimal("0.01")
ZERO = Decimal("0.00")

# Shopify GraphQL displayFinancialStatus values we persist (uppercased).
EXCLUDED_FINANCIAL_STATUSES: frozenset[str] = frozenset({"REFUNDED", "VOIDED"})


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(QUANT, rounding=ROUND_HALF_UP)


def average_order_value(revenue: Decimal, orders: int) -> Decimal | None:
    """AOV = revenue / orders. None when there are no included orders."""
    if orders <= 0:
        return None
    return money(revenue / Decimal(orders))


def growth_pct(current: Decimal | int, previous: Decimal | int) -> Decimal | None:
    """((current - previous) / previous) * 100. None when previous is zero."""
    prev = Decimal(previous)
    if prev == 0:
        return None
    return money(((Decimal(current) - prev) / prev) * Decimal(100))


def normalize_financial_status(raw: str) -> str:
    return raw.strip().upper()


def is_included_financial_status(raw: str) -> bool:
    return normalize_financial_status(raw) not in EXCLUDED_FINANCIAL_STATUSES
