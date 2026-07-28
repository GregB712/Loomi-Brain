from __future__ import annotations

from fastapi.testclient import TestClient
from httpx2 import Response


def test_unauthorized_document_list_is_blocked(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/v1/documents")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert response.json()["request_id"] is not None


def test_owner_can_login_and_logout(seeded_client: TestClient) -> None:
    login_response = _login(seeded_client)

    assert login_response.status_code == 200
    body = login_response.json()
    assert body["owner"]["email"] == "owner@example.test"
    assert body["csrf_token"]
    set_cookie_headers = login_response.headers.get_list("set-cookie")
    assert any("loomi_session=" in header and "HttpOnly" in header for header in set_cookie_headers)
    assert any(
        "loomi_csrf=" in header and "HttpOnly" not in header for header in set_cookie_headers
    )

    me_response = seeded_client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "owner@example.test"

    missing_csrf_response = seeded_client.post("/api/v1/auth/logout")
    assert missing_csrf_response.status_code == 403
    assert missing_csrf_response.json()["code"] == "forbidden"

    logout_response = seeded_client.post(
        "/api/v1/auth/logout",
        headers={"x-csrf-token": body["csrf_token"]},
    )
    assert logout_response.status_code == 204

    after_logout_response = seeded_client.get("/api/v1/auth/me")
    assert after_logout_response.status_code == 401


def test_bad_owner_password_is_rejected(seeded_client: TestClient) -> None:
    response = seeded_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.test", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid owner credentials."


def test_authenticated_document_list_is_owner_scoped(seeded_client: TestClient) -> None:
    _login(seeded_client)

    response = seeded_client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json() == []


def test_owner_can_revoke_current_session(seeded_client: TestClient) -> None:
    login_response = _login(seeded_client)
    csrf_token = login_response.json()["csrf_token"]

    sessions_response = seeded_client.get("/api/v1/auth/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True

    revoke_response = seeded_client.post(
        f"/api/v1/auth/sessions/{sessions[0]['id']}/revoke",
        headers={"x-csrf-token": csrf_token},
    )
    assert revoke_response.status_code == 204

    me_response = seeded_client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def _login(client: TestClient) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )
