import pytest
from merchantos_domain import InvalidShopDomainError
from merchantos_shopify.shop_domain import normalize_shop_domain


def test_accepts_myshopify_domain() -> None:
    assert normalize_shop_domain("Acme-Store.myshopify.com") == "acme-store.myshopify.com"


def test_rejects_open_redirect_suffix() -> None:
    with pytest.raises(InvalidShopDomainError):
        normalize_shop_domain("acme.myshopify.com.attacker.example")


def test_rejects_bare_host() -> None:
    with pytest.raises(InvalidShopDomainError):
        normalize_shop_domain("evil.example")
