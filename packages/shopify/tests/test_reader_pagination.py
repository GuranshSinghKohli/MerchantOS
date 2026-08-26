import json
from decimal import Decimal

import httpx
from merchantos_shopify.adapter import ShopifyAdapter
from merchantos_shopify.constants import ADMIN_API_VERSION


def test_products_pagination_and_official_path() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        calls.append(payload)
        after = (payload.get("variables") or {}).get("after")
        assert request.url.path.endswith(f"/admin/api/{ADMIN_API_VERSION}/graphql.json")
        if after is None:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "products": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                            "edges": [
                                {
                                    "node": {
                                        "id": "gid://shopify/Product/1",
                                        "title": "One",
                                        "status": "ACTIVE",
                                        "vendor": "Acme",
                                        "productType": "widget",
                                        "tags": ["a"],
                                        "publishedAt": "2026-01-01T00:00:00Z",
                                        "variants": {
                                            "edges": [
                                                {
                                                    "node": {
                                                        "id": "gid://shopify/ProductVariant/1",
                                                        "title": "Default",
                                                        "sku": "S1",
                                                        "price": "9.00",
                                                        "compareAtPrice": None,
                                                        "inventoryItem": {
                                                            "id": "gid://shopify/InventoryItem/1",
                                                            "unitCost": {"amount": "2.00"},
                                                        },
                                                    }
                                                }
                                            ]
                                        },
                                    }
                                }
                            ],
                        }
                    },
                    "extensions": {
                        "cost": {
                            "throttleStatus": {
                                "currentlyAvailable": 900,
                                "restoreRate": 50,
                                "maximumAvailable": 1000,
                            }
                        }
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "products": {
                        "pageInfo": {"hasNextPage": False, "endCursor": "c2"},
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/Product/2",
                                    "title": "Two",
                                    "status": "ACTIVE",
                                    "vendor": "Acme",
                                    "productType": "widget",
                                    "tags": [],
                                    "publishedAt": None,
                                    "variants": {"edges": []},
                                }
                            }
                        ],
                    }
                }
            },
        )

    slept: list[float] = []
    adapter = ShopifyAdapter(
        client_id="id",
        client_secret="secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=slept.append,
        jitter=lambda: 0.0,
    )
    page1 = adapter.fetch_products_page(
        "acme.myshopify.com", "tok", after=None, query=None, first=1
    )
    page2 = adapter.fetch_products_page(
        "acme.myshopify.com", "tok", after=page1.end_cursor, query=None, first=1
    )
    assert page1.has_next is True
    assert page1.items[0].title == "One"
    assert page1.items[0].variants[0].price == Decimal("9.00")
    assert page2.has_next is False
    assert page2.items[0].shopify_gid == "gid://shopify/Product/2"
    assert len(calls) == 2
