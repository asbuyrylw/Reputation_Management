"""Central object storage for generated media + reports (Phase G.3).

Import the accessors; the S3-compatible backend registers itself lazily on first use.

    from rep_engine import storage
    if storage.configured():
        obj = storage.require_storage().upload_bytes(business_id, png_bytes, "quote-card.png")
        url = storage.get_storage().presigned_get(obj.key, expires_seconds=86400)
"""

from .base import (
    Storage,
    StorageError,
    StoredObject,
    configured,
    get_storage,
    require_storage,
    reset_cache,
)

__all__ = [
    "Storage",
    "StorageError",
    "StoredObject",
    "configured",
    "get_storage",
    "require_storage",
    "reset_cache",
]
