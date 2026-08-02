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
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "geolocation=()" in response.headers["permissions-policy"]


def test_request_id_header_is_preserved(seeded_client: TestClient) -> None:
    client = seeded_client
    response = client.get("/api/v1/health", headers={"x-request-id": "req_test_123"})

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] == "ok"
    assert response.headers["x-request-id"] == "req_test_123"
    assert response.json()["request_id"] == "req_test_123"


def test_untrusted_host_is_blocked(seeded_client: TestClient) -> None:
    response = seeded_client.get("/health/live", headers={"host": "evil.example"})

    assert response.status_code == 400


def test_oversized_request_is_rejected_before_route(seeded_client: TestClient) -> None:
    response = seeded_client.get("/health/live", headers={"content-length": "999999999"})

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
