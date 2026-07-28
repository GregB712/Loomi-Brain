from __future__ import annotations

import pytest

from loomi_api.ingestion.errors import IngestionError
from loomi_api.ingestion.state import (
    CANCELLED,
    CHUNKING,
    COMPLETED,
    EMBEDDING,
    EXTRACTING,
    FAILED,
    INDEXING,
    NORMALIZING,
    QUEUED,
    SCANNING,
    VALIDATING,
    validate_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (QUEUED, VALIDATING),
        (VALIDATING, SCANNING),
        (SCANNING, EXTRACTING),
        (EXTRACTING, NORMALIZING),
        (NORMALIZING, CHUNKING),
        (CHUNKING, EMBEDDING),
        (EMBEDDING, INDEXING),
        (INDEXING, COMPLETED),
        (FAILED, QUEUED),
        (CANCELLED, QUEUED),
    ],
)
def test_valid_job_transitions(current: str, target: str) -> None:
    validate_transition(current, target)


def test_invalid_job_transition_is_rejected() -> None:
    with pytest.raises(IngestionError) as error:
        validate_transition(QUEUED, COMPLETED)

    assert error.value.code == "invalid_job_transition"
