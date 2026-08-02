from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

SpeechToTextProviderName = Literal["mock", "openai", "local-compatible"]
TextToSpeechProviderName = Literal["browser", "mock", "openai", "local-compatible"]
ExcludeBrowserProviderName = Literal["mock", "openai", "local-compatible"]

SUPPORTED_AUDIO_MIME_TYPES = (
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/ogg",
    "audio/flac",
    "audio/aac",
)

SUPPORTED_TTS_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
)


@dataclass(frozen=True)
class VoiceSettings:
    stt_provider: SpeechToTextProviderName
    stt_model: str
    tts_provider: TextToSpeechProviderName
    tts_model: str
    tts_voice: str
    language: str
    max_recording_seconds: int
    max_audio_bytes: int
    transcript_review_enabled: bool
    auto_speak_assistant: bool
    retain_raw_audio: bool
    retention_days: int
    demo_mode: bool
    cloud_enabled: bool
    accepted_mime_types: tuple[str, ...] = SUPPORTED_AUDIO_MIME_TYPES


@dataclass(frozen=True)
class SpeechToTextRequest:
    audio_bytes: bytes
    media_type: str
    filename: str
    model: str
    language: str
    duration_ms: int | None
    request_id: str
    trace_id: str


@dataclass(frozen=True)
class SpeechTranscript:
    text: str
    language: str
    confidence: float | None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TextToSpeechRequest:
    text: str
    model: str
    voice: str
    speed: float
    request_id: str
    trace_id: str


@dataclass(frozen=True)
class TextToSpeechAudio:
    audio_bytes: bytes
    media_type: str
    metadata: dict[str, object] = field(default_factory=dict)


class SpeechToTextProvider(Protocol):
    provider: SpeechToTextProviderName

    async def transcribe(
        self,
        request: SpeechToTextRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> SpeechTranscript:
        """Return a transcript without exposing provider internals or secrets."""


class TextToSpeechProvider(Protocol):
    provider: ExcludeBrowserProviderName

    async def synthesize(
        self,
        request: TextToSpeechRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> TextToSpeechAudio:
        """Return generated audio bytes without exposing provider internals or secrets."""


class VoiceProviderError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
