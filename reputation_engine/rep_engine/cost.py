"""
Reputation Crowding-Out Engine -- Cost Tracking + Budget Caps
=============================================================
Lightweight helper to (a) estimate and record the cost of each model call into
the cost_ledger table, and (b) enforce a per-business monthly budget so audits
can't run away. Used by ai_state_audit's LLM/answer-engine calls.

Pricing is approximate and MUST be updated to current rates -- see PRICING.
Costs are estimates for budgeting/COGS visibility, not billing-grade figures.
"""

from __future__ import annotations

import json
import logging
import os


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("cost")


# Approx USD unit cost for NON-token external services (flat/per-unit). Env-overridable so rates can
# be corrected without a deploy. These are estimates for COGS visibility; where a provider returns an
# exact cost (e.g. DataForSEO), we record THAT instead of these.
def _envf(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


EXT_PRICING = {
    # category           : (usd_per_unit, unit_label)
    "search":       (_envf("COST_SERPER_PER_SEARCH", 0.001), "searches"),      # Serper ~ $1/1k
    "keyword_volume": (_envf("COST_DATAFORSEO_PER_REQ", 0.05), "requests"),    # DataForSEO fallback if no exact cost
    "image":        (_envf("COST_IMAGE_PER_GEN", 0.04), "images"),             # Imagen/GPT-image ~ $0.04
    "video":        (_envf("COST_VIDEO_PER_SEC", 0.40), "seconds"),            # Veo ~ $0.40/sec
    "audio":        (_envf("COST_AUDIO_PER_MIN", 0.10), "minutes"),            # NotebookLM audio (approx)
    "katteb":       (_envf("COST_KATTEB_PER_CREDIT", 0.0), "credits"),         # 20k free/mo -> $0 marginal
    "analytics":    (0.0, "requests"),   # GA4 Data API — free
    "search_console": (0.0, "requests"), # GSC API — free
    "pagespeed":    (0.0, "requests"),   # PageSpeed Insights — free
}


def ext_estimate(category: str, units: float) -> tuple[float, str]:
    """Estimated flat cost + unit label for a non-token service. Unknown category -> (0, 'units')."""
    rate, label = EXT_PRICING.get(category, (0.0, "units"))
    return round(rate * float(units or 0), 6), label


# Approx USD per 1K tokens (input, output). UPDATE to current provider pricing.  PH 2
PRICING = {
    # model substring : (input_per_1k, output_per_1k). Rates current as of 2026-06.
    # NOTE: more specific keys MUST come first (substring match stops at first hit).
    # Anthropic ids look like claude-opus-4-8 / claude-sonnet-4-6 / claude-haiku-4-5,
    # so 'opus'/'sonnet'/'haiku' MUST precede the generic 'claude' fallback -- otherwise
    # 'claude' would catch claude-opus-4-8 at Sonnet's cheaper rate and UNDER-count Opus.
    "haiku":       (0.001, 0.005),   # Haiku 4.5 cheap tier (Anthropic)
    "gpt-4o-mini": (0.00015, 0.0006),  # cheap tier (OpenAI)
    "opus":        (0.005, 0.025),   # Opus 4.8 full tier (Anthropic)
    "sonnet":      (0.003, 0.015),   # Sonnet 4.6 mid tier (Anthropic)
    "claude":      (0.003, 0.015),   # generic Anthropic fallback (Sonnet-equivalent)
    "gpt-4o":      (0.005, 0.015),
    "gpt":         (0.005, 0.015),
    "sonar":       (0.001, 0.001),   # perplexity (approx; varies by model)
    "gemini":      (0.00125, 0.005),
    "_default":    (0.003, 0.015),
}




# Per-business count of cost rows we failed to persist this process. While a business
# has > 0 unrecorded writes its ledger under-counts real spend, so over_budget(business)
# fails CLOSED -- but for THAT business only. A single transient DB blip therefore no
# longer bricks every tenant for the process lifetime, and the flag SELF-HEALS: the next
# successful cost write for a business clears its entry. (A write with business_id=None is
# unattributable to a tenant, so we log it loudly but never let it fail-close other tenants.)
_unrecorded_writes: dict[int, int] = {}


def reset_unrecorded() -> None:
    """Clear the fail-closed flags (test isolation / operational recovery)."""
    _unrecorded_writes.clear()


def _rate(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, rate in PRICING.items():
        if key != "_default" and key in m:
            return rate
    return PRICING["_default"]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    ri, ro = _rate(model)
    return round((input_tokens / 1000.0) * ri + (output_tokens / 1000.0) * ro, 5)


def approx_tokens(text: str) -> int:
    """Rough token estimate when the provider doesn't return usage (~4 chars/token)."""
    return max(1, int(len(text or "") / 4))


# Map an LLM operation name -> a rollup category, so the ledger buckets audit vs gap vs strategy vs
# content spend without touching the dozens of existing record() call sites.
_LLM_CATEGORY = {
    "answer": "llm_audit", "score": "llm_audit", "gap_model": "llm_gap", "gap_critic": "llm_gap",
    "content_draft": "llm_content", "atomize": "llm_content", "outline": "llm_content",
    "strategy": "llm_strategy", "advisor": "llm_strategy", "writing_style": "llm_content",
}


def _insert(business_id, run_id, category, provider, operation, model,
            input_tokens, output_tokens, cost, units, unit_label, detail) -> None:
    """Single insert path used by both record() (LLM) and record_cost() (flat/external)."""
    try:
        with db() as conn:
            conn.execute(
                """INSERT INTO cost_ledger
                   (business_id, run_id, provider, operation, model, input_tokens, output_tokens,
                    est_cost_usd, category, units, unit_label, detail)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (business_id, run_id, provider, operation, model, input_tokens, output_tokens,
                 cost, category, units, unit_label, json.dumps(detail or {})),
            )
            conn.commit()
        if business_id is not None:
            _unrecorded_writes.pop(business_id, None)
    except Exception as e:  # noqa: BLE001 -- never let cost logging crash the caller...
        if business_id is not None:
            _unrecorded_writes[business_id] = _unrecorded_writes.get(business_id, 0) + 1
        log.error("cost record FAILED for business %s (spend under-counted; budget fails closed "
                  "for this business): %s", business_id, e)


def record(business_id: int | None, run_id: int | None, provider: str, operation: str,
           model: str, input_tokens: int, output_tokens: int, detail: dict | None = None) -> float:
    """Record a token-based LLM cost (audit/gap/strategy/content). Category is derived from the
    operation name so spend rolls up by service with zero changes at the call sites."""
    cost = estimate_cost(model, input_tokens, output_tokens)
    category = _LLM_CATEGORY.get(operation, "llm")
    _insert(business_id, run_id, category, provider, operation, model,
            input_tokens, output_tokens, cost, None, "tokens", detail)
    return cost


def record_cost(business_id: int | None, run_id: int | None, category: str, provider: str,
                operation: str, *, cost_usd: float | None = None, units: float = 0,
                unit_label: str | None = None, detail: dict | None = None,
                model: str | None = None) -> float:
    """Record a NON-token (flat/per-unit) cost for an external service — Serper search, DataForSEO
    request, image/video/audio generation, Katteb credits, etc. If cost_usd is None, estimate it
    from EXT_PRICING x units. Never raises."""
    if cost_usd is None:
        cost_usd, lbl = ext_estimate(category, units)
        unit_label = unit_label or lbl
    _insert(business_id, run_id, category, provider, operation, model or "",
            0, 0, round(float(cost_usd or 0), 6), units or None, unit_label or "units", detail)
    return float(cost_usd or 0)


def month_spend(business_id: int) -> float:
    """Sum of this calendar month's recorded spend, with a UTC month boundary so the
    window doesn't drift by hours when the DB session timezone differs from UTC.
    Raises on DB error so over_budget() can decide policy (it fails closed)."""
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(est_cost_usd),0) s FROM cost_ledger "
            "WHERE business_id=%s "
            "AND created_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
            (business_id,),
        ).fetchone()
    return float(row["s"])


def budget_for(business_id: int) -> float:
    """Configured monthly cap (USD); defaults to 50.0 when no config row exists.
    Raises on DB error (over_budget() fails closed)."""
    with db() as conn:
        row = conn.execute(
            "SELECT monthly_budget_usd FROM business_config WHERE business_id=%s",
            (business_id,),
        ).fetchone()
    return float(row["monthly_budget_usd"]) if row else 50.0


def over_budget(business_id: int) -> bool:
    """True if the business is at/over its monthly cap. Fails CLOSED: if spend can't be
    verified -- a DB error, or a cost write was lost this process -- report over-budget so
    a runaway can't slip through a degraded ledger. The cap is the only runaway guard."""
    lost = _unrecorded_writes.get(business_id, 0)
    if lost:
        log.error("Business %d: %d unrecorded cost write(s) this process -- failing closed.",
                  business_id, lost)
        return True
    try:
        spent, cap = month_spend(business_id), budget_for(business_id)
    except Exception as e:  # noqa: BLE001
        log.error("Business %d: budget check failed (%s) -- failing closed.", business_id, e)
        return True
    if spent >= cap:
        log.warning("Business %d over monthly budget: $%.2f / $%.2f", business_id, spent, cap)
        return True
    return False


# ---------------------------------------------------------------------------
# Reporting — itemized cost breakdowns for the admin cost dashboard
# ---------------------------------------------------------------------------
# Human labels for the rollup categories.
CATEGORY_LABEL = {
    "llm_audit": "AI audits (LLM)", "llm_gap": "Gap analysis (LLM)",
    "llm_strategy": "Strategy & advisor (LLM)", "llm_content": "Content writing (LLM)",
    "llm": "Other LLM", "search": "Search (Serper)", "keyword_volume": "Keyword volume (DataForSEO)",
    "image": "Image generation", "video": "Video generation", "audio": "Podcast/audio",
    "katteb": "Katteb", "analytics": "Google Analytics", "search_console": "Search Console",
    "pagespeed": "PageSpeed",
}


def _where(business_id: int | None, days: int):
    clause = "created_at >= now() - make_interval(days => %s)"
    args: list = [days]
    if business_id is not None:
        clause += " AND business_id=%s"
        args.append(business_id)
    return clause, args


def breakdown(business_id: int | None = None, days: int = 30) -> dict:
    """Itemized spend for the last `days`. business_id=None -> system-wide (all tenants).
    Returns totals + rollups by category / provider / operation, plus per-content-type and per-run."""
    where, args = _where(business_id, days)
    out: dict = {"days": days, "business_id": business_id}
    with db() as conn:
        total = conn.execute(f"SELECT COALESCE(SUM(est_cost_usd),0) s, COUNT(*) n FROM cost_ledger WHERE {where}",
                             tuple(args)).fetchone()
        out["total_usd"] = round(float(total["s"]), 4)
        out["events"] = int(total["n"])
        out["by_category"] = [
            {"category": r["category"] or "llm", "label": CATEGORY_LABEL.get(r["category"] or "llm", r["category"] or "llm"),
             "cost_usd": round(float(r["s"]), 4), "events": int(r["n"]),
             "units": float(r["u"]) if r["u"] is not None else None, "unit_label": r["ul"]}
            for r in conn.execute(
                f"SELECT category, COALESCE(SUM(est_cost_usd),0) s, COUNT(*) n, SUM(units) u, "
                f"MAX(unit_label) ul FROM cost_ledger WHERE {where} GROUP BY category ORDER BY s DESC",
                tuple(args)).fetchall()]
        out["by_provider"] = [
            {"provider": r["provider"] or "—", "cost_usd": round(float(r["s"]), 4), "events": int(r["n"])}
            for r in conn.execute(
                f"SELECT provider, COALESCE(SUM(est_cost_usd),0) s, COUNT(*) n FROM cost_ledger "
                f"WHERE {where} GROUP BY provider ORDER BY s DESC", tuple(args)).fetchall()]
        out["by_operation"] = [
            {"operation": r["operation"] or "—", "category": r["category"] or "llm",
             "cost_usd": round(float(r["s"]), 4), "events": int(r["n"])}
            for r in conn.execute(
                f"SELECT operation, category, COALESCE(SUM(est_cost_usd),0) s, COUNT(*) n FROM cost_ledger "
                f"WHERE {where} GROUP BY operation, category ORDER BY s DESC LIMIT 40", tuple(args)).fetchall()]
        # content by type + which API produced it (from detail JSON)
        out["by_content"] = [
            {"content_type": r["ct"] or "—", "api": r["api"] or "—",
             "cost_usd": round(float(r["s"]), 4), "events": int(r["n"])}
            for r in conn.execute(
                f"SELECT detail->>'content_type' ct, detail->>'api' api, COALESCE(SUM(est_cost_usd),0) s, "
                f"COUNT(*) n FROM cost_ledger WHERE {where} AND category IN "
                f"('llm_content','image','video','audio') GROUP BY ct, api ORDER BY s DESC LIMIT 30",
                tuple(args)).fetchall()]
        # cost per audit run (the biggest recurring unit of spend)
        out["by_run"] = [
            {"run_id": r["run_id"], "cost_usd": round(float(r["s"]), 4), "events": int(r["n"]),
             "started": r["st"].isoformat() if r["st"] else None}
            for r in conn.execute(
                f"SELECT cl.run_id, COALESCE(SUM(cl.est_cost_usd),0) s, COUNT(*) n, MIN(cl.created_at) st "
                f"FROM cost_ledger cl WHERE {where} AND cl.run_id IS NOT NULL "
                f"GROUP BY cl.run_id ORDER BY st DESC LIMIT 20", tuple(args)).fetchall()]
    return out


def by_business(days: int = 30) -> list[dict]:
    """System-wide: spend per tenant for the last `days` (admin roll-up)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT cl.business_id, b.name, COALESCE(SUM(cl.est_cost_usd),0) s, COUNT(*) n "
            "FROM cost_ledger cl LEFT JOIN businesses b ON b.id=cl.business_id "
            "WHERE cl.created_at >= now() - make_interval(days => %s) "
            "GROUP BY cl.business_id, b.name ORDER BY s DESC", (days,)).fetchall()
    return [{"business_id": r["business_id"], "name": r["name"] or f"#{r['business_id']}",
             "cost_usd": round(float(r["s"]), 4), "events": int(r["n"])} for r in rows]


def recent(business_id: int | None = None, limit: int = 50) -> list[dict]:
    """Most-recent individual cost events (the itemized line-item feed)."""
    where = "1=1"
    args: list = []
    if business_id is not None:
        where = "business_id=%s"
        args.append(business_id)
    args.append(limit)
    with db() as conn:
        rows = conn.execute(
            f"SELECT business_id, run_id, category, provider, operation, model, est_cost_usd, units, "
            f"unit_label, detail, created_at FROM cost_ledger WHERE {where} ORDER BY id DESC LIMIT %s",
            tuple(args)).fetchall()
    return [{"business_id": r["business_id"], "run_id": r["run_id"], "category": r["category"],
             "provider": r["provider"], "operation": r["operation"], "model": r["model"],
             "cost_usd": round(float(r["est_cost_usd"] or 0), 6), "units": float(r["units"]) if r["units"] is not None else None,
             "unit_label": r["unit_label"], "detail": r["detail"],
             "at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]
