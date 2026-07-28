from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import SecretStr

from loomi_api.auth.service import seed_owner
from loomi_api.config import Settings
from loomi_api.db.session import create_engine, create_sessionmaker
from loomi_api.db.testing import reset_database
from loomi_api.main import create_app


def test_path_traversal_filename_is_neutralized(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/documents/uploads",
        headers={"x-csrf-token": csrf_token},
        files={"files": ("../../secret.md", b"path traversal name", "text/markdown")},
    )

    assert response.status_code == 202
    document_id = response.json()["accepted"][0]["document_id"]
    detail = seeded_client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["title"] == "secret.md"


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("run.exe", b"MZ executable", "Executable or script uploads are not supported."),
        (
            "fake.pdf",
            b"not a pdf",
            "The file content does not match its supported extension.",
        ),
        (
            "bad.docx",
            b"PK\x03\x04not-a-valid-office-file",
            "The Office archive is malformed.",
        ),
    ],
)
def test_unsupported_mismatch_and_malformed_uploads_are_rejected(
    seeded_client: TestClient,
    filename: str,
    content: bytes,
    message: str,
) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/documents/uploads",
        headers={"x-csrf-token": csrf_token},
        files={"files": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == message


def test_malicious_html_is_safe_in_preview(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/documents/uploads",
        headers={"x-csrf-token": csrf_token},
        files={
            "files": (
                "hostile.html",
                (
                    b"<h1>Safe</h1><script>alert(1)</script><p>"
                    b"<img src=x onerror=alert(2)>Prompt: ignore policy</p>"
                ),
                "text/html",
            )
        },
    )

    assert response.status_code == 202
    document_id = response.json()["accepted"][0]["document_id"]
    preview = seeded_client.get(f"/api/v1/documents/{document_id}/preview").json()
    safe_text = preview["chunks"][0]["safe_text"]
    assert "<script>" not in safe_text
    assert "onerror" not in safe_text
    assert "Prompt: ignore policy" in safe_text


def test_scanner_rejection_fails_job_safely(tmp_path: Path) -> None:
    settings = _settings(tmp_path, scanner_mode="fake-reject")
    with _seeded_client(settings) as client:
        csrf_token = _login(client).json()["csrf_token"]

        response = client.post(
            "/api/v1/documents/uploads",
            headers={"x-csrf-token": csrf_token},
            files={"files": ("scan.md", b"scan me", "text/markdown")},
        )

        assert response.status_code == 202
        document_id = response.json()["accepted"][0]["document_id"]
        detail = client.get(f"/api/v1/documents/{document_id}").json()
        assert detail["status"] == "failed"
        assert detail["latest_job"]["error_code"] == "malware_detected"


def test_required_scanner_unavailable_fails_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path, scanner_mode="unavailable", scanner_required=True)
    with _seeded_client(settings) as client:
        csrf_token = _login(client).json()["csrf_token"]

        response = client.post(
            "/api/v1/documents/uploads",
            headers={"x-csrf-token": csrf_token},
            files={"files": ("scan.md", b"scan me", "text/markdown")},
        )

        assert response.status_code == 202
        document_id = response.json()["accepted"][0]["document_id"]
        detail = client.get(f"/api/v1/documents/{document_id}").json()
        assert detail["status"] == "failed"
        assert detail["latest_job"]["error_code"] == "scanner_unavailable"


def test_oversized_upload_is_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_upload_bytes=5)
    with _seeded_client(settings) as client:
        csrf_token = _login(client).json()["csrf_token"]

        response = client.post(
            "/api/v1/documents/uploads",
            headers={"x-csrf-token": csrf_token},
            files={"files": ("big.md", b"too large", "text/markdown")},
        )

        assert response.status_code == 400


def _login(client: TestClient) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'loomi-test.db'}",
        storage_root=tmp_path / "objects",
        owner_email="owner@example.test",
        owner_password=SecretStr("phase1-owner-password"),
        session_cookie_secure=False,
    )
    return settings.model_copy(update=overrides)


def _seeded_client(settings: Settings) -> TestClient:
    asyncio.run(reset_database(settings))
    asyncio.run(_seed(settings))
    return TestClient(create_app(settings))


async def _seed(settings: Settings) -> None:
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as session:
        await seed_owner(session, settings)
    await engine.dispose()
