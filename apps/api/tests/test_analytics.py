from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from merchantos_api.deps import db_engine, settings
from merchantos_api.main import create_app
from merchantos_api.session_cookie import SESSION_COOKIE
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
    session_scope,
)
from merchantos_domain import TenantContext
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.port import ShopInfo

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


def _seed_sale(
    db,
    ctx: TenantContext,
    *,
    suffix: str,
    processed_at: datetime,
    total: str,
    qty: int,
    available: int,
    financial: str = "PAID",
    cancelled: bool = False,
    email: str = "",
    orders_count: int = 1,
    first_order_at: datetime | None = None,
) -> None:
    commerce = CommerceRepository(db)
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
            published_at=processed_at,
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
            email=email,
            orders_count=orders_count,
            total_spent=Decimal(total),
            state="ENABLED",
            first_order_at=first_order_at or processed_at,
            last_order_at=processed_at,
        ),
    )
    commerce.upsert_order(
        ctx,
        OrderWrite(
            shopify_gid=f"gid://shopify/Order/{suffix}",
            customer_gid=customer_gid,
            name=f"#{suffix}",
            processed_at=processed_at,
            financial_status=financial,
            fulfillment_status="FULFILLED",
            subtotal=Decimal(total),
            total_discounts=Decimal("0"),
            total_price=Decimal(total),
            currency="USD",
            cancelled_at=processed_at if cancelled else None,
            lines=(
                OrderLineWrite(
                    shopify_gid=f"gid://shopify/LineItem/{suffix}",
                    variant_gid=variant_gid,
                    quantity=qty,
                    price=Decimal(total) / Decimal(qty),
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
            available=available,
            on_hand=available + 1,
            captured_at=processed_at,
        ),
    )


def _client() -> TestClient:
    settings.cache_clear()
    db_engine.cache_clear()
    return TestClient(create_app())


def test_overview_metrics_and_exclusions(postgres: None) -> None:
    now = datetime(2026, 8, 20, 15, tzinfo=UTC)
    with session_scope(db_engine()) as db:
        view = _install(db, "alpha.myshopify.com")
        ctx = _ctx(view)
        _seed_sale(db, ctx, suffix="paid", processed_at=now, total="100.00", qty=2, available=3)
        _seed_sale(
            db,
            ctx,
            suffix="refund",
            processed_at=now,
            total="40.00",
            qty=1,
            available=1,
            financial="REFUNDED",
        )
        _seed_sale(
            db,
            ctx,
            suffix="cancel",
            processed_at=now,
            total="25.00",
            qty=1,
            available=1,
            cancelled=True,
        )
        _seed_sale(
            db,
            ctx,
            suffix="old",
            processed_at=datetime(2026, 7, 10, tzinfo=UTC),
            total="50.00",
            qty=1,
            available=9,
        )
        session_id = str(view.session_id)
    client = _client()
    response = client.get(
        "/api/v1/analytics/overview",
        params={"preset": "custom", "from": "2026-08-01", "to": "2026-08-31"},
        cookies={SESSION_COOKIE: session_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["revenue"] == "100.00"
    assert body["kpis"]["orders"] == 1
    assert body["kpis"]["aov"] == "100.00"
    assert body["kpis"]["cancelled_orders"] == 1
    assert body["kpis"]["excluded_financial_orders"] == 1
    assert body["kpis"]["previous"]["revenue"] == "50.00"
    assert body["kpis"]["growth_pct"]["revenue"] == "100.00"
    assert body["store"]["shop_domain"] == "alpha.myshopify.com"
    assert "shpua_" not in response.text
    assert "@" not in "".join(str(item) for item in body["products"])
    assert body["health"]["score"] is not None
    assert body["request_id"]
    customers = client.get(
        "/api/v1/analytics/customers",
        params={"preset": "custom", "from": "2026-08-01", "to": "2026-08-31"},
        cookies={SESSION_COOKIE: session_id},
    ).json()
    assert isinstance(customers["kpis"]["growth_pct"], dict)
    assert customers["kpis"]["growth_pct"]["customers"] is not None


def test_tenant_isolation_across_analytics_endpoints(postgres: None) -> None:
    when = datetime(2026, 8, 15, tzinfo=UTC)
    with session_scope(db_engine()) as db:
        a = _install(db, "alpha.myshopify.com")
        b = _install(db, "beta.myshopify.com")
        _seed_sale(db, _ctx(a), suffix="a1", processed_at=when, total="80.00", qty=1, available=4)
        _seed_sale(db, _ctx(b), suffix="b1", processed_at=when, total="999.00", qty=3, available=2)
        sid_a, sid_b = str(a.session_id), str(b.session_id)
    client = _client()
    paths = (
        "/api/v1/overview",
        "/api/v1/analytics/overview",
        "/api/v1/analytics/revenue",
        "/api/v1/analytics/orders",
        "/api/v1/analytics/products",
        "/api/v1/analytics/inventory",
        "/api/v1/analytics/customers",
        "/api/v1/analytics/health",
        "/api/v1/analytics/opportunities",
    )
    for path in paths:
        params = {"preset": "custom", "from": "2026-08-01", "to": "2026-08-31"}
        a_res = client.get(path, params=params, cookies={SESSION_COOKIE: sid_a})
        b_res = client.get(path, params=params, cookies={SESSION_COOKIE: sid_b})
        assert a_res.status_code == 200, path
        assert b_res.status_code == 200, path
        assert "999" not in a_res.text
        assert "Product b1" not in a_res.text
        assert "Product a1" not in b_res.text
        assert a_res.json()["store"]["shop_domain"] == "alpha.myshopify.com"
        assert b_res.json()["store"]["shop_domain"] == "beta.myshopify.com"


def test_analytics_requires_session_and_rejects_bad_range(postgres: None) -> None:
    client = _client()
    assert client.get("/api/v1/analytics/overview").status_code == 401
    with session_scope(db_engine()) as db:
        view = _install(db, "alpha.myshopify.com")
        sid = str(view.session_id)
    bad = client.get(
        "/api/v1/analytics/overview",
        params={"preset": "custom", "from": "2026-08-20", "to": "2026-08-01"},
        cookies={SESSION_COOKIE: sid},
    )
    assert bad.status_code == 400
    assert "stack" not in bad.text.lower()
    ignored = client.get(
        "/api/v1/analytics/overview",
        params={"preset": "last_7", "merchant_id": str(uuid4())},
        cookies={SESSION_COOKIE: sid},
    )
    assert ignored.status_code == 200
    assert ignored.json()["kpis"]["revenue"] == "0.00"


def test_empty_store_has_empty_analytics(postgres: None) -> None:
    with session_scope(db_engine()) as db:
        view = _install(db, "empty.myshopify.com")
        sid = str(view.session_id)
    client = _client()
    body = client.get(
        "/api/v1/analytics/overview",
        params={"preset": "last_30"},
        cookies={SESSION_COOKIE: sid},
    ).json()
    assert body["kpis"]["orders"] == 0
    assert body["kpis"]["aov"] is None
    assert body["health"]["status"] == "insufficient_data"
    assert body["opportunities"] == []
    assert body["products"] == []
