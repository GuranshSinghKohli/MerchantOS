from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TokenGrant:
    access_token: str
    scope: str
    expires_at: datetime | None
    refresh_token: str | None
    refresh_expires_at: datetime | None


@dataclass(frozen=True)
class ShopInfo:
    shopify_shop_gid: str
    name: str
    myshopify_domain: str
    primary_host: str
    currency: str
    iana_timezone: str
    plan_name: str


class ShopifyPort(Protocol):
    """Application-facing Shopify boundary. Tokens stay inside the adapter."""

    def exchange_code(self, shop: str, code: str) -> TokenGrant: ...

    def fetch_shop(self, shop: str, access_token: str) -> ShopInfo: ...

    def register_app_uninstalled(self, shop: str, access_token: str, callback_uri: str) -> None: ...
