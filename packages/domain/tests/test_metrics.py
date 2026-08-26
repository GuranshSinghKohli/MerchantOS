from decimal import Decimal

from merchantos_domain import average_order_value, growth_pct, is_included_financial_status, money


def test_aov_divides_revenue_by_orders() -> None:
    assert average_order_value(Decimal("150.00"), 3) == Decimal("50.00")


def test_aov_none_when_zero_orders() -> None:
    assert average_order_value(Decimal("10.00"), 0) is None


def test_growth_pct_and_zero_baseline() -> None:
    assert growth_pct(Decimal("120.00"), Decimal("100.00")) == Decimal("20.00")
    assert growth_pct(80, 100) == Decimal("-20.00")
    assert growth_pct(Decimal("10.00"), 0) is None


def test_money_rounds_half_up() -> None:
    assert money(Decimal("1.235")) == Decimal("1.24")


def test_financial_status_exclusion() -> None:
    assert is_included_financial_status("PAID")
    assert is_included_financial_status("partially_refunded")
    assert not is_included_financial_status("refunded")
    assert not is_included_financial_status("VOIDED")
