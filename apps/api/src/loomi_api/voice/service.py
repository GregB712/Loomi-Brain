from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.config import Settings
from loomi_api.db.base import utc_now
from loomi_api.db.models import (
    AuditEvent,
    Conversation,
    OwnerSetting,
    VoiceAudioAsset,
    VoiceProviderEvent,
    VoiceSession,
    VoiceTranscript,
)
from loomi_api.ingestion.storage import LocalObjectStore
from loomi_api.observability.redaction import contains_unredacted_secret, redact_value
from loomi_api.observability.telemetry import elapsed_ms, record_span, start_timer
from loomi_api.voice.contracts import (
    SUPPORTED_AUDIO_MIME_TYPES,
    SUPPORTED_TTS_VOICES,
    SpeechToTextProvider,
    SpeechToTextProviderName,
    SpeechToTextRequest,
    TextToSpeechProvider,
    TextToSpeechProviderName,
    TextToSpeechRequest,
    VoiceProviderError,
    VoiceSettings,
)
from loomi_api.voice.providers import (
    MockSpeechToTextProvider,
    MockTextToSpeechProvider,
    OpenAISpeechToTextProvider,
    OpenAITextToSpeechProvider,
)

VOICE_SETTING_KEY = "voice"


@dataclass(frozen=True)
class TranscriptionResult:
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


@dataclass(frozen=True)
class TTSResult:
    audio_base64: str
    content_type: str
    provider: str
    model: str
    voice: str
    mocked: bool
    request_id: str
    trace_id: str


