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

    owner_email: str = "owner@loomi.local"
    owner_name: str = "Loomi Owner"
    owner_password: SecretStr = SecretStr(DEFAULT_LOCAL_OWNER_PASSWORD)
    password_hash_iterations: int = 390_000

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
    extraction_engine: Literal["builtin", "docling"] = "builtin"
    scanner_mode: Literal["fake-clean", "fake-reject", "unavailable"] = "fake-clean"
    scanner_required: bool = False

    @model_validator(mode="after")
    def validate_auth_settings(self) -> Self:
        if self.environment == "production":
            if self.owner_password.get_secret_value() == DEFAULT_LOCAL_OWNER_PASSWORD:
                raise ValueError("LOOMI_OWNER_PASSWORD must be set in production")
            if not self.session_cookie_secure:
                raise ValueError("LOOMI_SESSION_COOKIE_SECURE must be true in production")
            if "*" in self.cors_origins:
                raise ValueError("LOOMI_CORS_ORIGINS must not contain '*' in production")
            if not self.scanner_required:
                raise ValueError("LOOMI_SCANNER_REQUIRED must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
