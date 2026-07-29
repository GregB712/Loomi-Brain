from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from loomi_api.auth.service import seed_owner
from loomi_api.config import Settings
from loomi_api.db.models import TelemetrySpan
from loomi_api.db.session import create_engine, create_sessionmaker
from loomi_api.db.testing import reset_database
from loomi_api.observability.redaction import (
    REDACTED,
    contains_unredacted_secret,
    redact_attributes,
    redact_headers,
    redact_query_string,
)
from loomi_api.observability.telemetry import record_span, should_sample


def test_redaction_removes_headers_queries_secrets_and_large_fields(api_settings: Settings) -> None:
    headers = redact_headers(
        {
            "authorization": "Bearer sk-should-not-leak-1234567890",
            "cookie": "loomi_session=secret",
            "content-type": "application/json",
        },
        max_chars=64,
    )
    query = redact_query_string("token=abc123&mode=hybrid&X-Amz-Signature=signed", max_chars=24)
    attributes = redact_attributes(
        {
            "trace_id": "trace-1",
            "authorization": "Bearer secret",
            "document_text": "unrestricted personal document text",
            "model": "mock",
            "error_code": "provider_api_key=SHOULD_NOT_LEAK",
            "path": "/api/v1/search",
            "run_id": "x" * 200,
        },
        max_chars=64,
    )

    assert headers["authorization"] == REDACTED
    assert headers["cookie"] == REDACTED
    assert headers["content-type"] == "application/json"
    assert "token=%5Bredacted%5D" in query
    assert "X-Amz-Signature=%5Bredacted%5D" in query
    assert "document_text" not in attributes
    assert attributes["error_code"] == f"provider_api_key={REDACTED}"
    assert str(attributes["run_id"]).endswith("...")
    assert not contains_unredacted_secret(attributes)
    assert should_sample(api_settings, "trace-1")


def test_exporter_outage_is_persisted_without_raising(api_settings: Settings) -> None:
    settings = api_settings.model_copy(
        update={
            "observability_exporter": "otlp_http",
            "observability_local_only": False,
            "observability_exporter_endpoint": "http://127.0.0.1:9/v1/traces",
            "observability_export_timeout_seconds": 0.05,
        }
    )

    spans = asyncio.run(_record_one_span(settings))

    assert spans[0].exporter_status == "failed"
    assert spans[0].exporter_error


def test_sampling_zero_drops_span(api_settings: Settings) -> None:
    settings = api_settings.model_copy(update={"observability_sample_rate": 0.0})

    spans = asyncio.run(_record_one_span(settings))

    assert spans == []


def test_observability_endpoints_require_owner_and_bound_date_range(
    seeded_client: TestClient,
) -> None:
    unauthenticated = seeded_client.get("/api/v1/observability/summary")
    assert unauthenticated.status_code == 401

    csrf_token = _login(seeded_client)
    assert csrf_token
    too_wide = seeded_client.get(
        "/api/v1/observability/summary?start=2026-01-01T00:00:00Z&end=2026-03-15T00:00:00Z"
    )
    assert too_wide.status_code == 400


def test_chat_flow_produces_sanitized_correlated_observability(
    seeded_client: TestClient,
    api_settings: Settings,
) -> None:
    csrf_token = _login(seeded_client)
    _upload_fixture(seeded_client, csrf_token)
    conversation_id = _create_conversation(seeded_client, csrf_token)

    response = seeded_client.post(
        f"/api/v1/conversations/{conversation_id}/responses/stream",
        headers={"x-csrf-token": csrf_token, "idempotency-key": "observability-chat"},
        json={
            "content": "What method does hybrid search use? api_key=SHOULD_NOT_LEAK",
            "mode": "hybrid",
            "provider": "mock",
            "debug": True,
        },
    )

    assert response.status_code == 200
    completed = _parse_sse(response.text)[-1]["data"]
    trace_id = str(completed["trace_id"])

    summary = seeded_client.get("/api/v1/observability/summary")
    retrieval = seeded_client.get("/api/v1/observability/retrieval")
    status_response = seeded_client.get("/api/v1/observability/status")

    assert summary.status_code == 200
    assert retrieval.status_code == 200
    assert status_response.status_code == 200
    assert summary.json()["telemetry"]["spans"] >= 1
    assert summary.json()["retrieval"]["by_mode"]
    assert status_response.json()["prompt_registry"]

    spans = asyncio.run(_load_spans(api_settings))
    serialized = json.dumps([span.attributes for span in spans], sort_keys=True)
    assert trace_id in {span.trace_id for span in spans}
    assert "SHOULD_NOT_LEAK" not in serialized
    assert "unrestricted personal document text" not in serialized
    assert any(span.name == "loomi.model.generation" for span in spans)
    model_span = next(span for span in spans if span.name == "loomi.model.generation")
    assert model_span.attributes["prompt_id"] == "grounded_chat"
    assert model_span.attributes["prompt_version"] == "1.0.0"


def test_agent_run_records_prompt_and_policy_spans(
    seeded_client: TestClient,
    api_settings: Settings,
) -> None:
    csrf_token = _login(seeded_client)
    response = seeded_client.post(
        "/api/v1/agent-runs",
        headers={"x-csrf-token": csrf_token, "idempotency-key": "observability-agent"},
        json={"owner_request": "Calculate 2 + 2 with api_key=SHOULD_NOT_LEAK."},
    )

    assert response.status_code == 202
    spans = asyncio.run(_load_spans(api_settings))
    serialized = json.dumps([span.attributes for span in spans], sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert any(
        span.name == "loomi.agent.state" and span.attributes.get("prompt_id") == "agent_runtime"
        for span in spans
    )
    assert any(span.name == "loomi.agent.tool_call" for span in spans)


async def _record_one_span(settings: Settings) -> list[TelemetrySpan]:
    await reset_database(settings)
    await _seed(settings)
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            await record_span(
                session,
                settings,
                name="loomi.test.span",
                component="api",
                trace_id="trace-outage",
                attributes={"path": "/api/v1/test", "error_code": "none"},
                commit=True,
            )
        async with sessionmaker() as session:
            return list(await session.scalars(select(TelemetrySpan)))
    finally:
        await engine.dispose()


async def _load_spans(settings: Settings) -> list[TelemetrySpan]:
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            return list(await session.scalars(select(TelemetrySpan)))
    finally:
        await engine.dispose()


async def _seed(settings: Settings) -> None:
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            await seed_owner(session, settings)
    finally:
        await engine.dispose()


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def _upload_fixture(client: TestClient, csrf_token: str) -> str:
    response = client.post(
        "/api/v1/documents/uploads",
        headers={"x-csrf-token": csrf_token},
        files={
            "files": (
                "phase5.md",
                b"Hybrid search combines lexical and semantic ranks with reciprocal rank fusion.",
                "text/markdown",
            )
        },
    )
    assert response.status_code == 202
    return str(response.json()["accepted"][0]["document_id"])


def _create_conversation(client: TestClient, csrf_token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers={"x-csrf-token": csrf_token},
        json={"title": "Phase 5"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw.strip().split("\n\n"):
        lines = block.splitlines()
        event_name = next(
            line.removeprefix("event: ").strip() for line in lines if line.startswith("event: ")
        )
        data = next(
            line.removeprefix("data: ").strip() for line in lines if line.startswith("data: ")
        )
        events.append({"event": event_name, "data": json.loads(data)})
    return events
