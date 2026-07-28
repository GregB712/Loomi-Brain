from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from loomi_api.ingestion.chunking import ChunkingConfig, DeterministicChunker
from loomi_api.ingestion.contracts import ParsedDocument, ParsedSection


@given(st.text(min_size=1, max_size=4000))
@settings(max_examples=25)
def test_chunk_ids_are_stable(text: str) -> None:
    parsed = ParsedDocument(
        text=text,
        sections=(ParsedSection(text=text, page_number=1),),
        parser_name="test",
        parser_version="v1",
    )
    chunker = DeterministicChunker(
        ChunkingConfig(target_chars=300, overlap_chars=30, max_chunks=50)
    )

    first = chunker.chunk(
        owner_user_id="owner",
        document_id="doc",
        version_id="version",
        source_checksum="checksum",
        parsed=parsed,
    )
    second = chunker.chunk(
        owner_user_id="owner",
        document_id="doc",
        version_id="version",
        source_checksum="checksum",
        parsed=parsed,
    )

    assert [chunk.stable_id for chunk in first] == [chunk.stable_id for chunk in second]
    assert len(first) <= 50
