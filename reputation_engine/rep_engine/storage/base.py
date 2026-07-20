"""
Central object storage (Phase G.3) -- pluggable, S3-compatible.
================================================================
WHY THIS EXISTS. Generated media (images, rendered videos) + reports are written to the
container's EPHEMERAL disk today (visual_content._OUTPUT_DIR = "output/"), so every Railway
redeploy WIPES them and their DB `file_path` rows 404 -- a live data-loss defect. This layer
stores every generated asset in durable object storage and returns a stable KEY. Delivery is via
a presigned GET (bounded jobs, e.g. handing a URL to a cloud renderer) or an authenticated backend
proxy route (reports / in-app previews). One S3-compatible backend serves Railway Buckets
(private), Cloudflare R2, AWS S3, and self-hosted MinIO -- swapping providers is a config change,
not a code change.

FAIL-LOUD (reference invariant). A produce/publish step that runs without storage configured must
ERROR (`require_storage()`), never silently fall back to ephemeral disk under the illusion the file
will survive a redeploy. `verify()`/HEAD confirms an object is really stored + readable rather than
trusting a returned key -- a store that "succeeds" but can't be read would otherwise surface only
later as a broken render/report. StorageError is raised, never swallowed.

CONFIG. Reads env directly (dormant-safe, like source_material) -- no threading through config.py.
Railway Buckets inject BUCKET_ENDPOINT / BUCKET_NAME / BUCKET_ACCESS_KEY_ID / BUCKET_SECRET_ACCESS_KEY
when a bucket is connected to the service; generic REP_STORAGE_* / AWS_* are honored for R2/S3/MinIO.
`configured()` is False (and every producer stays on its current path) until those are set.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import quote

log = logging.getLogger("rep_engine.storage")

_REGISTRY: dict[str, type["Storage"]] = {}


def register(name: str):
    def deco(cls: type["Storage"]) -> type["Storage"]:
        _REGISTRY[name] = cls
        cls.provider = name
        return cls
    return deco


class StorageError(RuntimeError):
    """Storage config / upload / read failure. Raised, never swallowed -- a failed upload that
    returned a fake key/URL would surface as a broken render or a 404'd report later."""


@dataclass
class StoredObject:
    key: str
    bucket: str
    provider: str
    size: int
    content_type: str
    public_url: str | None = None   # a PERMANENT anonymous URL -- only when public_base_url is set
    meta: dict = field(default_factory=dict)


class Storage(ABC):
    """One object-storage backend. Subclasses implement the private _put/_head/_get/_delete +
    presigned_get + validate; the base handles idempotent per-business keying + the fail-loud
    upload contract + the public-URL shaping."""

    provider: str = "base"

    def __init__(self, config: dict):
        self.config = config or {}
        self.bucket = self.config.get("bucket", "")
        self.prefix = (self.config.get("prefix") or "assets").strip("/")
        self.public_base_url = (self.config.get("public_base_url") or "").rstrip("/")
        if not self.bucket:
            raise StorageError(f"{type(self).__name__} requires a bucket name in its config.")

    # --- backend hooks ------------------------------------------------------
    @abstractmethod
    def _put(self, key: str, data: bytes, content_type: str) -> None: ...
    @abstractmethod
    def _head(self, key: str) -> dict | None:
        """Object metadata dict, or None if the key does not exist. Raises StorageError on a real
        error (so 'not found' and 'the read broke' never look identical)."""
    @abstractmethod
    def _get(self, key: str) -> bytes: ...
    @abstractmethod
    def _delete(self, key: str) -> None: ...
    @abstractmethod
    def presigned_get(self, key: str, expires_seconds: int = 3600) -> str:
        """A time-limited signed GET URL -- the delivery path for a PRIVATE bucket (Railway). Set
        an expiry that outlasts the consumer's job; not suitable as a permanent public embed."""
    @abstractmethod
    def validate(self) -> tuple[bool, str]:
        """Cheap credential/bucket reachability check without uploading. (ok, message)."""

    # --- shared behaviour ---------------------------------------------------
    def key_for(self, business_id: int, filename: str, data: bytes) -> str:
        """Namespace by business + content hash so re-uploading identical bytes is idempotent
        (same key, same URL) and tenants never collide. Keeps a sanitized name + extension."""
        digest = hashlib.sha256(data).hexdigest()[:16]
        base = (filename or "asset").rsplit("/", 1)[-1]
        ext = ""
        if "." in base:
            ext = "." + "".join(c for c in base.rsplit(".", 1)[-1].lower() if c.isalnum())[:8]
            base = base.rsplit(".", 1)[0]
        safe = "".join(c for c in base if c.isalnum() or c in "-_")[:60] or "asset"
        return f"{self.prefix}/{business_id}/{safe}-{digest}{ext}"

    def upload_bytes(self, business_id: int, data: bytes, filename: str,
                     content_type: str | None = None) -> StoredObject:
        """Store bytes durably and return a StoredObject (stable key + optional public URL).
        Idempotent per (business, bytes). Raises StorageError on any failure -- never a fake key."""
        if not data:
            raise StorageError("Refusing to upload empty bytes.")
        ct = content_type or mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
        key = self.key_for(business_id, filename, data)
        try:
            self._put(key, data, ct)
        except StorageError:
            raise
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"{self.provider} upload failed for {key}: {e}") from e
        log.info("stored %d bytes -> %s/%s (%s)", len(data), self.bucket, key, self.provider)
        return StoredObject(key=key, bucket=self.bucket, provider=self.provider, size=len(data),
                            content_type=ct, public_url=self.public_url(key))

    def fetch(self, key: str) -> bytes:
        """Read the object's bytes with our own credentials (for the authenticated proxy route)."""
        return self._get(key)

    def head(self, key: str) -> dict | None:
        return self._head(key)

    def exists(self, key: str) -> bool:
        return self._head(key) is not None

    def delete(self, key: str) -> None:
        self._delete(key)

    def verify(self, key: str) -> bool:
        """Confirm the object is really stored + readable (HEAD with our creds). Cheap insurance
        against a misconfigured bucket that 'stores' but can't serve -- catch it now, not at render."""
        try:
            return self._head(key) is not None
        except Exception:  # noqa: BLE001
            return False

    def public_url(self, key: str) -> str | None:
        """A PERMANENT, unauthenticated URL -- ONLY when a public base URL is configured
        (S3-public / R2 public domain / custom domain). Private stores (Railway Buckets have no
        public URLs) return None; deliver via presigned_get() or the authenticated proxy route."""
        if self.public_base_url:
            return f"{self.public_base_url}/{quote(key)}"
        return None


