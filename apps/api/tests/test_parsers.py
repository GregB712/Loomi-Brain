from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from loomi_api.config import Settings
from loomi_api.ingestion.mime import CSV, DOCX, HTML, MARKDOWN, PPTX, TEXT
from loomi_api.ingestion.parsers import ParserRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "media_type", "content", "expected"),
    [
        ("note.md", MARKDOWN, b"# Heading\n\nHello **world**", "Hello"),
        ("note.txt", TEXT, b"plain text", "plain text"),
        ("table.csv", CSV, b"name,value\ncell,=SUM(A1:A2)\n", "'=SUM"),
        ("page.html", HTML, b"<h1>Title</h1><script>alert(1)</script><p>Body</p>", "Body"),
    ],
)
async def test_builtin_text_parsers(
    tmp_path: Path,
    filename: str,
    media_type: str,
    content: bytes,
    expected: str,
) -> None:
    path = tmp_path / filename
    path.write_bytes(content)

    parsed = await ParserRegistry(Settings(environment="test", storage_root=tmp_path)).parse(
        path, media_type, filename
    )

    assert expected in parsed.text
    assert "<script>" not in parsed.text


@pytest.mark.asyncio
async def test_docx_parser_uses_defused_xml(tmp_path: Path) -> None:
    path = tmp_path / "doc.docx"
    _write_zip(
        path,
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": (
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                "<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>"
            ),
        },
    )

    parsed = await ParserRegistry(Settings(environment="test", storage_root=tmp_path)).parse(
        path, DOCX, "doc.docx"
    )

    assert "Hello DOCX" in parsed.text


@pytest.mark.asyncio
async def test_pptx_parser_preserves_slide_provenance(tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    _write_zip(
        path,
        {
            "[Content_Types].xml": "<Types/>",
            "ppt/slides/slide1.xml": (
                "<p:sld xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main' "
                "xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'>"
                "<a:t>Slide text</a:t></p:sld>"
            ),
        },
    )

    parsed = await ParserRegistry(Settings(environment="test", storage_root=tmp_path)).parse(
        path, PPTX, "deck.pptx"
    )

    assert parsed.sections[0].slide_number == 1
    assert "Slide text" in parsed.text


def _write_zip(path: Path, members: dict[str, str]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
