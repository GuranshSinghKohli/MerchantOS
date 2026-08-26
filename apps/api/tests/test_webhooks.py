import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from merchantos_api.deps import db_engine
from merchantos_api.main import create_app
from merchantos_api.oauth_service import OAuthService
from merchantos_db import IdentityRepository, session_scope
from merchantos_domain import UnauthorizedError
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.port import ShopInfo, TokenGrant

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
SECRET = "test_secret"

pytestmark = pytest.mark.integration


class _Fake:
    def exchange_code(self, shop: str, code: str) -> TokenGrant:
        return TokenGrant("shpua_x", "read_products", None, None, None)

    def fetch_shop(self, shop: str, access_token: str) -> ShopInfo:
        return ShopInfo(
            "gid://shopify/Shop/1",
            "Acme",
            "acme.myshopify.com",
            "acme.myshopify.com",
            "USD",
            "UTC",
            "dev",
        )

    def register_app_uninstalled(self, shop: str, access_token: str, callback_uri: str) -> None:
        return None


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_webhook_bad_hmac_is_401(postgres: None) -> None:
    client = TestClient(create_app())
    body = b"{}"
    response = client.post(
        "/api/v1/webhooks/shopify/app/uninstalled",
        content=body,
        headers={
            "X-Shopify-Hmac-SHA256": "aaaa",
            "X-Shopify-Shop-Domain": "acme.myshopify.com",
            "X-Shopify-Triggered-At": datetime.now(UTC).isoformat(),
            "X-Shopify-Webhook-Id": "wh-1",
        },
    )
    assert response.status_code == 401


def test_uninstall_webhook_tombstones(postgres: None) -> None:
    with session_scope(db_engine()) as db:
        service = OAuthService(
            db=db,
            shopify=_Fake(),
            encryptor=TokenEncryptor.from_urlsafe_key(TEST_KEY, "test"),
            client_id="test_key",
            client_secret=SECRET,
            redirect_uri="http://localhost/cb",
            webhook_callback_uri="http://localhost/wh",
            session_ttl=timedelta(hours=1),
        )
        url = service.start_install("acme.myshopify.com")
        state = url.split("state=")[1].split("&")[0]
        query = {
            "code": "c",
            "shop": "acme.myshopify.com",
            "state": state,
            "timestamp": str(int(datetime.now(UTC).timestamp())),
        }
        message = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
        query["hmac"] = hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
        view = service.complete_install(query, uuid4())

    body = b'{"id":1}'
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/webhooks/shopify/app/uninstalled",
        content=body,
        headers={
            "X-Shopify-Hmac-SHA256": _sign(body),
            "X-Shopify-Shop-Domain": "acme.myshopify.com",
            "X-Shopify-Topic": "app/uninstalled",
            "X-Shopify-Triggered-At": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "X-Shopify-Webhook-Id": "wh-uninstall-1",
        },
    )
    assert response.status_code == 200
    replay = client.post(
        "/api/v1/webhooks/shopify/app/uninstalled",
        content=body,
        headers={
            "X-Shopify-Hmac-SHA256": _sign(body),
            "X-Shopify-Shop-Domain": "acme.myshopify.com",
            "X-Shopify-Topic": "app/uninstalled",
            "X-Shopify-Triggered-At": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "X-Shopify-Webhook-Id": "wh-uninstall-1",
        },
    )
    assert replay.status_code == 200
    with session_scope(db_engine()) as db:
        with pytest.raises(UnauthorizedError):
            IdentityRepository(db).get_session(view.session_id, uuid4(), now=datetime.now(UTC))
