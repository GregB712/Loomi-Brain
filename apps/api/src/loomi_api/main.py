from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from loomi_api import __version__
from loomi_api.config import Settings, get_settings
from loomi_api.logging import configure_logging
from loomi_api.middleware import RequestContextMiddleware


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    service: str
    status: str
    version: str
    environment: str
    request_id: str


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware, settings=resolved_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", resolved_settings.request_id_header],
    )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness(request: Request) -> HealthResponse:
        return _health_response(request, resolved_settings, "live")

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness(request: Request) -> HealthResponse:
        return _health_response(request, resolved_settings, "ready")

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    async def api_health(request: Request) -> HealthResponse:
        return _health_response(request, resolved_settings, "ready")

    return app


def _health_response(request: Request, settings: Settings, status: str) -> HealthResponse:
    return HealthResponse(
        service=settings.app_name,
        status=status,
        version=__version__,
        environment=settings.environment,
        request_id=str(request.state.request_id),
    )


app = create_app()
