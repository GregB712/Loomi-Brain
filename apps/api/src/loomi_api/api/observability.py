from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.api.dependencies import DbSession, OwnerContext, get_settings_from_app
from loomi_api.db.base import utc_now
from loomi_api.db.models import (
    AgentRun,
    Approval,
    EvaluationRun,
    IngestionJob,
    TelemetrySpan,
    ToolCall,
    UserFeedback,
)
from loomi_api.evaluation.run import build_report
from loomi_api.observability.prompts import prompt_registry_payload
from loomi_api.observability.telemetry import serialize_span, should_sample

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

MAX_RANGE_DAYS = 31
DEFAULT_RANGE_DAYS = 7
DateQuery = Annotated[datetime | None, Query()]
RunKindQuery = Annotated[str | None, Query(max_length=40)]
Limit25Query = Annotated[int, Query(ge=1, le=100)]
Limit50Query = Annotated[int, Query(ge=1, le=100)]
Limit100Query = Annotated[int, Query(ge=1, le=100)]
OffsetQuery = Annotated[int, Query(ge=0)]


@router.get("/status")
async def observability_status(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    settings = get_settings_from_app(request)
    latest_span = await session.scalar(
        select(TelemetrySpan)
        .where(
            (TelemetrySpan.owner_user_id == owner.user.id) | TelemetrySpan.owner_user_id.is_(None)
        )
        .order_by(desc(TelemetrySpan.created_at))
        .limit(1)
    )
    return {
        "enabled": settings.observability_enabled,
        "exporter": settings.observability_exporter,
        "local_only": settings.observability_local_only,
        "content_capture": settings.observability_content_capture,
        "sample_rate": settings.observability_sample_rate,
        "retention_days": settings.observability_retention_days,
        "sampling_preview": should_sample(settings, str(getattr(request.state, "trace_id", ""))),
        "latest_exporter_status": latest_span.exporter_status if latest_span else None,
        "latest_exporter_error": latest_span.exporter_error if latest_span else None,
        "prompt_registry": prompt_registry_payload(),
    }


@router.get("/summary")
async def observability_summary(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    start: DateQuery = None,
    end: DateQuery = None,
) -> dict[str, Any]:
    settings = get_settings_from_app(request)
    start_at, end_at = _bounded_range(start, end)
    spans = await _load_spans(session, owner.user.id, start_at, end_at, limit=1000)
    runs = await _load_runs(session, owner.user.id, start_at, end_at, limit=1000)
    ingestion_jobs = list(
        await session.scalars(
            select(IngestionJob)
            .where(
                IngestionJob.owner_user_id == owner.user.id,
                IngestionJob.created_at >= start_at,
                IngestionJob.created_at <= end_at,
            )
            .order_by(desc(IngestionJob.created_at))
            .limit(1000)
        )
    )
    tool_calls = list(
        await session.scalars(
            select(ToolCall)
            .where(
                ToolCall.owner_user_id == owner.user.id,
                ToolCall.created_at >= start_at,
                ToolCall.created_at <= end_at,
            )
            .limit(1000)
        )
    )
    approvals = list(
        await session.scalars(
            select(Approval)
            .where(
                Approval.owner_user_id == owner.user.id,
                Approval.created_at >= start_at,
                Approval.created_at <= end_at,
            )
            .limit(1000)
        )
    )
    durations = [span.duration_ms for span in spans if span.duration_ms is not None]
    error_spans = [span for span in spans if span.status == "error"]
    usage = _usage_totals(runs)
    return {
        "range": {"start": start_at.isoformat(), "end": end_at.isoformat()},
        "telemetry": {
            "enabled": settings.observability_enabled,
            "exporter": settings.observability_exporter,
            "local_only": settings.observability_local_only,
            "content_capture": settings.observability_content_capture,
            "sample_rate": settings.observability_sample_rate,
            "retention_days": settings.observability_retention_days,
            "spans": len(spans),
            "error_spans": len(error_spans),
            "latency_p50_ms": _percentile(durations, 50),
            "latency_p95_ms": _percentile(durations, 95),
            "exporter_status": _count_by(span.exporter_status for span in spans),
        },
        "runs": {
            "total": len(runs),
            "by_state": _count_by(run.state for run in runs),
            "success_rate": _success_rate(runs),
            "error_rate": _error_rate(runs),
            "recent": [_run_summary(run, settings) for run in runs[:8]],
        },
        "model_usage": usage,
        "providers": _provider_breakdown(runs),
        "retrieval": _retrieval_summary(spans),
        "ingestion": {
            "total": len(ingestion_jobs),
            "by_status": _count_by(job.status for job in ingestion_jobs),
            "chunks": sum(
                int((job.metrics or {}).get("chunk_count") or 0) for job in ingestion_jobs
            ),
            "embeddings": sum(
                int((job.metrics or {}).get("embedding_count") or 0) for job in ingestion_jobs
            ),
        },
        "tools": {
            "total": len(tool_calls),
            "by_status": _count_by(tool.status for tool in tool_calls),
            "by_risk": _count_by(tool.risk_class for tool in tool_calls),
        },
        "approvals": {
            "total": len(approvals),
            "by_status": _count_by(approval.status for approval in approvals),
        },
        "evaluation": build_report()["regression_summary"],
    }


@router.get("/runs")
async def recent_runs(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    start: DateQuery = None,
    end: DateQuery = None,
    run_kind: RunKindQuery = None,
    limit: Limit100Query = 30,
    offset: OffsetQuery = 0,
) -> dict[str, Any]:
    settings = get_settings_from_app(request)
    start_at, end_at = _bounded_range(start, end)
    stmt = select(AgentRun).where(
        AgentRun.owner_user_id == owner.user.id,
        AgentRun.created_at >= start_at,
        AgentRun.created_at <= end_at,
    )
    if run_kind:
        stmt = stmt.where(AgentRun.run_kind == run_kind)
    rows = list(
        await session.scalars(stmt.order_by(desc(AgentRun.created_at)).offset(offset).limit(limit))
    )
    return {
        "items": [_run_summary(run, settings) for run in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/model-usage")
async def model_usage(
    session: DbSession,
    owner: OwnerContext,
    start: DateQuery = None,
    end: DateQuery = None,
) -> dict[str, Any]:
    start_at, end_at = _bounded_range(start, end)
    runs = await _load_runs(session, owner.user.id, start_at, end_at, limit=2000)
    return {"totals": _usage_totals(runs), "breakdown": _provider_breakdown(runs)}


@router.get("/retrieval")
async def retrieval_metrics(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    start: DateQuery = None,
    end: DateQuery = None,
    limit: Limit50Query = 50,
) -> dict[str, Any]:
    settings = get_settings_from_app(request)
    start_at, end_at = _bounded_range(start, end)
    spans = [
        span
        for span in await _load_spans(session, owner.user.id, start_at, end_at, limit=1000)
        if span.component == "retrieval"
    ]
    recent = sorted(spans, key=lambda item: item.created_at, reverse=True)[:limit]
    return {
        "summary": _retrieval_summary(spans),
        "recent_spans": [serialize_span(span, settings) for span in recent],
    }


@router.get("/evaluations")
async def evaluation_history(
    session: DbSession,
    owner: OwnerContext,
    start: DateQuery = None,
    end: DateQuery = None,
    limit: Limit25Query = 25,
) -> dict[str, Any]:
    start_at, end_at = _bounded_range(start, end)
    rows = list(
        await session.scalars(
            select(EvaluationRun)
            .where(
                EvaluationRun.owner_user_id == owner.user.id,
                EvaluationRun.created_at >= start_at,
                EvaluationRun.created_at <= end_at,
            )
            .order_by(desc(EvaluationRun.created_at))
            .limit(limit)
        )
    )
    report = build_report()
    return {
        "current_synthetic_report": report,
        "items": [
            {
                "id": row.id,
                "status": row.status,
                "run_kind": row.run_kind,
                "baseline_name": row.baseline_name,
                "regression_count": row.regression_count,
                "metrics": row.metrics or {},
                "created_at": row.created_at.isoformat(),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in rows
        ],
    }


@router.get("/feedback")
async def feedback_summary(
    session: DbSession,
    owner: OwnerContext,
    start: DateQuery = None,
    end: DateQuery = None,
    limit: Limit50Query = 50,
) -> dict[str, Any]:
    start_at, end_at = _bounded_range(start, end)
    rows = list(
        await session.scalars(
            select(UserFeedback)
            .where(
                UserFeedback.owner_user_id == owner.user.id,
                UserFeedback.created_at >= start_at,
                UserFeedback.created_at <= end_at,
            )
            .order_by(desc(UserFeedback.created_at))
            .limit(limit)
        )
    )
    return {
        "total": len(rows),
        "by_rating": _count_by(str(row.rating) for row in rows),
        "items": [
            {
                "id": row.id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "rating": row.rating,
                "comment_chars": len(row.comment or ""),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


def _bounded_range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    resolved_end = _aware(end) if end else utc_now()
    resolved_start = _aware(start) if start else resolved_end - timedelta(days=DEFAULT_RANGE_DAYS)
    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be before end.",
        )
    if resolved_end - resolved_start > timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Date range cannot exceed {MAX_RANGE_DAYS} days.",
        )
    return resolved_start, resolved_end


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _load_spans(
    session: AsyncSession,
    owner_user_id: str,
    start_at: datetime,
    end_at: datetime,
    *,
    limit: int,
) -> list[TelemetrySpan]:
    return list(
        await session.scalars(
            select(TelemetrySpan)
            .where(
                (
                    (TelemetrySpan.owner_user_id == owner_user_id)
                    | TelemetrySpan.owner_user_id.is_(None)
                ),
                TelemetrySpan.created_at >= start_at,
                TelemetrySpan.created_at <= end_at,
            )
            .order_by(desc(TelemetrySpan.created_at))
            .limit(limit)
        )
    )


async def _load_runs(
    session: AsyncSession,
    owner_user_id: str,
    start_at: datetime,
    end_at: datetime,
    *,
    limit: int,
) -> list[AgentRun]:
    return list(
        await session.scalars(
            select(AgentRun)
            .where(
                AgentRun.owner_user_id == owner_user_id,
                AgentRun.created_at >= start_at,
                AgentRun.created_at <= end_at,
            )
            .order_by(desc(AgentRun.created_at))
            .limit(limit)
        )
    )


def _run_summary(run: AgentRun, settings: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "run_kind": run.run_kind,
        "state": run.state,
        "status_reason": run.status_reason,
        "provider": run.provider,
        "model": run.model,
        "usage": run.usage or {},
        "latency_ms": run.latency_ms,
        "trace_id": run.trace_id,
        "trace_url": _trace_url(settings, run.trace_id),
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _trace_url(settings: Any, trace_id: str | None) -> str | None:
    if not trace_id or not settings.observability_trace_base_url:
        return None
    return f"{settings.observability_trace_base_url.rstrip('/')}/trace/{trace_id}"


def _usage_totals(runs: Iterable[AgentRun]) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_cost_usd = 0.0
    for run in runs:
        usage = run.usage or {}
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        total_tokens += int(usage.get("total_tokens") or 0)
        estimated_cost_usd += float(usage.get("estimated_cost_usd") or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 6),
    }


def _provider_breakdown(runs: Iterable[AgentRun]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        key = (run.provider or "unknown", run.model or "unknown")
        item = grouped.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "runs": 0,
                "tokens": 0,
                "estimated_cost_usd": 0.0,
                "latency_values": [],
            },
        )
        item["runs"] += 1
        item["tokens"] += int((run.usage or {}).get("total_tokens") or 0)
        item["estimated_cost_usd"] += float((run.usage or {}).get("estimated_cost_usd") or 0)
        if run.latency_ms is not None:
            item["latency_values"].append(run.latency_ms)
    output: list[dict[str, Any]] = []
    for item in grouped.values():
        latencies = cast(list[int], item.pop("latency_values"))
        item["estimated_cost_usd"] = round(float(item["estimated_cost_usd"]), 6)
        item["latency_p95_ms"] = _percentile(latencies, 95)
        output.append(item)
    return sorted(output, key=lambda item: str(item["provider"]))


def _retrieval_summary(spans: Iterable[TelemetrySpan]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for span in spans:
        if span.name != "loomi.retrieval.search":
            continue
        mode = str((span.attributes or {}).get("mode") or "unknown")
        item = grouped.setdefault(
            mode,
            {
                "mode": mode,
                "runs": 0,
                "total_candidates": 0,
                "selected_context": 0,
                "warnings": 0,
                "latency_values": [],
            },
        )
        item["runs"] += 1
        item["total_candidates"] += int((span.attributes or {}).get("total") or 0)
        item["selected_context"] += int((span.attributes or {}).get("selected_context_count") or 0)
        item["warnings"] += int((span.attributes or {}).get("warning_count") or 0)
        item["latency_values"].append(span.duration_ms)
    by_mode: list[dict[str, Any]] = []
    for item in grouped.values():
        latencies = cast(list[int], item.pop("latency_values"))
        runs = max(int(item["runs"]), 1)
        item["avg_candidates"] = round(int(item["total_candidates"]) / runs, 2)
        item["avg_selected_context"] = round(int(item["selected_context"]) / runs, 2)
        item["latency_p95_ms"] = _percentile(latencies, 95)
        by_mode.append(item)
    return {"by_mode": sorted(by_mode, key=lambda item: str(item["mode"]))}


def _count_by(values: Iterable[str]) -> dict[str, int]:
    output: dict[str, int] = {}
    for value in values:
        output[str(value)] = output.get(str(value), 0) + 1
    return output


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round(((len(ordered) - 1) * percentile) / 100)
    return ordered[index]


def _success_rate(runs: list[AgentRun]) -> float:
    if not runs:
        return 0.0
    successes = len([run for run in runs if run.state in {"complete", "completed"}])
    return round(successes / len(runs), 4)


def _error_rate(runs: list[AgentRun]) -> float:
    if not runs:
        return 0.0
    failures = len([run for run in runs if run.state == "failed"])
    return round(failures / len(runs), 4)
