"""
Reputation Crowding-Out Engine -- Katteb API client (content scoring layer + flagship generation)
==================================================================================================
Katteb (app.katteb.com) is a paid AI-content platform. Our OWN generator stays the primary engine
(cheap, uncapped); Katteb is used SELECTIVELY as a quality/scoring layer + a few flagship articles,
because the credit budget is small:

    Plan appsumo_1, 1x multiplier, 20,000 credits/month.
      seo/analyze        = 1,000 credits   (competitor + SEO score; HEAVY: 50/day, 1/min)
      articles/generate  = 1,500 base (+500 featured image, +5 tldr)  (HEAVY: 50/day)
      humanizer/rewrite  = 100    humanizer/detect = 1    factcheck/verify = 100
      account/*, *_get, *_list = 0 (reads: 30/min)

So ~13 flagship articles OR ~20 SEO analyses per month. Everything here is HUMAN-TRIGGERED (never
an automatic per-draft spend) and DORMANT-SAFE: `configured()` is False without KATTEB_API_KEY and
every call returns {skipped:True} rather than raising. 402 (out of credits) and 429 (rate limit)
are surfaced as friendly errors, never exceptions.

Auth: Bearer token. Base URL carries the endpoint in the query string
(`https://app.katteb.com/api/v2/?endpoint=<name>`); GET params (e.g. &id=) merge on.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

log = logging.getLogger("katteb")

_DEFAULT_BASE = "https://app.katteb.com/api/v2/?endpoint="


def _key() -> str:
    return os.getenv("KATTEB_API_KEY", "").strip()


def _base() -> str:
    return (os.getenv("KATTEB_API_URL") or _DEFAULT_BASE).strip()


def configured() -> bool:
    return bool(_key())


def _call(method: str, endpoint: str, *, params: Optional[dict] = None,
          json: Optional[dict] = None, timeout: int = 30) -> dict:
    """One Katteb API call -> a plain dict. Never raises. Shapes failures as
    {ok:False, error, status} with friendly messages for out-of-credits / rate-limit."""
    if not configured():
        return {"skipped": True, "reason": "Katteb not configured (set KATTEB_API_KEY)"}
    url = _base() + endpoint
    hdr = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}
    res = _http.request_json(method, url, headers=hdr, params=params, json=json,
                             timeout=timeout, max_retries=2, guard_redirects=True)
    if res.failed:
        if res.status == 402:
            return {"ok": False, "status": 402, "error": "Out of Katteb credits for this month."}
        if res.status == 429:
            return {"ok": False, "status": 429, "error": "Katteb rate limit hit — try again shortly."}
        return {"ok": False, "status": res.status, "error": res.error or "Katteb request failed"}
    data = res.data if isinstance(res.data, dict) else {}
    return {"ok": True, **data}


# ---------------------------------------------------------------------------
# Account (free reads)
# ---------------------------------------------------------------------------
def credits() -> dict:
    """{credits_available, credits_total, plan_type, plan_tier, ...} or {skipped}/{ok:False}."""
    return _call("GET", "account/credits")


def limits() -> dict:
    return _call("GET", "account/limits")


# ---------------------------------------------------------------------------
# SEO analysis (competitor + SEO score) -- the "Analyze Competitors" data. HEAVY, 1000 credits.
# ---------------------------------------------------------------------------
def seo_analyze(value: str, *, keyword: Optional[str] = None, kind: str = "text",
                brand_id: Optional[int] = None) -> dict:
    """Submit a SEO/competitor analysis. kind='text' (raw HTML/text) or 'url'. Returns a job with
    job_id + poll_url; poll seo_get(job_id) until status=completed."""
    body: dict = {"type": kind, "value": value}
    if keyword:
        body["keyword"] = keyword
    if brand_id:
        body["brand_id"] = brand_id
    return _call("POST", "seo/analyze", json=body, timeout=45)


def seo_get(job_id: int) -> dict:
    return _call("GET", "seo/get", params={"id": job_id}, timeout=30)


def _poll(job_id: int, getter, *, max_polls: int = 24, poll_s: int = 8) -> dict:
    """Poll a *_get endpoint until status is terminal. Returns the final payload or an error."""
    for _ in range(max_polls):
        time.sleep(poll_s)
        r = getter(job_id)
        if not r.get("ok"):
            return r
        status = (r.get("status") or "").lower()
        if status in ("completed", "failed", "cancelled", "error"):
            return r
    return {"ok": False, "error": "Katteb job timed out (still processing) — check back shortly.",
            "job_id": job_id, "status": "processing"}


def seo_analyze_wait(value: str, *, keyword: Optional[str] = None, kind: str = "text",
                     brand_id: Optional[int] = None, max_polls: int = 24, poll_s: int = 8) -> dict:
    """Submit + poll a SEO analysis to completion. Human-triggered only (1000 credits)."""
    sub = seo_analyze(value, keyword=keyword, kind=kind, brand_id=brand_id)
    if sub.get("skipped") or not sub.get("ok"):
        return sub
    jid = sub.get("job_id")
    if not jid:
        return {"ok": False, "error": "Katteb did not return a job id"}
    out = _poll(jid, seo_get, max_polls=max_polls, poll_s=poll_s)
    out.setdefault("job_id", jid)
    out.setdefault("keyword", sub.get("keyword"))
    out.setdefault("credits_charged", sub.get("credits_charged"))
    return out


# ---------------------------------------------------------------------------
# Humanizer + fact-check (cheap-ish quality tools)
# ---------------------------------------------------------------------------
def humanize_detect(text: str, *, language: str = "English") -> dict:
    """AI-probability detector (1 credit). {ai_probability, verdict}."""
    return _call("POST", "humanizer/detect", json={"text": text[:50000], "language": language})


def humanize_rewrite(text: str, *, strength: str = "Moderate", language: str = "English",
                     brand_id: Optional[int] = None) -> dict:
    """Rewrite text to read more human (100 credits). {rewritten_text}."""
    body: dict = {"text": text[:50000], "strength": strength, "language": language}
    if brand_id:
        body["brand_id"] = brand_id
    return _call("POST", "humanizer/rewrite", json=body, timeout=60)


def factcheck(claim: str, *, brand_id: Optional[int] = None) -> dict:
    """Verify one claim (3-300 words, 100 credits). {verdict, is_fact, explanation, references}."""
    body: dict = {"text": claim}
    if brand_id:
        body["brand_id"] = brand_id
    return _call("POST", "factcheck/verify", json=body, timeout=60)


# ---------------------------------------------------------------------------
# Flagship article generation (1500+ credits, HEAVY). Human-triggered for select pieces only.
# ---------------------------------------------------------------------------
def article_generate(topic: str, *, language: str = "English", country: str = "us",
                     word_count: int = 1500, guidelines: Optional[str] = None,
                     enhancements: Optional[list[str]] = None, writing_style_id: Optional[int] = None,
                     brand_id: Optional[int] = None) -> dict:
    body: dict = {"topic": topic[:500], "language": language, "country": country,
                  "word_count": max(500, min(5000, word_count))}
    if guidelines:
        body["guidelines"] = guidelines[:2000]
    if enhancements:
        body["enhancements"] = enhancements
    if writing_style_id:
        body["writing_style_id"] = writing_style_id
    if brand_id:
        body["brand_id"] = brand_id
    return _call("POST", "articles/generate", json=body, timeout=45)


def article_get(job_id: int) -> dict:
    return _call("GET", "articles/get", params={"id": job_id}, timeout=30)


def article_generate_wait(topic: str, *, max_polls: int = 40, poll_s: int = 10, **opts) -> dict:
    """Submit + poll an article to completion. Human-triggered only (1500+ credits)."""
    sub = article_generate(topic, **opts)
    if sub.get("skipped") or not sub.get("ok"):
        return sub
    jid = sub.get("job_id")
    if not jid:
        return {"ok": False, "error": "Katteb did not return a job id"}
    out = _poll(jid, article_get, max_polls=max_polls, poll_s=poll_s)
    out.setdefault("job_id", jid)
    out.setdefault("credits_charged", sub.get("credits_charged"))
    return out


if __name__ == "__main__":  # pragma: no cover -- quick smoke: python -m rep_engine.katteb
    import json as _j
    print(_j.dumps(credits(), indent=2))