class VoiceRequestError(RuntimeError):
    def __init__(self, code: str, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


async def get_voice_settings(
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
) -> VoiceSettings:
    owner_setting = await session.scalar(
        select(OwnerSetting).where(
            OwnerSetting.owner_user_id == owner_user_id,
            OwnerSetting.key == VOICE_SETTING_KEY,
        )
    )
    overrides = owner_setting.value if owner_setting is not None else {}
    return _voice_settings_from(settings, overrides)


async def update_voice_settings(
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    patch: dict[str, Any],
    *,
    request_id: str,
    trace_id: str,
) -> VoiceSettings:
    current = await session.scalar(
        select(OwnerSetting).where(
            OwnerSetting.owner_user_id == owner_user_id,
            OwnerSetting.key == VOICE_SETTING_KEY,
        )
    )
    merged = dict(current.value if current is not None else {})
    allowed_keys = {
        "stt_provider",
        "stt_model",
        "tts_provider",
        "tts_model",
        "tts_voice",
        "language",
        "max_recording_seconds",
        "max_audio_bytes",
        "transcript_review_enabled",
        "auto_speak_assistant",
        "retain_raw_audio",
        "retention_days",
        "demo_mode",
        "cloud_enabled",
    }
    for key, value in patch.items():
        if value is not None and key in allowed_keys:
            merged[key] = value
    resolved = _voice_settings_from(settings, merged)
    if current is None:
        current = OwnerSetting(
            owner_user_id=owner_user_id,
            key=VOICE_SETTING_KEY,
            value=_settings_payload(resolved),
        )
        session.add(current)
    else:
        current.value = _settings_payload(resolved)
    session.add(
        AuditEvent(
            owner_user_id=owner_user_id,
            event_type="voice.settings.updated",
            request_id=request_id,
            trace_id=trace_id,
            event_metadata={
                "stt_provider": resolved.stt_provider,
                "tts_provider": resolved.tts_provider,
                "retain_raw_audio": resolved.retain_raw_audio,
                "cloud_enabled": resolved.cloud_enabled,
            },
        )
    )
    await session.commit()
    return resolved


async def transcribe_voice(
    session: AsyncSession,
    settings: Settings,
    *,
    owner_user_id: str,
    conversation_id: str | None,
    audio_bytes: bytes,
    media_type: str,
    filename: str,
    duration_ms: int | None,
    request_id: str,
    trace_id: str,
) -> TranscriptionResult:
    config = await get_voice_settings(session, settings, owner_user_id)
    _validate_audio_request(config, audio_bytes, media_type, duration_ms)
    if conversation_id is not None:
        await _load_owner_conversation(session, owner_user_id, conversation_id)
    model = _effective_stt_model(config, settings)
    voice_session = VoiceSession(
        owner_user_id=owner_user_id,
        conversation_id=conversation_id,
        status="transcribing",
        stt_provider=config.stt_provider,
        stt_model=model,
        tts_provider=config.tts_provider,
        tts_model=_effective_tts_model(config, settings),
        tts_voice=config.tts_voice,
        language=config.language,
        duration_ms=duration_ms,
        audio_size_bytes=len(audio_bytes),
        retention_policy={
            "retain_raw_audio": config.retain_raw_audio,
            "retention_days": config.retention_days,
        },
        request_id=request_id,
        trace_id=trace_id,
    )
    session.add(voice_session)
    await session.flush()
    retained_audio = False
    if config.retain_raw_audio:
        await _retain_audio(
            session,
            settings,
            owner_user_id=owner_user_id,
            voice_session_id=voice_session.id,
            audio_bytes=audio_bytes,
            media_type=media_type,
            retention_days=config.retention_days,
        )
        retained_audio = True
    provider = _stt_provider_for(config, settings)
    started = start_timer()
    try:
        transcript = await provider.transcribe(
            SpeechToTextRequest(
                audio_bytes=audio_bytes,
                media_type=media_type,
                filename=filename,
                model=model,
                language=config.language,
                duration_ms=duration_ms,
                request_id=request_id,
                trace_id=trace_id,
            ),
            _not_cancelled,
        )
        transcript_text = transcript.text.strip()
        if not transcript_text:
            raise VoiceProviderError("empty_transcript", "The speech provider returned no text.")
        voice_session.status = "completed"
        voice_session.completed_at = utc_now()
        row = VoiceTranscript(
            voice_session_id=voice_session.id,
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            provider=config.stt_provider,
            model=model,
            language=transcript.language or config.language,
            transcript_text=transcript_text,
            confidence=transcript.confidence,
            duration_ms=duration_ms,
            audio_size_bytes=len(audio_bytes),
            trace_id=trace_id,
            transcript_metadata=_safe_metadata(transcript.metadata),
        )
        session.add(row)
        await _record_voice_provider_event(
            session,
            owner_user_id=owner_user_id,
            voice_session_id=voice_session.id,
            event_type="transcription",
            provider=config.stt_provider,
            model=model,
            status="ok",
            latency_ms=elapsed_ms(started),
            trace_id=trace_id,
            safe_metadata={"audio_size_bytes": len(audio_bytes), "audio_duration_ms": duration_ms},
        )
        await record_span(
            session,
            settings,
            name="loomi.voice.transcription",
            component="voice",
            trace_id=trace_id,
            owner_user_id=owner_user_id,
            duration_ms=elapsed_ms(started),
            attributes={
                "provider": config.stt_provider,
                "model": model,
                "language": transcript.language or config.language,
                "voice_session_id": voice_session.id,
                "audio_size_bytes": len(audio_bytes),
                "audio_duration_ms": duration_ms,
                "retention_enabled": retained_audio,
                "request_id": request_id,
                "trace_id": trace_id,
            },
        )
        await session.commit()
        return TranscriptionResult(
            session_id=voice_session.id,
            transcript_id=row.id,
            text=transcript_text,
            language=transcript.language or config.language,
            confidence=transcript.confidence,
            provider=config.stt_provider,
            model=model,
            duration_ms=duration_ms,
            audio_size_bytes=len(audio_bytes),
            retained_audio=retained_audio,
            mocked=bool(transcript.metadata.get("mocked")),
            request_id=request_id,
            trace_id=trace_id,
        )
    except VoiceProviderError as exc:
        voice_session.status = "failed"
        voice_session.error_code = exc.code
        voice_session.error_detail = exc.detail
        await _record_voice_provider_event(
            session,
            owner_user_id=owner_user_id,
            voice_session_id=voice_session.id,
            event_type="transcription",
            provider=config.stt_provider,
            model=model,
            status="error",
            latency_ms=elapsed_ms(started),
            trace_id=trace_id,
            error_code=exc.code,
            safe_metadata={"audio_size_bytes": len(audio_bytes), "audio_duration_ms": duration_ms},
        )
        await record_span(
            session,
            settings,
            name="loomi.voice.transcription",
            component="voice",
            trace_id=trace_id,
            owner_user_id=owner_user_id,
            status="error",
            duration_ms=elapsed_ms(started),
            error_code=exc.code,
            attributes={
                "provider": config.stt_provider,
                "model": model,
                "voice_session_id": voice_session.id,
                "audio_size_bytes": len(audio_bytes),
                "audio_duration_ms": duration_ms,
                "error_code": exc.code,
                "request_id": request_id,
                "trace_id": trace_id,
            },
        )
        await session.commit()
        raise


async def synthesize_voice(
    session: AsyncSession,
    settings: Settings,
    *,
    owner_user_id: str,
    text: str,
    provider: TextToSpeechProviderName | None,
    model: str | None,
    voice: str | None,
    speed: float,
    request_id: str,
    trace_id: str,
) -> TTSResult:
    config = await get_voice_settings(session, settings, owner_user_id)
    selected_provider = provider or config.tts_provider
    if selected_provider == "browser":
        raise VoiceRequestError(
            "browser_tts_client_only",
            "Browser speech synthesis is handled in the client.",
            status_code=400,
        )
    selected_voice = voice or config.tts_voice
    if selected_voice not in SUPPORTED_TTS_VOICES:
        raise VoiceRequestError("unsupported_voice", "The selected voice is not allowed.", 422)
    clean_text = " ".join(text.split())
    if not clean_text:
        raise VoiceRequestError("empty_tts_text", "Text to speak is required.", 422)
    if len(clean_text) > settings.voice_tts_max_chars:
        raise VoiceRequestError("tts_text_too_long", "Text exceeds the TTS limit.", 413)
    if contains_unredacted_secret(clean_text):
        raise VoiceRequestError(
            "unsafe_tts_text",
            "Text containing secret-like material cannot be synthesized.",
            422,
        )
    provider_config = VoiceSettings(
        **{
            **_settings_payload(config),
            "tts_provider": selected_provider,
            "tts_model": model or _effective_tts_model(config, settings),
            "tts_voice": selected_voice,
        }
    )
    tts_provider = _tts_provider_for(provider_config, settings)
    selected_model = model or _effective_tts_model(provider_config, settings)
    started = start_timer()
    try:
        audio = await tts_provider.synthesize(
            TextToSpeechRequest(
                text=clean_text,
                model=selected_model,
                voice=selected_voice,
                speed=speed,
                request_id=request_id,
                trace_id=trace_id,
            ),
            _not_cancelled,
        )
        await _record_voice_provider_event(
            session,
            owner_user_id=owner_user_id,
            voice_session_id=None,
            event_type="tts",
            provider=selected_provider,
            model=selected_model,
            status="ok",
            latency_ms=elapsed_ms(started),
            trace_id=trace_id,
            safe_metadata={"tts_voice": selected_voice, "audio_size_bytes": len(audio.audio_bytes)},
        )
        await record_span(
            session,
            settings,
            name="loomi.voice.tts",
            component="voice",
            trace_id=trace_id,
            owner_user_id=owner_user_id,
            duration_ms=elapsed_ms(started),
            attributes={
                "provider": selected_provider,
                "model": selected_model,
                "tts_voice": selected_voice,
                "audio_size_bytes": len(audio.audio_bytes),
                "request_id": request_id,
                "trace_id": trace_id,
            },
        )
        await session.commit()
        return TTSResult(
            audio_base64=base64.b64encode(audio.audio_bytes).decode("ascii"),
            content_type=audio.media_type,
            provider=selected_provider,
            model=selected_model,
            voice=selected_voice,
            mocked=bool(audio.metadata.get("mocked")),
            request_id=request_id,
            trace_id=trace_id,
        )
    except VoiceProviderError as exc:
        await _record_voice_provider_event(
            session,
            owner_user_id=owner_user_id,
            voice_session_id=None,
            event_type="tts",
            provider=selected_provider,
            model=selected_model,
            status="error",
            latency_ms=elapsed_ms(started),
            trace_id=trace_id,
            error_code=exc.code,
            safe_metadata={"tts_voice": selected_voice},
        )
        await record_span(
            session,
            settings,
            name="loomi.voice.tts",
            component="voice",
            trace_id=trace_id,
            owner_user_id=owner_user_id,
            status="error",
            duration_ms=elapsed_ms(started),
            error_code=exc.code,
            attributes={
                "provider": selected_provider,
                "model": selected_model,
                "tts_voice": selected_voice,
                "error_code": exc.code,
                "request_id": request_id,
                "trace_id": trace_id,
            },
        )
        await session.commit()
        raise


async def list_voice_sessions(
    session: AsyncSession,
    owner_user_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[VoiceSession], int]:
    total = await session.scalar(
        select(func.count(VoiceSession.id)).where(VoiceSession.owner_user_id == owner_user_id)
    )
    items = list(
        await session.scalars(
            select(VoiceSession)
            .where(VoiceSession.owner_user_id == owner_user_id)
            .order_by(desc(VoiceSession.created_at))
            .limit(limit)
            .offset(offset)
        )
    )
    return items, int(total or 0)


async def get_voice_session(
    session: AsyncSession,
    owner_user_id: str,
    voice_session_id: str,
) -> tuple[VoiceSession, list[VoiceTranscript], list[VoiceAudioAsset], list[VoiceProviderEvent]]:
    voice_session = await _load_voice_session(session, owner_user_id, voice_session_id)
    transcripts = list(
        await session.scalars(
            select(VoiceTranscript)
            .where(
                VoiceTranscript.owner_user_id == owner_user_id,
                VoiceTranscript.voice_session_id == voice_session_id,
            )
            .order_by(VoiceTranscript.created_at.asc())
        )
    )
    assets = list(
        await session.scalars(
            select(VoiceAudioAsset).where(
                VoiceAudioAsset.owner_user_id == owner_user_id,
                VoiceAudioAsset.voice_session_id == voice_session_id,
            )
        )
    )
    events = list(
        await session.scalars(
            select(VoiceProviderEvent)
            .where(
                VoiceProviderEvent.owner_user_id == owner_user_id,
                VoiceProviderEvent.voice_session_id == voice_session_id,
            )
            .order_by(VoiceProviderEvent.created_at.asc())
        )
    )
    return voice_session, transcripts, assets, events


async def delete_voice_session(
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    voice_session_id: str,
) -> None:
    await _load_voice_session(session, owner_user_id, voice_session_id)
    await delete_voice_audio(session, settings, owner_user_id, voice_session_id, commit=False)
    await session.execute(
        delete(VoiceProviderEvent).where(
            VoiceProviderEvent.owner_user_id == owner_user_id,
            VoiceProviderEvent.voice_session_id == voice_session_id,
        )
    )
    await session.execute(
        delete(VoiceTranscript).where(
            VoiceTranscript.owner_user_id == owner_user_id,
            VoiceTranscript.voice_session_id == voice_session_id,
        )
    )
    await session.execute(
        delete(VoiceSession).where(
            VoiceSession.owner_user_id == owner_user_id,
            VoiceSession.id == voice_session_id,
        )
    )
    await session.commit()


async def delete_voice_audio(
    session: AsyncSession,
    settings: Settings,
    owner_user_id: str,
    voice_session_id: str,
    *,
    commit: bool = True,
) -> int:
    await _load_voice_session(session, owner_user_id, voice_session_id)
    assets = list(
        await session.scalars(
            select(VoiceAudioAsset).where(
                VoiceAudioAsset.owner_user_id == owner_user_id,
                VoiceAudioAsset.voice_session_id == voice_session_id,
                VoiceAudioAsset.deleted_at.is_(None),
            )
        )
    )
    store = LocalObjectStore(settings.storage_root)
    deleted_count = 0
    for asset in assets:
        if asset.object_key:
            store.delete(asset.object_key)
        asset.deleted_at = utc_now()
        deleted_count += 1
    if commit:
        session.add(
            AuditEvent(
            owner_user_id=owner_user_id,
            event_type="voice.audio.deleted",
            event_metadata={
                "voice_session_id": voice_session_id,
                "deleted_count": deleted_count,
            },
        )
        )
        await session.commit()
    return deleted_count


def _voice_settings_from(settings: Settings, overrides: dict[str, Any]) -> VoiceSettings:
    stt_provider = _stt_provider_value(overrides.get("stt_provider", settings.voice_stt_provider))
    tts_provider = _tts_provider_value(overrides.get("tts_provider", settings.voice_tts_provider))
    retention_days = _bounded_int(
        overrides.get("retention_days", settings.voice_retention_days),
        0,
        365,
    )
    retain_raw_audio = bool(overrides.get("retain_raw_audio", settings.voice_retain_raw_audio))
    if retain_raw_audio and retention_days < 1:
        raise VoiceRequestError(
            "invalid_retention_policy",
            "Raw audio retention requires a positive retention window.",
            422,
        )
    voice = str(overrides.get("tts_voice", settings.voice_tts_voice))
    if voice not in SUPPORTED_TTS_VOICES:
        raise VoiceRequestError("unsupported_voice", "The selected voice is not allowed.", 422)
    return VoiceSettings(
        stt_provider=stt_provider,
        stt_model=str(overrides.get("stt_model", settings.voice_stt_model))[:160],
        tts_provider=tts_provider,
        tts_model=str(overrides.get("tts_model", settings.voice_tts_model))[:160],
        tts_voice=voice,
        language=str(overrides.get("language", settings.voice_language))[:24] or "en",
        max_recording_seconds=_bounded_int(
            overrides.get("max_recording_seconds", settings.voice_max_recording_seconds), 1, 600
        ),
        max_audio_bytes=_bounded_int(
            overrides.get("max_audio_bytes", settings.voice_max_audio_bytes), 1024, 50 * 1024 * 1024
        ),
        transcript_review_enabled=bool(
            overrides.get(
                "transcript_review_enabled",
                settings.voice_transcript_review_enabled,
            )
        ),
        auto_speak_assistant=bool(
            overrides.get("auto_speak_assistant", settings.voice_auto_speak_assistant)
        ),
        retain_raw_audio=retain_raw_audio,
        retention_days=retention_days,
        demo_mode=bool(overrides.get("demo_mode", settings.voice_demo_mode)),
        cloud_enabled=bool(overrides.get("cloud_enabled", settings.voice_cloud_enabled)),
        accepted_mime_types=SUPPORTED_AUDIO_MIME_TYPES,
    )


def _settings_payload(config: VoiceSettings) -> dict[str, Any]:
    return {
        "stt_provider": config.stt_provider,
        "stt_model": config.stt_model,
        "tts_provider": config.tts_provider,
        "tts_model": config.tts_model,
        "tts_voice": config.tts_voice,
        "language": config.language,
        "max_recording_seconds": config.max_recording_seconds,
        "max_audio_bytes": config.max_audio_bytes,
        "transcript_review_enabled": config.transcript_review_enabled,
        "auto_speak_assistant": config.auto_speak_assistant,
        "retain_raw_audio": config.retain_raw_audio,
        "retention_days": config.retention_days,
        "demo_mode": config.demo_mode,
        "cloud_enabled": config.cloud_enabled,
    }


def _validate_audio_request(
    config: VoiceSettings,
    audio_bytes: bytes,
    media_type: str,
    duration_ms: int | None,
) -> None:
    if media_type not in config.accepted_mime_types:
        raise VoiceRequestError("unsupported_audio_type", "Unsupported audio MIME type.", 415)
    if len(audio_bytes) > config.max_audio_bytes:
        raise VoiceRequestError("audio_too_large", "Audio exceeds the configured limit.", 413)
    if not audio_bytes:
        raise VoiceRequestError("empty_audio", "Audio content is required.", 422)
    if duration_ms is not None and duration_ms > config.max_recording_seconds * 1000:
        raise VoiceRequestError(
            "audio_duration_too_long",
            "Audio duration exceeds the configured limit.",
            422,
        )


def _stt_provider_for(config: VoiceSettings, settings: Settings) -> SpeechToTextProvider:
    if config.stt_provider == "mock":
        return MockSpeechToTextProvider(settings.voice_mock_transcript)
    if config.stt_provider == "openai":
        if not config.cloud_enabled:
            raise VoiceProviderError(
                "cloud_speech_disabled",
                "Cloud speech providers are disabled until the owner enables them.",
            )
        return OpenAISpeechToTextProvider(
            provider="openai",
            base_url="https://api.openai.com/v1",
            api_key=settings.openai_api_key,
            timeout_seconds=settings.model_request_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
    return OpenAISpeechToTextProvider(
        provider="local-compatible",
        base_url=settings.voice_local_stt_base_url or "",
        api_key=settings.voice_local_api_key or _local_dummy_key(settings.voice_local_stt_base_url),
        timeout_seconds=settings.model_request_timeout_seconds,
        max_retries=settings.model_max_retries,
    )


def _tts_provider_for(config: VoiceSettings, settings: Settings) -> TextToSpeechProvider:
    if config.tts_provider == "mock":
        return MockTextToSpeechProvider()
    if config.tts_provider == "openai":
        if not config.cloud_enabled:
            raise VoiceProviderError(
                "cloud_speech_disabled",
                "Cloud speech providers are disabled until the owner enables them.",
            )
        return OpenAITextToSpeechProvider(
            provider="openai",
            base_url="https://api.openai.com/v1",
            api_key=settings.openai_api_key,
            timeout_seconds=settings.model_request_timeout_seconds,
            max_retries=settings.model_max_retries,
            max_response_bytes=settings.voice_tts_max_audio_bytes,
        )
    if config.tts_provider == "local-compatible":
        return OpenAITextToSpeechProvider(
            provider="local-compatible",
            base_url=settings.voice_local_tts_base_url or "",
            api_key=settings.voice_local_api_key
            or _local_dummy_key(settings.voice_local_tts_base_url),
            timeout_seconds=settings.model_request_timeout_seconds,
            max_retries=settings.model_max_retries,
            max_response_bytes=settings.voice_tts_max_audio_bytes,
        )
    raise VoiceProviderError("provider_not_configured", "The speech provider is not configured.")


async def _retain_audio(
    session: AsyncSession,
    settings: Settings,
    *,
    owner_user_id: str,
    voice_session_id: str,
    audio_bytes: bytes,
    media_type: str,
    retention_days: int,
) -> None:
    store = LocalObjectStore(settings.storage_root)
    digest = hashlib.sha256(audio_bytes).hexdigest()
    object_key = (
        f"owners/{owner_user_id}/voice/{voice_session_id}/"
        f"{secrets.token_urlsafe(24)}.audio"
    )
    destination = store.path_for_key(object_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio_bytes)
    session.add(
        VoiceAudioAsset(
            voice_session_id=voice_session_id,
            owner_user_id=owner_user_id,
            object_key=object_key,
            media_type=media_type,
            size_bytes=len(audio_bytes),
            sha256=digest,
            retention_expires_at=utc_now() + timedelta(days=retention_days),
        )
    )


async def _record_voice_provider_event(
    session: AsyncSession,
    *,
    owner_user_id: str,
    voice_session_id: str | None,
    event_type: str,
    provider: str,
    model: str | None,
    status: str,
    latency_ms: int | None,
    trace_id: str,
    safe_metadata: dict[str, object],
    error_code: str | None = None,
) -> None:
    session.add(
        VoiceProviderEvent(
            voice_session_id=voice_session_id,
            owner_user_id=owner_user_id,
            event_type=event_type,
            provider=provider,
            model=model,
            status=status,
            latency_ms=latency_ms,
            trace_id=trace_id,
            error_code=error_code,
            safe_metadata=_safe_metadata(safe_metadata),
        )
    )


async def _load_voice_session(
    session: AsyncSession,
    owner_user_id: str,
    voice_session_id: str,
) -> VoiceSession:
    voice_session = await session.scalar(
        select(VoiceSession).where(
            VoiceSession.id == voice_session_id,
            VoiceSession.owner_user_id == owner_user_id,
        )
    )
    if voice_session is None:
        raise LookupError("Voice session not found.")
    return voice_session


async def _load_owner_conversation(
    session: AsyncSession,
    owner_user_id: str,
    conversation_id: str,
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_user_id == owner_user_id,
            Conversation.archived_at.is_(None),
        )
    )
    if conversation is None:
        raise LookupError("Conversation not found.")
    return conversation


def _effective_stt_model(config: VoiceSettings, settings: Settings) -> str:
    if config.stt_provider == "openai" and config.stt_model == settings.voice_stt_model:
        return settings.voice_openai_stt_model
    if config.stt_provider == "local-compatible" and config.stt_model == settings.voice_stt_model:
        return "whisper-1"
    return config.stt_model


def _effective_tts_model(config: VoiceSettings, settings: Settings) -> str:
    if config.tts_provider == "openai" and config.tts_model == settings.voice_tts_model:
        return settings.voice_openai_tts_model
    if config.tts_provider == "local-compatible" and config.tts_model == settings.voice_tts_model:
        return "tts-1"
    return config.tts_model


def _safe_metadata(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], redact_value(value, max_chars=600))


def _local_dummy_key(base_url: str | None) -> Any:
    if not base_url:
        return None
    from pydantic import SecretStr

    return SecretStr("local-speech")


def _stt_provider_value(value: object) -> SpeechToTextProviderName:
    if value in {"mock", "openai", "local-compatible"}:
        return value
    raise VoiceRequestError("unsupported_stt_provider", "Unsupported speech-to-text provider.", 422)


def _tts_provider_value(value: object) -> TextToSpeechProviderName:
    if value in {"browser", "mock", "openai", "local-compatible"}:
        return value
    raise VoiceRequestError("unsupported_tts_provider", "Unsupported text-to-speech provider.", 422)


def _bounded_int(value: object, minimum: int, maximum: int) -> int:
    if not isinstance(value, str | bytes | bytearray | int | float):
        raise VoiceRequestError(
            "invalid_voice_setting",
            "Voice setting must be an integer.",
            422,
        )
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise VoiceRequestError(
            "invalid_voice_setting",
            "Voice setting must be an integer.",
            422,
        ) from exc
    return max(minimum, min(maximum, number))


async def _not_cancelled() -> bool:
    return False
