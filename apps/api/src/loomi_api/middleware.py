from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from loomi_api.config import Settings

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
        request_id = request.headers.get(self._settings.request_id_header) or str(uuid4())
        trace_id = request.headers.get(self._settings.trace_id_header) or request_id
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        response = await call_next(request)
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
        logger.info(
            "http.request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            request_id=request_id,
            trace_id=trace_id,
        )
        return response
