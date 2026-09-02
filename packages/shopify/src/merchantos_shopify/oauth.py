import secrets
from urllib.parse import urlencode

from merchantos_shopify.constants import INSTALL_SCOPES
from merchantos_shopify.shop_domain import normalize_shop_domain


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def authorization_url(
    *,
    shop: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = INSTALL_SCOPES,
) -> str:
    """Standalone authorization-code grant. Offline token (no grant_options)."""
    domain = normalize_shop_domain(shop)
    handle = domain.removesuffix(".myshopify.com")
    query = urlencode(
        {
            "client_id": client_id,
            "scope": ",".join(scopes),
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    # Unpublished / password-protected stores serve the storefront
    # "This store will be right back" page on {shop}.myshopify.com/admin/oauth.
    # Admin already lives on admin.shopify.com; authorize there with the same
    # query string. Token exchange stays on the shop domain (server-to-server).
    return f"https://admin.shopify.com/store/{handle}/oauth/authorize?{query}"
