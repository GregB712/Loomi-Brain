from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": f"https://loomi.local/problems/{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
        "trace_id": getattr(request.state, "trace_id", None),
    }
    if errors is not None:
        payload["errors"] = errors
    return JSONResponse(payload, status_code=status_code)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    code = _code_for_status(exc.status_code)
    return problem_response(
        request,
        status_code=exc.status_code,
        title=_title_for_status(exc.status_code),
        detail=detail,
        code=code,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": str(error["msg"]),
            "type": str(error["type"]),
        }
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status_code=422,
        title="Validation Error",
        detail="The request payload or parameters are invalid.",
        code="validation_error",
        errors=errors,
    )


def _title_for_status(status_code: int) -> str:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        413: "Payload Too Large",
        429: "Too Many Requests",
        422: "Validation Error",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }
    return titles.get(status_code, "Request Failed")


def _code_for_status(status_code: int) -> str:
    codes = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        429: "rate_limited",
        422: "validation_error",
        500: "internal_error",
        503: "service_unavailable",
    }
    return codes.get(status_code, "request_failed")
