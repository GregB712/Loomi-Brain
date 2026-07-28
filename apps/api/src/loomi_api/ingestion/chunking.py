from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from loomi_api.ingestion.contracts import ChunkCandidate, ParsedDocument

CHUNKER_VERSION = "phase2-char-window-v1"


@dataclass(frozen=True)
class ChunkingConfig:
    target_chars: int
    overlap_chars: int
    max_chunks: int


class DeterministicChunker:
    version = CHUNKER_VERSION

    def __init__(self, config: ChunkingConfig) -> None:
        self.config = config

    def chunk(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        version_id: str,
        source_checksum: str,
        parsed: ParsedDocument,
    ) -> list[ChunkCandidate]:
        text = parsed.text.strip()
        if not text:
            return []

        candidates: list[ChunkCandidate] = []
        cursor = 0
        ordinal = 0
        while cursor < len(text) and ordinal < self.config.max_chunks:
            hard_end = min(len(text), cursor + self.config.target_chars)
            end = _choose_breakpoint(text, cursor, hard_end)
            chunk_text = text[cursor:end].strip()
            if chunk_text:
                text_sha = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                stable_id = _stable_chunk_id(
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                    version_id=version_id,
                    source_checksum=source_checksum,
                    text_sha256=text_sha,
                    ordinal=ordinal,
                )
                candidates.append(
                    ChunkCandidate(
                        ordinal=ordinal,
                        stable_id=stable_id,
                        text=chunk_text,
                        text_sha256=text_sha,
                        token_count=max(1, len(chunk_text) // 4),
                        provenance={
                            "chunker": self.version,
                            "parser": parsed.parser_name,
                            "parser_version": parsed.parser_version,
                            "page_number": _first_non_null(
                                section.page_number for section in parsed.sections
                            ),
                            "slide_number": _first_non_null(
                                section.slide_number for section in parsed.sections
                            ),
                            "sheet_name": _first_non_null(
                                section.sheet_name for section in parsed.sections
                            ),
                            "heading_path": list(parsed.sections[0].heading_path)
                            if parsed.sections
                            else [],
                            "source_start_offset": cursor,
                            "source_end_offset": end,
                            "source_checksum": source_checksum,
                            "sequence": ordinal,
                            "section_count": len(parsed.sections),
                            "warnings": list(parsed.warnings),
                        },
                    )
                )
                ordinal += 1
            if end >= len(text):
                break
            cursor = max(end - self.config.overlap_chars, cursor + 1)
        return candidates


def _choose_breakpoint(text: str, start: int, hard_end: int) -> int:
    if hard_end >= len(text):
        return len(text)
    window = text[start:hard_end]
    paragraph = window.rfind("\n\n")
    if paragraph > len(window) * 0.45:
        return start + paragraph
    sentence = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
    if sentence > len(window) * 0.55:
        return start + sentence + 1
    whitespace = window.rfind(" ")
    if whitespace > len(window) * 0.75:
        return start + whitespace
    return hard_end


def _first_non_null(values: Iterable[object | None]) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _stable_chunk_id(
    *,
    owner_user_id: str,
    document_id: str,
    version_id: str,
    source_checksum: str,
    text_sha256: str,
    ordinal: int,
) -> str:
    value = "|".join(
        [
            owner_user_id,
            document_id,
            version_id,
            source_checksum,
            text_sha256,
            str(ordinal),
            CHUNKER_VERSION,
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
