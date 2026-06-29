"""
NeuronWriter plan enrichment (bidirectional)
============================================
Turns NeuronWriter from "scores our drafts" into "shapes the whole content plan". For the business's
priority keywords it runs a SERP+NLP analysis and feeds the results back into the plan:
  - the PAA / questions become each content brief's outline,
  - the must-cover terms/entities become content-gen grounding,
  - the competitor content scores become the target bar.

ONE shared, budget-aware cache (neuron_enrichments) is the entry point for BOTH planning and content
generation, so a keyword is analyzed at most once per ~month and the 75-analyses/month Gold cap is
never blown. Dormant-safe: no key -> every call is a {skipped} no-op.

Run:  python -m rep_engine.neuron_enrich run --business-id 1 --max 6
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import logging
import os

try:
    from .db import db
    from . import neuronwriter as nw
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import neuronwriter as nw  # type: ignore

log = logging.getLogger("neuron_enrich")

# Leave headroom under the Gold 75/mo analysis cap for ad-hoc content-gen analyses. The budget is
# enforced ACCOUNT-WIDE (nw.account_usage_this_month sums every project + hand-run UI analyses), so it
# holds even when each business analyzes under its own project. The guard fails CLOSED on an unknown
# count, and concurrent spends are serialized by a Postgres advisory lock so two jobs can't race past
# the cap. Net invariant: a keyword is analyzed at most ~once/month and the paid cap is never blown.
NEURON_MONTHLY_BUDGET = int(os.getenv("NEURON_MONTHLY_BUDGET", "70"))
_CACHE_FRESH_DAYS = 30
# Account-wide advisory-lock key serializing NeuronWriter analysis spends ("NURO" = 0x4E55524F).
_SPEND_LOCK_KEY = 0x4E55524F


def _norm_kw(keyword: str) -> str:
    """Canonical cache key for a keyword: trimmed, internal whitespace collapsed, lowercased. Storing
    AND looking up by this single form keeps the case-insensitive lookup in lock-step with the
    case-sensitive UNIQUE(business_id, keyword) constraint, so the same keyword can never spawn two
    rows (which would waste a paid analysis credit and split the cache)."""
    return " ".join((keyword or "").split()).lower()


def _as_dict(value) -> dict:
    """Coerce a JSONB column value to a dict. psycopg returns JSONB already-parsed (dict/list/str/None),
    so a malformed/degraded row (e.g. a stored array) must not crash a read -- return {} for anything
    that isn't a dict, parsing only a raw JSON string."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


@contextlib.contextmanager
def _spend_lock():
    """Non-blocking account-wide advisory lock that serializes NeuronWriter analysis SPENDS (not cache
    hits) so concurrent enrich/content-gen jobs cannot check-then-spend in parallel and race past the
    monthly cap. Yields True if acquired, False if another spend is already in flight (caller then
    serves cache / skips rather than risking an overspend). Best-effort: yields True if the lock can't
    be taken at all (no DB), so a degraded DB never blocks the feature entirely."""
    conn = None
    acquired = False
    try:
        conn = db()
        row = conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (_SPEND_LOCK_KEY,)).fetchone()
        acquired = bool(row and row.get("ok"))
        yield acquired
    except Exception as e:  # noqa: BLE001 -- lock is an optimization; never hard-fail the spend path
        log.debug("neuron spend-lock unavailable (%s); proceeding without serialization", e)
        yield True
    finally:
        if conn is not None:
            try:
                if acquired:
                    conn.execute("SELECT pg_advisory_unlock(%s)", (_SPEND_LOCK_KEY,))
            finally:
                conn.close()


