from __future__ import annotations

from datetime import datetime

from merchantos_db import (
    CommerceRepository,
    CustomerWrite,
    InventoryWrite,
    LocationWrite,
    OrderLineWrite,
    OrderWrite,
    ProductWrite,
    VariantWrite,
)
from merchantos_domain import TenantContext
from merchantos_shopify.reader import (
    CustomerRecord,
    InventoryRecord,
    LocationRecord,
    OrderRecord,
    ProductRecord,
)


def apply_product(repo: CommerceRepository, ctx: TenantContext, record: ProductRecord) -> None:
    repo.upsert_product(
        ctx,
        ProductWrite(
            shopify_gid=record.shopify_gid,
            title=record.title,
            status=record.status,
            vendor=record.vendor,
            product_type=record.product_type,
            tags=list(record.tags),
            published_at=record.published_at,
        ),
    )
    for variant in record.variants:
        repo.upsert_variant(
            ctx,
            VariantWrite(
                shopify_gid=variant.shopify_gid,
                product_gid=record.shopify_gid,
                sku=variant.sku,
                title=variant.title,
                price=variant.price,
                compare_at_price=variant.compare_at_price,
                cost=variant.cost,
                inventory_item_gid=variant.inventory_item_gid,
            ),
        )


def apply_order(repo: CommerceRepository, ctx: TenantContext, record: OrderRecord) -> None:
    repo.upsert_order(
        ctx,
        OrderWrite(
            shopify_gid=record.shopify_gid,
            customer_gid=record.customer_gid,
            name=record.name,
            processed_at=record.processed_at,
            financial_status=record.financial_status,
            fulfillment_status=record.fulfillment_status,
            subtotal=record.subtotal,
            total_discounts=record.total_discounts,
            total_price=record.total_price,
            currency=record.currency,
            cancelled_at=record.cancelled_at,
            lines=tuple(
                OrderLineWrite(
                    shopify_gid=line.shopify_gid,
                    variant_gid=line.variant_gid,
                    quantity=line.quantity,
                    price=line.price,
                    discount_allocation=line.discount_allocation,
                )
                for line in record.lines
            ),
        ),
    )


def apply_customer(repo: CommerceRepository, ctx: TenantContext, record: CustomerRecord) -> None:
    repo.upsert_customer(
        ctx,
        CustomerWrite(
            shopify_gid=record.shopify_gid,
            email=record.email,
            orders_count=record.orders_count,
            total_spent=record.total_spent,
            state=record.state,
        ),
    )


def apply_location(repo: CommerceRepository, ctx: TenantContext, record: LocationRecord) -> None:
    repo.upsert_location(
        ctx,
        LocationWrite(shopify_gid=record.shopify_gid, name=record.name, active=record.active),
    )


def apply_inventory(
    repo: CommerceRepository,
    ctx: TenantContext,
    record: InventoryRecord,
    captured_at: datetime,
) -> bool:
    result = repo.upsert_inventory(
        ctx,
        InventoryWrite(
            variant_gid=record.variant_gid,
            location_gid=record.location_gid,
            available=record.available,
            on_hand=record.on_hand,
            captured_at=captured_at,
        ),
    )
    return result is not None


def incremental_query(since: datetime | None) -> str | None:
    if since is None:
        return None
    return f"updated_at:>'{since.strftime('%Y-%m-%dT%H:%M:%SZ')}'"
