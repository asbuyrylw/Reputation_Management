"""Unit tests for the object-storage layer (Phase G.3) -- no DB, no network, no boto3.

Covers the shared base behaviour + the fail-loud config resolution. The live round-trip
(upload -> HEAD -> presign -> fetch) against a real bucket is a separate integration check run once
the Railway Bucket is connected.
"""
from __future__ import annotations

import pytest

from rep_engine.storage import base as st


class _Fake(st.Storage):
    """Concrete no-op backend so the abstract base's shared logic can be tested without boto3."""
    def _put(self, key, data, content_type): pass
    def _head(self, key): return None
    def _get(self, key): return b""
    def _delete(self, key): pass
    def presigned_get(self, key, expires_seconds=3600): return f"signed:{key}"
    def validate(self): return True, "ok"


def test_key_is_business_scoped_and_content_addressed():
    s = _Fake({"bucket": "b", "prefix": "assets"})
    k1 = s.key_for(7, "Quote Card.png", b"AAA")
    k2 = s.key_for(7, "Quote Card.png", b"AAA")
    k3 = s.key_for(7, "Quote Card.png", b"BBB")
    assert k1 == k2                  # identical bytes -> identical key (idempotent, same URL)
    assert k1 != k3                  # different bytes -> different key
    assert k1.startswith("assets/7/")
    assert k1.endswith(".png")
    assert " " not in k1             # sanitized
    assert s.key_for(9, "x.png", b"AAA").startswith("assets/9/")  # tenant-namespaced


def test_upload_rejects_empty_bytes():
    s = _Fake({"bucket": "b"})
    with pytest.raises(st.StorageError):
        s.upload_bytes(1, b"", "x.png")


def test_public_url_only_with_public_base():
    priv = _Fake({"bucket": "b"})                                   # private (e.g. Railway Bucket)
    assert priv.public_url("assets/1/x.png") is None
    pub = _Fake({"bucket": "b", "public_base_url": "https://cdn.example.com/"})
    assert pub.public_url("assets/1/x.png") == "https://cdn.example.com/assets/1/x.png"


def test_missing_bucket_is_a_config_error():
    with pytest.raises(st.StorageError):
        _Fake({})


_STORAGE_ENV = [
    "REP_STORAGE_ENDPOINT", "BUCKET_ENDPOINT", "S3_ENDPOINT",
    "REP_STORAGE_BUCKET", "BUCKET_NAME", "S3_BUCKET",
    "REP_STORAGE_ACCESS_KEY", "BUCKET_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID",
    "REP_STORAGE_SECRET_KEY", "BUCKET_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY",
]


def test_configured_false_and_require_raises_when_unset(monkeypatch):
    for v in _STORAGE_ENV:
        monkeypatch.delenv(v, raising=False)
    st.reset_cache()
    assert st.configured() is False
    with pytest.raises(st.StorageError):
        st.require_storage()


def test_configured_true_with_railway_bucket_vars(monkeypatch):
    for v in _STORAGE_ENV:
        monkeypatch.delenv(v, raising=False)
    st.reset_cache()
    # Railway injects these when a Bucket is connected to the service.
    monkeypatch.setenv("BUCKET_NAME", "reputation-assets")
    monkeypatch.setenv("BUCKET_ENDPOINT", "https://fly.storage.tigris.dev")
    monkeypatch.setenv("BUCKET_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("BUCKET_SECRET_ACCESS_KEY", "s")
    assert st.configured() is True
    conf = st._resolve_config()
    assert conf["bucket"] == "reputation-assets"
    assert conf["public_base_url"] == ""   # Railway Buckets are private -> no permanent public URL
