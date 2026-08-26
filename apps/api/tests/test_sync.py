from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from merchantos_api.deps import db_engine, queue, settings
from merchantos_api.main import create_app
from merchantos_api.session_cookie import SESSION_COOKIE
from merchantos_db import CommerceRepository, JobRepository, session_scope
from merchantos_domain import TenantContext
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.testing import FakeShopifyReader
from merchantos_worker.capabilities import (
    SyncCapabilities,
    WebhookCapabilities,
    WorkerRuntime,
    fake_agent_capabilities,
)
from merchantos_worker.dispatch import process_once
from merchantos_worker.testing import seed_installed_store

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
pytestmark = pytest.mark.integration


def test_sync_requires_session(postgres: None) -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/store/sync", json={"kind": "initial"})
    assert response.status_code == 401


def test_sync_enqueue_and_status(postgres: None) -> None:
    settings.cache_clear()
    db_engine.cache_clear()
    queue.cache_clear()
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(db_engine()) as db:
        view = seed_installed_store(db, shop="syncapi.myshopify.com", encryptor=encryptor)
    client = TestClient(create_app())
    client.cookies.set(SESSION_COOKIE, str(view.session_id))
    rejected = client.post(
        "/api/v1/store/sync", json={"kind": "initial", "merchant_id": str(uuid4())}
    )
    assert rejected.status_code == 422
    created = client.post("/api/v1/store/sync", json={"kind": "initial"})
    assert created.status_code == 202
    jobs = created.json()["jobs"]
    assert len(jobs) == 5
    again = client.post("/api/v1/store/sync", json={"kind": "initial"})
    assert {row["id"] for row in again.json()["jobs"]} == {row["id"] for row in jobs}
    status = client.get("/api/v1/store/sync")
    assert status.status_code == 200
    assert status.json()["store_sync_status"] == "pending"


def test_sync_worker_from_api_outbox(postgres: None) -> None:
    settings.cache_clear()
    db_engine.cache_clear()
    queue.cache_clear()
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(db_engine()) as db:
        view = seed_installed_store(db, shop="apirun.myshopify.com", encryptor=encryptor)
    client = TestClient(create_app())
    client.cookies.set(SESSION_COOKIE, str(view.session_id))
    response = client.post("/api/v1/store/sync", json={"kind": "initial"})
    assert response.status_code == 202
    reader = FakeShopifyReader()
    runtime = WorkerRuntime(
        engine=db_engine(),
        queue=queue(),
        sync=SyncCapabilities(reader=reader),
        webhook=WebhookCapabilities(reader=reader),
        agent=fake_agent_capabilities(),
        encryptor=encryptor,
        owner="api-sync",
    )
    for _ in range(20):
        process_once(runtime)
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
        jobs = JobRepository(db).list_sync_jobs(ctx)
    assert products
    assert {job.status for job in jobs} == {"completed"}
    status = client.get("/api/v1/store/sync")
    assert status.json()["store_sync_status"] == "completed"