# ---------------------------------------------------------------------------
# env-driven resolution (dormant-safe)
# ---------------------------------------------------------------------------
def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def _resolve_config() -> dict | None:
    """Build the storage config from env. A connected Railway Bucket injects the STANDARD AWS SDK
    vars (AWS_S3_BUCKET_NAME / AWS_ENDPOINT_URL / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
    AWS_DEFAULT_REGION); REP_STORAGE_* overrides are honored for R2/S3/MinIO or a manual setup.
    Returns None when storage isn't configured -- callers stay dormant, no exception."""
    bucket = _env("REP_STORAGE_BUCKET", "AWS_S3_BUCKET_NAME", "BUCKET_NAME", "S3_BUCKET")
    access = _env("REP_STORAGE_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "BUCKET_ACCESS_KEY_ID")
    secret = _env("REP_STORAGE_SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "BUCKET_SECRET_ACCESS_KEY")
    if not (bucket and access and secret):
        return None
    return {
        "provider": _env("REP_STORAGE_PROVIDER", default="s3"),
        "bucket": bucket,
        "endpoint": _env("REP_STORAGE_ENDPOINT", "AWS_ENDPOINT_URL", "BUCKET_ENDPOINT", "S3_ENDPOINT"),
        "access_key": access,
        "secret_key": secret,
        "region": _env("REP_STORAGE_REGION", "AWS_DEFAULT_REGION", "AWS_REGION", "BUCKET_REGION",
                       default="us-east-1"),
        "prefix": _env("REP_STORAGE_PREFIX", default="assets"),
        # Set ONLY if you front the bucket with a public domain (R2 public / CloudFront). Leave
        # unset for Railway Buckets (private) -> delivery is presigned / proxied.
        "public_base_url": _env("REP_STORAGE_PUBLIC_BASE_URL"),
    }


def configured() -> bool:
    """True when object storage is set up (Railway Bucket connected, or REP_STORAGE_*/AWS_* set)."""
    return _resolve_config() is not None


_CACHED: "Storage | None" = None


def get_storage() -> "Storage":
    """The configured storage backend (cached). Raises StorageError if storage isn't configured."""
    global _CACHED
    if _CACHED is not None:
        return _CACHED
    conf = _resolve_config()
    if not conf:
        raise StorageError(
            "No object storage configured. Connect a Railway Bucket to this service (injects "
            "BUCKET_ENDPOINT/BUCKET_NAME/BUCKET_ACCESS_KEY_ID/BUCKET_SECRET_ACCESS_KEY), or set "
            "REP_STORAGE_BUCKET/ENDPOINT/ACCESS_KEY/SECRET_KEY for R2/S3/MinIO.")
    from . import s3  # noqa: F401 -- import registers the S3-compatible backend(s)
    provider = conf.get("provider", "s3")
    cls = _REGISTRY.get(provider)
    if not cls:
        raise StorageError(f"Unknown storage provider {provider!r}. Available: {sorted(_REGISTRY)}.")
    _CACHED = cls(conf)
    return _CACHED


def require_storage() -> "Storage":
    """Fail-loud accessor for produce/publish steps: raises if storage isn't configured, so an asset
    is NEVER written to ephemeral disk under the illusion it will survive a redeploy."""
    return get_storage()


def reset_cache() -> None:
    """Drop the cached backend (tests / after an env change)."""
    global _CACHED
    _CACHED = None