def project_for(business_id: int) -> str | None:
    """Resolve the NeuronWriter project for a business: its own mapping -> NEURONWRITER_PROJECT ->
    the account's first project. A concrete id (so usage counting + analyses are scoped correctly).
    Dormant-safe: returns None immediately when NeuronWriter isn't configured."""
    if not nw.configured():
        return None
    with db() as conn:
        r = conn.execute("SELECT neuronwriter_project FROM businesses WHERE id=%s", (business_id,)).fetchone()
    p = (r and r["neuronwriter_project"]) or (os.getenv("NEURONWRITER_PROJECT") or "").strip() or None
    if p:
        return p
    projs = nw.list_projects()
    return projs[0].get("project") if projs and isinstance(projs[0], dict) else None


def _terms_list(value, limit: int = 40) -> list[str]:
    """NeuronWriter 'basic terms' arrive as a newline/comma-delimited string (terms_txt) or a list of
    ``{t: ...}`` objects. Normalize to a clean, de-duped list of term strings for briefs + the UI.
    (Content generation keeps the raw string for prompt concatenation; this is only for list consumers.)"""
    if isinstance(value, str):
        items = [t for part in value.split("\n") for t in part.split(",")]
    elif isinstance(value, list):
        items = [(t.get("t") or t.get("term") or "") if isinstance(t, dict) else str(t) for t in value]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in (s.strip() for s in items):
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:limit]


