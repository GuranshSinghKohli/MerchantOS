from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from merchantos_domain import TenantContext
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from merchantos_db.ids import uuid7
from merchantos_db.models import (
    Customer,
    InventorySnapshot,
    Location,
    Order,
    OrderLine,
    Product,
    Variant,
)
from merchantos_db.rls import tenant_scope


@dataclass(frozen=True)
class ProductWrite:
    shopify_gid: str
    title: str
    status: str
    vendor: str
    product_type: str
    tags: list[str]
    published_at: datetime | None
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class VariantWrite:
    shopify_gid: str
    product_gid: str
    sku: str | None
    title: str
    price: Decimal
    compare_at_price: Decimal | None
    cost: Decimal | None
    inventory_item_gid: str | None


@dataclass(frozen=True)
class LocationWrite:
    shopify_gid: str
    name: str
    active: bool


@dataclass(frozen=True)
class CustomerWrite:
    shopify_gid: str
    email: str
    orders_count: int
    total_spent: Decimal
    state: str
    first_order_at: datetime | None = None
    last_order_at: datetime | None = None
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class OrderLineWrite:
    shopify_gid: str
    variant_gid: str | None
    quantity: int
    price: Decimal
    discount_allocation: Decimal
    cost_at_sale: Decimal | None = None


@dataclass(frozen=True)
class OrderWrite:
    shopify_gid: str
    customer_gid: str | None
    name: str
    processed_at: datetime | None
    financial_status: str
    fulfillment_status: str
    subtotal: Decimal
    total_discounts: Decimal
    total_price: Decimal
    currency: str
    cancelled_at: datetime | None
    lines: tuple[OrderLineWrite, ...]


@dataclass(frozen=True)
class InventoryWrite:
    variant_gid: str
    location_gid: str
    available: int
    on_hand: int
    captured_at: datetime


