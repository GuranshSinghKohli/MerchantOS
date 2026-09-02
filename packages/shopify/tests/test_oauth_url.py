from merchantos_shopify.oauth import authorization_url


def test_authorization_url_is_offline_grant() -> None:
    url = authorization_url(
        shop="acme.myshopify.com",
        client_id="key",
        redirect_uri="https://app.example/api/v1/auth/shopify/callback",
        state="nonce-1",
    )
    assert url.startswith("https://admin.shopify.com/store/acme/oauth/authorize?")
    assert "client_id=key" in url
    assert "state=nonce-1" in url
    assert "grant_options" not in url
    assert "read_products" in url
    assert "write_products" in url
    assert "write_discounts" not in url
