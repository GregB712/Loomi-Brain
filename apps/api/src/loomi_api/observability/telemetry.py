from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.config import Settings
from loomi_api.db.base import utc_now
from loomi_api.db.models import TelemetrySpan
from loomi_api.observability.redaction import redact_attributes, redact_value

logger = logging.getLogger(__name__)


def should_sample(settings: Settings, trace_id: str) -> bool:
    if not settings.observability_enabled:
        return False
    rate = max(0.0, min(settings.observability_sample_rate, 1.0))
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.sha256(trace_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket <= rate


def start_timer() -> float:
    return time.perf_counter()


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


async def record_span(
    session: AsyncSession,
    settings: Settings,
    *,
    name: str,
    component: str,
    trace_id: str | None,
    owner_user_id: str | None = None,
    parent_span_id: str | None = None,
    kind: str = "internal",
    status: str = "ok",
    attributes: dict[str, Any] | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    commit: bool = False,
) -> str | None:
    resolved_trace_id = trace_id or str(uuid4())
    if not should_sample(settings, resolved_trace_id):
        return None
    now = utc_now()
    safe_attributes = redact_attributes(
        {
            "component": component,
            "trace_id": resolved_trace_id,
            **(attributes or {}),
        },
        max_chars=settings.observability_max_field_chars,
    )
    span = TelemetrySpan(
        owner_user_id=owner_user_id,
        trace_id=resolved_trace_id,
        span_id=uuid4().hex[:16],
        parent_span_id=parent_span_id,
        name=name,
        component=component,
        kind=kind,
        status=status,
        attributes=safe_attributes,
        started_at=started_at or now,
        ended_at=ended_at or now,
        duration_ms=max(duration_ms or 0, 0),
        error_code=error_code,
        sampled=True,
        exporter_status="not_exported",
    )
    try:
        session.add(span)
        await session.flush()
        export_status, export_error = await _export_span(settings, span)
        span.exporter_status = export_status
        span.exporter_error = export_error
        if commit:
            await session.commit()
        return span.span_id
    except Exception as exc:  # pragma: no cover - observability must not break product flow
        logger.info("telemetry.record_failed", extra={"error": str(exc), "span_name": name})
        if commit:
            await session.rollback()
        return None


def serialize_span(span: TelemetrySpan, settings: Settings) -> dict[str, Any]:
    trace_url = None
    if settings.observability_trace_base_url:
        trace_url = f"{settings.observability_trace_base_url.rstrip('/')}/trace/{span.trace_id}"
    return {
        "id": span.id,
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "component": span.component,
        "kind": span.kind,
        "status": span.status,
        "attributes": span.attributes or {},
        "duration_ms": span.duration_ms,
        "error_code": span.error_code,
        "sampled": span.sampled,
        "exporter_status": span.exporter_status,
        "exporter_error": span.exporter_error,
        "started_at": span.started_at.isoformat(),
        "ended_at": span.ended_at.isoformat(),
        "trace_url": trace_url,
    }


async def _export_span(settings: Settings, span: TelemetrySpan) -> tuple[str, str | None]:
    if not settings.observability_enabled:
        return ("disabled", None)
    if settings.observability_exporter == "none":
        return ("disabled", None)
    payload = _export_payload(span)
    if settings.observability_exporter == "local_file":
        await asyncio.to_thread(_append_jsonl, settings.storage_root, payload)
        return ("stored_local", None)
    if settings.observability_local_only:
        return ("local_only", None)
    if not settings.observability_exporter_endpoint:
        return ("missing_endpoint", None)
    try:
        await asyncio.to_thread(_post_payload, settings, payload)
        return ("sent", None)
    except (HTTPError, TimeoutError, URLError, OSError) as exc:
        return ("failed", str(redact_value(str(exc), max_chars=180)))


def _export_payload(span: TelemetrySpan) -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": "loomi-api"}]},
                "scopeSpans": [
                    {
                        "scope": {"name": "loomi.observability"},
                        "spans": [
                            {
                                "traceId": span.trace_id,
                                "spanId": span.span_id,
                                "parentSpanId": span.parent_span_id,
                                "name": span.name,
                                "kind": span.kind,
                                "status": span.status,
                                "attributes": span.attributes or {},
                                "startTimeUnixNano": _unix_nano(span.started_at),
                                "endTimeUnixNano": _unix_nano(span.ended_at),
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _append_jsonl(storage_root: Path, payload: dict[str, Any]) -> None:
    output_path = storage_root / "observability" / "telemetry.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _post_payload(settings: Settings, payload: dict[str, Any]) -> None:
    assert settings.observability_exporter_endpoint is not None
    headers = {"content-type": "application/json"}
    if (
        settings.observability_exporter == "langfuse_otlp"
        and settings.observability_langfuse_public_key is not None
        and settings.observability_langfuse_secret_key is not None
    ):
        username = settings.observability_langfuse_public_key.get_secret_value()
        password = settings.observability_langfuse_secret_key.get_secret_value()
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["authorization"] = f"Basic {token}"
    request = Request(  # noqa: S310
        settings.observability_exporter_endpoint,
        data=json.dumps(payload, sort_keys=True, default=str).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=settings.observability_export_timeout_seconds) as response:  # noqa: S310
        response.read()


def _unix_nano(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)
