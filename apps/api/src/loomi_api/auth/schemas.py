from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class OwnerResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    display_name: str


class SessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    created_at: datetime
    expires_at: datetime
    current: bool


class LoginResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner: OwnerResponse
    csrf_token: str
