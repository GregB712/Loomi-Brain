from __future__ import annotations

from fastapi.testclient import TestClient
from httpx2 import Response


def test_upload_to_preview_retry_reindex_delete_flow(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    upload_response = _upload_markdown(
        seeded_client,
        csrf_token,
        filename="fixture.md",
        content=b"# Source\n\nThis is synthetic knowledge for ingestion.",
    )

    assert upload_response.status_code == 202
    accepted = upload_response.json()["accepted"][0]
    document_id = accepted["document_id"]
    job_id = accepted["ingestion_job_id"]

    job_response = seeded_client.get(f"/api/v1/ingestion-jobs/{job_id}")
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "completed"

    detail_response = seeded_client.get(f"/api/v1/documents/{document_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "completed"
    assert detail["chunk_count"] >= 1
    assert detail["embedding_count"] >= 1
    assert detail["checksum"] == accepted["checksum"]

    preview_response = seeded_client.get(f"/api/v1/documents/{document_id}/preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["chunks"][0]["provenance"]["document_id"] == document_id
    assert "synthetic knowledge" in preview["chunks"][0]["safe_text"]

    reindex_response = seeded_client.post(
        f"/api/v1/documents/{document_id}/reindex",
        headers={"x-csrf-token": csrf_token, "idempotency-key": "reindex-once"},
    )
    assert reindex_response.status_code == 202
    reindex_job_id = reindex_response.json()["ingestion_job_id"]

    duplicate_reindex_response = seeded_client.post(
        f"/api/v1/documents/{document_id}/reindex",
        headers={"x-csrf-token": csrf_token, "idempotency-key": "reindex-once"},
    )
    assert duplicate_reindex_response.status_code == 202
    assert duplicate_reindex_response.json()["ingestion_job_id"] == reindex_job_id

    delete_response = seeded_client.delete(
        f"/api/v1/documents/{document_id}",
        headers={"x-csrf-token": csrf_token},
    )
    assert delete_response.status_code == 204

    after_delete_response = seeded_client.get(f"/api/v1/documents/{document_id}")
    assert after_delete_response.status_code == 404


def test_duplicate_upload_is_owner_scoped_by_checksum(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    content = b"same document"

    first = _upload_markdown(seeded_client, csrf_token, filename="one.md", content=content)
    second = _upload_markdown(seeded_client, csrf_token, filename="two.md", content=content)

    assert first.status_code == 202
    assert second.status_code == 202
    first_document_id = first.json()["accepted"][0]["document_id"]
    duplicate = second.json()["accepted"][0]
    assert duplicate["document_id"] == first_document_id
    assert duplicate["duplicate_of_document_id"] == first_document_id


def test_tags_are_owner_scoped_document_metadata(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    upload_response = _upload_markdown(
        seeded_client,
        csrf_token,
        filename="tagged.md",
        content=b"tagged document",
    )
    document_id = upload_response.json()["accepted"][0]["document_id"]

    tags_response = seeded_client.put(
        f"/api/v1/documents/{document_id}/tags",
        headers={"x-csrf-token": csrf_token},
        json={"tags": ["Research", "research", "  ai "]},
    )

    assert tags_response.status_code == 200
    assert tags_response.json()["tags"] == ["ai", "research"]

    list_response = seeded_client.get("/api/v1/documents")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["tag_names"] == ["ai", "research"]


def test_upload_requires_owner_session_and_csrf(seeded_client: TestClient) -> None:
    unauthenticated = seeded_client.post(
        "/api/v1/documents/uploads",
        files={"files": ("note.md", b"hello", "text/markdown")},
    )
    assert unauthenticated.status_code == 401

    _login(seeded_client)
    missing_csrf = seeded_client.post(
        "/api/v1/documents/uploads",
        files={"files": ("note.md", b"hello", "text/markdown")},
    )
    assert missing_csrf.status_code == 403


def _upload_markdown(
    client: TestClient,
    csrf_token: str,
    *,
    filename: str,
    content: bytes,
) -> Response:
    return client.post(
        "/api/v1/documents/uploads",
        headers={"x-csrf-token": csrf_token},
        files={"files": (filename, content, "text/markdown")},
    )


def _login(client: TestClient) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )
