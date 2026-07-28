from __future__ import annotations

from typing import Final

from loomi_api.ingestion.errors import IngestionError

QUEUED = "queued"
VALIDATING = "validating"
SCANNING = "scanning"
EXTRACTING = "extracting"
NORMALIZING = "normalizing"
CHUNKING = "chunking"
EMBEDDING = "embedding"
INDEXING = "indexing"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

ORDERED_STAGES: Final[tuple[str, ...]] = (
    QUEUED,
    VALIDATING,
    SCANNING,
    EXTRACTING,
    NORMALIZING,
    CHUNKING,
    EMBEDDING,
    INDEXING,
    COMPLETED,
)

TERMINAL_STATES: Final[frozenset[str]] = frozenset({COMPLETED, FAILED, CANCELLED})
ALL_STATES: Final[frozenset[str]] = frozenset({*ORDERED_STAGES, FAILED, CANCELLED})

_FORWARD_TRANSITIONS: Final[dict[str, set[str]]] = {
    QUEUED: {VALIDATING, CANCELLED, FAILED},
    VALIDATING: {SCANNING, CANCELLED, FAILED},
    SCANNING: {EXTRACTING, CANCELLED, FAILED},
    EXTRACTING: {NORMALIZING, CANCELLED, FAILED},
    NORMALIZING: {CHUNKING, CANCELLED, FAILED},
    CHUNKING: {EMBEDDING, CANCELLED, FAILED},
    EMBEDDING: {INDEXING, CANCELLED, FAILED},
    INDEXING: {COMPLETED, CANCELLED, FAILED},
    COMPLETED: {QUEUED},
    FAILED: {QUEUED},
    CANCELLED: {QUEUED},
}


def validate_transition(current: str, target: str) -> None:
    if current not in ALL_STATES:
        raise IngestionError("invalid_job_state", "The ingestion job is in an invalid state.")
    if target not in ALL_STATES:
        raise IngestionError("invalid_job_state", "The requested ingestion state is invalid.")
    if target not in _FORWARD_TRANSITIONS[current]:
        raise IngestionError(
            "invalid_job_transition",
            f"Ingestion job cannot transition from {current} to {target}.",
        )


def progress_for_state(state: str) -> int:
    if state == FAILED:
        return 100
    if state == CANCELLED:
        return 100
    try:
        index = ORDERED_STAGES.index(state)
    except ValueError:
        return 0
    return min(100, round((index / (len(ORDERED_STAGES) - 1)) * 100))
