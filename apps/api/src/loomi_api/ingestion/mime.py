from __future__ import annotations

import zipfile
from pathlib import Path

from loomi_api.ingestion.errors import UnsupportedMediaTypeError

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MARKDOWN = "text/markdown"
TEXT = "text/plain"
HTML = "text/html"
CSV = "text/csv"
PNG = "image/png"
JPEG = "image/jpeg"
TIFF = "image/tiff"
WEBP = "image/webp"

ALLOWED_MEDIA_TYPES = frozenset({PDF, DOCX, PPTX, MARKDOWN, TEXT, HTML, CSV, PNG, JPEG, TIFF, WEBP})
IMAGE_MEDIA_TYPES = frozenset({PNG, JPEG, TIFF, WEBP})

_EXTENSION_MEDIA_TYPES = {
    ".pdf": PDF,
    ".docx": DOCX,
    ".pptx": PPTX,
    ".md": MARKDOWN,
    ".markdown": MARKDOWN,
    ".txt": TEXT,
    ".text": TEXT,
    ".html": HTML,
    ".htm": HTML,
    ".csv": CSV,
    ".png": PNG,
    ".jpg": JPEG,
    ".jpeg": JPEG,
    ".tif": TIFF,
    ".tiff": TIFF,
    ".webp": WEBP,
}

_DANGEROUS_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".dmg",
    ".exe",
    ".js",
    ".msi",
    ".ps1",
    ".scr",
    ".sh",
    ".vbs",
}


def detect_media_type(path: Path, filename: str) -> str:
    extension = Path(filename).suffix.casefold()
    if extension in _DANGEROUS_EXTENSIONS:
        raise UnsupportedMediaTypeError(
            "unsupported_media_type",
            "Executable or script uploads are not supported.",
        )
    expected = _EXTENSION_MEDIA_TYPES.get(extension)
    if expected is None:
        raise UnsupportedMediaTypeError(
            "unsupported_media_type",
            "This file extension is not supported.",
        )

    header = path.read_bytes()[:4096]
    detected = _detect_from_header(path, header, expected)
    if detected != expected and not _is_textual_equivalent(expected, detected):
        raise UnsupportedMediaTypeError(
            "mime_mismatch",
            "The file content does not match its supported extension.",
        )
    if detected not in ALLOWED_MEDIA_TYPES:
        raise UnsupportedMediaTypeError(
            "unsupported_media_type", "This media type is not supported."
        )
    return expected


def _detect_from_header(path: Path, header: bytes, expected: str) -> str:
    if header.startswith(b"%PDF"):
        return PDF
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if header.startswith(b"\xff\xd8\xff"):
        return JPEG
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return TIFF
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return WEBP
    if header.startswith(b"PK\x03\x04"):
        return _detect_office_zip(path)
    if _looks_like_text(header):
        if expected in {MARKDOWN, TEXT, HTML, CSV}:
            return expected
        return TEXT
    raise UnsupportedMediaTypeError(
        "unsupported_media_type",
        "The uploaded content is not a supported document type.",
    )


def _detect_office_zip(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise UnsupportedMediaTypeError(
            "malformed_archive", "The Office archive is malformed."
        ) from exc
    if "[Content_Types].xml" not in names:
        raise UnsupportedMediaTypeError(
            "malformed_archive", "The Office archive is missing metadata."
        )
    if "word/document.xml" in names:
        return DOCX
    if any(name.startswith("ppt/slides/slide") and name.endswith(".xml") for name in names):
        return PPTX
    raise UnsupportedMediaTypeError(
        "unsupported_media_type", "This Office document is not supported."
    )


def _looks_like_text(header: bytes) -> bool:
    if b"\x00" in header:
        return False
    try:
        header.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _is_textual_equivalent(expected: str, detected: str) -> bool:
    return expected in {MARKDOWN, TEXT, HTML, CSV} and detected in {MARKDOWN, TEXT, HTML, CSV}
