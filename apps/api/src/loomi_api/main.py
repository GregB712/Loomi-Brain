from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from loomi_api import __version__
from loomi_api.api import (
    agent_runs,
    auth,
    conversations,
    documents,
    feedback,
    health,
    ingestion_jobs,
    mcp,
    observability,
    providers,
    search,
)
from loomi_api.config import Settings, get_settings
from loomi_api.db.session import create_engine, create_sessionmaker
from loomi_api.logging import configure_logging
from loomi_api.middleware import RequestContextMiddleware
from loomi_api.problems import http_exception_handler, validation_exception_handler


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging()
    db_engine = create_engine(resolved_settings)
    db_sessionmaker = create_sessionmaker(db_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.db_engine = db_engine
        app.state.db_sessionmaker = db_sessionmaker
        try:
            yield
        finally:
            await db_engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = db_sessionmaker

    app.add_middleware(RequestContextMiddleware, settings=resolved_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "authorization",
            "content-type",
            "idempotency-key",
            resolved_settings.csrf_header_name,
            resolved_settings.request_id_header,
            resolved_settings.trace_id_header,
        ],
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(ingestion_jobs.router)
    app.include_router(search.router)
    app.include_router(conversations.router)
    app.include_router(agent_runs.router)
    app.include_router(mcp.router)
    app.include_router(providers.router)
    app.include_router(feedback.router)
    app.include_router(observability.router)

    return app


app = create_app()
