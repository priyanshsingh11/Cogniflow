"""Object storage abstraction for uploaded documents.

Dev uses a local folder; production swaps in Cloudflare R2 (an S3-compatible
bucket) at deploy time by providing another implementation — callers only
ever see opaque keys of the form ``{workspace_id}/{document_id}/{filename}``.
"""

from typing import Protocol


class StorageBackend(Protocol):
    async def save(self, key: str, data: bytes) -> None: ...

    async def load(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None:
        """Remove the object. Missing objects are not an error (idempotent)."""
        ...
