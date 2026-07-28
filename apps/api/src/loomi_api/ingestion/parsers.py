from __future__ import annotations

import csv
import io
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from defusedxml import ElementTree  # type: ignore[import-untyped]
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from loomi_api.config import Settings
from loomi_api.ingestion.contracts import ParsedDocument, ParsedSection
from loomi_api.ingestion.errors import IngestionError, ParserOutputLimitError
from loomi_api.ingestion.mime import CSV, DOCX, HTML, IMAGE_MEDIA_TYPES, MARKDOWN, PDF, PPTX, TEXT
from loomi_api.ingestion.sanitize import normalize_extracted_text, safe_csv_cell

BUILTIN_PARSER_VERSION = "phase2-builtin-v1"
DOCLING_PARSER_VERSION = "docling-2.115.0"


class ParserRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.image_ocr = FakeOCRProvider(settings)

    async def parse(self, path: Path, media_type: str, filename: str) -> ParsedDocument:
        if self.settings.extraction_engine == "docling":
            return await OptionalDoclingParser(self.settings).parse(path, media_type, filename)

        if media_type == PDF:
            return _parse_pdf(path, self.settings)
        if media_type == DOCX:
            return _parse_docx(path, self.settings)
        if media_type == PPTX:
            return _parse_pptx(path, self.settings)
        if media_type == CSV:
            return _parse_csv(path, self.settings)
        if media_type == HTML:
            return _parse_html(path, self.settings)
        if media_type in {MARKDOWN, TEXT}:
            return _parse_text(path, media_type, self.settings)
        if media_type in IMAGE_MEDIA_TYPES:
            return await self.image_ocr.extract_text(path, media_type, filename)
        raise IngestionError("unsupported_media_type", "This media type has no parser.")


class OptionalDoclingParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def parse(self, path: Path, media_type: str, filename: str) -> ParsedDocument:
        try:
            from docling.document_converter import (  # type: ignore[import-not-found]
                DocumentConverter,
            )
        except ImportError as exc:
            raise IngestionError(
                "docling_unavailable",
                "Docling extraction is configured but the optional extra is not installed.",
            ) from exc
        converter = DocumentConverter()
        result = converter.convert(str(path))
        document = result.document
        text = _bounded_text(
            normalize_extracted_text(document.export_to_markdown()),
            self.settings,
        )
        return ParsedDocument(
            text=text,
            sections=(ParsedSection(text=text, page_number=1, classification="document"),),
            parser_name="docling",
            parser_version=DOCLING_PARSER_VERSION,
            metadata={"media_type": media_type, "filename": filename},
        )


class FakeOCRProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def extract_text(self, path: Path, media_type: str, filename: str) -> ParsedDocument:
        try:
            with Image.open(path) as image:
                width, height = image.size
                if width * height > self.settings.max_image_pixels:
                    raise IngestionError(
                        "image_too_large",
                        "The image dimensions exceed the configured OCR limit.",
                    )
                image.verify()
        except UnidentifiedImageError as exc:
            raise IngestionError("malformed_image", "The image could not be decoded.") from exc

        text = (
            f"OCR placeholder for {filename}. "
            f"Image media type: {media_type}. Dimensions: {width}x{height}."
        )
        return ParsedDocument(
            text=text,
            sections=(ParsedSection(text=text, page_number=1, classification="ocr"),),
            parser_name="fake-ocr",
            parser_version=BUILTIN_PARSER_VERSION,
            metadata={"media_type": media_type, "width": width, "height": height},
            warnings=("OCR is deterministic fake output in local/test mode.",),
        )


def _parse_pdf(path: Path, settings: Settings) -> ParsedDocument:
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as exc:
        raise IngestionError("malformed_pdf", "The PDF could not be parsed.") from exc
    page_count = len(reader.pages)
    if page_count > settings.max_pdf_pages:
        raise IngestionError("too_many_pages", "The PDF exceeds the configured page limit.")

    sections: list[ParsedSection] = []
    parts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = normalize_extracted_text(page.extract_text() or "")
        if not page_text:
            continue
        parts.append(page_text)
        sections.append(ParsedSection(text=page_text, page_number=page_number))
    text = _bounded_text(normalize_extracted_text("\n\n".join(parts)), settings)
    return ParsedDocument(
        text=text,
        sections=tuple(sections),
        parser_name="pypdf",
        parser_version=BUILTIN_PARSER_VERSION,
        metadata={"page_count": page_count},
    )


def _parse_docx(path: Path, settings: Settings) -> ParsedDocument:
    xml_bytes = _read_archive_member(path, "word/document.xml", settings)
    text = _text_from_xml(xml_bytes)
    normalized = _bounded_text(normalize_extracted_text(text), settings)
    return ParsedDocument(
        text=normalized,
        sections=(ParsedSection(text=normalized, page_number=1),),
        parser_name="docx-xml",
        parser_version=BUILTIN_PARSER_VERSION,
        metadata={"format": "docx"},
    )


