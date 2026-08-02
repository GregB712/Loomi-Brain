from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from loomi_api.config import Settings
from loomi_api.observability.telemetry import elapsed_ms, record_span, start_timer
from loomi_api.problems import problem_response

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
        rejected_response = self._reject_oversized_request(request)
        if rejected_response is not None:
            self._apply_security_headers(rejected_response)
            rejected_response.headers[self._settings.request_id_header] = request_id
            rejected_response.headers[self._settings.trace_id_header] = trace_id
            return rejected_response
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
        self._apply_security_headers(response)
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

    def _reject_oversized_request(self, request: Request) -> JSONResponse | None:
        content_length = request.headers.get("content-length")
        if content_length is None:
            return None
        try:
            request_bytes = int(content_length)
        except ValueError:
            return None
        if request_bytes <= self._settings.max_request_bytes:
            return None
        return problem_response(
            request,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            title="Payload Too Large",
            detail="The request body exceeds the configured size limit.",
            code="payload_too_large",
        )

    def _apply_security_headers(self, response: Response) -> None:
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = (
            "camera=(), microphone=(self), geolocation=(), payment=()"
        )
        response.headers["content-security-policy"] = self._settings.csp_policy
        if self._settings.environment == "production":
            response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"

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
