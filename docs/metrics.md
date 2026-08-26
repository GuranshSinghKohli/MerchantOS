# MerchantOS metric definitions (Phase 4)

**Status:** Accepted for Phase 4  
**Calculator of record:** Python domain + SQL aggregation. The LLM is never used.

All money is `NUMERIC` / `Decimal` quantized to 0.01. API responses serialize money as strings.

## Included order

An order is **included** in revenue, order count, AOV, and customer-from-orders metrics when all of:

1. `store_id` and `merchant_id` match the trusted session
2. `processed_at` is not null and falls in the half-open window `[start, end)`
3. `cancelled_at` is null
4. `upper(financial_status)` is not `REFUNDED` or `VOIDED`

`displayFinancialStatus` values persist as stored by Phase 3 (`PAID`, `PENDING`, `PARTIALLY_REFUNDED`, …). Partially refunded orders use the stored `total_price`; we do not have a separate refund amount, so we do not invent one.

## Definitions

| Metric | Definition |
|--------|------------|
| **Revenue** | `SUM(orders.total_price)` of included orders. This is Shopify's stored order total, not a reconstructed line-item total. |
| **Orders** | `COUNT(*)` of included orders |
| **AOV** | `revenue / orders`. `null` when orders = 0 |
| **Cancelled order** | `cancelled_at IS NOT NULL`. Counted separately; excluded from revenue |
| **Refunded / voided** | financial status `REFUNDED` or `VOIDED`. Counted separately; excluded from revenue |
| **Customer (period)** | Distinct `customer_id` on included orders |
| **New customer** | `customers.first_order_at` in the current window (store timezone) |
| **Returning customer** | Included order in the window and `first_order_at` before the window |
| **Product revenue** | `SUM(unit_price * quantity - discount_allocation)` on included order lines |
| **Product units** | `SUM(quantity)` on included order lines |
| **Inventory available / on hand** | Sum of the latest snapshot per `(variant, location)` |
| **Inventory utilization** | `available / on_hand * 100` when `on_hand > 0`, else `null` |
| **Growth %** | `((current - previous) / previous) * 100`. `null` when previous is 0 |

## Date windows

Bounds are half-open and computed in the **store `iana_timezone`**, then converted to UTC for SQL.

| Preset | Local span |
|--------|------------|
| today / yesterday | that calendar day |
| last_7 / last_30 / last_90 | inclusive of today, N calendar days |
| this_month | month start through end of today |
| previous_month | previous calendar month |
| custom | `from` and `to` as inclusive local dates (`to` is exclusive after +1 day) |

**Previous period:** the same number of local days immediately before the current window.  
**Previous month:** the prior calendar month, clipped to the current span length.

Maximum window: 366 days. Unknown IANA timezones are rejected.

## Health indicator

Internal MerchantOS score 0–100. **Not a forecast.**

| Component | Weight |
|-----------|--------|
| Revenue trend | 0.40 |
| Order volume | 0.20 |
| Inventory coverage | 0.25 |
| Customer activity | 0.15 |

Trend components map −20% → 0, 0% → 50, +20% → 100 (clamped). No activity in either period → `insufficient_data`.

## Opportunities

Deterministic rules only. Every card has title, explanation, metric, evidence, severity, and timestamp. No fabricated expected revenue.
