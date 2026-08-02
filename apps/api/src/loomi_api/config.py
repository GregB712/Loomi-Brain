from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_LOCAL_OWNER_PASSWORD = "loomi-local-owner-password"  # noqa: S105


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="LOOMI_", extra="ignore")

    app_name: str = "Loomi-Brain API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://loomi:loomi_dev_password@127.0.0.1:15432/loomi_brain"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    request_id_header: str = "x-request-id"
    trace_id_header: str = "x-trace-id"
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "testserver"]
    )
    csp_policy: str = (
        "default-src 'self'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "form-action 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    max_request_bytes: int = 20 * 1024 * 1024

    owner_email: str = "owner@loomi.local"
    owner_name: str = "Loomi Owner"
    owner_password: SecretStr = SecretStr(DEFAULT_LOCAL_OWNER_PASSWORD)
    password_hash_iterations: int = 390_000
    auth_login_rate_limit_attempts: int = 8
    auth_login_rate_limit_window_seconds: int = 300

    session_cookie_name: str = "loomi_session"
    csrf_cookie_name: str = "loomi_csrf"
    csrf_header_name: str = "x-csrf-token"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_minutes: int = 60 * 24 * 7

    storage_root: Path = Path("var/private-objects")
    max_upload_bytes: int = 15 * 1024 * 1024
    max_upload_files: int = 8
    max_parser_output_chars: int = 250_000
    max_archive_entries: int = 200
    max_archive_uncompressed_bytes: int = 40 * 1024 * 1024
    max_pdf_pages: int = 80
    max_image_pixels: int = 24_000_000
    max_chunks_per_document: int = 500
    chunk_target_chars: int = 1_400
    chunk_overlap_chars: int = 180
    embedding_dimensions: int = 16
    embedding_model: str = "loomi-deterministic-embedding-v1"
    chat_provider: Literal["mock", "openai-compatible", "openai", "anthropic", "gemini", "vllm"] = (
        "mock"
    )
    chat_model: str = "loomi-mock-cited-chat-v1"
    openai_compatible_base_url: str | None = None
    openai_compatible_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    vllm_base_url: str | None = None
    model_request_timeout_seconds: float = 30.0
    model_max_retries: int = 2
    model_max_input_tokens: int = 6000
    model_max_output_tokens: int = 800
    model_max_estimated_cost_usd: float = 0.25
    voice_stt_provider: Literal["mock", "openai", "local-compatible"] = "mock"
    voice_stt_model: str = "loomi-mock-transcribe-v1"
    voice_tts_provider: Literal["browser", "mock", "openai", "local-compatible"] = "browser"
    voice_tts_model: str = "loomi-browser-speech-synthesis"
    voice_tts_voice: str = "alloy"
    voice_language: str = "en"
    voice_max_recording_seconds: int = 60
    voice_max_audio_bytes: int = 5 * 1024 * 1024
    voice_transcript_review_enabled: bool = True
    voice_auto_speak_assistant: bool = False
    voice_retain_raw_audio: bool = False
    voice_retention_days: int = 0
    voice_demo_mode: bool = True
    voice_cloud_enabled: bool = False
    voice_mock_transcript: str = "What method does hybrid search use?"
    voice_openai_stt_model: str = "gpt-4o-mini-transcribe"
    voice_openai_tts_model: str = "gpt-4o-mini-tts"
    voice_local_stt_base_url: str | None = None
    voice_local_tts_base_url: str | None = None
    voice_local_api_key: SecretStr | None = None
    voice_rate_limit_attempts: int = 20
    voice_rate_limit_window_seconds: int = 60
    voice_tts_max_chars: int = 4096
    voice_tts_max_audio_bytes: int = 6 * 1024 * 1024
    extraction_engine: Literal["builtin", "docling"] = "builtin"
    scanner_mode: Literal["fake-clean", "fake-reject", "unavailable"] = "fake-clean"
    scanner_required: bool = False
    observability_enabled: bool = True
    observability_exporter: Literal["none", "local_file", "otlp_http", "langfuse_otlp"] = (
        "local_file"
    )
    observability_exporter_endpoint: str | None = None
    observability_trace_base_url: str | None = None
    observability_langfuse_public_key: SecretStr | None = None
    observability_langfuse_secret_key: SecretStr | None = None
    observability_local_only: bool = True
    observability_sample_rate: float = 1.0
    observability_content_capture: Literal["none", "metadata", "redacted"] = "none"
    observability_max_field_chars: int = 600
    observability_retention_days: int = 14
    observability_export_timeout_seconds: float = 0.4
    mcp_enabled: bool = True
    mcp_allow_private_networks: bool = False
    mcp_default_connection_timeout_seconds: int = 5
    mcp_default_tool_timeout_seconds: int = 10
    mcp_default_output_size_limit: int = 12_000
    mcp_max_stdio_stdout_bytes: int = 128_000
    mcp_max_stdio_stderr_bytes: int = 32_000

    @model_validator(mode="after")
    def validate_auth_settings(self) -> Self:
        if self.max_request_bytes < self.max_upload_bytes:
            raise ValueError("LOOMI_MAX_REQUEST_BYTES must be >= LOOMI_MAX_UPLOAD_BYTES")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None cookies require LOOMI_SESSION_COOKIE_SECURE=true")
        if self.auth_login_rate_limit_attempts < 1:
            raise ValueError("LOOMI_AUTH_LOGIN_RATE_LIMIT_ATTEMPTS must be >= 1")
        if self.auth_login_rate_limit_window_seconds < 1:
            raise ValueError("LOOMI_AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS must be >= 1")
        if self.voice_max_recording_seconds < 1:
            raise ValueError("LOOMI_VOICE_MAX_RECORDING_SECONDS must be >= 1")
        if self.voice_max_audio_bytes < 1024:
            raise ValueError("LOOMI_VOICE_MAX_AUDIO_BYTES must be >= 1024")
        if self.voice_rate_limit_attempts < 1:
            raise ValueError("LOOMI_VOICE_RATE_LIMIT_ATTEMPTS must be >= 1")
        if self.voice_rate_limit_window_seconds < 1:
            raise ValueError("LOOMI_VOICE_RATE_LIMIT_WINDOW_SECONDS must be >= 1")
        if self.voice_tts_max_chars < 1 or self.voice_tts_max_chars > 4096:
            raise ValueError("LOOMI_VOICE_TTS_MAX_CHARS must be between 1 and 4096")
        if self.voice_retain_raw_audio and self.voice_retention_days < 1:
            raise ValueError("LOOMI_VOICE_RETENTION_DAYS must be >= 1 when audio retention is on")
        if self.environment == "production":
            if self.owner_password.get_secret_value() == DEFAULT_LOCAL_OWNER_PASSWORD:
                raise ValueError("LOOMI_OWNER_PASSWORD must be set in production")
            if not self.session_cookie_secure:
                raise ValueError("LOOMI_SESSION_COOKIE_SECURE must be true in production")
            if "*" in self.cors_origins:
                raise ValueError("LOOMI_CORS_ORIGINS must not contain '*' in production")
            if "*" in self.trusted_hosts:
                raise ValueError("LOOMI_TRUSTED_HOSTS must not contain '*' in production")
            if not self.scanner_required:
                raise ValueError("LOOMI_SCANNER_REQUIRED must be true in production")
            if self.observability_content_capture != "none":
                raise ValueError("LOOMI_OBSERVABILITY_CONTENT_CAPTURE must be 'none' in production")
            if self.observability_sample_rate > 0.25:
                raise ValueError("LOOMI_OBSERVABILITY_SAMPLE_RATE must be <= 0.25 in production")
            if not self.observability_local_only and self.observability_exporter == "local_file":
                raise ValueError("External production observability needs an external exporter")
            if self.mcp_allow_private_networks:
                raise ValueError("LOOMI_MCP_ALLOW_PRIVATE_NETWORKS must be false in production")
            if self.voice_retain_raw_audio and self.voice_retention_days < 1:
                raise ValueError("Raw voice audio retention requires a positive retention window")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
