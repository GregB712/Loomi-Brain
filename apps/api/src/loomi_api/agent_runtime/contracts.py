from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.config import Settings
from loomi_api.retrieval.contracts import ContextItem

AgentState = Literal[
    "receive_request",
    "classify_intent",
    "retrieve_context",
    "plan",
    "select_tool",
    "validate_tool_request",
    "request_tool_approval",
    "execute_tool",
    "observe_tool_result",
    "synthesize_answer",
    "validate_citations",
    "persist_result",
    "complete",
    "cancelled",
    "failed",
]

TerminalState = Literal["complete", "cancelled", "failed"]

ToolRisk = Literal[
    "read-only",
    "local-mutation",
    "external-mutation",
    "credential-sensitive",
    "destructive",
]

ToolApprovalPolicy = Literal["never", "risk-based", "always"]


@dataclass(frozen=True)
class AgentRunLimits:
    max_steps: int = 16
    max_tool_calls: int = 3
    request_timeout_seconds: int = 45
    per_step_timeout_seconds: int = 10
    token_budget: int = 6000
    cost_budget_usd: float = 0.25
    max_retries: int = 1

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> AgentRunLimits:
        if not payload:
            return cls()
        defaults = cls()
        return cls(
            max_steps=_bounded_int(payload.get("max_steps"), defaults.max_steps, 1, 64),
            max_tool_calls=_bounded_int(
                payload.get("max_tool_calls"), defaults.max_tool_calls, 0, 12
            ),
            request_timeout_seconds=_bounded_int(
                payload.get("request_timeout_seconds"),
                defaults.request_timeout_seconds,
                1,
                300,
            ),
            per_step_timeout_seconds=_bounded_int(
                payload.get("per_step_timeout_seconds"),
                defaults.per_step_timeout_seconds,
                1,
                60,
            ),
            token_budget=_bounded_int(
                payload.get("token_budget"),
                defaults.token_budget,
                1,
                50_000,
            ),
            cost_budget_usd=_bounded_float(
                payload.get("cost_budget_usd"), defaults.cost_budget_usd, 0.0, 50.0
            ),
            max_retries=_bounded_int(payload.get("max_retries"), defaults.max_retries, 0, 5),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "request_timeout_seconds": self.request_timeout_seconds,
            "per_step_timeout_seconds": self.per_step_timeout_seconds,
            "token_budget": self.token_budget,
            "cost_budget_usd": self.cost_budget_usd,
            "max_retries": self.max_retries,
        }


@dataclass(frozen=True)
class AgentRunRequest:
    owner_user_id: str
    owner_request: str
    request_id: str
    trace_id: str
    idempotency_key: str | None = None
    provider: str | None = None
    model: str | None = None
    allowed_tools: tuple[str, ...] = ()
    limits: AgentRunLimits = field(default_factory=AgentRunLimits)


@dataclass(frozen=True)
class PlannedToolCall:
    tool_id: str
    arguments: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    settings: Settings
    owner_user_id: str
    request_id: str
    trace_id: str
    owner_request: str
    retrieved_context: tuple[ContextItem, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    output: dict[str, Any]
    citations: tuple[ContextItem, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)


class ToolExecutionError(RuntimeError):
    def __init__(self, code: str, detail: str, *, transient: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.transient = transient


class Tool(Protocol):
    id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_class: ToolRisk
    timeout_seconds: int
    output_size_limit: int
    idempotent: bool
    approval_policy: ToolApprovalPolicy

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute the tool with already validated arguments."""


class AgentRuntime(Protocol):
    async def start(self, request: AgentRunRequest) -> dict[str, Any]:
        """Start or return an idempotent agent run."""

    async def cancel(self, owner_user_id: str, run_id: str) -> dict[str, Any]:
        """Cancel a non-terminal run."""

    async def approve(
        self,
        owner_user_id: str,
        run_id: str,
        approval_id: str,
        *,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Approve a pending tool call if the canonical arguments still match."""

    async def deny(
        self,
        owner_user_id: str,
        run_id: str,
        approval_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Deny a pending tool call without executing it."""


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int):
        return default
    return min(max(value, minimum), maximum)


def _bounded_float(value: object, default: float, minimum: float, maximum: float) -> float:
    if not isinstance(value, int | float):
        return default
    return min(max(float(value), minimum), maximum)
