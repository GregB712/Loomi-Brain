from __future__ import annotations

from fastapi.testclient import TestClient


def test_phase2_mutation_headers_are_allowed_by_cors(seeded_client: TestClient) -> None:
    response = seeded_client.options(
        "/api/v1/documents/uploads",
        headers={
            "origin": "http://localhost:3000",
            "access-control-request-method": "POST",
            "access-control-request-headers": "idempotency-key,x-csrf-token",
        },
    )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed_headers
    assert "x-csrf-token" in allowed_headers
