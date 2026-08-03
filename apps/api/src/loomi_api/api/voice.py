from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from loomi_api.api.dependencies import (
    CsrfOwnerContext,
    DbSession,
    OwnerContext,
    get_settings_from_app,
)
from loomi_api.config import Settings
from loomi_api.db.models import VoiceSession
from loomi_api.problems import problem_response
from loomi_api.voice.contracts import (
    SUPPORTED_TTS_VOICES,
    SpeechToTextProviderName,
    TextToSpeechProviderName,
    VoiceProviderError,
    VoiceSettings,
)
from loomi_api.voice.service import (
    VoiceRequestError,
    delete_voice_audio,
    delete_voice_session,
    get_voice_session,
    get_voice_settings,
    list_voice_sessions,
    synthesize_voice,
    transcribe_voice,
    update_voice_settings,
)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


class VoiceSettingsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    accepted_mime_types: list[str]
    allowed_tts_voices: list[str]
    openai_configured: bool
    local_stt_configured: bool
    local_tts_configured: bool


class VoiceSettingsPatch(BaseModel):
    stt_provider: SpeechToTextProviderName | None = None
    stt_model: str | None = Field(default=None, min_length=1, max_length=160)
    tts_provider: TextToSpeechProviderName | None = None
    tts_model: str | None = Field(default=None, min_length=1, max_length=160)
    tts_voice: str | None = Field(default=None, min_length=1, max_length=80)
    language: str | None = Field(default=None, min_length=1, max_length=24)
    max_recording_seconds: int | None = Field(default=None, ge=1, le=600)
    max_audio_bytes: int | None = Field(default=None, ge=1024, le=50 * 1024 * 1024)
    transcript_review_enabled: bool | None = None
    auto_speak_assistant: bool | None = None
    retain_raw_audio: bool | None = None
    retention_days: int | None = Field(default=None, ge=0, le=365)
    demo_mode: bool | None = None
    cloud_enabled: bool | None = None


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    transcript_id: str
    text: str
    language: str
    confidence: float | None
    provider: str
    model: str
    duration_ms: int | None
    audio_size_bytes: int
    retained_audio: bool
    mocked: bool
    request_id: str
    trace_id: str


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    provider: Literal["mock", "openai", "local-compatible"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=160)
    voice: str | None = Field(default=None, min_length=1, max_length=80)
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


class TTSResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    audio_base64: str
    content_type: str
    provider: str
    model: str
    voice: str
    mocked: bool
    request_id: str
    trace_id: str


class VoiceSessionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    conversation_id: str | None
    message_id: str | None
    status: str
    stt_provider: str
    stt_model: str
    tts_provider: str | None
    tts_model: str | None
    tts_voice: str | None
    language: str
    duration_ms: int | None
    audio_size_bytes: int
    retention_policy: dict[str, object]
    request_id: str | None
    trace_id: str | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None


class VoiceSessionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[VoiceSessionSummary]
    total: int
    limit: int
    offset: int


class VoiceTranscriptPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    provider: str
    model: str
    language: str
    text: str
    confidence: float | None
    duration_ms: int | None
    audio_size_bytes: int
    trace_id: str | None
    metadata: dict[str, object]
    created_at: datetime


class VoiceAudioAssetPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    media_type: str
    size_bytes: int
    sha256: str
    retained: bool
    retention_expires_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime


class VoiceProviderEventPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    event_type: str
    provider: str
    model: str | None
    status: str
    latency_ms: int | None
    metadata: dict[str, object]
    error_code: str | None
    trace_id: str | None
    created_at: datetime


class VoiceSessionDetail(VoiceSessionSummary):
    transcripts: list[VoiceTranscriptPayload]
    audio_assets: list[VoiceAudioAssetPayload]
    provider_events: list[VoiceProviderEventPayload]


class VoiceAudioDeleteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    deleted_count: int


