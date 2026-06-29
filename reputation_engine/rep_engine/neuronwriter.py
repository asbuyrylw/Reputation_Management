"""
NeuronWriter API client (content-optimization layer)
====================================================
Buy-not-build: instead of replicating a SERP-scrape + NLP term-extraction engine, we call
NeuronWriter's API for the content-optimization layer -- the SERP+NLP TERM/ENTITY/HEADING
recommendations and the per-draft CONTENT SCORE -- and combine them with OUR reputation/AEO/
compliance engine. (Their AI-Visibility module is deliberately NOT used -- that overlaps our core
multi-engine answer audit + citation share-of-voice.)

Flow:
  analyze(keyword)  -> POST /new-query (1 monthly analysis credit) then poll /get-query (free) for
                       terms / terms_txt (H1/H2 term lists) / ideas (PAA) / competitors (+score).
  score(query, html)-> POST /evaluate-content (free) -> a 0-100 content_score for a draft.

Keyless/dormant-safe: with no NEURONWRITER_API_KEY every call returns {"skipped": ...} and nothing
breaks. Host-pinned to app.neuronwriter.com via the SSRF-guarded http client.

Docs: https://neuronwriter.com/faqs/neuronwriter-api-how-to-use/  (Gold plan or higher required.)
"""

from __future__ import annotations

import logging
import os
import time

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

log = logging.getLogger("neuronwriter")

_BASE = "https://app.neuronwriter.com/neuron-api/0.5/writer"


def _key() -> str:
    return (os.getenv("NEURONWRITER_API_KEY") or os.getenv("NEURON_API_KEY") or "").strip()


def configured() -> bool:
    return bool(_key())


def _default_project() -> str:
    return (os.getenv("NEURONWRITER_PROJECT") or "").strip()


def _post(method: str, body: dict, *, timeout: int = 30) -> dict | None:
    """POST to a NeuronWriter endpoint. Returns the parsed dict, or None on failure/not-configured."""
    if not configured():
        return None
    res = _http.request_json(
        "POST", f"{_BASE}/{method}",
        headers={"X-API-KEY": _key(), "Content-Type": "application/json"},
        json=body, timeout=timeout, max_retries=2, guard_redirects=True,
    )
    # list-projects / list-queries return a JSON ARRAY; the rest return an OBJECT -- accept both.
    if res.failed or not isinstance(res.data, (dict, list)):
        if res.failed:
            log.warning("neuronwriter %s failed: %s", method, res.error)
        return None
    return res.data


def list_projects() -> list[dict]:
    data = _post("list-projects", {})
    if not isinstance(data, list):
        # some deployments wrap it; tolerate {projects:[...]} or a bare list
        data = (data or {}).get("projects") if isinstance(data, dict) else None
    return data or []


def _resolve_project(project: str | None) -> str | None:
    if project:
        return project
    p = _default_project()
    if p:
        return p
    projs = list_projects()
    return (projs[0].get("project") if projs and isinstance(projs[0], dict) else None)


def new_query(keyword: str, *, project: str | None = None, engine: str = "google.com",
              language: str = "English", competitors_mode: str = "top10") -> str | None:
    """Start a SERP+NLP analysis (costs ONE monthly analysis credit). Returns the query id or None."""
    proj = _resolve_project(project)
    if not proj:
        log.warning("neuronwriter new_query: no project (set NEURONWRITER_PROJECT or create one)")
        return None
    data = _post("new-query", {"project": proj, "keyword": keyword, "engine": engine,
                               "language": language, "competitors_mode": competitors_mode})
    return (data or {}).get("query")


def get_query(query: str) -> dict | None:
    """Retrieve a query's status + recommendations (free). status: not found|waiting|in progress|ready."""
    return _post("get-query", {"query": query})


def list_queries(project: str, *, source: str | None = None) -> list[dict]:
    """List queries (analyses) in a project (free). source='neuron-api' = those WE created via API."""
    if not project:
        return []
    body = {"project": project}
    if source:
        body["source"] = source
    data = _post("list-queries", body)
    if isinstance(data, dict):
        data = data.get("queries")
    return data or []


def _month_prefix() -> str:
    """Current calendar month as YYYY-MM in UTC -- NeuronWriter 'created' timestamps are UTC, so we
    compare apples to apples and avoid an off-by-one at month boundaries in non-UTC server TZs."""
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


