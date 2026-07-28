from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from loomi_api.retrieval.contracts import ContextItem

ProviderName = Literal["mock", "openai-compatible", "openai", "anthropic", "gemini", "vllm"]


@dataclass(frozen=True)
class ModelCapability:
    provider: ProviderName
    model: str
    supports_streaming: bool
    supports_structured_output: bool
    supports_health_check: bool
    configured: bool
    notes: str | None = None


@dataclass(frozen=True)
class ProviderHealth:
    provider: ProviderName
    ok: bool
    configured: bool
    latency_ms: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


@dataclass(frozen=True)
class ModelRequest:
    provider: ProviderName
    model: str
    owner_request: str
    context: tuple[ContextItem, ...]
    request_id: str
    trace_id: str
    max_output_tokens: int


@dataclass(frozen=True)
class ModelDelta:
    delta_type: Literal["token", "citation", "warning", "completed"]
    text: str = ""
    citation_id: str | None = None
    warning: str | None = None
    usage: TokenUsage | None = None
    raw_citation_ids: tuple[str, ...] = ()


class ModelProvider(Protocol):
    provider: ProviderName

    def capabilities(self) -> tuple[ModelCapability, ...]:
        """Return model capabilities without exposing provider secrets."""

    async def health(self) -> ProviderHealth:
        """Check provider availability without leaking credentials."""

    def stream_chat(
        self,
        request: ModelRequest,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> AsyncIterator[ModelDelta]:
        """Stream provider-neutral chat events."""


class ProviderError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ParsedProviderText:
    text: str
    citation_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)
