from fastapi.testclient import TestClient
from merchantos_api.main import create_app


def test_install_rejects_invalid_shop_domain() -> None:
    response = TestClient(create_app()).get(
        "/api/v1/auth/shopify/install",
        params={"shop": "evil.example"},
    )
    assert response.status_code == 400
    assert "myshopify.com" in response.json()["detail"]
