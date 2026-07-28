from __future__ import annotations

import secrets
from pathlib import Path

from loomi_api.ingestion.errors import IngestionError


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def reserve_key(self, owner_user_id: str, document_id: str, version_id: str) -> str:
        random_name = f"{secrets.token_urlsafe(24)}.bin"
        return f"owners/{owner_user_id}/documents/{document_id}/versions/{version_id}/{random_name}"

    def path_for_key(self, key: str) -> Path:
        if key.startswith("/") or ".." in Path(key).parts:
            raise IngestionError("invalid_object_key", "Stored object key is invalid.")
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise IngestionError("invalid_object_key", "Stored object key escapes private storage.")
        return candidate

    def move_private_file(self, source: Path, key: str) -> Path:
        destination = self.path_for_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        return destination

    def delete(self, key: str) -> None:
        self.path_for_key(key).unlink(missing_ok=True)
