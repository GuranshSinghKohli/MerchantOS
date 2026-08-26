import re

from merchantos_domain import InvalidShopDomainError

from merchantos_shopify.constants import SHOP_DOMAIN_PATTERN

_SHOP_RE = re.compile(SHOP_DOMAIN_PATTERN)


def normalize_shop_domain(raw: str) -> str:
    """Accept only `{store}.myshopify.com` (official standalone OAuth regex)."""
    shop = raw.strip().lower()
    shop = shop.removeprefix("https://").removeprefix("http://")
    shop = shop.split("/", 1)[0]
    if not _SHOP_RE.fullmatch(shop):
        raise InvalidShopDomainError("shop must be a *.myshopify.com domain")
    return shop
