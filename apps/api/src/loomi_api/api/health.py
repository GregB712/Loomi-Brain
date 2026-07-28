from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from loomi_api import __version__
from loomi_api.config import Settings
from loomi_api.db.session import ping_database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    service: str
    status: str
    version: str
    environment: str
    request_id: str
    trace_id: str
    checks: dict[str, str]


@router.get("/health/live", response_model=HealthResponse)
async def liveness(request: Request) -> HealthResponse:
    return _health_response(request, "live", checks={"api": "ok"})


@router.get("/health/ready", response_model=HealthResponse)
@router.get("/api/v1/health", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    engine = cast(AsyncEngine, request.app.state.db_engine)
    checks = {"api": "ok", "database": "ok"}
    health_status = "ready"
    try:
        await ping_database(engine)
    except Exception:
        checks["database"] = "unavailable"
        health_status = "not_ready"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return _health_response(request, health_status, checks=checks)


def _health_response(
    request: Request,
    health_status: str,
    *,
    checks: dict[str, str],
) -> HealthResponse:
    settings = cast(Settings, request.app.state.settings)
    return HealthResponse(
        service=settings.app_name,
        status=health_status,
        version=__version__,
        environment=settings.environment,
        request_id=str(request.state.request_id),
        trace_id=str(request.state.trace_id),
        checks=checks,
    )
