from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    has_next: bool
    end_cursor: str | None


@dataclass(frozen=True)
class VariantRecord:
    shopify_gid: str
    title: str
    sku: str | None
    price: Decimal
    compare_at_price: Decimal | None
    cost: Decimal | None
    inventory_item_gid: str | None


@dataclass(frozen=True)
class ProductRecord:
    shopify_gid: str
    title: str
    status: str
    vendor: str
    product_type: str
    tags: tuple[str, ...]
    published_at: datetime | None
    variants: tuple[VariantRecord, ...]


@dataclass(frozen=True)
class OrderLineRecord:
    shopify_gid: str
    variant_gid: str | None
    quantity: int
    price: Decimal
    discount_allocation: Decimal


@dataclass(frozen=True)
class OrderRecord:
    shopify_gid: str
    name: str
    processed_at: datetime | None
    cancelled_at: datetime | None
    financial_status: str
    fulfillment_status: str
    currency: str
    subtotal: Decimal
    total_discounts: Decimal
    total_price: Decimal
    customer_gid: str | None
    lines: tuple[OrderLineRecord, ...]


@dataclass(frozen=True)
class CustomerRecord:
    shopify_gid: str
    email: str
    orders_count: int
    total_spent: Decimal
    state: str


@dataclass(frozen=True)
class LocationRecord:
    shopify_gid: str
    name: str
    active: bool


@dataclass(frozen=True)
class InventoryRecord:
    variant_gid: str
    inventory_item_gid: str | None
    location_gid: str
    available: int
    on_hand: int


class ShopifyReader(Protocol):
    """Read-only Shopify projection source. No mutations."""

    def fetch_products_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        query: str | None,
        first: int,
    ) -> Page[ProductRecord]: ...

    def fetch_orders_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        query: str | None,
        first: int,
    ) -> Page[OrderRecord]: ...

    def fetch_customers_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        query: str | None,
        first: int,
    ) -> Page[CustomerRecord]: ...

    def fetch_locations_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        first: int,
    ) -> Page[LocationRecord]: ...

    def fetch_inventory_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        first: int,
    ) -> Page[InventoryRecord]: ...

    def fetch_product(self, shop: str, access_token: str, gid: str) -> ProductRecord | None: ...

    def fetch_order(self, shop: str, access_token: str, gid: str) -> OrderRecord | None: ...

    def fetch_customer(self, shop: str, access_token: str, gid: str) -> CustomerRecord | None: ...

    def fetch_location(self, shop: str, access_token: str, gid: str) -> LocationRecord | None: ...
