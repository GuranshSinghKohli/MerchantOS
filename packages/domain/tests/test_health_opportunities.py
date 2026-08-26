from datetime import UTC, datetime
from decimal import Decimal

from merchantos_domain import ProductSignal, build_opportunities, compute_health_score


def test_health_insufficient_data() -> None:
    score = compute_health_score(
        revenue=Decimal("0"),
        previous_revenue=Decimal("0"),
        orders=0,
        previous_orders=0,
        tracked_variants=0,
        in_stock_variants=0,
        ordering_customers=0,
        previous_ordering_customers=0,
    )
    assert score.score is None
    assert score.status == "insufficient_data"


def test_health_is_deterministic_and_weighted() -> None:
    a = compute_health_score(
        revenue=Decimal("120"),
        previous_revenue=Decimal("100"),
        orders=12,
        previous_orders=10,
        tracked_variants=10,
        in_stock_variants=8,
        ordering_customers=6,
        previous_ordering_customers=5,
    )
    b = compute_health_score(
        revenue=Decimal("120"),
        previous_revenue=Decimal("100"),
        orders=12,
        previous_orders=10,
        tracked_variants=10,
        in_stock_variants=8,
        ordering_customers=6,
        previous_ordering_customers=5,
    )
    assert a.score == b.score
    assert a.status == b.status
    assert len(a.components) == 4
    assert sum(c.weight for c in a.components) == Decimal("1.00")
    assert "not a forecast" in a.summary


def test_opportunities_require_evidence_and_skip_invented_impact() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    rows = build_opportunities(
        now=now,
        revenue=Decimal("70"),
        previous_revenue=Decimal("100"),
        orders=4,
        previous_orders=8,
        top_products=(
            ProductSignal(
                product_gid="gid://shopify/Product/1",
                title="Hero Mug",
                units_sold=12,
                revenue=Decimal("240"),
                available=2,
            ),
        ),
        repeat_customers_idle=4,
    )
    keys = {row.key for row in rows}
    assert "revenue_declining" in keys
    assert "orders_declining" in keys
    assert "low_stock_high_seller" in keys
    assert "idle_repeat_customers" in keys
    blob = " ".join(row.explanation for row in rows).lower()
    assert "expected revenue" not in blob or "no expected revenue" in blob
    for row in rows:
        assert row.evidence
        assert row.detected_at == now
