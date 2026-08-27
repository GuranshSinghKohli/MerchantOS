import pytest
from fastapi.testclient import TestClient
from merchantos_agents.selection import select_agents
from merchantos_api.deps import db_engine, queue, settings
from merchantos_api.main import create_app
from merchantos_api.session_cookie import SESSION_COOKIE
from merchantos_app import AnalyticsService
from merchantos_db import session_scope
from merchantos_domain import AgentRunStatus
from merchantos_llm import FakeLLM, default_intelligence_turns
from merchantos_mcp import build_commerce_registry
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.mutator import FakeShopifyMutator
from merchantos_shopify.testing import FakeShopifyReader
from merchantos_worker.capabilities import (
    AgentCapabilities,
    ExecutionCapabilities,
    SyncCapabilities,
    WebhookCapabilities,
    WorkerRuntime,
)
from merchantos_worker.dispatch import process_once
from merchantos_worker.testing import seed_installed_store

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
pytestmark = pytest.mark.integration


def _client() -> TestClient:
    settings.cache_clear()
    db_engine.cache_clear()
    return TestClient(create_app())


def test_intelligence_query_lifecycle_and_isolation(postgres: None) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(db_engine()) as db:
        a = seed_installed_store(db, shop="intel-a.myshopify.com", encryptor=encryptor)
        b = seed_installed_store(db, shop="intel-b.myshopify.com", encryptor=encryptor)
    client = _client()
    unauthorized = client.post("/api/v1/intelligence/query", json={"question": "How is revenue?"})
    assert unauthorized.status_code == 401
    invalid = client.post(
        "/api/v1/intelligence/query",
        json={"question": "How is revenue?", "agents": ["analytics"]},
        cookies={SESSION_COOKIE: str(a.session_id)},
    )
    assert invalid.status_code == 422
    oversized = client.post(
        "/api/v1/intelligence/query",
        json={"question": "x" * 4001},
        cookies={SESSION_COOKIE: str(a.session_id)},
    )
    assert oversized.status_code == 422
    question = "Why is my revenue down?"
    created = client.post(
        "/api/v1/intelligence/query",
        json={"question": question},
        cookies={SESSION_COOKIE: str(a.session_id)},
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    assert created.json()["run_kind"] == "intelligence"
    assert created.json()["status"] == AgentRunStatus.PENDING.value
    foreign = client.get(
        f"/api/v1/intelligence/{run_id}",
        cookies={SESSION_COOKIE: str(b.session_id)},
    )
    assert foreign.status_code == 404
    ask_surface = client.get(
        f"/api/v1/ask/{run_id}",
        cookies={SESSION_COOKIE: str(a.session_id)},
    )
    assert ask_surface.status_code == 404
    runtime = WorkerRuntime(
        engine=db_engine(),
        queue=queue(),
        sync=SyncCapabilities(reader=FakeShopifyReader()),
        webhook=WebhookCapabilities(reader=FakeShopifyReader()),
        agent=AgentCapabilities(
            tools=build_commerce_registry(AnalyticsService(db_engine())),
            llm=FakeLLM(default_intelligence_turns(select_agents(question))),
        ),
        execution=ExecutionCapabilities(mutator=FakeShopifyMutator()),
        encryptor=encryptor,
        owner="intel-test",
    )
    assert process_once(runtime) >= 1
    done = client.get(
        f"/api/v1/intelligence/{run_id}",
        cookies={SESSION_COOKIE: str(a.session_id)},
    )
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == AgentRunStatus.COMPLETED.value
    result = body["result"]
    assert result["executive_summary"]
    assert result["selected_agents"] == ["analytics", "inventory"]
    assert result["recommendations"]
    assert "tenant_id" not in result
    assert "approved_action" not in result
    assert "shpua_" not in str(body)
    listed = client.get("/api/v1/intelligence", cookies={SESSION_COOKIE: str(b.session_id)})
    assert listed.status_code == 200
    assert listed.json()["runs"] == []
    own = client.get("/api/v1/intelligence", cookies={SESSION_COOKIE: str(a.session_id)})
    assert any(item["run_id"] == run_id for item in own.json()["runs"])
