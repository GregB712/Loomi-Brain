from __future__ import annotations

import base64
from typing import Any, cast

from fastapi.testclient import TestClient
from httpx2 import Response

_WEBM_BYTES = b"\x1a\x45\xdf\xa3mock webm audio"


def test_voice_transcribe_requires_authentication(seeded_client: TestClient) -> None:
    response = seeded_client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("voice.webm", b"audio", "audio/webm")},
        data={"duration_ms": "1000"},
    )

    assert response.status_code == 401


def test_mock_transcription_persists_metadata_without_raw_audio(
    seeded_client: TestClient,
) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    conversation_id = _create_conversation(seeded_client, csrf_token)

    response = _transcribe(seeded_client, csrf_token, conversation_id=conversation_id)

    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "What method does hybrid search use?"
    assert body["mocked"] is True
    assert body["retained_audio"] is False
    assert body["request_id"]
    assert body["trace_id"]

    detail = seeded_client.get(f"/api/v1/voice/sessions/{body['session_id']}")
    assert detail.status_code == 200
    session = detail.json()
    assert session["conversation_id"] == conversation_id
    assert session["transcripts"][0]["text"] == body["text"]
    assert session["audio_assets"] == []
    assert session["provider_events"][0]["provider"] == "mock"


def test_voice_rejects_unsupported_audio_type(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/voice/transcribe",
        headers={"x-csrf-token": csrf_token},
        files={"audio": ("voice.txt", b"audio", "text/plain")},
        data={"duration_ms": "1000"},
    )

    assert response.status_code == 415


def test_voice_requires_duration_metadata(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/voice/transcribe",
        headers={"x-csrf-token": csrf_token},
        files={"audio": ("voice.webm", _WEBM_BYTES, "audio/webm")},
    )

    assert response.status_code == 422
    assert "duration" in response.json()["detail"].lower()


def test_voice_rejects_mime_mismatch(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/voice/transcribe",
        headers={"x-csrf-token": csrf_token},
        files={"audio": ("voice.webm", b"not a webm file", "audio/webm")},
        data={"duration_ms": "1000"},
    )

    assert response.status_code == 415
    assert "MIME" in response.json()["detail"]


def test_voice_rejects_oversized_and_overlong_audio(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    settings = cast(Any, seeded_client.app).state.settings
    settings.voice_max_audio_bytes = 1024
    settings.voice_max_recording_seconds = 1

    oversized = _transcribe(seeded_client, csrf_token, audio=b"x" * 2048)
    assert oversized.status_code == 413

    overlong = _transcribe(seeded_client, csrf_token, duration_ms=2000)
    assert overlong.status_code == 422


def test_cloud_speech_is_disabled_until_owner_enables_it(
    seeded_client: TestClient,
) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    settings = seeded_client.patch(
        "/api/v1/voice/settings",
        headers={"x-csrf-token": csrf_token},
        json={"stt_provider": "openai", "stt_model": "gpt-4o-mini-transcribe"},
    )
    assert settings.status_code == 200
    assert settings.json()["cloud_enabled"] is False

    response = _transcribe(seeded_client, csrf_token)

    assert response.status_code == 403
    assert "Cloud speech providers are disabled" in response.json()["detail"]


def test_mock_tts_returns_deterministic_audio(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    response = seeded_client.post(
        "/api/v1/voice/tts",
        headers={"x-csrf-token": csrf_token},
        json={"text": "Visible assistant answer.", "provider": "mock", "voice": "alloy"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content_type"] == "audio/wav"
    assert body["mocked"] is True
    assert base64.b64decode(body["audio_base64"]).startswith(b"RIFF")


def test_tts_enforces_voice_allowlist_and_secret_redaction(
    seeded_client: TestClient,
) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]

    bad_voice = seeded_client.post(
        "/api/v1/voice/tts",
        headers={"x-csrf-token": csrf_token},
        json={"text": "Visible answer.", "provider": "mock", "voice": "unknown"},
    )
    assert bad_voice.status_code == 422

    secret_text = seeded_client.post(
        "/api/v1/voice/tts",
        headers={"x-csrf-token": csrf_token},
        json={"text": "sk-" + "testfakefakefakefake", "provider": "mock", "voice": "alloy"},
    )
    assert secret_text.status_code == 422


def test_raw_audio_retention_is_explicit_and_deletable(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    updated = seeded_client.patch(
        "/api/v1/voice/settings",
        headers={"x-csrf-token": csrf_token},
        json={"retain_raw_audio": True, "retention_days": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["retain_raw_audio"] is True

    transcribed = _transcribe(seeded_client, csrf_token)
    assert transcribed.status_code == 201
    session_id = transcribed.json()["session_id"]

    detail = seeded_client.get(f"/api/v1/voice/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["audio_assets"][0]["retained"] is True

    deleted = seeded_client.delete(
        f"/api/v1/voice/sessions/{session_id}/audio",
        headers={"x-csrf-token": csrf_token},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_count"] == 1

    after = seeded_client.get(f"/api/v1/voice/sessions/{session_id}")
    assert after.status_code == 200
    assert after.json()["audio_assets"][0]["retained"] is False


def test_voice_rate_limit_returns_problem_details(seeded_client: TestClient) -> None:
    csrf_token = _login(seeded_client).json()["csrf_token"]
    cast(Any, seeded_client.app).state.settings.voice_rate_limit_attempts = 1

    first = _transcribe(seeded_client, csrf_token)
    second = _transcribe(seeded_client, csrf_token)

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["code"] == "rate_limited"
    assert second.json()["request_id"]


def _transcribe(
    client: TestClient,
    csrf_token: str,
    *,
    conversation_id: str | None = None,
    audio: bytes = _WEBM_BYTES,
    duration_ms: int = 1000,
) -> Response:
    data: dict[str, Any] = {"duration_ms": str(duration_ms)}
    if conversation_id is not None:
        data["conversation_id"] = conversation_id
    return client.post(
        "/api/v1/voice/transcribe",
        headers={"x-csrf-token": csrf_token},
        files={"audio": ("voice.webm", audio, "audio/webm")},
        data=data,
    )



def _create_conversation(client: TestClient, csrf_token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers={"x-csrf-token": csrf_token},
        json={"title": "Voice"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _login(client: TestClient) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )
