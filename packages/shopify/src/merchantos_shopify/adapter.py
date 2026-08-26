from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from random import random
from typing import Any

import httpx
from merchantos_domain import (
    InstallationFailedError,
    ShopifyThrottledError,
    StoreUninstalledError,
    TransientJobError,
)

from merchantos_shopify.constants import ADMIN_API_VERSION, SHOP_QUERY, WEBHOOK_SUBSCRIBE
from merchantos_shopify.parse import (
    connection_page,
    parse_customer,
    parse_inventory_levels,
    parse_location,
    parse_order,
    parse_product,
)
from merchantos_shopify.port import ShopInfo, TokenGrant
from merchantos_shopify.queries import (
    CUSTOMER_NODE,
    CUSTOMERS_PAGE,
    INVENTORY_PAGE,
    LOCATION_NODE,
    LOCATIONS_PAGE,
    ORDER_NODE,
    ORDERS_PAGE,
    PRODUCT_NODE,
    PRODUCTS_PAGE,
)
from merchantos_shopify.reader import (
    CustomerRecord,
    InventoryRecord,
    LocationRecord,
    OrderRecord,
    Page,
    ProductRecord,
)
from merchantos_shopify.shop_domain import normalize_shop_domain

_TIMEOUT = httpx.Timeout(30.0)
_MAX_READ_ATTEMPTS = 5


