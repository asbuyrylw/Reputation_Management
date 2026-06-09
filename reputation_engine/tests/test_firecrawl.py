"""Firecrawl JS-render fallback tests (no live key; the fetch is mocked)."""

from __future__ import annotations

import pytest


def _thin_http():
    class R:
        failed = False
        status = 200
        text = "<html><head><title>App</title></head><body><div id=root></div></body></html>"
    return lambda *a, **k: R()


def _rich_html(words=200):
    return ("<html><head><title>Rendered Co</title>"
            "<meta name='description' content='A real rendered description here'></head>"
            "<body><h1>Welcome</h1><p>" + ("word " * words) + "</p></body></html>")


def test_firecrawl_triggers_on_thin_page(monkeypatch):
    from rep_engine import site_crawl as sc
    monkeypatch.setattr(sc, "FIRECRAWL_MODE", "auto")
    monkeypatch.setattr(sc, "FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setattr(sc._http, "request_json", _thin_http())
    monkeypatch.setattr(sc, "_firecrawl_fetch", lambda url: _rich_html(200))
    pa, _ = sc.audit_page("https://x.com", "https://x.com")
    assert pa.word_count > 120
    assert pa.title == "Rendered Co"
    assert "rendered_via_firecrawl" in pa.issues


def test_firecrawl_not_used_when_page_is_rich(monkeypatch):
    from rep_engine import site_crawl as sc
    monkeypatch.setattr(sc, "FIRECRAWL_MODE", "auto")
    monkeypatch.setattr(sc, "FIRECRAWL_API_KEY", "fc-test")

    class R:
        failed = False
        status = 200
        text = _rich_html(300)
    monkeypatch.setattr(sc._http, "request_json", lambda *a, **k: R())
    called = {"n": 0}
    def _fc(url):
        called["n"] += 1
        return _rich_html(300)
    monkeypatch.setattr(sc, "_firecrawl_fetch", _fc)
    pa, _ = sc.audit_page("https://x.com", "https://x.com")
    # rich page -> firecrawl never called, no marker
    assert called["n"] == 0
    assert "rendered_via_firecrawl" not in pa.issues


def test_firecrawl_off_mode_skips(monkeypatch):
    from rep_engine import site_crawl as sc
    monkeypatch.setattr(sc, "FIRECRAWL_MODE", "off")
    monkeypatch.setattr(sc, "FIRECRAWL_API_KEY", "")
    assert sc._firecrawl_fetch("https://x.com") is None


def test_info_marker_excluded_from_issue_counts():
    from rep_engine import site_crawl as sc
    p1 = sc.PageAudit(url="https://a.com")
    p1.issues = ["rendered_via_firecrawl", "thin_content"]
    p2 = sc.PageAudit(url="https://b.com")
    p2.issues = ["rendered_via_firecrawl"]
    summary = sc.summarize([p1, p2], lh={})
    # the info marker is not counted as an issue
    assert "rendered_via_firecrawl" not in summary["issue_counts"]
    # but it IS surfaced separately
    assert summary["rendered_via_firecrawl"] == 2
    # real issues still counted
    assert summary["issue_counts"].get("thin_content") == 1
