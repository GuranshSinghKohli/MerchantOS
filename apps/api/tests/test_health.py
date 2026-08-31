from fastapi.testclient import TestClient
from merchantos_api.main import create_app


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert response.headers["x-request-id"]


def test_health_echoes_request_id() -> None:
    client = TestClient(create_app())
    response = client.get("/health", headers={"X-Request-ID": "test-id-123"})
    assert response.headers["x-request-id"] == "test-id-123"


def test_ready_skips_redis_when_unset(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "")
    from merchantos_api.deps import db_engine, redis_client, settings

    settings.cache_clear()
    db_engine.cache_clear()
    redis_client.cache_clear()
    response = TestClient(create_app()).get("/ready")
    assert response.json()["redis"] == "skipped"
