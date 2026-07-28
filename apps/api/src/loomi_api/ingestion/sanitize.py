from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_display_filename(filename: str | None) -> str:
    raw = filename or "document"
    basename = Path(raw.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", basename)
    normalized = _CONTROL_CHARS.sub("", normalized)
    normalized = normalized.replace("/", "").replace("\\", "")
    normalized = _WHITESPACE.sub(" ", normalized).strip(" .")
    if not normalized:
        return "document"
    return normalized[:180]


def sanitize_preview_text(text: str, *, limit: int = 40_000) -> str:
    clipped = text[:limit]
    without_controls = _CONTROL_CHARS.sub(" ", clipped)
    return html.escape(without_controls, quote=False)


def normalize_extracted_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return normalized.strip()


def safe_csv_cell(value: str) -> str:
    stripped = value.lstrip()
    if stripped.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value
