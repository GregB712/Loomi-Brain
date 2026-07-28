from __future__ import annotations

from loomi_api.agent_runtime.contracts import AgentState

TERMINAL_STATES: frozenset[AgentState] = frozenset({"complete", "cancelled", "failed"})

LEGAL_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    "receive_request": frozenset({"classify_intent", "cancelled", "failed"}),
    "classify_intent": frozenset({"retrieve_context", "cancelled", "failed"}),
    "retrieve_context": frozenset({"plan", "cancelled", "failed"}),
    "plan": frozenset({"select_tool", "synthesize_answer", "cancelled", "failed"}),
    "select_tool": frozenset({"validate_tool_request", "synthesize_answer", "cancelled", "failed"}),
    "validate_tool_request": frozenset(
        {"request_tool_approval", "execute_tool", "synthesize_answer", "cancelled", "failed"}
    ),
    "request_tool_approval": frozenset({"execute_tool", "cancelled", "failed"}),
    "execute_tool": frozenset({"observe_tool_result", "cancelled", "failed"}),
    "observe_tool_result": frozenset({"select_tool", "synthesize_answer", "cancelled", "failed"}),
    "synthesize_answer": frozenset({"validate_citations", "cancelled", "failed"}),
    "validate_citations": frozenset({"persist_result", "cancelled", "failed"}),
    "persist_result": frozenset({"complete", "cancelled", "failed"}),
    "complete": frozenset(),
    "cancelled": frozenset(),
    "failed": frozenset(),
}


class StateTransitionError(ValueError):
    """Raised when an agent run attempts an illegal state transition."""


def validate_transition(current: str, next_state: AgentState) -> None:
    if current not in LEGAL_TRANSITIONS:
        raise StateTransitionError(f"Unknown agent state: {current}")
    allowed = LEGAL_TRANSITIONS[current]
    if next_state not in allowed:
        raise StateTransitionError(f"Illegal transition from {current} to {next_state}")


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES
