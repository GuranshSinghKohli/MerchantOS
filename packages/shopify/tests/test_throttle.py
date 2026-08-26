import json

import httpx
import pytest
from merchantos_domain import ShopifyThrottledError
from merchantos_shopify.adapter import ShopifyAdapter


def test_http_429_then_success() -> None:
    states = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        states["n"] += 1
        if states["n"] == 1:
            return httpx.Response(429, json={})
        return httpx.Response(
            200,
            json={"data": {"locations": {"pageInfo": {"hasNextPage": False}, "edges": []}}},
        )

    slept: list[float] = []
    adapter = ShopifyAdapter(
        client_id="id",
        client_secret="secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=slept.append,
        jitter=lambda: 0.0,
    )
    page = adapter.fetch_locations_page("acme.myshopify.com", "tok", after=None, first=5)
    assert page.items == ()
    assert slept
    assert adapter.last_retries == 1


def test_graphql_throttled_then_success() -> None:
    states = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        _ = json.loads(request.content.decode())
        states["n"] += 1
        if states["n"] == 1:
            return httpx.Response(
                200,
                json={"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]},
            )
        return httpx.Response(
            200,
            json={"data": {"customers": {"pageInfo": {"hasNextPage": False}, "edges": []}}},
        )

    adapter = ShopifyAdapter(
        client_id="id",
        client_secret="secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _s: None,
        jitter=lambda: 0.0,
    )
    page = adapter.fetch_customers_page(
        "acme.myshopify.com", "tok", after=None, query=None, first=5
    )
    assert page.items == ()


def test_throttle_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(429, json={})

    adapter = ShopifyAdapter(
        client_id="id",
        client_secret="secret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _s: None,
        jitter=lambda: 0.0,
    )
    with pytest.raises(ShopifyThrottledError):
        adapter.fetch_orders_page("acme.myshopify.com", "tok", after=None, query=None, first=1)
