from fastapi.testclient import TestClient


def test_liveness_returns_service_status(seeded_client: TestClient) -> None:
    client = seeded_client
    response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Loomi-Brain API"
    assert body["status"] == "live"
    assert body["environment"] == "test"
    assert body["checks"] == {"api": "ok"}
    assert response.headers["x-request-id"] == body["request_id"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_request_id_header_is_preserved(seeded_client: TestClient) -> None:
    client = seeded_client
    response = client.get("/api/v1/health", headers={"x-request-id": "req_test_123"})

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] == "ok"
    assert response.headers["x-request-id"] == "req_test_123"
    assert response.json()["request_id"] == "req_test_123"