class ShopifyAdapter:
    """HTTP adapter for token exchange and GraphQL Admin API 2026-07."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        http: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=_TIMEOUT)
        self._sleeper = sleeper or time.sleep
        self._jitter = jitter or random
        self.last_retries = 0

    def exchange_code(self, shop: str, code: str) -> TokenGrant:
        domain = normalize_shop_domain(shop)
        url = f"https://{domain}/admin/oauth/access_token"
        try:
            response = self._http.post(
                url,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "expiring": "1",
                },
            )
        except httpx.HTTPError as exc:
            raise InstallationFailedError("Shopify token endpoint unreachable") from exc
        if response.status_code >= 400:
            raise InstallationFailedError("Shopify token exchange failed")
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise InstallationFailedError("Shopify token exchange returned no access_token")
        now = datetime.now(UTC)
        expires_in = payload.get("expires_in")
        refresh_in = payload.get("refresh_token_expires_in")
        return TokenGrant(
            access_token=token,
            scope=str(payload.get("scope") or ""),
            expires_at=now + timedelta(seconds=int(expires_in)) if expires_in else None,
            refresh_token=payload.get("refresh_token")
            if isinstance(payload.get("refresh_token"), str)
            else None,
            refresh_expires_at=now + timedelta(seconds=int(refresh_in)) if refresh_in else None,
        )

    def fetch_shop(self, shop: str, access_token: str) -> ShopInfo:
        data = self._graphql(shop, access_token, SHOP_QUERY)
        node = (data.get("data") or {}).get("shop")
        if not isinstance(node, dict):
            raise InstallationFailedError("Shopify shop query failed")
        primary_raw = node.get("primaryDomain")
        plan_raw = node.get("plan")
        primary = primary_raw if isinstance(primary_raw, dict) else {}
        plan = plan_raw if isinstance(plan_raw, dict) else {}
        myshopify = normalize_shop_domain(str(node.get("myshopifyDomain") or shop))
        host = str(primary.get("host") or myshopify)
        gid = str(node.get("id") or "")
        if not gid:
            raise InstallationFailedError("Shopify shop query missing id")
        return ShopInfo(
            shopify_shop_gid=gid,
            name=str(node.get("name") or myshopify),
            myshopify_domain=myshopify,
            primary_host=host,
            currency=str(node.get("currencyCode") or "USD")[:3],
            iana_timezone=str(node.get("ianaTimezone") or "UTC"),
            plan_name=str(plan.get("displayName") or ""),
        )

    def register_app_uninstalled(self, shop: str, access_token: str, callback_uri: str) -> None:
        try:
            data = self._graphql(shop, access_token, WEBHOOK_SUBSCRIBE, {"uri": callback_uri})
        except InstallationFailedError:
            return
        errors = ((data.get("data") or {}).get("webhookSubscriptionCreate") or {}).get(
            "userErrors"
        ) or []
        if errors:
            return

    def _graphql(
        self,
        shop: str,
        access_token: str,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not access_token:
            raise StoreUninstalledError("no Shopify access token")
        domain = normalize_shop_domain(shop)
        url = f"https://{domain}/admin/api/{ADMIN_API_VERSION}/graphql.json"
        try:
            response = self._http.post(
                url,
                json={"query": query, "variables": variables or {}},
                headers={
                    "X-Shopify-Access-Token": access_token,
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise InstallationFailedError("Shopify GraphQL unreachable") from exc
        if response.status_code == 401:
            raise StoreUninstalledError("Shopify rejected the access token")
        if response.status_code >= 400:
            raise InstallationFailedError("Shopify GraphQL request failed")
        payload: dict[str, Any] = response.json()
        if payload.get("errors"):
            raise InstallationFailedError("Shopify GraphQL returned errors")
        return payload

    def fetch_products_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        query: str | None,
        first: int,
    ) -> Page[ProductRecord]:
        payload = self._graphql_read(
            shop,
            access_token,
            PRODUCTS_PAGE,
            {"first": first, "after": after, "query": query},
        )
        return connection_page(payload, "products", parse_product)

    def fetch_orders_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        query: str | None,
        first: int,
    ) -> Page[OrderRecord]:
        payload = self._graphql_read(
            shop,
            access_token,
            ORDERS_PAGE,
            {"first": first, "after": after, "query": query},
        )
        return connection_page(payload, "orders", parse_order)

    def fetch_customers_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        query: str | None,
        first: int,
    ) -> Page[CustomerRecord]:
        payload = self._graphql_read(
            shop,
            access_token,
            CUSTOMERS_PAGE,
            {"first": first, "after": after, "query": query},
        )
        return connection_page(payload, "customers", parse_customer)

    def fetch_locations_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        first: int,
    ) -> Page[LocationRecord]:
        payload = self._graphql_read(
            shop,
            access_token,
            LOCATIONS_PAGE,
            {"first": first, "after": after},
        )
        return connection_page(payload, "locations", parse_location)

    def fetch_inventory_page(
        self,
        shop: str,
        access_token: str,
        *,
        after: str | None,
        first: int,
    ) -> Page[InventoryRecord]:
        payload = self._graphql_read(
            shop,
            access_token,
            INVENTORY_PAGE,
            {"first": first, "after": after},
        )
        return connection_page(payload, "productVariants", parse_inventory_levels)

    def fetch_product(self, shop: str, access_token: str, gid: str) -> ProductRecord | None:
        payload = self._graphql_read(shop, access_token, PRODUCT_NODE, {"id": gid})
        node = (payload.get("data") or {}).get("product")
        return parse_product(node) if isinstance(node, dict) else None

    def fetch_order(self, shop: str, access_token: str, gid: str) -> OrderRecord | None:
        payload = self._graphql_read(shop, access_token, ORDER_NODE, {"id": gid})
        node = (payload.get("data") or {}).get("order")
        return parse_order(node) if isinstance(node, dict) else None

    def fetch_customer(self, shop: str, access_token: str, gid: str) -> CustomerRecord | None:
        payload = self._graphql_read(shop, access_token, CUSTOMER_NODE, {"id": gid})
        node = (payload.get("data") or {}).get("customer")
        return parse_customer(node) if isinstance(node, dict) else None

    def fetch_location(self, shop: str, access_token: str, gid: str) -> LocationRecord | None:
        payload = self._graphql_read(shop, access_token, LOCATION_NODE, {"id": gid})
        node = (payload.get("data") or {}).get("location")
        return parse_location(node) if isinstance(node, dict) else None

    def _graphql_read(
        self,
        shop: str,
        access_token: str,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Paginated read path: retry 429 / THROTTLED with backoff (official leaky bucket)."""
        if not access_token:
            raise StoreUninstalledError("no Shopify access token")
        domain = normalize_shop_domain(shop)
        url = f"https://{domain}/admin/api/{ADMIN_API_VERSION}/graphql.json"
        delay = 1.0
        last_error: Exception | None = None
        self.last_retries = 0
        for attempt in range(1, _MAX_READ_ATTEMPTS + 1):
            try:
                response = self._http.post(
                    url,
                    json={"query": query, "variables": variables or {}},
                    headers={
                        "X-Shopify-Access-Token": access_token,
                        "Content-Type": "application/json",
                    },
                )
            except httpx.HTTPError as exc:
                last_error = TransientJobError("Shopify GraphQL unreachable")
                last_error.__cause__ = exc
                self.last_retries = attempt
                self._sleeper(delay + self._jitter())
                delay = min(delay * 2, 16)
                continue
            if response.status_code == 429:
                last_error = ShopifyThrottledError("Shopify HTTP 429")
                self.last_retries = attempt
                self._sleeper(delay + self._jitter())
                delay = min(delay * 2, 16)
                continue
            if response.status_code == 401:
                raise StoreUninstalledError("Shopify rejected the access token")
            if response.status_code >= 400:
                raise InstallationFailedError("Shopify GraphQL request failed")
            payload: dict[str, Any] = response.json()
            errors = payload.get("errors") or []
            throttled = any(
                isinstance(err, dict) and (err.get("extensions") or {}).get("code") == "THROTTLED"
                for err in errors
            )
            if throttled:
                last_error = ShopifyThrottledError("Shopify GraphQL THROTTLED")
                self.last_retries = attempt
                self._sleeper(max(1.0, delay) + self._jitter())
                delay = min(delay * 2, 16)
                continue
            if errors:
                raise InstallationFailedError("Shopify GraphQL returned errors")
            cost = ((payload.get("extensions") or {}).get("cost") or {}).get("throttleStatus")
            if isinstance(cost, dict):
                available = cost.get("currentlyAvailable")
                restore = cost.get("restoreRate") or 50
                if isinstance(available, int) and isinstance(restore, int) and available < 100:
                    wait = max(0.0, (100 - available) / max(restore, 1))
                    self._sleeper(wait)
            self.last_retries = attempt - 1
            return payload
        if last_error is not None:
            raise last_error
        raise TransientJobError("Shopify GraphQL retries exhausted")
