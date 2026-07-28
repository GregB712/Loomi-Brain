from __future__ import annotations

from pathlib import Path

import anyio

from loomi_api.config import Settings
from loomi_api.ingestion.errors import MalwareDetectedError, ScannerUnavailableError

_EICAR_FRAGMENT = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"
_LOOMI_TEST_FRAGMENT = b"LOOMI-MALWARE-TEST"


class ConfiguredMalwareScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def scan(self, path: Path) -> None:
        if self.settings.scanner_mode == "unavailable":
            if self.settings.scanner_required:
                raise ScannerUnavailableError(
                    "scanner_unavailable",
                    "The malware scanner is required but unavailable.",
                )
            return
        if self.settings.scanner_mode == "fake-reject":
            raise MalwareDetectedError(
                "malware_detected",
                "The malware scanner rejected the uploaded file.",
            )
        content = await anyio.to_thread.run_sync(path.read_bytes)
        if _EICAR_FRAGMENT in content or _LOOMI_TEST_FRAGMENT in content:
            raise MalwareDetectedError(
                "malware_detected",
                "The malware scanner rejected the uploaded file.",
            )
