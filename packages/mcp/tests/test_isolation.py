import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_app import AnalyticsService
from merchantos_db import (
    CommerceRepository,
    CustomerWrite,
    IdentityRepository,
    InventoryWrite,
    LocationWrite,
    OrderLineWrite,
    OrderWrite,
    ProductWrite,
    VariantWrite,
    create_db_engine,
    session_scope,
)
from merchantos_domain import TenantContext
from merchantos_mcp import build_commerce_registry
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.port import ShopInfo

from .fakes import ALL_READ

pytestmark = pytest.mark.integration
TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _ctx(view) -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            user_id=view.user_id,
            request_id=uuid4(),
            scopes=view.scopes,
        )
    )


def _install(db, shop: str):
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    return IdentityRepository(db).persist_installation(
        shop_info=ShopInfo(
            shopify_shop_gid=f"gid://shopify/Shop/{shop}",
            name=shop.split(".")[0],
            myshopify_domain=shop,
            primary_host=shop,
            currency="USD",
            iana_timezone="UTC",
            plan_name="dev",
        ),
        encrypted_token=encryptor.encrypt("shpua_test"),
        encrypted_refresh=None,
        token_expires_at=None,
        refresh_expires_at=None,
        scopes=("read_products", "read_orders", "read_customers", "read_inventory"),
        key_version="test",
        session_ttl=datetime.now(UTC) + timedelta(hours=1),
        request_id=uuid4(),
    )


def _seed_sale(db, ctx: TenantContext, *, suffix: str, total: str) -> None:
    commerce = CommerceRepository(db)
    when = datetime(2026, 8, 15, tzinfo=UTC)
    product_gid = f"gid://shopify/Product/{suffix}"
    variant_gid = f"gid://shopify/ProductVariant/{suffix}"
    location_gid = f"gid://shopify/Location/{suffix}"
    customer_gid = f"gid://shopify/Customer/{suffix}"
    commerce.upsert_product(
        ctx,
        ProductWrite(
            shopify_gid=product_gid,
            title=f"Product {suffix}",
            status="ACTIVE",
            vendor="Acme",
            product_type="Mug",
            tags=[],
            published_at=when,
        ),
    )
    commerce.upsert_variant(
        ctx,
        VariantWrite(
            shopify_gid=variant_gid,
            product_gid=product_gid,
            sku=suffix,
            title="Default",
            price=Decimal(total),
            compare_at_price=None,
            cost=None,
            inventory_item_gid=None,
        ),
    )
    commerce.upsert_location(ctx, LocationWrite(shopify_gid=location_gid, name="HQ", active=True))
    commerce.upsert_customer(
        ctx,
        CustomerWrite(
            shopify_gid=customer_gid,
            email=f"{suffix}@example.com",
            orders_count=1,
            total_spent=Decimal(total),
            state="ENABLED",
            first_order_at=when,
            last_order_at=when,
        ),
    )
    commerce.upsert_order(
        ctx,
        OrderWrite(
            shopify_gid=f"gid://shopify/Order/{suffix}",
            customer_gid=customer_gid,
            name=f"#{suffix}",
            processed_at=when,
            financial_status="PAID",
            fulfillment_status="FULFILLED",
            subtotal=Decimal(total),
            total_discounts=Decimal("0"),
            total_price=Decimal(total),
            currency="USD",
            cancelled_at=None,
            lines=(
                OrderLineWrite(
                    shopify_gid=f"gid://shopify/LineItem/{suffix}",
                    variant_gid=variant_gid,
                    quantity=1,
                    price=Decimal(total),
                    discount_allocation=Decimal("0"),
                ),
            ),
        ),
    )
    commerce.upsert_inventory(
        ctx,
        InventoryWrite(
            variant_gid=variant_gid,
            location_gid=location_gid,
            available=4,
            on_hand=5,
            captured_at=when,
        ),
    )


def _registry():
    url = os.environ["DATABASE_URL"]
    return build_commerce_registry(AnalyticsService(create_db_engine(url)))


def test_tools_return_real_analytics_for_trusted_tenant(postgres: None) -> None:
    url = os.environ["DATABASE_URL"]
    with session_scope(create_db_engine(url)) as db:
        view = _install(db, "alpha.myshopify.com")
        ctx = _ctx(view)
        _seed_sale(db, ctx, suffix="paid", total="100.00")
    registry = _registry()
    args = {"preset": "custom", "from": "2026-08-01", "to": "2026-08-31"}
    overview = registry.invoke("get_store_overview", args, ctx, permissions=ALL_READ)
    assert overview["kpis"]["revenue"] == "100.00"
    assert overview["store"]["shop_domain"] == "alpha.myshopify.com"
    assert "example.com" not in str(overview)
    assert "shpua_" not in str(overview)
    revenue = registry.invoke("get_revenue_metrics", args, ctx, permissions=ALL_READ)
    assert revenue["kpis"]["revenue"] == "100.00"
    products = registry.invoke(
        "get_product_performance",
        {**args, "limit": 10},
        ctx,
        permissions=ALL_READ,
    )
    assert products["items"][0]["title"] == "Product paid"


def test_tenant_a_cannot_read_tenant_b_via_tool_args(postgres: None) -> None:
    url = os.environ["DATABASE_URL"]
    with session_scope(create_db_engine(url)) as db:
        a = _install(db, "alpha.myshopify.com")
        b = _install(db, "beta.myshopify.com")
        ctx_a = _ctx(a)
        ctx_b = _ctx(b)
        _seed_sale(db, ctx_a, suffix="a1", total="80.00")
        _seed_sale(db, ctx_b, suffix="b1", total="999.00")
    registry = _registry()
    names = (
        "get_store_overview",
        "get_revenue_metrics",
        "get_order_metrics",
        "get_product_performance",
        "get_inventory_health",
        "get_customer_metrics",
        "get_sales_trends",
        "get_merchant_health",
        "get_opportunities",
    )
    poisoned = {
        "preset": "custom",
        "from": "2026-08-01",
        "to": "2026-08-31",
        "tenant_id": str(b.merchant_id),
        "merchant_id": str(b.merchant_id),
        "store_id": str(b.store_id),
    }
    for name in names:
        out = registry.invoke(name, poisoned, ctx_a, permissions=ALL_READ)
        blob = str(out)
        assert "999.00" not in blob
        assert "Product b1" not in blob
        assert "beta.myshopify.com" not in blob
        assert out["store"]["shop_domain"] == "alpha.myshopify.com"
        assert out["store"]["store_id"] == str(a.store_id)


def test_empty_store_tools_are_bounded(postgres: None) -> None:
    url = os.environ["DATABASE_URL"]
    with session_scope(create_db_engine(url)) as db:
        view = _install(db, "empty.myshopify.com")
        ctx = _ctx(view)
    registry = _registry()
    out = registry.invoke("get_store_overview", {"preset": "last_30"}, ctx, permissions=ALL_READ)
    assert out["kpis"]["orders"] == 0
    assert out["opportunities"] == []
    assert out["health"]["status"] == "insufficient_data"
