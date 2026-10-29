"""Local-filesystem storage backend (dev and single-node deploys).

Keys are ``{workspace_id}/{document_id}/{filename}``; every component is
validated so a crafted filename can never escape the storage root.
"""

import asyncio
from pathlib import Path

from app.config import settings
from app.storage.base import StorageBackend


class StorageError(Exception):
    """A key or filesystem operation is invalid/unusable."""


class LocalStorage:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.storage_dir).resolve()

    def _path(self, key: str) -> Path:
        parts = key.split("/")
        if not parts or any(p in ("", ".", "..") for p in parts):
            raise StorageError(f"invalid storage key: {key!r}")
        path = (self.root / Path(*parts)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError(f"storage key escapes root: {key!r}")
        return path

    async def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(self._write, path, data)

    async def load(self, key: str) -> bytes:
        path = self._path(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(self._unlink, path)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


_storage: LocalStorage | None = None


def get_storage() -> StorageBackend:
    """Module-level singleton; override via app.dependency_overrides in tests."""
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage
