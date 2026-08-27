from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_db import CommerceRepository, JobRepository, session_scope
from merchantos_db.models import OutboxMessage, WebhookEvent
from merchantos_domain import JobKind, QueueMessage, TenantContext
from merchantos_queue.memory import InMemoryQueue
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

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
pytestmark = pytest.mark.integration


def _encryptor() -> TokenEncryptor:
    return TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")


def test_webhook_job_is_async_and_idempotent(postgres) -> None:
    engine = postgres
    encryptor = _encryptor()
    reader = FakeShopifyReader()
    queue = InMemoryQueue()
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="hook.myshopify.com", encryptor=encryptor)
        event = WebhookEvent(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            topic="products/update",
            shop_domain="hook.myshopify.com",
            event_id="wh-product-1",
            payload_hash="abc",
            resource_gid="gid://shopify/Product/1",
            payload_json='{"admin_graphql_api_id":"gid://shopify/Product/1"}',
            status="received",
        )
        db.add(event)
        db.flush()
        db.add(
            OutboxMessage(
                merchant_id=view.merchant_id,
                job_kind=JobKind.WEBHOOK.value,
                job_id=event.id,
            )
        )
        event_pk = event.id
    runtime = WorkerRuntime(
        engine=engine,
        queue=queue,
        sync=SyncCapabilities(reader=reader),
        webhook=WebhookCapabilities(reader=reader),
        agent=fake_agent_capabilities(),
        execution=ExecutionCapabilities(mutator=FakeShopifyMutator()),
        encryptor=encryptor,
        owner="wh",
    )
    assert process_once(runtime) == 1
    ctx = TenantContext.from_session(
        SimpleNamespace(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            user_id=view.user_id,
            request_id=uuid4(),
            scopes=view.scopes,
        )
    )
    with session_scope(engine) as db:
        products = CommerceRepository(db).list_products(ctx)
        variants = CommerceRepository(db).list_variants(ctx)
        event = JobRepository(db).get_webhook(event_pk)
        assert len(products) == 1
        assert products[0].title == "Product 1"
        assert variants
        assert event is not None
        assert event.status == "processed"
    queue.enqueue(QueueMessage(job_kind=JobKind.WEBHOOK, job_id=event_pk))
    process_once(runtime)
    with session_scope(engine) as db:
        assert len(CommerceRepository(db).list_products(ctx)) == 1


def test_duplicate_webhook_event_id_does_not_insert(postgres) -> None:
    engine = postgres
    from merchantos_db import IdentityRepository

    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="dup.myshopify.com", encryptor=_encryptor())
        repo = IdentityRepository(db)
        first = repo.record_webhook(
            event_id="same-event",
            topic="products/create",
            shop_domain="dup.myshopify.com",
            payload_hash="h",
            resource_gid="gid://shopify/Product/1",
        )
        second = repo.record_webhook(
            event_id="same-event",
            topic="products/create",
            shop_domain="dup.myshopify.com",
            payload_hash="h",
        )
        assert first is not None
        assert second is None
        _ = view
        _ = datetime.now(UTC)
