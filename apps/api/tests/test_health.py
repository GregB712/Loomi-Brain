from fastapi.testclient import TestClient

from loomi_api.config import Settings
from loomi_api.main import create_app


def test_liveness_returns_service_status() -> None:
    app = create_app(Settings(environment="test"))
    client = TestClient(app)

    response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Loomi-Brain API"
    assert body["status"] == "live"
    assert body["environment"] == "test"
    assert response.headers["x-request-id"] == body["request_id"]


def test_request_id_header_is_preserved() -> None:
    app = create_app(Settings(environment="test"))
    client = TestClient(app)

    response = client.get("/api/v1/health", headers={"x-request-id": "req_test_123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req_test_123"
    assert response.json()["request_id"] == "req_test_123"
