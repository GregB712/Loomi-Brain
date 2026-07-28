from __future__ import annotations

import pytest

from loomi_api.ingestion.embeddings import DeterministicEmbeddingProvider


@pytest.mark.asyncio
async def test_fake_embeddings_are_deterministic() -> None:
    provider = DeterministicEmbeddingProvider(model="test-model", dimensions=8)

    first = await provider.embed(["same text"])
    second = await provider.embed(["same text"])

    assert first == second
    assert first[0].dimensions == 8
    assert first[0].provider == "fake"
