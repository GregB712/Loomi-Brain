from __future__ import annotations

import asyncio
import io
import json
import math
import secrets
import struct
import wave
from collections.abc import Awaitable, Callable
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest
from urllib.request import urlopen

from pydantic import SecretStr

from loomi_api.voice.contracts import (
    ExcludeBrowserProviderName,
    SpeechToTextProviderName,
    SpeechToTextRequest,
    SpeechTranscript,
    TextToSpeechAudio,
    TextToSpeechRequest,
    VoiceProviderError,
)


class MockSpeechToTextProvider:
    provider: SpeechToTextProviderName = "mock"

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript

    async def transcribe(
        self,
        request: SpeechToTextRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> SpeechTranscript:
        if await is_cancelled():
            raise VoiceProviderError("voice_cancelled", "The voice request was cancelled.")
        del request
        return SpeechTranscript(
            text=self._transcript,
            language="en",
            confidence=1.0,
            metadata={"mocked": True, "provider_mode": "deterministic"},
        )


class MockTextToSpeechProvider:
    provider: ExcludeBrowserProviderName = "mock"

    async def synthesize(
        self,
        request: TextToSpeechRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> TextToSpeechAudio:
        if await is_cancelled():
            raise VoiceProviderError("voice_cancelled", "The voice request was cancelled.")
        return TextToSpeechAudio(
            audio_bytes=_mock_wav(request.text),
            media_type="audio/wav",
            metadata={"mocked": True, "voice": request.voice},
        )


class OpenAISpeechToTextProvider:
    provider: SpeechToTextProviderName

    def __init__(
        self,
        *,
        provider: SpeechToTextProviderName,
        base_url: str,
        api_key: SecretStr | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.provider = provider
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def transcribe(
        self,
        request: SpeechToTextRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> SpeechTranscript:
        if await is_cancelled():
            raise VoiceProviderError("voice_cancelled", "The voice request was cancelled.")
        body = await _request_multipart_json(
            url=f"{self._base_url.rstrip('/')}/audio/transcriptions",
            api_key=self._api_key,
            fields={
                "model": request.model,
                "response_format": "json",
                "language": request.language,
            },
            file_field="file",
            filename=request.filename or "voice.webm",
            media_type=request.media_type,
            file_bytes=request.audio_bytes,
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
        )
        if await is_cancelled():
            raise VoiceProviderError("voice_cancelled", "The voice request was cancelled.")
        text = body.get("text")
        if not isinstance(text, str):
            raise VoiceProviderError(
                "provider_malformed_response",
                "The speech provider returned malformed transcription data.",
            )
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
        return SpeechTranscript(
            text=" ".join(text.split()),
            language=request.language,
            confidence=_confidence_from_usage(usage),
            metadata={"usage": usage or {}, "provider": self.provider},
        )


class OpenAITextToSpeechProvider:
    provider: SpeechToTextProviderName

    def __init__(
        self,
        *,
        provider: SpeechToTextProviderName,
        base_url: str,
        api_key: SecretStr | None,
        timeout_seconds: float,
        max_retries: int,
        max_response_bytes: int,
    ) -> None:
        self.provider = provider
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_response_bytes = max_response_bytes

    async def synthesize(
        self,
        request: TextToSpeechRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> TextToSpeechAudio:
        if await is_cancelled():
            raise VoiceProviderError("voice_cancelled", "The voice request was cancelled.")
        audio_bytes, media_type = await _request_json_bytes(
            url=f"{self._base_url.rstrip('/')}/audio/speech",
            api_key=self._api_key,
            payload={
                "model": request.model,
                "input": request.text,
                "voice": request.voice,
                "response_format": "mp3",
                "speed": request.speed,
            },
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            max_response_bytes=self._max_response_bytes,
        )
        if await is_cancelled():
            raise VoiceProviderError("voice_cancelled", "The voice request was cancelled.")
        return TextToSpeechAudio(
            audio_bytes=audio_bytes,
            media_type=media_type or "audio/mpeg",
            metadata={"provider": self.provider, "voice": request.voice},
        )


async def _request_multipart_json(
    *,
    url: str,
    api_key: SecretStr | None,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    media_type: str,
    file_bytes: bytes,
    timeout_seconds: float,
    max_retries: int,
) -> dict[str, Any]:
    body, content_type = _multipart_body(
        fields=fields,
        file_field=file_field,
        filename=filename,
        media_type=media_type,
        file_bytes=file_bytes,
    )
    response_bytes, _ = await _request_bytes(
        url=url,
        api_key=api_key,
        body=body,
        content_type=content_type,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_response_bytes=512_000,
    )
    try:
        return cast(dict[str, Any], json.loads(response_bytes.decode("utf-8")))
    except json.JSONDecodeError as exc:
        raise VoiceProviderError(
            "provider_malformed_response",
            "The speech provider returned malformed data.",
        ) from exc


async def _request_json_bytes(
    *,
    url: str,
    api_key: SecretStr | None,
    payload: dict[str, object],
    timeout_seconds: float,
    max_retries: int,
    max_response_bytes: int,
) -> tuple[bytes, str | None]:
    return await _request_bytes(
        url=url,
        api_key=api_key,
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_response_bytes=max_response_bytes,
    )


async def _request_bytes(
    *,
    url: str,
    api_key: SecretStr | None,
    body: bytes,
    content_type: str,
    timeout_seconds: float,
    max_retries: int,
    max_response_bytes: int,
) -> tuple[bytes, str | None]:
    if not url:
        raise VoiceProviderError(
            "provider_not_configured",
            "The speech provider is not configured.",
        )
    if api_key is None:
        raise VoiceProviderError(
            "provider_not_configured",
            "The speech provider is not configured.",
        )
    attempts = max(max_retries, 0) + 1
    last_error: VoiceProviderError | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.to_thread(
                _request_bytes_sync,
                url,
                api_key,
                body,
                content_type,
                timeout_seconds,
                max_response_bytes,
            )
        except VoiceProviderError as exc:
            last_error = exc
            if exc.code not in {"provider_rate_limited", "provider_unavailable"}:
                break
            if attempt < attempts - 1:
                await asyncio.sleep(0.15 * (2**attempt))
    raise last_error or VoiceProviderError("provider_error", "The speech provider failed.")


def _request_bytes_sync(
    url: str,
    api_key: SecretStr,
    body: bytes,
    content_type: str,
    timeout_seconds: float,
    max_response_bytes: int,
) -> tuple[bytes, str | None]:
    request = URLRequest(  # noqa: S310
        url,
        data=body,
        headers={
            "authorization": f"Bearer {api_key.get_secret_value()}",
            "content-type": content_type,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            content = response.read(max_response_bytes + 1)
            if len(content) > max_response_bytes:
                raise VoiceProviderError(
                    "provider_response_too_large",
                    "The speech provider response exceeded the configured limit.",
                )
            return content, response.headers.get("content-type")
    except HTTPError as exc:
        if exc.code == 429:
            raise VoiceProviderError(
                "provider_rate_limited",
                "The speech provider is rate limited.",
            ) from exc
        if exc.code >= 500:
            raise VoiceProviderError(
                "provider_unavailable",
                "The speech provider is unavailable.",
            ) from exc
        raise VoiceProviderError(
            "provider_error",
            "The speech provider rejected the request.",
        ) from exc
    except (TimeoutError, URLError) as exc:
        raise VoiceProviderError(
            "provider_unavailable",
            "The speech provider is unavailable.",
        ) from exc


def _multipart_body(
    *,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    media_type: str,
    file_bytes: bytes,
) -> tuple[bytes, str]:
    boundary = f"loomi-{secrets.token_hex(16)}"
    output = bytearray()
    for key, value in fields.items():
        output.extend(f"--{boundary}\r\n".encode())
        output.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        output.extend(value.encode())
        output.extend(b"\r\n")
    safe_filename = (
        filename.replace('"', "").replace("\r", "").replace("\n", "") or "voice.webm"
    )
    output.extend(f"--{boundary}\r\n".encode())
    output.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{safe_filename}"\r\n'
            f"Content-Type: {media_type}\r\n\r\n"
        ).encode()
    )
    output.extend(file_bytes)
    output.extend(b"\r\n")
    output.extend(f"--{boundary}--\r\n".encode())
    return bytes(output), f"multipart/form-data; boundary={boundary}"


def _confidence_from_usage(usage: object) -> float | None:
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if isinstance(total, int) and total > 0:
        return None
    return None


def _mock_wav(text: str) -> bytes:
    sample_rate = 16_000
    duration_seconds = min(2.0, max(0.35, len(text) / 120))
    sample_count = int(sample_rate * duration_seconds)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(sample_count):
            envelope = 1.0 - (index / max(sample_count, 1))
            value = int(9000 * envelope * math.sin(2 * math.pi * 440 * index / sample_rate))
            wav.writeframes(struct.pack("<h", value))
    return output.getvalue()
