from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="LOOMI_", extra="ignore")

    app_name: str = "Loomi-Brain API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    request_id_header: str = "x-request-id"


@lru_cache
def get_settings() -> Settings:
    return Settings()
