from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.agent_runtime.contracts import (
    AgentRunLimits,
    AgentRunRequest,
    AgentState,
    PlannedToolCall,
    Tool,
    ToolContext,
    ToolExecutionError,
    ToolResult,
)
from loomi_api.agent_runtime.policy import (
    POLICY_VERSION,
    PolicyError,
    approval_required,
    canonical_tool_args_hash,
    forbidden_tool_request,
    policy_decision,
    sanitize_value,
    truncate_json_payload,
    validate_tool_args,
)
from loomi_api.agent_runtime.state_machine import is_terminal, validate_transition
from loomi_api.agent_runtime.tools import ToolRegistry, default_tool_registry
from loomi_api.config import Settings
from loomi_api.db.base import new_id, utc_now
from loomi_api.db.models import AgentEvent, AgentRun, Approval, AuditEvent, ToolCall
from loomi_api.mcp_client.protocol import MCP_TOOL_ID_PREFIX, MCPClientError, parse_mcp_tool_id
from loomi_api.mcp_client.tools import load_mcp_tool
from loomi_api.observability.prompts import get_prompt
from loomi_api.observability.telemetry import record_span
from loomi_api.retrieval.contracts import ContextItem, RetrievalQuery, SearchFilters
from loomi_api.retrieval.service import RetrievalService

DEFAULT_ALLOWED_TOOLS: tuple[str, ...] = (
    "knowledge.search",
    "knowledge.get_document_metadata",
    "knowledge.get_source_excerpt",
    "calculator",
    "notes.create_draft",
)


@dataclass
class _RunWork:
    run: AgentRun
    request: AgentRunRequest
    intent: str = "search"
    context: tuple[ContextItem, ...] = ()
    planned_tool: PlannedToolCall | None = None
    tool: Tool | None = None
    tool_call: ToolCall | None = None
    execution_args: dict[str, Any] | None = None
    tool_result: ToolResult | None = None
    answer_text: str = ""
    citations: tuple[ContextItem, ...] = ()
    warnings: list[str] | None = None


