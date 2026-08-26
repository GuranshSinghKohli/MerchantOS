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
    query = urlencode(
        {
            "client_id": client_id,
            "scope": ",".join(scopes),
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"https://{domain}/admin/oauth/authorize?{query}"
