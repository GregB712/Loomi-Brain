from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

import structlog
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from loomi_api.config import Settings
from loomi_api.observability.telemetry import elapsed_ms, record_span, start_timer

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = start_timer()
        request_id = request.headers.get(self._settings.request_id_header) or str(uuid4())
        trace_id = request.headers.get(self._settings.trace_id_header) or request_id
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
        except Exception:
            await self._record_request_span(
                request,
                request_id=request_id,
                trace_id=trace_id,
                status_code=500,
                duration_ms=elapsed_ms(started),
                error_code="unhandled_exception",
            )
            raise
        response.headers[self._settings.request_id_header] = request_id
        response.headers[self._settings.trace_id_header] = trace_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        if self._settings.environment == "production":
            response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        duration_ms = elapsed_ms(started)
        logger.info(
            "http.request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            request_id=request_id,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )
        await self._record_request_span(
            request,
            request_id=request_id,
            trace_id=trace_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
            error_code=None if response.status_code < 500 else "server_error",
        )
        return response

    async def _record_request_span(
        self,
        request: Request,
        *,
        request_id: str,
        trace_id: str,
        status_code: int,
        duration_ms: int,
        error_code: str | None,
    ) -> None:
        sessionmaker = cast(
            async_sessionmaker[AsyncSession] | None,
            getattr(request.app.state, "db_sessionmaker", None),
        )
        if sessionmaker is None:
            return
        try:
            async with sessionmaker() as session:
                await record_span(
                    session,
                    self._settings,
                    name="loomi.http.request",
                    component="api",
                    trace_id=trace_id,
                    kind="server",
                    status="error" if status_code >= 500 else "ok",
                    duration_ms=duration_ms,
                    error_code=error_code,
                    attributes={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "request_id": request_id,
                        "trace_id": trace_id,
                    },
                    commit=True,
                )
        except Exception:
            logger.info("http.telemetry_failed", request_id=request_id, trace_id=trace_id)
