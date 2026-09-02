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


def test_customers_page_falls_back_when_email_is_denied() -> None:
    states = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        states["n"] += 1
        if "defaultEmailAddress" in body:
            return httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Access denied for defaultEmailAddress field.",
                            "extensions": {"code": "ACCESS_DENIED"},
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "customers": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/Customer/1",
                                    "numberOfOrders": 2,
                                    "state": "ENABLED",
                                    "amountSpent": {"amount": "12.00"},
                                }
                            }
                        ],
                    }
                }
            },
        )

    adapter = ShopifyAdapter(
        client_id="id",
        client_secret="secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    page = adapter.fetch_customers_page(
        "acme.myshopify.com", "tok", after=None, query=None, first=5
    )
    assert states["n"] == 2
    assert len(page.items) == 1
    assert page.items[0].shopify_gid == "gid://shopify/Customer/1"
    assert page.items[0].email == ""


def test_customers_page_empty_when_list_is_denied() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(
            200,
            json={
                "errors": [
                    {
                        "message": "Access denied for customers field.",
                        "extensions": {"code": "ACCESS_DENIED"},
                    }
                ]
            },
        )

    adapter = ShopifyAdapter(
        client_id="id",
        client_secret="secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    page = adapter.fetch_customers_page(
        "acme.myshopify.com", "tok", after=None, query=None, first=5
    )
    assert page.items == ()
    assert page.has_next is False