@router.get("/settings", response_model=VoiceSettingsResponse)
async def read_voice_settings(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> VoiceSettingsResponse:
    settings = get_settings_from_app(request)
    config = await get_voice_settings(session, settings, owner.user.id)
    return _settings_response(config, settings)


@router.patch("/settings", response_model=VoiceSettingsResponse)
async def patch_voice_settings(
    request: Request,
    payload: VoiceSettingsPatch,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> VoiceSettingsResponse:
    settings = get_settings_from_app(request)
    try:
        config = await update_voice_settings(
            session,
            settings,
            owner.user.id,
            payload.model_dump(exclude_unset=True),
            request_id=str(getattr(request.state, "request_id", "")),
            trace_id=str(getattr(request.state, "trace_id", "")),
        )
    except VoiceRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _settings_response(config, settings)


@router.post("/transcribe", response_model=TranscriptionResponse, status_code=201)
async def transcribe(
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
    audio: Annotated[UploadFile, File()],
    conversation_id: Annotated[str | None, Form()] = None,
    duration_ms: Annotated[int | None, Form(ge=0)] = None,
) -> TranscriptionResponse | JSONResponse:
    settings = get_settings_from_app(request)
    if _rate_limited(request, f"transcribe:{owner.user.id}"):
        return problem_response(
            request,
            status_code=429,
            title="Too Many Requests",
            detail="Too many voice transcription requests. Try again shortly.",
            code="rate_limited",
        )
    request_id = str(getattr(request.state, "request_id", ""))
    trace_id = str(getattr(request.state, "trace_id", ""))
    media_type = _normal_media_type(audio.content_type)
    try:
        audio_bytes = await _read_limited_audio(audio, settings.voice_max_audio_bytes)
        result = await transcribe_voice(
            session,
            settings,
            owner_user_id=owner.user.id,
            conversation_id=conversation_id,
            audio_bytes=audio_bytes,
            media_type=media_type,
            filename=audio.filename or "voice.webm",
            duration_ms=duration_ms,
            request_id=request_id,
            trace_id=trace_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VoiceRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except VoiceProviderError as exc:
        raise HTTPException(status_code=_provider_status(exc), detail=exc.detail) from exc
    return TranscriptionResponse(**result.__dict__)


@router.post("/tts", response_model=TTSResponse)
async def tts(
    request: Request,
    payload: TTSRequest,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> TTSResponse | JSONResponse:
    settings = get_settings_from_app(request)
    if _rate_limited(request, f"tts:{owner.user.id}"):
        return problem_response(
            request,
            status_code=429,
            title="Too Many Requests",
            detail="Too many voice synthesis requests. Try again shortly.",
            code="rate_limited",
        )
    request_id = str(getattr(request.state, "request_id", ""))
    trace_id = str(getattr(request.state, "trace_id", ""))
    try:
        result = await synthesize_voice(
            session,
            settings,
            owner_user_id=owner.user.id,
            text=payload.text,
            provider=payload.provider,
            model=payload.model,
            voice=payload.voice,
            speed=payload.speed,
            request_id=request_id,
            trace_id=trace_id,
        )
    except VoiceRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except VoiceProviderError as exc:
        raise HTTPException(status_code=_provider_status(exc), detail=exc.detail) from exc
    return TTSResponse(**result.__dict__)


@router.get("/sessions", response_model=VoiceSessionListResponse)
async def sessions(
    session: DbSession,
    owner: OwnerContext,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VoiceSessionListResponse:
    items, total = await list_voice_sessions(session, owner.user.id, limit=limit, offset=offset)
    return VoiceSessionListResponse(
        items=[_session_summary(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{voice_session_id}", response_model=VoiceSessionDetail)
async def session_detail(
    voice_session_id: str,
    session: DbSession,
    owner: OwnerContext,
) -> VoiceSessionDetail:
    try:
        voice_session, transcripts, assets, events = await get_voice_session(
            session, owner.user.id, voice_session_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoiceSessionDetail(
        **_session_summary(voice_session).model_dump(),
        transcripts=[
            VoiceTranscriptPayload(
                id=item.id,
                provider=item.provider,
                model=item.model,
                language=item.language,
                text=item.transcript_text,
                confidence=item.confidence,
                duration_ms=item.duration_ms,
                audio_size_bytes=item.audio_size_bytes,
                trace_id=item.trace_id,
                metadata=item.transcript_metadata,
                created_at=item.created_at,
            )
            for item in transcripts
        ],
        audio_assets=[
            VoiceAudioAssetPayload(
                id=item.id,
                media_type=item.media_type,
                size_bytes=item.size_bytes,
                sha256=item.sha256,
                retained=item.deleted_at is None and item.object_key is not None,
                retention_expires_at=item.retention_expires_at,
                deleted_at=item.deleted_at,
                created_at=item.created_at,
            )
            for item in assets
        ],
        provider_events=[
            VoiceProviderEventPayload(
                id=item.id,
                event_type=item.event_type,
                provider=item.provider,
                model=item.model,
                status=item.status,
                latency_ms=item.latency_ms,
                metadata=item.safe_metadata,
                error_code=item.error_code,
                trace_id=item.trace_id,
                created_at=item.created_at,
            )
            for item in events
        ],
    )


@router.delete("/sessions/{voice_session_id}", status_code=204)
async def delete_session(
    request: Request,
    voice_session_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> None:
    settings = get_settings_from_app(request)
    try:
        await delete_voice_session(session, settings, owner.user.id, voice_session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sessions/{voice_session_id}/audio", response_model=VoiceAudioDeleteResponse)
async def delete_session_audio(
    request: Request,
    voice_session_id: str,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> VoiceAudioDeleteResponse:
    settings = get_settings_from_app(request)
    try:
        deleted_count = await delete_voice_audio(session, settings, owner.user.id, voice_session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoiceAudioDeleteResponse(deleted_count=deleted_count)


def _settings_response(config: VoiceSettings, settings: Settings) -> VoiceSettingsResponse:
    return VoiceSettingsResponse(
        stt_provider=config.stt_provider,
        stt_model=config.stt_model,
        tts_provider=config.tts_provider,
        tts_model=config.tts_model,
        tts_voice=config.tts_voice,
        language=config.language,
        max_recording_seconds=config.max_recording_seconds,
        max_audio_bytes=config.max_audio_bytes,
        transcript_review_enabled=config.transcript_review_enabled,
        auto_speak_assistant=config.auto_speak_assistant,
        retain_raw_audio=config.retain_raw_audio,
        retention_days=config.retention_days,
        demo_mode=config.demo_mode,
        cloud_enabled=config.cloud_enabled,
        accepted_mime_types=list(config.accepted_mime_types),
        allowed_tts_voices=list(SUPPORTED_TTS_VOICES),
        openai_configured=settings.openai_api_key is not None,
        local_stt_configured=bool(settings.voice_local_stt_base_url),
        local_tts_configured=bool(settings.voice_local_tts_base_url),
    )


def _session_summary(typed: VoiceSession) -> VoiceSessionSummary:
    return VoiceSessionSummary(
        id=typed.id,
        conversation_id=typed.conversation_id,
        message_id=typed.message_id,
        status=typed.status,
        stt_provider=typed.stt_provider,
        stt_model=typed.stt_model,
        tts_provider=typed.tts_provider,
        tts_model=typed.tts_model,
        tts_voice=typed.tts_voice,
        language=typed.language,
        duration_ms=typed.duration_ms,
        audio_size_bytes=typed.audio_size_bytes,
        retention_policy=typed.retention_policy,
        request_id=typed.request_id,
        trace_id=typed.trace_id,
        error_code=typed.error_code,
        error_detail=typed.error_detail,
        created_at=typed.created_at,
        updated_at=typed.updated_at,
        completed_at=typed.completed_at,
        cancelled_at=typed.cancelled_at,
    )


def _normal_media_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().casefold()


async def _read_limited_audio(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise VoiceRequestError(
                    "audio_too_large",
                    "Audio exceeds the configured limit.",
                    413,
                )
            chunks.append(chunk)
    finally:
        await upload.close()
    return b"".join(chunks)


def _provider_status(exc: VoiceProviderError) -> int:
    if exc.code == "cloud_speech_disabled":
        return 403
    if exc.code == "provider_not_configured":
        return 400
    if exc.code == "provider_response_too_large":
        return 502
    if exc.code in {"provider_rate_limited"}:
        return 429
    return 503


def _rate_limited(request: Request, key: str) -> bool:
    settings = get_settings_from_app(request)
    now = time.monotonic()
    bucket = getattr(request.app.state, "voice_rate_limits", None)
    if bucket is None:
        bucket = {}
        request.app.state.voice_rate_limits = bucket
    window = settings.voice_rate_limit_window_seconds
    attempts = settings.voice_rate_limit_attempts
    timestamps = [stamp for stamp in bucket.get(key, []) if now - stamp < window]
    if len(timestamps) >= attempts:
        bucket[key] = timestamps
        return True
    timestamps.append(now)
    bucket[key] = timestamps
    return False
