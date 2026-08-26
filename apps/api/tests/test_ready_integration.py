import os

import pytest
from fastapi.testclient import TestClient
from merchantos_api.deps import db_engine, redis_client, settings
from merchantos_api.main import create_app


@pytest.fixture
def integration_client() -> TestClient:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for integration tests")
    settings.cache_clear()
    db_engine.cache_clear()
    redis_client.cache_clear()
    return TestClient(create_app())


@pytest.mark.integration
def test_ready_with_compose_deps(integration_client: TestClient) -> None:
    response = integration_client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True
