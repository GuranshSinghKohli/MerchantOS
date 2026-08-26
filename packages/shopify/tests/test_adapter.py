from datetime import UTC, datetime

import httpx
from merchantos_shopify.adapter import ShopifyAdapter
from merchantos_shopify.constants import ADMIN_API_VERSION


def test_exchange_and_shop_query_use_official_surfaces() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/admin/oauth/access_token"):
            assert b"expiring=1" in request.content
            assert b"client_secret" in request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "shpua_test",
                    "scope": "read_products",
                    "expires_in": 3600,
                    "refresh_token": "refresh",
                    "refresh_token_expires_in": 86400,
                },
            )
        assert request.url.path.endswith(f"/admin/api/{ADMIN_API_VERSION}/graphql.json")
        assert request.headers["X-Shopify-Access-Token"] == "shpua_test"
        return httpx.Response(
            200,
            json={
                "data": {
                    "shop": {
                        "id": "gid://shopify/Shop/1",
                        "name": "Acme",
                        "myshopifyDomain": "acme.myshopify.com",
                        "primaryDomain": {"host": "acme.myshopify.com"},
                        "currencyCode": "USD",
                        "ianaTimezone": "America/New_York",
                        "plan": {"displayName": "Developer Preview"},
                    }
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ShopifyAdapter(client_id="id", client_secret="secret", http=http)
    grant = adapter.exchange_code("acme.myshopify.com", "code")
    assert grant.access_token == "shpua_test"
    assert grant.expires_at is not None
    shop = adapter.fetch_shop("acme.myshopify.com", grant.access_token)
    assert shop.shopify_shop_gid == "gid://shopify/Shop/1"
    assert shop.myshopify_domain == "acme.myshopify.com"
    _ = datetime.now(UTC)