def _questions_list(ideas: dict, limit: int = 12) -> list[str]:
    """Pull PAA / content questions out of NeuronWriter ``ideas`` as plain strings, de-duped. Real
    Google People-Also-Ask leads (highest-intent, cleanest); competitor content-extracted questions
    follow for depth. Each idea is a ``{q: ...}`` dict (or occasionally a bare string)."""
    if not isinstance(ideas, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for src in ("people_also_ask", "content_questions", "suggest_questions"):
        for it in (ideas.get(src) or []):
            q = it.get("q") if isinstance(it, dict) else it
            q = q.strip() if isinstance(q, str) else ""
            if q and q.lower() not in seen:
                seen.add(q.lower())
                out.append(q)
                if len(out) >= limit:
                    return out
    return out


def _cached_row(business_id: int, keyword: str) -> dict | None:
    # Match on the canonical key, newest first, so a read is deterministic even if a legacy
    # mixed-case duplicate row still exists (we always serve the freshest analysis).
    with db() as conn:
        r = conn.execute(
            "SELECT keyword, query_id, terms, ideas, competitors, content_target, created_at "
            "FROM neuron_enrichments WHERE business_id=%s "
            "AND lower(btrim(regexp_replace(keyword, '\\s+', ' ', 'g')))=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (business_id, _norm_kw(keyword)),
        ).fetchone()
    return dict(r) if r else None


def _is_fresh(row: dict) -> bool:
    ca = row.get("created_at")
    if not ca:
        return False
    now = datetime.datetime.now(ca.tzinfo) if ca.tzinfo else datetime.datetime.now()
    return (now - ca).days <= _CACHE_FRESH_DAYS


def _to_brief(row: dict, *, budget_capped: bool = False) -> dict:
    """Shape a cached row like analyze()'s return so callers are uniform. ``budget_capped`` flags that
    this cache was served BECAUSE the monthly budget was hit (not a fresh-enough hit) so enrich() can
    report it as budget-skipped rather than a clean reuse."""
    terms = _as_dict(row.get("terms"))
    return {"query": row.get("query_id"), "keyword": row.get("keyword"),
            "content_score_target": float(row["content_target"]) if row.get("content_target") is not None else None,
            "terms_basic": terms.get("basic"), "terms_extended": terms.get("extended"),
            "terms_h1": terms.get("h1"), "terms_h2": terms.get("h2"),
            "ideas": _as_dict(row.get("ideas")), "competitors": row.get("competitors") or [],
            "cached": True, "budget_capped": budget_capped}


def _store(business_id: int, keyword: str, brief: dict) -> None:
    # Store under the canonical key so the case-sensitive UNIQUE(business_id, keyword) collapses
    # different-cased forms of the same keyword to ONE row (no duplicate -> no wasted credit).
    terms = {"basic": brief.get("terms_basic"), "extended": brief.get("terms_extended"),
             "h1": brief.get("terms_h1"), "h2": brief.get("terms_h2")}
    with db() as conn:
        conn.execute(
            """INSERT INTO neuron_enrichments
               (business_id, keyword, query_id, terms, ideas, competitors, content_target, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (business_id, keyword) DO UPDATE SET
                 query_id=EXCLUDED.query_id, terms=EXCLUDED.terms, ideas=EXCLUDED.ideas,
                 competitors=EXCLUDED.competitors, content_target=EXCLUDED.content_target,
                 created_at=now()""",
            (business_id, _norm_kw(keyword), brief.get("query"), json.dumps(terms),
             json.dumps(brief.get("ideas") or {}), json.dumps(brief.get("competitors") or []),
             brief.get("content_score_target")),
        )
        conn.commit()


def _budget_reached() -> bool:
    """True when the account-wide monthly analysis budget is reached OR the spend cannot be safely
    determined. Fails CLOSED: for a paid hard cap, an unknown count must block a new spend."""
    used = nw.account_usage_this_month()
    return used is None or used >= NEURON_MONTHLY_BUDGET


def brief_for(business_id: int, keyword: str, allow_new: bool = True, *, _cached: dict | None = None) -> dict:
    """The ONE entry point for a keyword's SERP brief, for both planning and content generation.
    Returns a fresh cache hit, else (if allowed + within the account-wide budget) runs+caches a new
    analysis, else the stale cache, else {skipped}. The spend is account-wide budget-guarded (fails
    closed) and serialized by an advisory lock so concurrent callers can never race past the cap.
    Pass ``_cached`` to reuse an already-fetched cache row (avoids a redundant DB read)."""
    if not nw.configured() or not keyword:
        return {"skipped": True, "reason": "neuronwriter not configured"}
    cached = _cached if _cached is not None else _cached_row(business_id, keyword)
    if cached and _is_fresh(cached):
        return _to_brief(cached)
    if not allow_new:
        return _to_brief(cached) if cached else {"skipped": True, "reason": "no cached brief"}
    project = project_for(business_id)
    if not project:
        return _to_brief(cached) if cached else {"skipped": True, "reason": "no NeuronWriter project"}
    # Serialize the check-then-spend so two jobs can't both pass the budget gate and double-spend.
    with _spend_lock() as got:
        if not got:
            log.info("neuron analysis already in flight; serving cache for '%s'", keyword)
            return (_to_brief(cached, budget_capped=True) if cached
                    else {"skipped": True, "reason": "another analysis in progress"})
        if _budget_reached():
            log.warning("neuron budget (%d/mo, account-wide) reached/unknown; reusing cache for '%s'",
                        NEURON_MONTHLY_BUDGET, keyword)
            return (_to_brief(cached, budget_capped=True) if cached
                    else {"skipped": True, "reason": "monthly analysis budget reached", "budget_capped": True})
        brief = nw.analyze(keyword, project=project)
        if brief.get("skipped"):
            return _to_brief(cached) if cached else brief
        _store(business_id, keyword, brief)
        return brief


def _feed_briefs(business_id: int) -> int:
    """Attach each cached keyword's SERP questions + must-cover terms onto matching content briefs
    (production_briefs) so the brief an operator/AI writes from is SERP-grounded. Best-effort."""
    updated = 0
    with db() as conn:
        # Newest first so a (legacy) duplicate keyword resolves to the freshest enrichment.
        enr = {}
        for r in conn.execute(
                "SELECT keyword, terms, ideas FROM neuron_enrichments WHERE business_id=%s "
                "ORDER BY created_at DESC", (business_id,)).fetchall():
            enr.setdefault(_norm_kw(r["keyword"]), r)
        if not enr:
            return 0
        briefs = conn.execute(
            "SELECT id, target_query, brief FROM production_briefs WHERE business_id=%s "
            "AND status='to_produce'", (business_id,)).fetchall()
        for b in briefs:
            tq = _norm_kw(b["target_query"] or "")
            row = enr.get(tq)
            if not row:  # loose contains match as a fallback
                row = next((v for k, v in enr.items() if tq and (tq in k or k in tq)), None)
            if not row:
                continue
            ideas = _as_dict(row["ideas"])
            terms = _as_dict(row["terms"])
            patch = {"serp_questions": _questions_list(ideas, limit=12),
                     "must_cover_terms": _terms_list(terms.get("basic"))}
            cur = _as_dict(b["brief"])
            cur["neuron"] = patch
            conn.execute("UPDATE production_briefs SET brief=%s WHERE id=%s", (json.dumps(cur), b["id"]))
            updated += 1
        conn.commit()
    return updated


def enrich(business_id: int, max_keywords: int = 6, quiet: bool = True) -> dict:
    """Analyze the business's top-priority keywords (account-wide budget-guarded) and feed the results
    into the content briefs. The `neuron_enrich` job entrypoint. Dormant-safe.

    Each spend is gated authoritatively by brief_for under the account-wide budget + advisory lock, so
    this loop holds no separate budget counter that could drift; it stops early once the cap is hit."""
    if not nw.configured():
        return {"skipped": True, "reason": "NEURON_API_KEY not set"}
    project = project_for(business_id)
    if not project:
        return {"skipped": True, "reason": "no NeuronWriter project (create one + map it to the business)"}
    used = nw.account_usage_this_month()
    with db() as conn:
        kws = [r["keyword"] for r in conn.execute(
            "SELECT keyword FROM target_keywords WHERE business_id=%s "
            "ORDER BY priority DESC NULLS LAST, keyword LIMIT %s", (business_id, max_keywords)).fetchall()]
    analyzed, reused, skipped = [], [], []
    for kw in kws:
        cached = _cached_row(business_id, kw)
        if cached and _is_fresh(cached):
            reused.append(kw); continue
        # brief_for re-checks the budget under the lock; thread the row we already read so it doesn't
        # re-query it. A budget_capped result means the cap was hit -> count as skipped, not reused.
        b = brief_for(business_id, kw, allow_new=True, _cached=cached)
        if b.get("skipped") or b.get("budget_capped"):
            skipped.append(kw)
        elif b.get("cached"):
            reused.append(kw)
        else:
            analyzed.append(kw)
    try:
        fed = _feed_briefs(business_id)
    except Exception as e:  # noqa: BLE001 -- feed is best-effort; never lose the analyses we paid for
        log.warning("neuron _feed_briefs failed (analyses still cached): %s", e)
        fed = 0
    out = {"project": project, "monthly_used_before": used, "budget": NEURON_MONTHLY_BUDGET,
           "analyzed": analyzed, "reused": reused, "skipped_over_budget_or_no_kw": skipped,
           "briefs_enriched": fed}
    if not quiet:
        print(json.dumps(out, indent=2, default=str))
    return out


def latest(business_id: int) -> list[dict]:
    """Read the cached enrichments for the plan/UI."""
    with db() as conn:
        rows = conn.execute(
            "SELECT keyword, content_target, terms, ideas, competitors, created_at "
            "FROM neuron_enrichments WHERE business_id=%s ORDER BY created_at DESC", (business_id,)).fetchall()
    out = []
    for r in rows:
        ideas = _as_dict(r["ideas"])
        terms = _as_dict(r["terms"])
        out.append({"keyword": r["keyword"],
                    "content_target": float(r["content_target"]) if r["content_target"] is not None else None,
                    "must_cover_terms": _terms_list(terms.get("basic")),
                    "questions": _questions_list(ideas, limit=8),
                    "competitors": r["competitors"], "analyzed_at": str(r["created_at"])})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeuronWriter plan enrichment")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--business-id", type=int, required=True); r.add_argument("--max", type=int, default=6)
    s = sub.add_parser("latest"); s.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        enrich(args.business_id, max_keywords=args.max, quiet=False)
    elif args.cmd == "latest":
        print(json.dumps(latest(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
