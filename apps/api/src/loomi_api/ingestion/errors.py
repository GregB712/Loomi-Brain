from __future__ import annotations


class IngestionError(Exception):
    """Safe ingestion failure that can be returned to the owner."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class UploadRejectedError(IngestionError):
    """Raised when an upload fails pre-ingestion validation."""


class ScannerUnavailableError(IngestionError):
    """Raised when policy requires a scanner but it is unavailable."""


class MalwareDetectedError(IngestionError):
    """Raised when the scanner rejects an uploaded object."""


class UnsupportedMediaTypeError(UploadRejectedError):
    """Raised when content or extension is unsupported."""


class ParserOutputLimitError(IngestionError):
    """Raised when extracted text exceeds configured bounds."""
