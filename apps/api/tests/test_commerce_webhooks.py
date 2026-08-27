import base64
import hashlib
import hmac
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from merchantos_api.deps import db_engine, queue, settings
from merchantos_api.main import create_app
from merchantos_db import CommerceRepository, session_scope
from merchantos_db.models import OutboxMessage, WebhookEvent
from merchantos_domain import TenantContext
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.mutator import FakeShopifyMutator
from merchantos_shopify.testing import FakeShopifyReader
from merchantos_worker.capabilities import (
    ExecutionCapabilities,
    SyncCapabilities,
    WebhookCapabilities,
    WorkerRuntime,
    fake_agent_capabilities,
)
from merchantos_worker.dispatch import process_once
from merchantos_worker.testing import seed_installed_store
from sqlalchemy import func, select

SECRET = "test_secret"
TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
pytestmark = pytest.mark.integration


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _headers(
    body: bytes, *, event_id: str, topic: str, shop: str = "whapi.myshopify.com"
) -> dict[str, str]:
    return {
        "X-Shopify-Hmac-SHA256": _sign(body),
        "X-Shopify-Shop-Domain": shop,
        "X-Shopify-Topic": topic,
        "X-Shopify-Triggered-At": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "X-Shopify-Webhook-Id": event_id,
    }


def test_invalid_webhook_rejected(postgres: None) -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/webhooks/shopify/products/create",
        content=b"{}",
        headers={
            "X-Shopify-Hmac-SHA256": "nope",
            "X-Shopify-Shop-Domain": "whapi.myshopify.com",
            "X-Shopify-Triggered-At": datetime.now(UTC).isoformat(),
            "X-Shopify-Webhook-Id": "bad",
        },
    )
    assert response.status_code == 401


def test_commerce_webhook_acks_without_writing_catalog(postgres: None) -> None:
    settings.cache_clear()
    db_engine.cache_clear()
    queue.cache_clear()
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(db_engine()) as db:
        view = seed_installed_store(db, shop="whapi.myshopify.com", encryptor=encryptor)
    body = b'{"id":1,"admin_graphql_api_id":"gid://shopify/Product/1"}'
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/webhooks/shopify/products/create",
        content=body,
        headers=_headers(body, event_id="wh-async-1", topic="products/create"),
    )
    assert response.status_code == 200
    replay = client.post(
        "/api/v1/webhooks/shopify/products/create",
        content=body,
        headers=_headers(body, event_id="wh-async-1", topic="products/create"),
    )
    assert replay.status_code == 200
    ctx = TenantContext.from_session(
        SimpleNamespace(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            user_id=view.user_id,
            request_id=uuid4(),
            scopes=view.scopes,
        )
    )
    with session_scope(db_engine()) as db:
        products = CommerceRepository(db).list_products(ctx)
        events = db.scalars(select(WebhookEvent)).all()
        outbox = db.scalars(select(OutboxMessage)).all()
        assert products == []
        assert len(events) == 1
        assert sum(1 for row in outbox if row.job_kind == "webhook") == 1

    reader = FakeShopifyReader()
    runtime = WorkerRuntime(
        engine=db_engine(),
        queue=queue(),
        sync=SyncCapabilities(reader=reader),
        webhook=WebhookCapabilities(reader=reader),
        agent=fake_agent_capabilities(),
        execution=ExecutionCapabilities(mutator=FakeShopifyMutator()),
        encryptor=encryptor,
        owner="wh-api",
    )
    process_once(runtime)
    with session_scope(db_engine()) as db:
        products = CommerceRepository(db).list_products(ctx)
        assert len(products) == 1
        assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1
