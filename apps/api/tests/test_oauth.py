import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from merchantos_api.deps import db_engine, settings
from merchantos_api.main import create_app
from merchantos_api.oauth_service import OAuthService
from merchantos_db import IdentityRepository, session_scope
from merchantos_domain import (
    InstallationFailedError,
    InvalidHmacError,
    InvalidOAuthStateError,
    TenantContext,
    UnauthorizedError,
)
from merchantos_domain import InstallationFailedError as _IFE
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.port import ShopInfo, TokenGrant
from sqlalchemy import text

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class FakeShopify:
    def __init__(self, *, shop: str = "acme.myshopify.com", fail: bool = False) -> None:
        self.shop = shop
        self.fail = fail

    def exchange_code(self, shop: str, code: str) -> TokenGrant:
        if self.fail:
            raise _IFE("token exchange failed")
        return TokenGrant(
            access_token=f"shpua_{code}",
            scope="read_products,read_orders",
            expires_at=None,
            refresh_token="refresh_token_value",
            refresh_expires_at=None,
        )

    def fetch_shop(self, shop: str, access_token: str) -> ShopInfo:
        return ShopInfo(
            shopify_shop_gid="gid://shopify/Shop/1",
            name="Acme",
            myshopify_domain=self.shop,
            primary_host=self.shop,
            currency="USD",
            iana_timezone="UTC",
            plan_name="Developer Preview",
        )

    def register_app_uninstalled(self, shop: str, access_token: str, callback_uri: str) -> None:
        return None


pytestmark = pytest.mark.integration


def _service(db, fake: FakeShopify) -> OAuthService:
    return OAuthService(
        db=db,
        shopify=fake,
        encryptor=TokenEncryptor.from_urlsafe_key(TEST_KEY, "test"),
        client_id="test_key",
        client_secret="test_secret",
        redirect_uri="http://localhost:8000/api/v1/auth/shopify/callback",
        webhook_callback_uri="http://localhost:8000/api/v1/webhooks/shopify/app/uninstalled",
        session_ttl=timedelta(hours=1),
    )


def _signed_query(shop: str, state: str, *, secret: str = "test_secret") -> dict[str, str]:
    query = {
        "code": "authcode",
        "shop": shop,
        "state": state,
        "timestamp": str(int(datetime.now(UTC).timestamp())),
    }
    message = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    query["hmac"] = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return query


def test_oauth_initiation_persists_bound_state(postgres: None) -> None:
    fake = FakeShopify()
    with session_scope(db_engine()) as db:
        url = _service(db, fake).start_install("acme.myshopify.com")
    assert url.startswith("https://acme.myshopify.com/admin/oauth/authorize?")
    assert "state=" in url


def test_invalid_oauth_state_rejected(postgres: None) -> None:
    fake = FakeShopify()
    with session_scope(db_engine()) as db:
        service = _service(db, fake)
        service.start_install("acme.myshopify.com")
        query = _signed_query("acme.myshopify.com", "not-the-state")
        with pytest.raises(InvalidOAuthStateError):
            service.complete_install(query, uuid4())


def test_callback_hmac_must_match(postgres: None) -> None:
    fake = FakeShopify()
    with session_scope(db_engine()) as db:
        service = _service(db, fake)
        url = service.start_install("acme.myshopify.com")
        state = url.split("state=")[1].split("&")[0]
        query = _signed_query("acme.myshopify.com", state, secret="wrong")
        with pytest.raises(InvalidHmacError):
            service.complete_install(query, uuid4())


def test_shop_swap_rejected(postgres: None) -> None:
    fake = FakeShopify()
    with session_scope(db_engine()) as db:
        service = _service(db, fake)
        url = service.start_install("acme.myshopify.com")
        state = url.split("state=")[1].split("&")[0]
        query = _signed_query("other.myshopify.com", state)
        with pytest.raises((InvalidHmacError, InvalidOAuthStateError)):
            service.complete_install(query, uuid4())


def test_successful_installation_creates_tenant(postgres: None) -> None:
    fake = FakeShopify()
    with session_scope(db_engine()) as db:
        service = _service(db, fake)
        url = service.start_install("acme.myshopify.com")
        state = url.split("state=")[1].split("&")[0]
        view = service.complete_install(_signed_query("acme.myshopify.com", state), uuid4())
        assert view.installed is True
        assert view.myshopify_domain == "acme.myshopify.com"
        identity = IdentityRepository(db).get_session(
            view.session_id, uuid4(), now=datetime.now(UTC)
        )
        ctx = TenantContext.from_session(identity)
        assert str(ctx.store_id) == str(view.store_id)
        blob = IdentityRepository(db).load_credential_blob(view.merchant_id, view.store_id)
        assert blob is not None
        assert b"shpua_" not in blob
        token = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test").decrypt(blob)
        assert token.startswith("shpua_")


def test_failed_installation_does_not_persist_token(postgres: None) -> None:
    fake = FakeShopify(fail=True)
    with session_scope(db_engine()) as db:
        service = _service(db, fake)
        url = service.start_install("acme.myshopify.com")
        state = url.split("state=")[1].split("&")[0]
        with pytest.raises(InstallationFailedError):
            service.complete_install(_signed_query("acme.myshopify.com", state), uuid4())
        stores = db.execute(text("SELECT count(*) FROM stores")).scalar()
        assert stores == 0


def test_store_isolation_and_token_not_in_me(postgres: None) -> None:
    settings.cache_clear()
    db_engine.cache_clear()
    app = create_app()
    client = TestClient(app)

    def install(shop: str) -> str:
        fake = FakeShopify(shop=shop)
        with session_scope(db_engine()) as db:
            service = _service(db, fake)
            url = service.start_install(shop)
            state = url.split("state=")[1].split("&")[0]
            view = service.complete_install(_signed_query(shop, state), uuid4())
            return str(view.session_id)

    session_a = install("acme.myshopify.com")
    session_b = install("beta.myshopify.com")
    a = client.get("/api/v1/me", cookies={"merchantos_session": session_a})
    b = client.get("/api/v1/me", cookies={"merchantos_session": session_b})
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json()["shop_domain"] == "acme.myshopify.com"
    assert b.json()["shop_domain"] == "beta.myshopify.com"
    assert a.json()["store_id"] != b.json()["store_id"]
    dumped = a.text + b.text
    assert "shpua_" not in dumped
    assert "refresh_token" not in dumped
    assert "encrypted" not in dumped
    settings_body = client.get("/api/v1/settings", cookies={"merchantos_session": session_a})
    assert settings_body.status_code == 200
    assert "shpua_" not in settings_body.text


def test_uninstall_revokes_session_and_tombstones_token(postgres: None) -> None:
    fake = FakeShopify()
    with session_scope(db_engine()) as db:
        service = _service(db, fake)
        url = service.start_install("acme.myshopify.com")
        state = url.split("state=")[1].split("&")[0]
        view = service.complete_install(_signed_query("acme.myshopify.com", state), uuid4())
        service.handle_uninstall("acme.myshopify.com", "req")
        blob = IdentityRepository(db).load_credential_blob(view.merchant_id, view.store_id)
        assert blob == TokenEncryptor.tombstone()
        with pytest.raises(UnauthorizedError):
            IdentityRepository(db).get_session(view.session_id, uuid4(), now=datetime.now(UTC))
