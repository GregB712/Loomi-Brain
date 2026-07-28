from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from loomi_api.api.dependencies import OwnerContext, get_settings_from_app
from loomi_api.model_gateway.providers import ProviderGateway

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


class ModelCapabilityPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    supports_streaming: bool
    supports_structured_output: bool
    supports_health_check: bool
    configured: bool
    notes: str | None = None


class ProviderHealthPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    ok: bool
    configured: bool
    latency_ms: int | None = None
    error_code: str | None = None


@router.get("/models", response_model=list[ModelCapabilityPayload])
async def list_models(request: Request, owner: OwnerContext) -> list[ModelCapabilityPayload]:
    del owner
    gateway = ProviderGateway(get_settings_from_app(request))
    return [
        ModelCapabilityPayload(
            provider=item.provider,
            model=item.model,
            supports_streaming=item.supports_streaming,
            supports_structured_output=item.supports_structured_output,
            supports_health_check=item.supports_health_check,
            configured=item.configured,
            notes=item.notes,
        )
        for item in gateway.capabilities()
    ]


@router.get("/health", response_model=list[ProviderHealthPayload])
async def provider_health(request: Request, owner: OwnerContext) -> list[ProviderHealthPayload]:
    del owner
    gateway = ProviderGateway(get_settings_from_app(request))
    health = []
    for capability in gateway.capabilities():
        item = await gateway.provider_for(capability.provider).health()
        health.append(
            ProviderHealthPayload(
                provider=item.provider,
                ok=item.ok,
                configured=item.configured,
                latency_ms=item.latency_ms,
                error_code=item.error_code,
            )
        )
    return health