class CommerceRepository:
    """Tenant-scoped commerce projection. Requires TenantContext on every call."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_product(self, ctx: TenantContext, row: ProductWrite) -> UUID:
        with tenant_scope(self._session, ctx.merchant_id):
            values = {
                "id": uuid7(),
                "merchant_id": ctx.merchant_id,
                "store_id": ctx.store_id,
                "shopify_gid": row.shopify_gid,
                "title": row.title,
                "status": row.status,
                "vendor": row.vendor,
                "product_type": row.product_type,
                "tags": row.tags,
                "published_at": row.published_at,
                "deleted_at": row.deleted_at,
            }
            stmt = insert(Product).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["merchant_id", "shopify_gid"],
                set_={
                    "title": row.title,
                    "status": row.status,
                    "vendor": row.vendor,
                    "product_type": row.product_type,
                    "tags": row.tags,
                    "published_at": row.published_at,
                    "deleted_at": row.deleted_at,
                },
            )
            self._session.execute(stmt)
            found = self._session.scalar(
                select(Product.id).where(
                    Product.merchant_id == ctx.merchant_id,
                    Product.shopify_gid == row.shopify_gid,
                )
            )
            if found is None:
                raise RuntimeError("product upsert did not persist")
            return found

    def upsert_variant(self, ctx: TenantContext, row: VariantWrite) -> UUID | None:
        with tenant_scope(self._session, ctx.merchant_id):
            product = self._session.scalar(
                select(Product).where(
                    Product.merchant_id == ctx.merchant_id,
                    Product.shopify_gid == row.product_gid,
                )
            )
            if product is None:
                return None
            values = {
                "id": uuid7(),
                "merchant_id": ctx.merchant_id,
                "store_id": ctx.store_id,
                "product_id": product.id,
                "shopify_gid": row.shopify_gid,
                "sku": row.sku,
                "title": row.title,
                "price": row.price,
                "compare_at_price": row.compare_at_price,
                "cost": row.cost,
                "inventory_item_gid": row.inventory_item_gid,
            }
            stmt = insert(Variant).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["merchant_id", "shopify_gid"],
                set_={
                    "product_id": product.id,
                    "sku": row.sku,
                    "title": row.title,
                    "price": row.price,
                    "compare_at_price": row.compare_at_price,
                    "cost": row.cost,
                    "inventory_item_gid": row.inventory_item_gid,
                },
            )
            self._session.execute(stmt)
            found = self._session.scalar(
                select(Variant.id).where(
                    Variant.merchant_id == ctx.merchant_id,
                    Variant.shopify_gid == row.shopify_gid,
                )
            )
            return found

    def upsert_location(self, ctx: TenantContext, row: LocationWrite) -> UUID:
        with tenant_scope(self._session, ctx.merchant_id):
            values = {
                "id": uuid7(),
                "merchant_id": ctx.merchant_id,
                "store_id": ctx.store_id,
                "shopify_gid": row.shopify_gid,
                "name": row.name,
                "active": row.active,
            }
            stmt = insert(Location).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["merchant_id", "shopify_gid"],
                set_={"name": row.name, "active": row.active},
            )
            self._session.execute(stmt)
            found = self._session.scalar(
                select(Location.id).where(
                    Location.merchant_id == ctx.merchant_id,
                    Location.shopify_gid == row.shopify_gid,
                )
            )
            if found is None:
                raise RuntimeError("location upsert did not persist")
            return found

    def upsert_customer(self, ctx: TenantContext, row: CustomerWrite) -> UUID:
        with tenant_scope(self._session, ctx.merchant_id):
            values = {
                "id": uuid7(),
                "merchant_id": ctx.merchant_id,
                "store_id": ctx.store_id,
                "shopify_gid": row.shopify_gid,
                "email": row.email,
                "orders_count": row.orders_count,
                "total_spent": row.total_spent,
                "state": row.state,
                "first_order_at": row.first_order_at,
                "last_order_at": row.last_order_at,
                "deleted_at": row.deleted_at,
            }
            stmt = insert(Customer).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["merchant_id", "shopify_gid"],
                set_={
                    "email": row.email,
                    "orders_count": row.orders_count,
                    "total_spent": row.total_spent,
                    "state": row.state,
                    "first_order_at": row.first_order_at,
                    "last_order_at": row.last_order_at,
                    "deleted_at": row.deleted_at,
                },
            )
            self._session.execute(stmt)
            found = self._session.scalar(
                select(Customer.id).where(
                    Customer.merchant_id == ctx.merchant_id,
                    Customer.shopify_gid == row.shopify_gid,
                )
            )
            if found is None:
                raise RuntimeError("customer upsert did not persist")
            return found

    def ensure_customer_stub(self, ctx: TenantContext, shopify_gid: str) -> UUID:
        existing = self.get_customer_id(ctx, shopify_gid)
        if existing is not None:
            return existing
        return self.upsert_customer(
            ctx,
            CustomerWrite(
                shopify_gid=shopify_gid,
                email="",
                orders_count=0,
                total_spent=Decimal("0.00"),
                state="",
            ),
        )

    def upsert_order(self, ctx: TenantContext, row: OrderWrite) -> UUID:
        customer_id: UUID | None = None
        if row.customer_gid:
            customer_id = self.ensure_customer_stub(ctx, row.customer_gid)
        with tenant_scope(self._session, ctx.merchant_id):
            values = {
                "id": uuid7(),
                "merchant_id": ctx.merchant_id,
                "store_id": ctx.store_id,
                "customer_id": customer_id,
                "shopify_gid": row.shopify_gid,
                "name": row.name,
                "processed_at": row.processed_at,
                "financial_status": row.financial_status,
                "fulfillment_status": row.fulfillment_status,
                "subtotal": row.subtotal,
                "total_discounts": row.total_discounts,
                "total_price": row.total_price,
                "currency": row.currency,
                "cancelled_at": row.cancelled_at,
            }
            stmt = insert(Order).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["merchant_id", "shopify_gid"],
                set_={
                    "customer_id": customer_id,
                    "name": row.name,
                    "processed_at": row.processed_at,
                    "financial_status": row.financial_status,
                    "fulfillment_status": row.fulfillment_status,
                    "subtotal": row.subtotal,
                    "total_discounts": row.total_discounts,
                    "total_price": row.total_price,
                    "currency": row.currency,
                    "cancelled_at": row.cancelled_at,
                },
            )
            self._session.execute(stmt)
            order_id = self._session.scalar(
                select(Order.id).where(
                    Order.merchant_id == ctx.merchant_id,
                    Order.shopify_gid == row.shopify_gid,
                )
            )
            if order_id is None:
                raise RuntimeError("order upsert did not persist")
            if customer_id is not None and row.processed_at is not None:
                customer = self._session.get(Customer, customer_id)
                if customer is not None:
                    first = customer.first_order_at
                    last = customer.last_order_at
                    if first is None or row.processed_at < first:
                        customer.first_order_at = row.processed_at
                    if last is None or row.processed_at > last:
                        customer.last_order_at = row.processed_at
            for line in row.lines:
                variant_id = (
                    self.get_variant_id(ctx, line.variant_gid) if line.variant_gid else None
                )
                line_values = {
                    "id": uuid7(),
                    "merchant_id": ctx.merchant_id,
                    "store_id": ctx.store_id,
                    "order_id": order_id,
                    "variant_id": variant_id,
                    "shopify_gid": line.shopify_gid,
                    "quantity": line.quantity,
                    "price": line.price,
                    "discount_allocation": line.discount_allocation,
                    "cost_at_sale": line.cost_at_sale,
                }
                line_stmt = insert(OrderLine).values(**line_values)
                line_stmt = line_stmt.on_conflict_do_update(
                    index_elements=["merchant_id", "shopify_gid"],
                    set_={
                        "order_id": order_id,
                        "variant_id": variant_id,
                        "quantity": line.quantity,
                        "price": line.price,
                        "discount_allocation": line.discount_allocation,
                        "cost_at_sale": line.cost_at_sale,
                    },
                )
                self._session.execute(line_stmt)
            return order_id

    def upsert_inventory(self, ctx: TenantContext, row: InventoryWrite) -> UUID | None:
        variant_id = self.get_variant_id(ctx, row.variant_gid)
        location_id = self.get_location_id(ctx, row.location_gid)
        if variant_id is None or location_id is None:
            return None
        with tenant_scope(self._session, ctx.merchant_id):
            values = {
                "id": uuid7(),
                "merchant_id": ctx.merchant_id,
                "store_id": ctx.store_id,
                "variant_id": variant_id,
                "location_id": location_id,
                "available": row.available,
                "on_hand": row.on_hand,
                "captured_at": row.captured_at,
            }
            stmt = insert(InventorySnapshot).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["merchant_id", "variant_id", "location_id", "captured_at"],
                set_={"available": row.available, "on_hand": row.on_hand},
            )
            self._session.execute(stmt)
            found = self._session.scalar(
                select(InventorySnapshot.id).where(
                    InventorySnapshot.merchant_id == ctx.merchant_id,
                    InventorySnapshot.variant_id == variant_id,
                    InventorySnapshot.location_id == location_id,
                    InventorySnapshot.captured_at == row.captured_at,
                )
            )
            return found

    def mark_product_deleted(self, ctx: TenantContext, shopify_gid: str, when: datetime) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            product = self._session.scalar(
                select(Product).where(
                    Product.merchant_id == ctx.merchant_id,
                    Product.shopify_gid == shopify_gid,
                )
            )
            if product is not None:
                product.deleted_at = when

    def mark_customer_deleted(self, ctx: TenantContext, shopify_gid: str, when: datetime) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            customer = self._session.scalar(
                select(Customer).where(
                    Customer.merchant_id == ctx.merchant_id,
                    Customer.shopify_gid == shopify_gid,
                )
            )
            if customer is not None:
                customer.deleted_at = when

    def get_product(self, ctx: TenantContext, shopify_gid: str) -> Product | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Product).where(
                    Product.merchant_id == ctx.merchant_id,
                    Product.shopify_gid == shopify_gid,
                )
            )

    def list_products(self, ctx: TenantContext) -> list[Product]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(select(Product).where(Product.merchant_id == ctx.merchant_id))
            )

    def list_variants(self, ctx: TenantContext) -> list[Variant]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(select(Variant).where(Variant.merchant_id == ctx.merchant_id))
            )

    def list_orders(self, ctx: TenantContext) -> list[Order]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(select(Order).where(Order.merchant_id == ctx.merchant_id))
            )

    def list_order_lines(self, ctx: TenantContext) -> list[OrderLine]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(OrderLine).where(OrderLine.merchant_id == ctx.merchant_id)
                )
            )

    def list_customers(self, ctx: TenantContext) -> list[Customer]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(Customer).where(Customer.merchant_id == ctx.merchant_id)
                )
            )

    def list_locations(self, ctx: TenantContext) -> list[Location]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(Location).where(Location.merchant_id == ctx.merchant_id)
                )
            )

    def list_inventory(self, ctx: TenantContext) -> list[InventorySnapshot]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(InventorySnapshot).where(
                        InventorySnapshot.merchant_id == ctx.merchant_id
                    )
                )
            )

    def get_customer_id(self, ctx: TenantContext, shopify_gid: str) -> UUID | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Customer.id).where(
                    Customer.merchant_id == ctx.merchant_id,
                    Customer.shopify_gid == shopify_gid,
                )
            )

    def get_variant_id(self, ctx: TenantContext, shopify_gid: str) -> UUID | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Variant.id).where(
                    Variant.merchant_id == ctx.merchant_id,
                    Variant.shopify_gid == shopify_gid,
                )
            )

    def get_variant_id_by_inventory_item(
        self, ctx: TenantContext, inventory_item_gid: str
    ) -> UUID | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Variant.id).where(
                    Variant.merchant_id == ctx.merchant_id,
                    Variant.inventory_item_gid == inventory_item_gid,
                )
            )

    def get_variant_gid_by_inventory_item(
        self, ctx: TenantContext, inventory_item_gid: str
    ) -> str | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Variant.shopify_gid).where(
                    Variant.merchant_id == ctx.merchant_id,
                    Variant.inventory_item_gid == inventory_item_gid,
                )
            )

    def get_location_id(self, ctx: TenantContext, shopify_gid: str) -> UUID | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Location.id).where(
                    Location.merchant_id == ctx.merchant_id,
                    Location.shopify_gid == shopify_gid,
                )
            )
