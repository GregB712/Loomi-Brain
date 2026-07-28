from __future__ import annotations

import hashlib
import struct

from loomi_api.ingestion.contracts import EmbeddingVector


class DeterministicEmbeddingProvider:
    provider = "fake"
    version = "phase2-v1"

    def __init__(self, *, model: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> EmbeddingVector:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
            for offset in range(0, len(block), 4):
                if len(values) == self.dimensions:
                    break
                integer = struct.unpack(">I", block[offset : offset + 4])[0]
                values.append(round((integer / 2**32) * 2 - 1, 8))
            counter += 1
        checksum = hashlib.sha256(
            ",".join(f"{value:.8f}" for value in values).encode("utf-8")
        ).hexdigest()
        return EmbeddingVector(
            provider=self.provider,
            model=self.model,
            dimensions=self.dimensions,
            version=self.version,
            vector=values,
            checksum=checksum,
        )
