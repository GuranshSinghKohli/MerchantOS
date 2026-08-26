"""Pinned Shopify Admin API version and least-privilege install scopes.

Re-validated against https://shopify.dev/docs/api/usage/access-scopes
and GraphQL Admin API 2026-07 on 2026-08-25.

Write scopes are omitted until the demo mutation (discount vs price) is locked.
`write_*` implicitly includes the matching `read_*` — we must not request write
just to get read. `read_all_orders` is out of V1 (Partner permission + 60-day
window is an explicit constraint).
"""

ADMIN_API_VERSION = "2026-07"

# Official shop-domain pattern from Shopify standalone OAuth docs.
SHOP_DOMAIN_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9\-]*\.myshopify\.com$"

INSTALL_SCOPES: tuple[str, ...] = (
    "read_products",
    "read_orders",
    "read_customers",
    "read_inventory",
    "read_locations",
    "read_discounts",
)

MANDATORY_WEBHOOK_TOPICS: tuple[str, ...] = (
    "app/uninstalled",
    "customers/data_request",
    "customers/redact",
    "shop/redact",
)

COMMERCE_WEBHOOK_TOPICS: tuple[str, ...] = (
    "products/create",
    "products/update",
    "products/delete",
    "orders/create",
    "orders/updated",
    "orders/cancelled",
    "customers/create",
    "customers/update",
    "customers/delete",
    "inventory_levels/update",
    "locations/create",
    "locations/update",
)

SHOP_QUERY = """
query ShopIdentity {
  shop {
    id
    name
    myshopifyDomain
    primaryDomain { host }
    currencyCode
    ianaTimezone
    plan { displayName }
  }
}
"""

WEBHOOK_SUBSCRIBE = """
mutation AppUninstalledSubscribe($uri: URL!) {
  webhookSubscriptionCreate(
    topic: APP_UNINSTALLED
    webhookSubscription: { uri: $uri, format: JSON }
  ) {
    webhookSubscription { id }
    userErrors { field message }
  }
}
"""
