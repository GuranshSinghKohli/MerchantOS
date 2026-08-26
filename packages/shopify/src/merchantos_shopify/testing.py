"""In-process ShopifyReader fake for tests. Not a live Shopify client."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from merchantos_domain import ShopifyThrottledError, TransientJobError

from merchantos_shopify.reader import (
    CustomerRecord,
    InventoryRecord,
    LocationRecord,
    OrderLineRecord,
    OrderRecord,
    Page,
    ProductRecord,
    VariantRecord,
)


def sample_product(n: int, *, title: str | None = None) -> ProductRecord:
    return ProductRecord(
        shopify_gid=f"gid://shopify/Product/{n}",
        title=title or f"Product {n}",
        status="ACTIVE",
        vendor="Acme",
        product_type="widget",
        tags=("summer",),
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        variants=(
            VariantRecord(
                shopify_gid=f"gid://shopify/ProductVariant/{n}",
                title="Default",
                sku=f"SKU-{n}",
                price=Decimal("10.00"),
                compare_at_price=Decimal("12.00"),
                cost=Decimal("4.00"),
                inventory_item_gid=f"gid://shopify/InventoryItem/{n}",
            ),
        ),
    )


def sample_order(n: int) -> OrderRecord:
    return OrderRecord(
        shopify_gid=f"gid://shopify/Order/{n}",
        name=f"#{n}",
        processed_at=datetime(2026, 2, 1, tzinfo=UTC),
        cancelled_at=None,
        financial_status="PAID",
        fulfillment_status="UNFULFILLED",
        currency="USD",
        subtotal=Decimal("10.00"),
        total_discounts=Decimal("0.00"),
        total_price=Decimal("10.00"),
        customer_gid=f"gid://shopify/Customer/{n}",
        lines=(
            OrderLineRecord(
                shopify_gid=f"gid://shopify/LineItem/{n}",
                variant_gid=f"gid://shopify/ProductVariant/{n}",
                quantity=1,
                price=Decimal("10.00"),
                discount_allocation=Decimal("0.00"),
            ),
        ),
    )


def sample_customer(n: int) -> CustomerRecord:
    return CustomerRecord(
        shopify_gid=f"gid://shopify/Customer/{n}",
        email=f"c{n}@example.com",
        orders_count=1,
        total_spent=Decimal("10.00"),
        state="ENABLED",
    )


def sample_location(n: int = 1) -> LocationRecord:
    return LocationRecord(shopify_gid=f"gid://shopify/Location/{n}", name="HQ", active=True)


def sample_inventory(n: int = 1) -> InventoryRecord:
    return InventoryRecord(
        variant_gid=f"gid://shopify/ProductVariant/{n}",
        inventory_item_gid=f"gid://shopify/InventoryItem/{n}",
        location_gid=f"gid://shopify/Location/{n}",
        available=7,
        on_hand=9,
    )


class FakeShopifyReader:
    def __init__(self) -> None:
        self.products = [sample_product(1), sample_product(2)]
        self.orders = [sample_order(1)]
        self.customers = [sample_customer(1)]
        self.locations = [sample_location(1)]
        self.inventory = [sample_inventory(1)]
        self.page_size = 50
        self.inject_bad_item = False
        self.fail_resource: str | None = None
        self.throttle_remaining = 0
        self.transient_remaining = 0
        self.calls = 0
        self.last_retries = 0
        self.last_query: str | None = None

    def _page(self, items: list[object], after: str | None, resource: str) -> Page[object]:
        self.calls += 1
        if self.throttle_remaining > 0:
            self.throttle_remaining -= 1
            self.last_retries += 1
            raise ShopifyThrottledError("throttled")
        if self.transient_remaining > 0:
            self.transient_remaining -= 1
            raise TransientJobError("transient")
        if self.fail_resource == resource:
            raise RuntimeError("forced resource failure")
        start = 0 if after is None else int(after) + 1
        chunk = items[start : start + self.page_size]
        if self.inject_bad_item and resource == "products":
            chunk = [*chunk, object()]
        has_next = start + self.page_size < len(items)
        end = str(start + len(chunk) - 1) if chunk else after
        return Page(items=tuple(chunk), has_next=has_next, end_cursor=end)

    def fetch_products_page(
        self, shop: str, access_token: str, *, after: str | None, query: str | None, first: int
    ) -> Page[ProductRecord]:
        _ = shop, access_token, first
        self.last_query = query
        return self._page(list(self.products), after, "products")  # type: ignore[return-value]

    def fetch_orders_page(
        self, shop: str, access_token: str, *, after: str | None, query: str | None, first: int
    ) -> Page[OrderRecord]:
        _ = shop, access_token, query, first
        return self._page(list(self.orders), after, "orders")  # type: ignore[return-value]

    def fetch_customers_page(
        self, shop: str, access_token: str, *, after: str | None, query: str | None, first: int
    ) -> Page[CustomerRecord]:
        _ = shop, access_token, query, first
        return self._page(list(self.customers), after, "customers")  # type: ignore[return-value]

    def fetch_locations_page(
        self, shop: str, access_token: str, *, after: str | None, first: int
    ) -> Page[LocationRecord]:
        _ = shop, access_token, first
        return self._page(list(self.locations), after, "locations")  # type: ignore[return-value]

    def fetch_inventory_page(
        self, shop: str, access_token: str, *, after: str | None, first: int
    ) -> Page[InventoryRecord]:
        _ = shop, access_token, first
        return self._page(list(self.inventory), after, "inventory")  # type: ignore[return-value]

    def fetch_product(self, shop: str, access_token: str, gid: str) -> ProductRecord | None:
        _ = shop, access_token
        return next((row for row in self.products if row.shopify_gid == gid), None)

    def fetch_order(self, shop: str, access_token: str, gid: str) -> OrderRecord | None:
        _ = shop, access_token
        return next((row for row in self.orders if row.shopify_gid == gid), None)

    def fetch_customer(self, shop: str, access_token: str, gid: str) -> CustomerRecord | None:
        _ = shop, access_token
        return next((row for row in self.customers if row.shopify_gid == gid), None)

    def fetch_location(self, shop: str, access_token: str, gid: str) -> LocationRecord | None:
        _ = shop, access_token
        return next((row for row in self.locations if row.shopify_gid == gid), None)