def _parse_pptx(path: Path, settings: Settings) -> ParsedDocument:
    _validate_archive_limits(path, settings)
    sections: list[ParsedSection] = []
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for index, name in enumerate(slide_names, start=1):
            slide_text = normalize_extracted_text(_text_from_xml(archive.read(name)))
            if slide_text:
                sections.append(ParsedSection(text=slide_text, slide_number=index))
    text = _bounded_text(
        normalize_extracted_text("\n\n".join(section.text for section in sections)),
        settings,
    )
    return ParsedDocument(
        text=text,
        sections=tuple(sections),
        parser_name="pptx-xml",
        parser_version=BUILTIN_PARSER_VERSION,
        metadata={"slide_count": len(slide_names)},
    )


def _parse_text(path: Path, media_type: str, settings: Settings) -> ParsedDocument:
    text = _bounded_text(normalize_extracted_text(path.read_text(encoding="utf-8")), settings)
    classification = "markdown" if media_type == MARKDOWN else "text"
    return ParsedDocument(
        text=text,
        sections=(ParsedSection(text=text, page_number=1, classification=classification),),
        parser_name=classification,
        parser_version=BUILTIN_PARSER_VERSION,
        metadata={"media_type": media_type},
    )


def _parse_html(path: Path, settings: Settings) -> ParsedDocument:
    parser = _HTMLTextParser()
    parser.feed(path.read_text(encoding="utf-8"))
    text = _bounded_text(normalize_extracted_text(parser.text), settings)
    return ParsedDocument(
        text=text,
        sections=(ParsedSection(text=text, page_number=1, classification="html"),),
        parser_name="html-parser",
        parser_version=BUILTIN_PARSER_VERSION,
        metadata={"raw_html_rendered": False},
    )


def _parse_csv(path: Path, settings: Settings) -> ParsedDocument:
    source = path.read_text(encoding="utf-8-sig")
    output = io.StringIO()
    reader = csv.reader(io.StringIO(source))
    row_count = 0
    for row in reader:
        sanitized = [safe_csv_cell(cell) for cell in row]
        output.write("\t".join(sanitized))
        output.write("\n")
        row_count += 1
        if output.tell() > settings.max_parser_output_chars:
            raise ParserOutputLimitError(
                "parser_output_limit",
                "The CSV extraction exceeded the configured output limit.",
            )
    text = _bounded_text(normalize_extracted_text(output.getvalue()), settings)
    return ParsedDocument(
        text=text,
        sections=(ParsedSection(text=text, page_number=1, sheet_name="csv"),),
        parser_name="csv",
        parser_version=BUILTIN_PARSER_VERSION,
        metadata={"row_count": row_count, "formula_cells_prefixed": True},
    )


def _read_archive_member(path: Path, member: str, settings: Settings) -> bytes:
    _validate_archive_limits(path, settings)
    with zipfile.ZipFile(path) as archive:
        try:
            return archive.read(member)
        except KeyError as exc:
            raise IngestionError(
                "malformed_archive", "The Office document is missing content."
            ) from exc


def _validate_archive_limits(path: Path, settings: Settings) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > settings.max_archive_entries:
                raise IngestionError("archive_limit", "The archive has too many entries.")
            total = 0
            for info in infos:
                parts = Path(info.filename).parts
                if info.filename.startswith("/") or ".." in parts:
                    raise IngestionError(
                        "archive_path_traversal", "The archive contains an unsafe path."
                    )
                total += info.file_size
                if total > settings.max_archive_uncompressed_bytes:
                    raise IngestionError(
                        "archive_limit",
                        "The archive exceeds the configured extraction limit.",
                    )
    except zipfile.BadZipFile as exc:
        raise IngestionError("malformed_archive", "The Office archive is malformed.") from exc


def _text_from_xml(xml_bytes: bytes) -> str:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise IngestionError("malformed_xml", "The Office XML could not be parsed safely.") from exc
    values: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) == "t" and element.text:
            values.append(element.text)
    return " ".join(values)


def _local_name(tag: Any) -> str:
    value = str(tag)
    if "}" in value:
        return value.rsplit("}", 1)[1]
    return value


def _bounded_text(text: str, settings: Settings) -> str:
    if len(text) > settings.max_parser_output_chars:
        raise ParserOutputLimitError(
            "parser_output_limit",
            "The extracted text exceeds the configured output limit.",
        )
    return text


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    @property
    def text(self) -> str:
        return " ".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "template"}:
            self._skip_depth += 1
        if tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)