def usage_this_month(project: str, *, source: str | None = "neuron-api") -> int:
    """How many analyses were created this calendar month under a single project. ``source='neuron-api'``
    (default) counts only the ones WE created via API; ``source=None`` counts ALL analyses (incl. ones
    run by hand in the NeuronWriter UI), which share the same account quota. 0 on any failure."""
    if not configured() or not project:
        return 0
    prefix = _month_prefix()
    n = 0
    for q in list_queries(project, source=source):
        if str((q or {}).get("created") or "")[:7] == prefix:
            n += 1
    return n


def account_usage_this_month() -> "int | None":
    """Total analyses spent this calendar month ACROSS ALL PROJECTS and ALL sources -- the Gold monthly
    cap (~75) is account-wide, so THIS is the authoritative budget figure (a per-project count cannot
    enforce an account-wide cap, and hand-run UI analyses draw from the same quota).

    Returns ``None`` when usage cannot be determined (list-projects/list-queries failed). Callers MUST
    treat ``None`` as 'cap reached' and fail CLOSED -- for a paid hard cap, refusing to spend on an
    unknown count is safer than risking an overspend. Returns 0 only when genuinely no analyses exist."""
    if not configured():
        return 0
    projs = _post("list-projects", {})
    if isinstance(projs, dict):
        projs = projs.get("projects")
    if not isinstance(projs, list):
        return None  # list-projects failed -> usage unknown -> fail closed
    prefix = _month_prefix()
    total = 0
    for p in projs:
        pid = p.get("project") if isinstance(p, dict) else None
        if not pid:
            continue
        data = _post("list-queries", {"project": pid})  # no source filter -> the FULL account spend
        if isinstance(data, dict):
            data = data.get("queries")
        if not isinstance(data, list):
            return None  # a project's usage is unknown -> fail closed
        for q in data:
            if str((q or {}).get("created") or "")[:7] == prefix:
                total += 1
    return total


def analyze(keyword: str, *, project: str | None = None, engine: str = "google.com",
            language: str = "English", max_wait_s: int = 150, poll_s: int = 12) -> dict:
    """End-to-end: start an analysis and poll until ready, returning the compact recommendations a
    content brief needs. Meant for the content-generation JOB (an analysis takes ~60s), not a live
    request. Dormant-safe: returns {"skipped": True} with no key."""
    if not configured():
        return {"skipped": True, "reason": "NEURONWRITER_API_KEY not set"}
    qid = new_query(keyword, project=project, engine=engine, language=language)
    if not qid:
        return {"skipped": True, "reason": "could not start analysis (project/credits?)"}
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        data = get_query(qid) or {}
        status = (data.get("status") or "").lower()
        if status == "ready":
            terms = data.get("terms") or {}
            txt = data.get("terms_txt") or {}
            comps = data.get("competitors") or []
            # A meaningful target so the gauge reads "43 of ~74": prefer the API's metric, else the
            # best competitor's content score (beating the top-ranked page is the real bar).
            target = (data.get("metrics") or {}).get("target_content_score")
            if target is None:
                cs = [c.get("content_score") for c in comps if isinstance(c.get("content_score"), (int, float))]
                target = max(cs) if cs else None
            return {
                "query": qid, "keyword": keyword,
                "content_score_target": target,
                "terms_basic": txt.get("content_basic"),
                "terms_extended": txt.get("content_extended"),
                "terms_title": txt.get("title"), "terms_h1": txt.get("h1"), "terms_h2": txt.get("h2"),
                "terms": terms,
                "ideas": data.get("ideas") or {},
                "competitors": [{"rank": c.get("rank"), "url": c.get("url"), "title": c.get("title"),
                                 "content_score": c.get("content_score")}
                                for c in (data.get("competitors") or [])][:10],
            }
        if status in ("not found",):
            return {"skipped": True, "reason": "query not found"}
        time.sleep(poll_s)
    return {"skipped": True, "reason": "analysis timed out", "query": qid}


def score(query: str, html: str, *, title: str = "", description: str = "") -> dict:
    """Score a draft against an existing analysis WITHOUT saving a revision (free). Returns
    {content_score} or {skipped}. Use the `query` id returned by analyze()."""
    if not configured():
        return {"skipped": True, "reason": "NEURONWRITER_API_KEY not set"}
    data = _post("evaluate-content", {"query": query, "html": html, "title": title,
                                      "description": description})
    if not data:
        return {"skipped": True, "reason": "evaluate-content failed"}
    return {"content_score": data.get("content_score"), "status": data.get("status")}


def verify() -> bool:
    """Cheap liveness check: list projects works iff the key is valid."""
    if not configured():
        return False
    return isinstance(_post("list-projects", {}), (list, dict))
