from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ParsedSection:
    text: str
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    heading_path: tuple[str, ...] = ()
    start_offset: int | None = None
    end_offset: int | None = None
    classification: str = "body"


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    sections: tuple[ParsedSection, ...]
    parser_name: str
    parser_version: str
    metadata: dict[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChunkCandidate:
    ordinal: int
    stable_id: str
    text: str
    text_sha256: str
    token_count: int
    provenance: dict[str, object]


@dataclass(frozen=True)
class EmbeddingVector:
    provider: str
    model: str
    dimensions: int
    version: str
    vector: list[float]
    checksum: str


class ObjectStore(Protocol):
    def path_for_key(self, key: str) -> Path:
        """Return a local private path for a storage key."""

    def reserve_key(self, owner_user_id: str, document_id: str, version_id: str) -> str:
        """Create a random, owner-namespaced storage key."""

    def delete(self, key: str) -> None:
        """Delete an object if it exists."""


class MalwareScanner(Protocol):
    async def scan(self, path: Path) -> None:
        """Raise when an object is malicious or scanner policy cannot be met."""


class OCRProvider(Protocol):
    async def extract_text(self, path: Path, media_type: str, filename: str) -> ParsedDocument:
        """Extract text from an image-like document."""


class DocumentParser(Protocol):
    async def parse(self, path: Path, media_type: str, filename: str) -> ParsedDocument:
        """Parse a stored document into text and provenance sections."""


class Chunker(Protocol):
    def chunk(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        version_id: str,
        source_checksum: str,
        parsed: ParsedDocument,
    ) -> list[ChunkCandidate]:
        """Split extracted text into deterministic chunks."""


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        """Create embeddings for a batch of chunk texts."""
