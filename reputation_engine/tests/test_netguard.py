"""No-DB / no-network tests for the SSRF guard (netguard.py).

All cases use IP-literal hosts or a monkeypatched resolver, so the suite stays
deterministic with no DNS / network access.
"""

from __future__ import annotations

import pytest

from rep_engine import netguard
from rep_engine.netguard import UnsafeURLError, assert_url_allowed, is_safe_url


def test_blocks_private_loopback_linklocal_metadata_and_bad_scheme(monkeypatch):
    blocked = [
        "http://127.0.0.1/",                          # loopback
        "http://10.0.0.1/",                           # private
        "http://192.168.1.1/",                        # private
        "http://169.254.169.254/latest/meta-data/",   # link-local + metadata
        "http://[::1]/",                              # IPv6 loopback
        "file:///etc/passwd",                         # disallowed scheme
        "http:///nohost",                             # no host
    ]
    for url in blocked:
        assert is_safe_url(url) is False
        with pytest.raises(UnsafeURLError):
            assert_url_allowed(url)
    # 'localhost' resolves to loopback -- resolver monkeypatched for determinism.
    monkeypatch.setattr(netguard.socket, "getaddrinfo",
                        lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    assert is_safe_url("http://localhost/") is False


def test_allows_public_ip_and_respects_disable_flag(monkeypatch):
    # Public IP literal -> allowed, no DNS needed.
    assert is_safe_url("http://8.8.8.8/") is True
    # Disable flag is read at call time -> a no-op even for an internal target.
    monkeypatch.setenv("CRAWL_SSRF_GUARD", "0")
    assert assert_url_allowed("http://127.0.0.1/") is None


def test_redirect_to_internal_is_blocked(monkeypatch):
    from rep_engine import http as h

    class _Next:
        url = "http://169.254.169.254/"

    class _Resp:
        status_code = 302
        is_redirect = True
        next = _Next()
        headers: dict = {}
        text = ""

        def json(self):
            return {}

    monkeypatch.setattr(h.requests, "request", lambda *a, **k: _Resp())
    res = h.request_json("GET", "http://example.com/", guard_redirects=True)
    assert res.ok is False
    assert "redirect blocked by SSRF guard" in (res.error or "")