class AgentRuntimeService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.registry = registry or default_tool_registry()

    async def start(self, request: AgentRunRequest) -> dict[str, Any]:
        existing = await self._load_idempotent_run(request)
        if existing is not None:
            return await self.detail(request.owner_user_id, existing.id)

        prompt = get_prompt("agent_runtime")
        run = AgentRun(
            id=_deterministic_run_id(request.owner_user_id, request.idempotency_key),
            owner_user_id=request.owner_user_id,
            state="receive_request",
            idempotency_key=request.idempotency_key,
            trace_id=request.trace_id,
            budget={"policy_version": POLICY_VERSION},
            run_kind=request.run_kind,
            status_reason="started",
            owner_request=cast(str, sanitize_value(request.owner_request, string_limit=5000)),
            provider=request.provider or self.settings.chat_provider,
            model=request.model or "loomi-deterministic-agent-runtime-v1",
            allowed_tools=list(request.allowed_tools or DEFAULT_ALLOWED_TOOLS),
            limits=request.limits.as_dict(),
            usage={},
            sanitized_input={
                "owner_request": sanitize_value(request.owner_request, string_limit=5000),
                "request_id": request.request_id,
                "trace_id": request.trace_id,
            },
            retry_count=0,
            started_at=utc_now(),
            trace_metadata={
                **request.trace_metadata,
                "step_count": 1,
                "tool_call_count": 0,
                "events": [],
                "prompt_id": prompt.stable_id,
                "prompt_version": prompt.version,
            },
        )
        self.session.add(run)
        await self.session.flush()
        await self._event(
            run,
            "receive_request",
            {
                "state": "receive_request",
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "allowed_tools": run.allowed_tools,
                "limits": run.limits,
            },
        )
        await self._audit(
            run,
            "agent.run_started",
            {"idempotency_key": request.idempotency_key, "state": run.state},
        )
        await self.session.commit()

        initial_failure = self._initial_budget_failure(run, request.limits)
        if initial_failure is not None:
            await self._fail(run, initial_failure[0], initial_failure[1])
            return await self.detail(request.owner_user_id, run.id)

        work = _RunWork(run=run, request=request, warnings=[])
        await self._advance_until_pause_or_terminal(work)
        return await self.detail(request.owner_user_id, run.id)

    async def approve(
        self,
        owner_user_id: str,
        run_id: str,
        approval_id: str,
        *,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = await self._load_run(owner_user_id, run_id)
        approval = await self._load_approval(owner_user_id, run.id, approval_id)
        tool_call = await self._load_tool_call(owner_user_id, run.id, approval.tool_call_id)
        if approval.status != "pending":
            raise RuntimeError("Approval is not pending.")
        if _as_aware(approval.expires_at) <= utc_now():
            await self._expire_approval(run, approval, tool_call, "approval_expired")
            return await self.detail(owner_user_id, run.id)
        if approval.used_at is not None:
            raise RuntimeError("Approval has already been used.")
        work = _RunWork(
            run=run,
            request=self._request_from_run(run),
            tool_call=tool_call,
            warnings=[],
        )
        work.tool = await self._resolve_tool(run, str(approval.tool_id))
        if work.tool is None:
            await self._fail(run, "tool_not_found", "Approved tool is no longer registered.")
            return await self.detail(owner_user_id, run.id)
        if (
            arguments is not None
            and canonical_tool_args_hash(work.tool, arguments) != approval.arguments_hash
        ):
            await self._expire_approval(run, approval, tool_call, "approval_arguments_changed")
            return await self.detail(owner_user_id, run.id)
        try:
            work.execution_args = self._execution_args_for(work.tool, tool_call)
        except PolicyError:
            await self._expire_approval(run, approval, tool_call, "approval_arguments_changed")
            return await self.detail(owner_user_id, run.id)
        approval.status = "approved"
        approval.decided_at = utc_now()
        approval.decided_by_user_id = owner_user_id
        await self._event(
            run,
            "approval_approved",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
                "arguments_hash": approval.arguments_hash,
            },
        )
        await self._record_agent_span(
            run,
            "loomi.agent.approval",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
                "risk_class": approval.risk_class,
                "arguments_hash": approval.arguments_hash,
                "status": "approved",
            },
        )
        await self._audit(
            run,
            "agent.approval_approved",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
                "risk_class": approval.risk_class,
            },
        )
        approval.used_at = utc_now()
        await self._execute_tool_and_finish(work)
        return await self.detail(owner_user_id, run.id)

    async def deny(
        self,
        owner_user_id: str,
        run_id: str,
        approval_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        run = await self._load_run(owner_user_id, run_id)
        approval = await self._load_approval(owner_user_id, run.id, approval_id)
        tool_call = await self._load_tool_call(owner_user_id, run.id, approval.tool_call_id)
        if approval.status != "pending":
            raise RuntimeError("Approval is not pending.")
        approval.status = "denied"
        approval.decided_at = utc_now()
        approval.decided_by_user_id = owner_user_id
        approval.denial_reason = sanitize_value(reason or "Denied by owner.", string_limit=500)
        tool_call.status = "denied"
        await self._event(
            run,
            "approval_denied",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
                "reason": approval.denial_reason,
            },
        )
        await self._record_agent_span(
            run,
            "loomi.agent.approval",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
                "risk_class": approval.risk_class,
                "arguments_hash": approval.arguments_hash,
                "status": "denied",
            },
            status="error",
            error_code="approval_denied",
        )
        await self._audit(
            run,
            "agent.approval_denied",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
            },
        )
        await self._fail(run, "approval_denied", "Owner denied the tool call.")
        return await self.detail(owner_user_id, run.id)

    async def cancel(self, owner_user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._load_run(owner_user_id, run_id)
        if is_terminal(run.state):
            return await self.detail(owner_user_id, run.id)
        run.cancel_requested_at = utc_now()
        await self._transition(run, "cancelled", {"reason": "owner_cancelled"})
        run.status_reason = "owner_cancelled"
        run.completed_at = utc_now()
        await self._audit(run, "agent.run_cancelled", {"state": run.state})
        await self.session.commit()
        return await self.detail(owner_user_id, run.id)

    async def retry(self, owner_user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._load_run(owner_user_id, run_id)
        if run.state != "failed":
            raise RuntimeError("Only failed agent runs can be retried.")
        retry_count = int(run.retry_count or 0) + 1
        limits = AgentRunLimits.from_mapping(run.limits)
        if retry_count > limits.max_retries:
            raise RuntimeError("Retry limit exceeded.")
        request = self._request_from_run(
            run,
            idempotency_key=f"{run.id}:retry:{retry_count}",
        )
        detail = await self.start(request)
        run.retry_count = retry_count
        await self.session.commit()
        return detail

    async def detail(self, owner_user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._load_run(owner_user_id, run_id)
        events = await self._events(run.id)
        tool_calls = await self._tool_calls(owner_user_id, run.id)
        approvals = await self._approvals(owner_user_id, run.id)
        return serialize_run(run, events=events, tool_calls=tool_calls, approvals=approvals)

    async def list_runs(
        self,
        owner_user_id: str,
        *,
        state: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        stmt = select(AgentRun).where(
            AgentRun.owner_user_id == owner_user_id,
            AgentRun.run_kind == "agent",
        )
        count_stmt = select(func.count(AgentRun.id)).where(
            AgentRun.owner_user_id == owner_user_id,
            AgentRun.run_kind == "agent",
        )
        if state:
            stmt = stmt.where(AgentRun.state == state)
            count_stmt = count_stmt.where(AgentRun.state == state)
        total = int(await self.session.scalar(count_stmt) or 0)
        rows = list(
            await self.session.scalars(
                stmt.order_by(desc(AgentRun.created_at)).offset(offset).limit(limit)
            )
        )
        return {
            "items": [serialize_run_summary(run) for run in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def event_history(self, owner_user_id: str, run_id: str) -> list[dict[str, Any]]:
        run = await self._load_run(owner_user_id, run_id)
        return [serialize_event(event) for event in await self._events(run.id)]

    async def _advance_until_pause_or_terminal(self, work: _RunWork) -> None:
        run = work.run
        await self._transition(run, "classify_intent", {"intent": self._classify(work.request)})
        work.intent = cast(str, run.trace_metadata.get("intent", self._classify(work.request)))
        await self._transition(run, "retrieve_context", {"mode": "hybrid"})
        work.context = await self._retrieve_context(work)
        await self._transition(
            run,
            "plan",
            {
                "intent": work.intent,
                "selected_context_count": len(work.context),
                "forbidden_tool_request": forbidden_tool_request(work.request.owner_request),
            },
        )
        if forbidden_tool_request(work.request.owner_request):
            work.answer_text = (
                "I cannot use shell, filesystem, raw SQL, unrestricted HTTP, email, or secret "
                "access tools. Runtime policy allows only the run's server-side tool allowlist."
            )
            work.citations = ()
            await self._synthesize_and_complete(work)
            return

        work.planned_tool = self._plan_tool(work)
        if work.planned_tool is None:
            work.answer_text = self._answer_without_tool(work)
            work.citations = work.context[:2]
            await self._synthesize_and_complete(work)
            return

        await self._transition(
            run,
            "select_tool",
            {
                "tool_id": work.planned_tool.tool_id,
                "reason": work.planned_tool.reason,
            },
        )
        await self._validate_or_pause(work)

    async def _validate_or_pause(self, work: _RunWork) -> None:
        assert work.planned_tool is not None
        run = work.run
        tool = await self._resolve_tool(run, work.planned_tool.tool_id)
        if tool is None:
            await self._fail(run, "tool_not_found", "Requested tool is not registered.")
            return
        work.tool = tool
        try:
            validated_args = validate_tool_args(tool, work.planned_tool.arguments)
            execution_args = self._sanitize_execution_args(tool, validated_args)
        except PolicyError as exc:
            await self._fail(run, "tool_argument_validation_failed", str(exc))
            return
        args_hash = canonical_tool_args_hash(tool, execution_args)
        decision = policy_decision(tool, tuple(run.allowed_tools or []), args_hash)
        await self._transition(run, "validate_tool_request", decision)
        if not decision["allowed"]:
            await self._fail(run, "tool_not_allowed", "Tool is not on this run's allowlist.")
            return
        duplicate = await self._duplicate_tool_call(run, tool.id, args_hash)
        if duplicate is not None and duplicate.status in {"succeeded", "approval_required"}:
            work.tool_call = duplicate
            work.answer_text = "Duplicate tool call suppressed by runtime policy."
            work.citations = work.context[:2]
            await self._synthesize_and_complete(work)
            return
        tool_count = int((run.trace_metadata or {}).get("tool_call_count", 0))
        limits = AgentRunLimits.from_mapping(run.limits)
        if tool_count >= limits.max_tool_calls:
            await self._fail(run, "max_tool_calls_exceeded", "Tool-call budget was exhausted.")
            return
        run.trace_metadata = {**(run.trace_metadata or {}), "tool_call_count": tool_count + 1}
        tool_call = ToolCall(
            run_id=run.id,
            owner_user_id=run.owner_user_id,
            tool_name=tool.id,
            tool_id=tool.id,
            risk_class=tool.risk_class,
            status="validated",
            redacted_arguments=execution_args,
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            arguments_hash=args_hash,
            idempotency_key=f"{run.id}:{tool.id}:{args_hash}",
            policy_decision=decision,
            timeout_seconds=tool.timeout_seconds,
            output_size_limit=tool.output_size_limit,
            retry_count=0,
            trace_id=run.trace_id,
        )
        self.session.add(tool_call)
        await self.session.flush()
        work.tool_call = tool_call
        work.execution_args = execution_args
        if approval_required(tool):
            await self._request_approval(work, execution_args, args_hash, decision)
            return
        await self._execute_tool_and_finish(work)

    async def _request_approval(
        self,
        work: _RunWork,
        execution_args: dict[str, Any],
        args_hash: str,
        decision: dict[str, Any],
    ) -> None:
        assert work.tool is not None
        assert work.tool_call is not None
        run = work.run
        work.tool_call.status = "approval_required"
        approval = Approval(
            owner_user_id=run.owner_user_id,
            run_id=run.id,
            tool_call_id=work.tool_call.id,
            status="pending",
            policy_version=POLICY_VERSION,
            expires_at=utc_now() + timedelta(minutes=15),
            tool_id=work.tool.id,
            arguments_hash=args_hash,
            risk_class=work.tool.risk_class,
            approval_metadata={
                "redacted_arguments": execution_args,
                "policy_decision": decision,
                "single_use": True,
            },
        )
        self.session.add(approval)
        await self.session.flush()
        await self._transition(
            run,
            "request_tool_approval",
            {
                "approval_id": approval.id,
                "tool_call_id": work.tool_call.id,
                "tool_id": work.tool.id,
                "risk_class": work.tool.risk_class,
                "arguments_hash": args_hash,
                "expires_at": approval.expires_at.isoformat(),
            },
        )
        await self._audit(
            run,
            "agent.approval_requested",
            {
                "approval_id": approval.id,
                "tool_call_id": work.tool_call.id,
                "tool_id": work.tool.id,
                "risk_class": work.tool.risk_class,
                "arguments_hash": args_hash,
            },
        )
        await self.session.commit()

    async def _execute_tool_and_finish(self, work: _RunWork) -> None:
        assert work.tool is not None
        assert work.tool_call is not None
        run = work.run
        await self._transition(
            run,
            "execute_tool",
            {"tool_call_id": work.tool_call.id, "tool_id": work.tool.id},
        )
        work.tool_call.status = "running"
        work.tool_call.started_at = utc_now()
        started = time.perf_counter()
        args = work.execution_args or self._execution_args_for(work.tool, work.tool_call)
        context = ToolContext(
            session=self.session,
            settings=self.settings,
            owner_user_id=run.owner_user_id,
            request_id=work.request.request_id,
            trace_id=work.request.trace_id,
            owner_request=work.request.owner_request,
            retrieved_context=work.context,
        )
        try:
            result = await asyncio.wait_for(
                self._execute_with_retry(work.tool, args, context, work),
                timeout=work.tool.timeout_seconds,
            )
        except TimeoutError:
            await self._tool_failed(work, "tool_timeout", "Tool execution timed out.")
            return
        except ToolExecutionError as exc:
            await self._tool_failed(work, exc.code, exc.detail)
            return
        work.tool_result = result
        output = truncate_json_payload(result.output, max_bytes=work.tool.output_size_limit)
        work.tool_call.redacted_result = output
        work.tool_call.status = "succeeded"
        work.tool_call.completed_at = utc_now()
        work.tool_call.latency_ms = round((time.perf_counter() - started) * 1000)
        work.citations = result.citations or work.context[:2]
        await self._transition(
            run,
            "observe_tool_result",
            {
                "tool_call_id": work.tool_call.id,
                "tool_id": work.tool.id,
                "status": work.tool_call.status,
                "latency_ms": work.tool_call.latency_ms,
                "usage": result.usage,
            },
        )
        await self._record_agent_span(
            run,
            "loomi.agent.tool_call",
            {
                "tool_call_id": work.tool_call.id,
                "tool_id": work.tool.id,
                "tool_name": work.tool.id,
                "risk_class": work.tool.risk_class,
                "status": work.tool_call.status,
                "latency_ms": work.tool_call.latency_ms,
            },
            duration_ms=work.tool_call.latency_ms or 0,
        )
        work.answer_text = self._answer_from_tool(work)
        await self._synthesize_and_complete(work)

    async def _execute_with_retry(
        self,
        tool: Tool,
        args: dict[str, Any],
        context: ToolContext,
        work: _RunWork,
    ) -> ToolResult:
        limits = AgentRunLimits.from_mapping(work.run.limits)
        attempts = limits.max_retries + 1
        last_error: ToolExecutionError | None = None
        for attempt in range(attempts):
            try:
                return await tool.execute(args, context)
            except ToolExecutionError as exc:
                last_error = exc
                if not exc.transient or attempt >= attempts - 1:
                    break
                assert work.tool_call is not None
                work.tool_call.retry_count = attempt + 1
                await self._event(
                    work.run,
                    "tool_retry",
                    {
                        "tool_call_id": work.tool_call.id,
                        "tool_id": tool.id,
                        "attempt": attempt + 1,
                        "code": exc.code,
                    },
                )
                await asyncio.sleep(0)
        raise last_error or ToolExecutionError("tool_failed", "Tool execution failed.")

    async def _tool_failed(self, work: _RunWork, code: str, detail: str) -> None:
        assert work.tool_call is not None
        work.tool_call.status = "failed"
        work.tool_call.completed_at = utc_now()
        work.tool_call.error_code = code
        await self._transition(
            work.run,
            "observe_tool_result",
            {
                "tool_call_id": work.tool_call.id,
                "status": "failed",
                "code": code,
            },
        )
        await self._record_agent_span(
            work.run,
            "loomi.agent.tool_call",
            {
                "tool_call_id": work.tool_call.id,
                "tool_id": work.tool_call.tool_id,
                "tool_name": work.tool_call.tool_name,
                "risk_class": work.tool_call.risk_class,
                "status": "failed",
                "error_code": code,
            },
            status="error",
            error_code=code,
        )
        await self._fail(work.run, code, detail)

    async def _synthesize_and_complete(self, work: _RunWork) -> None:
        run = work.run
        estimated_output_tokens = _estimate_tokens(work.answer_text)
        estimated_input_tokens = _estimate_tokens(work.request.owner_request)
        usage = {
            "input_tokens": estimated_input_tokens,
            "output_tokens": estimated_output_tokens,
            "total_tokens": estimated_input_tokens + estimated_output_tokens,
            "estimated_cost_usd": round(
                (estimated_input_tokens + estimated_output_tokens) * 0.0000005,
                6,
            ),
        }
        await self._transition(
            run,
            "synthesize_answer",
            {"output_tokens": estimated_output_tokens, "model": run.model},
        )
        valid_citations = [
            {
                "citation_id": item.allowed_citation_id,
                "chunk_id": item.candidate.chunk_id,
                "document_id": item.candidate.document_id,
                "document_title": item.candidate.document_title,
                "excerpt": item.excerpt,
            }
            for item in work.citations
        ]
        await self._transition(run, "validate_citations", {"valid_citations": valid_citations})
        output = {
            "answer_text": work.answer_text,
            "citations": valid_citations,
            "warnings": sorted(set(work.warnings or [])),
        }
        run.sanitized_output = cast(dict[str, Any], sanitize_value(output, string_limit=2400))
        run.usage = usage
        run.latency_ms = _run_latency_ms(run)
        await self._transition(
            run,
            "persist_result",
            {"usage": usage, "latency_ms": run.latency_ms},
        )
        await self._transition(run, "complete", {"answer_text": work.answer_text, "usage": usage})
        run.status_reason = "completed"
        run.completed_at = utc_now()
        await self._audit(
            run,
            "agent.run_completed",
            {"usage": usage, "latency_ms": run.latency_ms},
        )
        await self.session.commit()

    async def _retrieve_context(self, work: _RunWork) -> tuple[ContextItem, ...]:
        if len(work.request.owner_request.strip()) < 2:
            return ()
        try:
            result = await RetrievalService(self.settings).search(
                self.session,
                RetrievalQuery(
                    owner_user_id=work.request.owner_user_id,
                    query=work.request.owner_request,
                    mode="hybrid",
                    filters=SearchFilters(),
                    limit=6,
                    min_score=0.0,
                    debug=True,
                    request_id=work.request.request_id,
                    trace_id=work.request.trace_id,
                ),
            )
        except Exception:
            work.warnings = [*(work.warnings or []), "retrieval_failed"]
            return ()
        await self._event(
            work.run,
            "retrieval_completed",
            {
                "selected_context_count": len(result.selected_context),
                "candidate_count": len(result.candidates),
                "warnings": list(result.warnings),
            },
        )
        return result.selected_context

    def _classify(self, request: AgentRunRequest) -> str:
        text = request.owner_request.casefold()
        intent = "search"
        if "calculate" in text or re.search(r"\d+\s*[-+*/%]\s*\d+", text):
            intent = "calculate"
        if "draft note" in text or "create a note" in text:
            intent = "draft_note"
        if "metadata" in text:
            intent = "metadata"
        if "excerpt" in text or "source" in text:
            intent = "source_excerpt"
        return intent

    def _plan_tool(self, work: _RunWork) -> PlannedToolCall | None:
        mcp_call = _plan_mcp_tool(work.request.owner_request, work.request.allowed_tools)
        if mcp_call is not None:
            return mcp_call
        if work.intent == "calculate":
            return PlannedToolCall(
                tool_id="calculator",
                arguments={"expression": _extract_expression(work.request.owner_request)},
                reason="Arithmetic request detected.",
            )
        if work.intent == "draft_note":
            return PlannedToolCall(
                tool_id="notes.create_draft",
                arguments={
                    "title": _title_from_request(work.request.owner_request),
                    "content": work.request.owner_request,
                },
                reason="Owner asked to stage a local draft note.",
            )
        if work.intent == "metadata" and work.context:
            return PlannedToolCall(
                tool_id="knowledge.get_document_metadata",
                arguments={"document_id": work.context[0].candidate.document_id},
                reason="Document metadata requested.",
            )
        if work.intent == "source_excerpt" and work.context:
            return PlannedToolCall(
                tool_id="knowledge.get_source_excerpt",
                arguments={"chunk_id": work.context[0].candidate.chunk_id},
                reason="Source excerpt requested.",
            )
        return PlannedToolCall(
            tool_id="knowledge.search",
            arguments={
                "query": work.request.owner_request,
                "mode": "hybrid",
                "limit": 5,
                "min_score": 0.0,
            },
            reason="Default bounded knowledge lookup.",
        )

    def _answer_without_tool(self, work: _RunWork) -> str:
        if not work.context:
            return (
                "I cannot answer from the current knowledge base because no evidence was selected."
            )
        first = work.context[0]
        return (
            f"The strongest selected evidence is from {first.candidate.document_title}: "
            f"{first.excerpt}"
        )

    def _answer_from_tool(self, work: _RunWork) -> str:
        assert work.tool is not None
        assert work.tool_result is not None
        output = work.tool_result.output
        if work.tool.id == "calculator":
            return f"Result: {output.get('result')}."
        if work.tool.id == "notes.create_draft":
            return f"Draft note staged: {output.get('title')} ({output.get('draft_note_id')})."
        if work.tool.id == "knowledge.search":
            items = output.get("items", [])
            if not isinstance(items, list) or not items:
                return "The bounded knowledge search found no matching stored chunks."
            first = cast(dict[str, Any], items[0])
            return (
                f"Knowledge search found {len(items)} matching chunks. "
                f"Top source: {first.get('document_title')} - {first.get('excerpt')}"
            )
        if work.tool.id == "knowledge.get_document_metadata":
            document = cast(dict[str, Any], output.get("document", {}))
            return (
                f"Document metadata: {document.get('title')} has "
                f"{document.get('chunk_count')} chunks and status {document.get('status')}."
            )
        if work.tool.id == "knowledge.get_source_excerpt":
            return f"Source excerpt: {output.get('excerpt')}"
        return "Tool execution completed."

    async def _transition(
        self,
        run: AgentRun,
        next_state: AgentState,
        payload: dict[str, Any],
    ) -> None:
        validate_transition(run.state, next_state)
        limits = AgentRunLimits.from_mapping(run.limits)
        metadata = dict(run.trace_metadata or {})
        step_count = int(metadata.get("step_count", 0))
        if next_state not in {"failed", "cancelled"} and step_count >= limits.max_steps:
            await self._fail(run, "max_steps_exceeded", "State-step budget was exhausted.")
            return
        previous = run.state
        if next_state not in {"failed", "cancelled"}:
            metadata["step_count"] = step_count + 1
        if next_state == "classify_intent":
            metadata["intent"] = payload.get("intent")
        run.trace_metadata = metadata
        run.state = next_state
        await self._event(
            run,
            next_state,
            {
                "from_state": previous,
                "to_state": next_state,
                "state": next_state,
                **sanitize_value(payload),
            },
        )
        await self._record_agent_span(
            run,
            "loomi.agent.state",
            {
                "from_state": previous,
                "to_state": next_state,
                "state": next_state,
                "provider": run.provider,
                "model": run.model,
                "prompt_id": metadata.get("prompt_id"),
                "prompt_version": metadata.get("prompt_version"),
                **cast(dict[str, Any], sanitize_value(payload)),
            },
            status="error" if next_state == "failed" else "ok",
            error_code=payload.get("code") if isinstance(payload.get("code"), str) else None,
        )

    async def _fail(self, run: AgentRun, code: str, detail: str) -> None:
        if is_terminal(run.state):
            return
        validate_transition(run.state, "failed")
        run.state = "failed"
        run.status_reason = code
        run.last_error = {"code": code, "detail": sanitize_value(detail, string_limit=1000)}
        run.completed_at = utc_now()
        run.latency_ms = _run_latency_ms(run)
        await self._event(
            run,
            "failed",
            {
                "state": "failed",
                "code": code,
                "detail": "Run failed safely.",
                "latency_ms": run.latency_ms,
            },
        )
        await self._audit(run, "agent.run_failed", {"code": code})
        await self.session.commit()

    async def _record_agent_span(
        self,
        run: AgentRun,
        name: str,
        attributes: dict[str, Any],
        *,
        status: str = "ok",
        duration_ms: int = 0,
        error_code: str | None = None,
    ) -> None:
        await record_span(
            self.session,
            self.settings,
            name=name,
            component="agent",
            trace_id=run.trace_id,
            owner_user_id=run.owner_user_id,
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            attributes={
                "run_id": run.id,
                "trace_id": run.trace_id,
                **attributes,
            },
        )

    async def _expire_approval(
        self,
        run: AgentRun,
        approval: Approval,
        tool_call: ToolCall,
        reason: str,
    ) -> None:
        approval.status = "expired"
        approval.expired_at = utc_now()
        tool_call.status = "approval_invalidated"
        await self._event(
            run,
            "approval_expired",
            {
                "approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "tool_id": approval.tool_id,
                "reason": reason,
            },
        )
        await self._audit(
            run,
            "agent.approval_expired",
            {"approval_id": approval.id, "reason": reason},
        )
        await self._fail(run, reason, "Approval can no longer be used.")

    async def _event(self, run: AgentRun, event_type: str, payload: dict[str, Any]) -> None:
        metadata = dict(run.trace_metadata or {})
        sequence = int(metadata.get("event_sequence") or 0)
        if sequence <= 0:
            latest_sequence = await self.session.scalar(
                select(AgentEvent.sequence_number)
                .where(AgentEvent.run_id == run.id)
                .order_by(desc(AgentEvent.sequence_number))
                .limit(1)
            )
            sequence = int(latest_sequence or 0)
        sequence += 1
        run.trace_metadata = {**metadata, "event_sequence": sequence}
        self.session.add(
            AgentEvent(
                run_id=run.id,
                event_type=event_type,
                sequence_number=sequence,
                payload=json.loads(json.dumps(sanitize_value(payload), default=str)),
            )
        )

    async def _audit(self, run: AgentRun, event_type: str, metadata: dict[str, Any]) -> None:
        self.session.add(
            AuditEvent(
                owner_user_id=run.owner_user_id,
                event_type=event_type,
                request_id=(run.sanitized_input or {}).get("request_id"),
                trace_id=run.trace_id,
                event_metadata=cast(dict[str, Any], sanitize_value(metadata)),
            )
        )

    async def _load_idempotent_run(self, request: AgentRunRequest) -> AgentRun | None:
        if not request.idempotency_key:
            return None
        return cast(
            AgentRun | None,
            await self.session.scalar(
                select(AgentRun).where(
                    AgentRun.id
                    == _deterministic_run_id(
                        request.owner_user_id,
                        request.idempotency_key,
                    ),
                    AgentRun.owner_user_id == request.owner_user_id,
                )
            ),
        )

    async def _load_run(self, owner_user_id: str, run_id: str) -> AgentRun:
        run = await self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.owner_user_id == owner_user_id,
            )
        )
        if run is None:
            raise LookupError("Agent run not found.")
        return run

    async def _load_approval(self, owner_user_id: str, run_id: str, approval_id: str) -> Approval:
        approval = await self.session.scalar(
            select(Approval).where(
                Approval.id == approval_id,
                Approval.owner_user_id == owner_user_id,
                Approval.run_id == run_id,
            )
        )
        if approval is None:
            raise LookupError("Approval not found.")
        return approval

    async def _load_tool_call(
        self,
        owner_user_id: str,
        run_id: str,
        tool_call_id: str | None,
    ) -> ToolCall:
        if tool_call_id is None:
            raise LookupError("Tool call not found.")
        tool_call = await self.session.scalar(
            select(ToolCall).where(
                ToolCall.id == tool_call_id,
                ToolCall.owner_user_id == owner_user_id,
                ToolCall.run_id == run_id,
            )
        )
        if tool_call is None:
            raise LookupError("Tool call not found.")
        return tool_call

    async def _duplicate_tool_call(
        self,
        run: AgentRun,
        tool_id: str,
        arguments_hash: str,
    ) -> ToolCall | None:
        return cast(
            ToolCall | None,
            await self.session.scalar(
                select(ToolCall)
                .where(
                    ToolCall.run_id == run.id,
                    ToolCall.owner_user_id == run.owner_user_id,
                    ToolCall.tool_id == tool_id,
                    ToolCall.arguments_hash == arguments_hash,
                )
                .order_by(ToolCall.created_at.asc())
                .limit(1)
            ),
        )

    def _sanitize_execution_args(self, tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
        sanitized = sanitize_value(arguments)
        if not isinstance(sanitized, dict):
            raise PolicyError("Sanitized tool arguments must be an object.")
        return validate_tool_args(tool, sanitized)

    def _execution_args_for(self, tool: Tool, tool_call: ToolCall) -> dict[str, Any]:
        execution_args = validate_tool_args(tool, dict(tool_call.redacted_arguments or {}))
        if (
            tool_call.arguments_hash is not None
            and canonical_tool_args_hash(tool, execution_args) != tool_call.arguments_hash
        ):
            raise PolicyError("Tool arguments no longer match their canonical hash.")
        return execution_args

    async def _resolve_tool(self, run: AgentRun, tool_id: str) -> Tool | None:
        tool = self.registry.get(tool_id)
        if tool is not None:
            return tool
        if tool_id.startswith(MCP_TOOL_ID_PREFIX):
            return cast(
                Tool | None,
                await load_mcp_tool(
                    self.session,
                    self.settings,
                    run.owner_user_id,
                    tool_id,
                ),
            )
        return None

    async def _events(self, run_id: str) -> list[AgentEvent]:
        return list(
            await self.session.scalars(
                select(AgentEvent)
                .where(AgentEvent.run_id == run_id)
                .order_by(AgentEvent.sequence_number.asc())
            )
        )

    async def _tool_calls(self, owner_user_id: str, run_id: str) -> list[ToolCall]:
        return list(
            await self.session.scalars(
                select(ToolCall)
                .where(ToolCall.owner_user_id == owner_user_id, ToolCall.run_id == run_id)
                .order_by(ToolCall.created_at.asc())
            )
        )

    async def _approvals(self, owner_user_id: str, run_id: str) -> list[Approval]:
        return list(
            await self.session.scalars(
                select(Approval)
                .where(Approval.owner_user_id == owner_user_id, Approval.run_id == run_id)
                .order_by(Approval.created_at.asc())
            )
        )

    def _request_from_run(
        self,
        run: AgentRun,
        *,
        idempotency_key: str | None = None,
    ) -> AgentRunRequest:
        request = str(run.owner_request or "")
        sanitized_input = run.sanitized_input or {}
        return AgentRunRequest(
            owner_user_id=run.owner_user_id,
            owner_request=request,
            request_id=str(sanitized_input.get("request_id") or ""),
            trace_id=str(run.trace_id or sanitized_input.get("trace_id") or ""),
            idempotency_key=idempotency_key or run.idempotency_key,
            provider=run.provider,
            model=run.model,
            allowed_tools=tuple(run.allowed_tools or DEFAULT_ALLOWED_TOOLS),
            limits=AgentRunLimits.from_mapping(run.limits),
            run_kind=run.run_kind,
            trace_metadata=run.trace_metadata or {},
        )

    def _initial_budget_failure(
        self,
        run: AgentRun,
        limits: AgentRunLimits,
    ) -> tuple[str, str] | None:
        estimated_input_tokens = _estimate_tokens(str(run.owner_request or ""))
        if limits.max_steps < 4:
            return ("max_steps_exceeded", "Run limits are too low to start safely.")
        if estimated_input_tokens > limits.token_budget:
            run.status_reason = "token_budget_exceeded"
            run.last_error = {"code": "token_budget_exceeded"}
            return ("token_budget_exceeded", "Token budget was exhausted before planning.")
        return None


def serialize_run(
    run: AgentRun,
    *,
    events: list[AgentEvent],
    tool_calls: list[ToolCall],
    approvals: list[Approval],
) -> dict[str, Any]:
    payload = serialize_run_summary(run)
    payload.update(
        {
            "events": [serialize_event(event) for event in events],
            "tool_calls": [serialize_tool_call(tool_call) for tool_call in tool_calls],
            "approvals": [serialize_approval(approval) for approval in approvals],
        }
    )
    return payload


def serialize_run_summary(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "run_kind": run.run_kind,
        "state": run.state,
        "status_reason": run.status_reason,
        "owner_request": run.owner_request,
        "provider": run.provider,
        "model": run.model,
        "allowed_tools": list(run.allowed_tools or []),
        "limits": run.limits or {},
        "usage": run.usage or {},
        "sanitized_input": run.sanitized_input or {},
        "sanitized_output": run.sanitized_output,
        "retry_count": run.retry_count or 0,
        "latency_ms": run.latency_ms,
        "trace_id": run.trace_id,
        "trace_metadata": run.trace_metadata or {},
        "last_error": run.last_error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "cancel_requested_at": (
            run.cancel_requested_at.isoformat() if run.cancel_requested_at else None
        ),
    }


def serialize_event(event: AgentEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "event_type": event.event_type,
        "sequence_number": event.sequence_number,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


def serialize_tool_call(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "run_id": tool_call.run_id,
        "tool_id": tool_call.tool_id or tool_call.tool_name,
        "tool_name": tool_call.tool_name,
        "risk_class": tool_call.risk_class,
        "status": tool_call.status,
        "redacted_arguments": tool_call.redacted_arguments or {},
        "redacted_result": tool_call.redacted_result,
        "arguments_hash": tool_call.arguments_hash,
        "idempotency_key": tool_call.idempotency_key,
        "policy_decision": tool_call.policy_decision or {},
        "timeout_seconds": tool_call.timeout_seconds,
        "output_size_limit": tool_call.output_size_limit,
        "retry_count": tool_call.retry_count or 0,
        "latency_ms": tool_call.latency_ms,
        "error_code": tool_call.error_code,
        "trace_id": tool_call.trace_id,
        "created_at": tool_call.created_at.isoformat(),
        "updated_at": tool_call.updated_at.isoformat(),
        "started_at": tool_call.started_at.isoformat() if tool_call.started_at else None,
        "completed_at": tool_call.completed_at.isoformat() if tool_call.completed_at else None,
    }


def serialize_approval(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "run_id": approval.run_id,
        "tool_call_id": approval.tool_call_id,
        "tool_id": approval.tool_id,
        "status": approval.status,
        "policy_version": approval.policy_version,
        "arguments_hash": approval.arguments_hash,
        "risk_class": approval.risk_class,
        "expires_at": approval.expires_at.isoformat(),
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        "decided_by_user_id": approval.decided_by_user_id,
        "used_at": approval.used_at.isoformat() if approval.used_at else None,
        "expired_at": approval.expired_at.isoformat() if approval.expired_at else None,
        "cancelled_at": approval.cancelled_at.isoformat() if approval.cancelled_at else None,
        "denial_reason": approval.denial_reason,
        "approval_metadata": approval.approval_metadata or {},
        "created_at": approval.created_at.isoformat(),
        "updated_at": approval.updated_at.isoformat(),
    }


def _deterministic_run_id(owner_user_id: str, idempotency_key: str | None) -> str:
    if not idempotency_key:
        return new_id()
    return str(uuid5(NAMESPACE_URL, f"loomi-agent-runtime:{owner_user_id}:{idempotency_key}"))


def _extract_expression(owner_request: str) -> str:
    expression = "".join(char for char in owner_request if char in "0123456789+-*/%(). ").strip()
    if not expression:
        return "0"
    return expression


def _plan_mcp_tool(owner_request: str, allowed_tools: tuple[str, ...]) -> PlannedToolCall | None:
    text = owner_request.casefold()
    if "mcp" not in text:
        return None
    for tool_id in allowed_tools:
        if not tool_id.startswith(MCP_TOOL_ID_PREFIX):
            continue
        try:
            _, tool_name = parse_mcp_tool_id(tool_id)
        except MCPClientError:
            continue
        if tool_name.casefold() not in text and "tool" not in text:
            continue
        return PlannedToolCall(
            tool_id=tool_id,
            arguments=_extract_mcp_arguments(owner_request, tool_name),
            reason="Owner requested an explicitly allowlisted MCP tool.",
        )
    return None


def _extract_mcp_arguments(owner_request: str, tool_name: str) -> dict[str, Any]:
    parsed = _extract_first_json_object(owner_request)
    if parsed is not None:
        return parsed
    if tool_name == "echo":
        return {"text": owner_request[:200]}
    if tool_name == "add":
        numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", owner_request)[:2]]
        if len(numbers) == 2:
            return {"a": numbers[0], "b": numbers[1]}
        return {"a": 0, "b": 0}
    if "search" in tool_name:
        return {"query": owner_request[:120]}
    return {}


def _extract_first_json_object(value: str) -> dict[str, Any] | None:
    start = value.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(value[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(value[start : index + 1])
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def _title_from_request(owner_request: str) -> str:
    cleaned = " ".join(owner_request.split())
    if len(cleaned) <= 80:
        return cleaned or "Draft note"
    return f"{cleaned[:77].rstrip()}..."


def _estimate_tokens(value: str) -> int:
    return max(1, len(value) // 4)


def _run_latency_ms(run: AgentRun) -> int | None:
    if run.started_at is None:
        return None
    delta = utc_now() - _as_aware(run.started_at)
    return round(delta.total_seconds() * 1000)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
