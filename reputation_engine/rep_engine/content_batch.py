"""
Gap-driven content BATCHES (content-program Phase 4 core)
=========================================================
The program creates content one GAP at a time, not one PIECE at a time. For a single gap (a missing
owned topic + the weak AI answers it should fix) we spin up MULTIPLE content types — blog, article,
white paper, social — all targeting that gap, grouped in a `content_batches` row with a BASELINE
snapshot of the gap's Share-of-Voice/alignment. After the next audit, `content_impact` measures how
far the batch moved that gap (collectively, and per type where attributable), so the program can
keep producing and adjust based on what actually moved the number.

Dormant-safe + fail-loud: generation errors per piece are captured, not swallowed; a batch that
produced zero pieces is marked failed (never a silent "complete").
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

try:
    from .db import db
    from . import content_generator as _cg
    from . import textutils as _tu
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import content_generator as _cg  # type: ignore
    import textutils as _tu  # type: ignore

log = logging.getLogger("content_batch")

# A sensible default multi-type spread per gap. Tailored by gap intent in _types_for_gap().
_DEFAULT_TYPES = ["blog", "article", "white_paper", "social_post"]
_LOCAL_TYPES = ["local_page", "blog", "faq", "social_post"]
_COMMERCIAL_TYPES = ["landing_page", "article", "social_post"]
# A video gap can't be auto-published as a finished video (Veo is paid/dormant), so we produce the
# generatable, honest deliverable -- a shootable VIDEO SCRIPT -- plus a supporting blog + social,
# instead of silently masquerading the gap as a plain blog (the gap's asset_type used to be ignored).
_VIDEO_TYPES = ["video_script", "blog", "social_post"]

# How each content type frames the same gap topic (title lens + capability).
_TYPE_FRAME = {
    "blog":         ("Blog: {t}", "content_writing"),
    "article":      ("{t}", "content_writing"),
    "white_paper":  ("White paper: {t} — an in-depth, cited guide", "content_writing"),
    "landing_page": ("{t} — overview page", "content_writing"),
    "local_page":   ("{t} in {geo}", "content_writing"),
    "faq":          ("{t}: frequently asked questions", "content_writing"),
    "video_script": ("Video script: {t} — a shootable script + shot list", "content_writing"),
    "social_post":  ("{t}", "social_publishing"),
}


def _latest_gap_model(conn, business_id: int) -> dict:
    row = conn.execute("SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                       (business_id,)).fetchone()
    if not row:
        return {}
    m = row["model"]
    return m if isinstance(m, dict) else (json.loads(m) if m else {})


_STOPW = {"and", "with", "the", "for", "your", "our", "page", "overview", "detail", "case", "studies", "story", "stories"}


def _match_prompts(topic: str, weak: list[dict]) -> list[str]:
    """Which weak-answer prompts belong to this gap. Exact/substring on addressed_by first, then a
    lenient token-overlap fallback (gap topics and addressed_by rarely match verbatim)."""
    tl = (topic or "").lower()
    ttoks = _tu.word_set(tl, stop=_STOPW)
    out: list[str] = []
    for w in weak:
        p = w.get("prompt")
        if not p:
            continue
        ab = (w.get("addressed_by") or "").strip().lower()
        if ab and (ab == tl or ab in tl or tl in ab):
            out.append(p)
            continue
        cmp_toks = _tu.word_set((ab or "") + " " + p.lower(), stop=_STOPW)
        if ttoks and len(ttoks & cmp_toks) >= max(2, len(ttoks) // 3):
            out.append(p)
    # dedupe, preserve order
    seen, ded = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            ded.append(p)
    return ded


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).strip()


def _local_keywords(business_id: int, query: str, limit: int = 3) -> list[str]:
    """The ranking keywords a local/geo goal should target -- from the keyword-research set
    (target_keywords), scored by relevance to the geo query. A page-1 goal needs a PROGRAM of
    content across this keyword cluster (not one page), so each becomes a supporting blog."""
    qtoks = _tu.word_set(query, stop=_STOPW)
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT keyword, kind, priority FROM target_keywords WHERE business_id=%s "
                "AND (source IS NULL OR source <> 'dataforseo_competitor') "
                "ORDER BY priority DESC NULLS LAST LIMIT 80", (business_id,)).fetchall()
    except Exception:  # noqa: BLE001 -- no keyword table yet -> no extra pieces
        return []
    scored: list[tuple[int, str]] = []
    for r in rows:
        kw = (r.get("keyword") or "").strip()
        if not kw or kw.lower() == (query or "").lower():
            continue
        ktoks = _tu.word_set(kw, stop=_STOPW)
        overlap = len(qtoks & ktoks)
        is_local = (r.get("kind") or "") == "local"
        if overlap >= 1 or is_local:
            scored.append((overlap + (1 if is_local else 0), kw))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, kw in scored:
        k = kw.lower()
        if k not in seen:
            seen.add(k)
            out.append(kw)
        if len(out) >= limit:
            break
    return out


# Distinct local content-angle templates. Each is a genuinely DIFFERENT search intent a local-service
# prospect has (cost, how-to-choose, what-to-expect, who-it's-for, vetting, mistakes) -- NOT a keyword
# variant of the same query. GEO research penalizes near-duplicate / keyword-stuffed pages (~-8%), so a
# program's breadth must come from distinct subtopics, not re-phrasings. Used to size a local program up
# to the research target when the tenant's seed-keyword set is thinner than that target.
_LOCAL_ANGLES = [
    "How to choose {q}",
    "What does {q} cost? Fees and pricing explained",
    "Questions to ask before hiring {q}",
    "{q}: what to expect at your first meeting",
    "Signs of a trustworthy {q}",
    "{q} for young families just starting out",
    "{q} for retirees and pre-retirees",
    "Working with a local {q} vs. a national firm",
    "Common mistakes when choosing {q}",
    "Credentials and licensing to verify in {q}",
    "How to check the reputation and reviews of {q}",
    "A checklist for your first year with {q}",
]


def _local_spokes(business_id: int, query: str, target: int) -> list[dict]:
    """The SUPPORTING pieces for a local pillar, sized to the RESEARCH target
    (`content_research.cluster_count_for`) -- NOT to however many seed keywords happen to exist. Real
    ranking keywords (`target_keywords`) come first; when the tenant has fewer than the target, we
    backfill with DISTINCT local sub-topic angles (cost / how-to-choose / what-to-expect / who-it's-for
    / vetting) so the program is big enough to build topical authority and crowd out the negative
    narrative, instead of stopping at 'however many seeds exist' (the under-production the audit flagged).
    Each item: {topic, kind: 'keyword'|'angle'}."""
    q = (query or "").strip()
    target = max(1, int(target or 1))
    seeds = _local_keywords(business_id, q, limit=target)   # real ranking keywords, best first
    out: list[dict] = [{"topic": kw, "kind": "keyword"} for kw in seeds]
    seen = {_norm(q)} | {_norm(kw) for kw in seeds}
    for tpl in _LOCAL_ANGLES:
        if len(out) >= target:
            break
        topic = tpl.format(q=q)
        n = _norm(topic)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append({"topic": topic, "kind": "angle"})
    return out[:target]


def _avg_local_difficulty(business_id: int, query: str) -> Optional[float]:
    """Average keyword_difficulty (0..100) of the local target keywords that overlap this geo query, or
    None when no difficulty data exists (provider unpopulated / dormant). The competitiveness signal that
    sizes how much content a local ranking needs."""
    qtoks = _tu.word_set(query, stop=_STOPW)
    if not qtoks:
        return None
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT keyword, keyword_difficulty FROM target_keywords WHERE business_id=%s "
                "AND keyword_difficulty IS NOT NULL", (business_id,)).fetchall()
    except Exception:  # noqa: BLE001 -- no table / no data -> unknown competitiveness
        return None
    diffs = []
    for r in rows:
        if qtoks & _tu.word_set(r.get("keyword") or "", stop=_STOPW):
            try:
                diffs.append(float(r["keyword_difficulty"]))
            except (TypeError, ValueError):
                pass
    return (sum(diffs) / len(diffs)) if diffs else None


def difficulty_to_target(avg_difficulty) -> int:
    """The DYNAMIC supporting-piece count for a hub, scaled by COMPETITIVENESS: research band MIN at
    difficulty 0, up to the strong-pillar MAX at difficulty 100 (a harder ranking needs more content to
    win). None difficulty -> band MIN. The SINGLE sizing curve shared by the local program, the
    topic-cluster generator, and (indirectly) the strategist floor, so no path sizes a hub differently."""
    base, band_max = 8, 24
    try:
        from . import content_research as _cr
        base = int(_cr.cluster_count_for("topical_authority")[0])          # 8
        band_max = int(_cr.cluster_count_for("topical_authority", strong=True)[1])  # 24
    except Exception:  # noqa: BLE001
        pass
    if avg_difficulty is None:
        return base
    d = max(0.0, min(100.0, float(avg_difficulty)))
    return max(base, min(band_max, round(base + (d / 100.0) * (band_max - base))))


def local_spoke_target(business_id: int, query: str) -> int:
    """How many SUPPORTING pieces a local pillar needs -- DYNAMIC, sized by the geo query's
    COMPETITIVENESS (avg keyword_difficulty of the matching local keywords) via the shared
    difficulty_to_target curve. Used by BOTH the plan path (strategy_generator) and the batch path
    (gaps_for_business) so they can never diverge on local size."""
    return difficulty_to_target(_avg_local_difficulty(business_id, query))


def resolve_prompts(business_id: int, prompts: list[str]) -> list[str]:
    """Snap gap-model prompt strings (LLM-authored, often paraphrased) to the ACTUAL battery prompt
    text stored in `answers`, so the cluster query (`prompt = ANY`) matches instead of silently
    hitting 0 rows. Exact-normalized match first, then best token-set (Jaccard >= 0.5) fallback.
    Unresolvable candidates are dropped; if NONE resolve, returns [] so the caller falls back to
    whole-run (a coarser but valid collective measure) rather than a silent empty cluster."""
    prompts = [p for p in (prompts or []) if p]
    if not prompts:
        return []
    with db() as conn:
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND status='complete' AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
        if not run:
            return []
        battery = [r["prompt"] for r in conn.execute(
            "SELECT DISTINCT prompt FROM answers WHERE run_id=%s AND prompt IS NOT NULL", (run["id"],)).fetchall()]
    bnorm = [(_norm(p), p) for p in battery]
    resolved: list[str] = []
    for cand in prompts:
        cn = _norm(cand)
        if not cn:
            continue
        exact = next((p for n, p in bnorm if n == cn), None)
        if exact:
            resolved.append(exact)
            continue
        ctoks = set(cn.split())
        best, best_j = None, 0.0
        for n, p in bnorm:
            ptoks = set(n.split())
            if not ptoks:
                continue
            j = len(ctoks & ptoks) / len(ctoks | ptoks)
            if j > best_j:
                best, best_j = p, j
        if best and best_j >= 0.5:
            resolved.append(best)
    seen, out = set(), []
    for p in resolved:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def gaps_for_business(business_id: int) -> list[dict]:
    """Enumerate the content-fillable gaps -- each becomes a MULTI-PIECE program, not one draft:
      - missing_owned_content topics (the primary owned-content gaps),
      - local_seo_gaps (a page-1 GOAL fans into a geo cluster: local page + blog + FAQ + social),
      - competitor_defense (a rival-won question fans into competing owned content).
    Returns [{gap_key, topic, asset_type, gap_source, why, target_prompts}]. target_prompts are the
    weak AI answers the gap should move (token-matched); [] falls back to the whole run."""
    with db() as conn:
        gm = _latest_gap_model(conn, business_id)
    weak = gm.get("weak_queries") or []
    out = []
    for i, item in enumerate(gm.get("missing_owned_content") or []):
        topic = (item.get("topic") or f"topic {i+1}").strip()
        out.append({
            "gap_key": _tu.gid("moc", topic),
            "topic": topic,
            "asset_type": (item.get("asset_type") or "article").lower(),
            "gap_source": "audited gap: missing_owned_content",
            "why": item.get("why") or "",
            "target_prompts": _match_prompts(topic, weak),
        })
    # Local page-1 GOALS -> a KEYWORD-DRIVEN geo content program (not one draftable item): the geo
    # page + a supporting blog per ranking keyword + FAQ + social, so a page-2→page-1 move has a
    # cluster of ranking assets behind it, not a single page.
    for i, item in enumerate(gm.get("local_seo_gaps") or []):
        q = (item.get("query") or f"local query {i+1}").strip()
        out.append({
            "gap_key": _tu.gid("local", q),
            "topic": q,
            "asset_type": "local_page",
            "gap_source": "local search ranking",
            "why": item.get("recommendation") or item.get("why") or "",
            "target_prompts": _match_prompts(q, weak),
            # The SUPPORTING-piece set for this geo program -- sized DYNAMICALLY by competitiveness via
            # the SAME helper the plan path uses (local_spoke_target + _local_spokes), so the batch and
            # the plan never diverge on local size, and real ranking keywords are backfilled with distinct
            # local sub-topic angles to the research target (no fixed limit=3 / [:3] cap).
            "keywords": [sp["topic"] for sp in _local_spokes(business_id, q, local_spoke_target(business_id, q))],
        })
    # Questions a rival wins -> competing owned content.
    for i, item in enumerate(gm.get("competitor_defense") or []):
        q = (item.get("query") or f"competitor query {i+1}").strip()
        out.append({
            "gap_key": _tu.gid("comp", q),
            "topic": q,
            "asset_type": "article",
            "gap_source": "competitor analysis",
            "why": item.get("recommendation") or item.get("why") or "",
            "target_prompts": _match_prompts(q, weak),
        })
    return out


def noncontent_gaps(business_id: int) -> list[dict]:
    """Enumerate the gap categories a content PIECE does not close -- weak_queries, thin_corroboration,
    schema_gaps, site_technical_gaps, surface_actions. These are real gaps from the SAME gap model, but
    they're worked on other surfaces (Website fixes, Outreach, per-platform tasks), so each carries a
    `where` note + content_addressable=False. Surfacing them lets the completion view reflect the WHOLE
    gap analysis instead of only the content-fillable slice. Uniform shape:
    {gap_key, topic, gap_source, why, category, where, content_addressable}. Fail-safe (never raises)."""
    try:
        with db() as conn:
            gm = _latest_gap_model(conn, business_id)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []

    def add(category: str, key_prefix: str, topic, why, where: str) -> None:
        topic = (topic or "").strip()
        if not topic:
            return
        out.append({"gap_key": _tu.gid(key_prefix, topic), "topic": topic, "gap_source": category,
                    "why": (why or "").strip(), "category": category, "where": where,
                    "content_addressable": False})

    for w in gm.get("weak_queries") or []:
        add("weak_queries", "weak", (w.get("prompt") or w.get("query")),
            (w.get("problem") or w.get("fix")),
            "Tracked as the target answers your content pieces must move.")
    for t in gm.get("thin_corroboration") or []:
        add("thin_corroboration", "corrob", t.get("claim"),
            (t.get("where_to_get_it") or t.get("why")),
            "Tracked in Outreach — third-party corroboration (press, media, partners).")
    for sg in gm.get("schema_gaps") or []:
        label = sg if isinstance(sg, str) else (sg.get("type") or sg.get("issue") or "")
        add("schema_gaps", "schema", label, "",
            "Tracked in Website fixes — schema / structured data.")
    for g in gm.get("site_technical_gaps") or []:
        if isinstance(g, dict):
            add("site_technical_gaps", "tech", g.get("issue"), (g.get("recommendation") or g.get("why")),
                "Tracked in Website fixes — technical SEO.")
        else:
            add("site_technical_gaps", "tech", g, "", "Tracked in Website fixes — technical SEO.")
    surfaces = gm.get("surface_actions") or {}
    if isinstance(surfaces, dict):
        for surface, actions in surfaces.items():
            acts = [str(a) for a in (actions or []) if a]
            if not acts:
                continue
            label = str(surface).replace("_", " ").title()
            why = f"{len(acts)} recommended action(s): " + "; ".join(acts[:3]) + ("…" if len(acts) > 3 else "")
            add("surface_actions", "surface", f"{label} presence", why,
                "Tracked as per-platform tasks in your plan.")
    return out


def _types_for_gap(gap: dict, default_types: Optional[list[str]] = None) -> list[str]:
    at = (gap.get("asset_type") or "").lower()
    topic = (gap.get("topic") or "").lower()
    prof = [t for t in (default_types or []) if t in _TYPE_FRAME]   # the tenant's preferred spread

    def _apply_profile(types: list[str], required: set[str]) -> list[str]:
        """Honor the tenant profile on EVERY branch (not just default): keep the branch's REQUIRED lead
        type(s) always, and filter the supporting types to the tenant's preferred spread when one is
        defined (so a tenant that doesn't do, e.g., social still gets the required local_page/landing_page/
        video_script, minus formats it never uses). No profile -> the branch's full list."""
        keep = [t for t in types if t in required or (not prof) or t in prof]
        return [t for t in keep if t in _TYPE_FRAME] or [t for t in types if t in required] or types

    # Video is an explicit asset intent -> a shootable script spread, not a text article.
    if "video" in at or "video" in topic:
        return _apply_profile(_VIDEO_TYPES, {"video_script"})
    if "local" in at or "local" in topic:
        return _apply_profile(_LOCAL_TYPES, {"local_page"})
    if at in ("landing_page", "comparison") or "landing" in topic or any(k in topic for k in ("best", "vs", "compare", "top ")):
        return _apply_profile(_COMMERCIAL_TYPES, {"landing_page"})
    # DEFAULT branch: the tenant's profile-driven content spread (generic drops the finance
    # 'white_paper' and carries 'faq'; finance keeps 'white_paper'), restricted to the content types the
    # batch pipeline can frame + generate so an unknown type never becomes a mislabeled generic blog.
    return prof or [t for t in _DEFAULT_TYPES if t in _TYPE_FRAME] or list(_DEFAULT_TYPES)


def capture_baseline(business_id: int, target_prompts: list[str]) -> dict:
    """Snapshot the gap's current Share-of-Voice + alignment from the latest COMPLETE full audit,
    over the specific prompts the gap owns (or the whole battery if none are named). Also snapshots the
    baseline keyword RANK (dormant/None until a GSC/SERP source is connected) so content_impact can later
    show ranking MOVEMENT, not just AI-answer lift."""
    # Baseline rank for these prompts (None-safe, dormant): the SAME signal content_impact re-measures.
    base_rank = None
    try:
        from . import content_impact as _ci
        with db() as conn:
            base_rank = _ci._rank_signal(conn, business_id, target_prompts, "")
    except Exception:  # noqa: BLE001 -- rank baseline is best-effort / dormant
        base_rank = None
    with db() as conn:
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND status='complete' AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
        if not run:
            return {"run_id": None, "sov": None, "alignment": None, "owned_rate": None,
                    "contested_rate": None, "n": 0, "rank": base_rank}
        return {**_cluster_metrics(conn, business_id, run["id"], target_prompts),
                "run_id": run["id"], "rank": base_rank}


def _prompts_for_gap(business_id: int, gap_key: str, fallback: str = "") -> list[str]:
    """The gap's FULL resolved prompt cluster (the weak AI answers it should move), derived from the
    CANONICAL gap topic (the part after the gap_key prefix) so BOTH the mainline path (ensure_impact_batch)
    and the batch path (generate_batch via gaps_for_business) baseline over the identical prompt window
    for a shared gap_key. Falls back to [fallback] when no weak-query cluster matches."""
    topic = gap_key.split(":", 1)[1] if (gap_key and ":" in gap_key) else (gap_key or fallback or "")
    try:
        with db() as conn:
            gm = _latest_gap_model(conn, business_id)
        matched = _match_prompts(topic, gm.get("weak_queries") or [])
    except Exception:  # noqa: BLE001
        matched = []
    return resolve_prompts(business_id, matched or ([fallback] if fallback else []))


def ensure_impact_batch(business_id: int, wo: dict) -> Optional[int]:
    """Find-or-create a content_batches baseline for the gap a work order targets, so a draft made by
    the MAINLINE generate() path (not just the content_batch fan-out) is measured for AI-visibility lift
    after the next audit -- closing the content_impact loop for ALL generated content, not only batches.
    Reuses an open (not-yet-measured) batch for the same gap so many WOs on one gap share a single
    baseline; creates one with a fresh baseline otherwise. Returns the batch id, or None when the WO
    carries no gap linkage or on any error (the draft still generates, just unmeasured -- today's
    behavior). The baseline is captured against the LATEST audit so a later audit can show the delta."""
    try:
        gs = wo.get("gap_specifics") if isinstance(wo.get("gap_specifics"), dict) else {}
        src_q = (wo.get("target_query") or gs.get("source_query") or "").strip()
        topic = (wo.get("title") or src_q or "").strip()
        if not (src_q or topic):
            return None
        # Prefer the planner-stamped canonical gap_key (so a whole PROGRAM shares one batch that joins to
        # the real gap). Absent that, DERIVE the canonical key (same scheme as gaps_for_business) from the
        # WO's gap_source + its SOURCE QUERY -- never the piece title, which used to mint a unique
        # 'moc:<title>' key per piece that matched no gap (no collective measurement, no completion credit).
        gap_key = gs.get("gap_key")
        if not gap_key:
            rat = wo.get("rationale") if isinstance(wo.get("rationale"), dict) else {}
            src_low = (wo.get("gap_source") or gs.get("gap_source") or rat.get("gap_source") or "").lower()
            prefix = "local" if "local" in src_low else ("comp" if "competitor" in src_low else "moc")
            gap_key = _tu.gid(prefix, src_q or topic)
        with db() as conn:
            row = conn.execute(
                "SELECT id FROM content_batches WHERE business_id=%s AND gap_key=%s "
                "AND status <> 'measured' ORDER BY id DESC LIMIT 1", (business_id, gap_key)).fetchone()
            if row:
                return row["id"]
        # Baseline over the gap's FULL prompt cluster (the same window generate_batch uses), derived from
        # the canonical gap topic -- so whichever path creates the batch first for a shared gap_key sets
        # the SAME measurement window (was [src_q] here vs the full _match_prompts cluster in the batch).
        prompts = _prompts_for_gap(business_id, gap_key, src_q)
        baseline = capture_baseline(business_id, prompts)
        with db() as conn:
            b = conn.execute(
                "INSERT INTO content_batches (business_id, gap_key, gap_source, label, target_topic, "
                "target_prompts, content_types, baseline, status, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'generating',%s) RETURNING id",
                (business_id, gap_key, gs.get("gap_source") or "content",
                 f"Fill gap: {topic or src_q}", topic or src_q,
                 json.dumps(prompts), json.dumps([]), json.dumps(baseline), None)).fetchone()
            conn.commit()
        log.info("content_impact: opened baseline batch %s for gap %s (business %d)",
                 b["id"], gap_key, business_id)
        return b["id"]
    except Exception as e:  # noqa: BLE001 -- measurement wiring must never break generation
        log.debug("ensure_impact_batch skipped: %s", e)
        return None


def _cluster_metrics(conn, business_id: int, run_id: int, prompts: list[str]) -> dict:
    """Aggregate AI-visibility metrics for a run over a set of prompts (empty = whole run)."""
    if prompts:
        row = conn.execute(
            "SELECT AVG((surfaces_owned)::int) owned, AVG(goal_alignment) align, "
            "AVG((mentions_contested)::int) contested, COUNT(*) n FROM answers "
            "WHERE business_id=%s AND run_id=%s AND NOT COALESCE(failed,false) AND prompt = ANY(%s)",
            (business_id, run_id, prompts)).fetchone()
    else:
        row = conn.execute(
            "SELECT AVG((surfaces_owned)::int) owned, AVG(goal_alignment) align, "
            "AVG((mentions_contested)::int) contested, COUNT(*) n FROM answers "
            "WHERE business_id=%s AND run_id=%s AND NOT COALESCE(failed,false)",
            (business_id, run_id)).fetchone()
    owned = float(row["owned"]) if row and row["owned"] is not None else None
    align = float(row["align"]) if row and row["align"] is not None else None
    contested = float(row["contested"]) if row and row["contested"] is not None else None
    # Share of Voice for the cluster: how often our owned content surfaces (0..1).
    return {"sov": owned, "owned_rate": owned, "alignment": align,
            "contested_rate": contested, "n": int(row["n"]) if row else 0}


def _grade_social(business_id: int, draft_ids: list[int]) -> None:
    """Give each atomized social post its social GEO grade (atomize_draft doesn't run the grader).
    Linkage (batch_id/content_type) is already set atomically at insert, so a failure here only loses
    the grade, never the batch membership. Best-effort per post."""
    try:
        from . import content_quality as _cq
    except ImportError:  # pragma: no cover
        import content_quality as _cq  # type: ignore
    for sid in draft_ids:
        try:
            with db() as conn:
                row = conn.execute("SELECT body, quality_notes FROM content_drafts WHERE id=%s", (sid,)).fetchone()
                if not row:
                    continue
                qn = row["quality_notes"] if isinstance(row["quality_notes"], dict) else json.loads(row["quality_notes"] or "{}")
                g = _cq.geo_score(row["body"] or "", content_type="social_post")
                qn["geo"] = g
                conn.execute("UPDATE content_drafts SET geo_score=%s, quality_notes=%s WHERE id=%s",
                             (g.get("score"), json.dumps(qn), sid))
                conn.commit()
        except Exception as e:  # noqa: BLE001 -- one post's grade must not abort the rest
            log.debug("social grade skipped for draft %s: %s", sid, e)


def _match_content_wo(business_id: int, topic: str, source_query: str) -> Optional[int]:
    """The open CONTENT work order this gap's batch fills, so the drafts link back to the plan:
    approve() then advances the work order, and the work order is prune-protected while a draft
    exists. Before this, batch drafts had work_order_id=NULL -- so plan progress never moved and a
    still-pending work order could be hard-deleted despite shipped content. Returns a work-order id,
    or None when the plan tracks no matching content task (the batch still generates; it just isn't
    plan-linked). Matches on the work order's source_query, else title overlap (reuses the brief
    lineage matcher)."""
    try:
        from . import production_brief as _pb
    except ImportError:  # pragma: no cover
        import production_brief as _pb  # type: ignore
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, capability, gap_specifics FROM work_orders "
            "WHERE business_id=%s AND NOT superseded", (business_id,)).fetchall()
    cands = []
    for r in rows:
        if (r["capability"] or "").lower() not in ("content_writing", "content_creation"):
            continue
        gs = r["gap_specifics"]
        gs = gs if isinstance(gs, dict) else (json.loads(gs) if gs else {})
        cands.append({"id": r["id"], "title": r["title"], "gap_specifics": gs})
    if not cands:
        return None
    ids = _pb._match_work_orders(source_query or topic, cands) or _pb._match_work_orders(topic, cands)
    return int(ids[0]) if ids else None


def generate_batch(business_id: int, gap: dict, content_types: Optional[list[str]] = None,
                   created_by: Optional[int] = None) -> dict:
    """Create a content batch for one gap and generate a piece per content type. Fail-loud: raises
    if EVERY piece failed (so the job is marked failed, never a silent 'complete')."""
    # Budget guard: the batch path calls generate_for_wo directly (bypassing generate()'s guard), so
    # enforce the monthly cap here or a batch could run past it. The cap is the runaway backstop.
    _budget_or_raise(business_id)
    # The default content-type spread is profile-driven (generic drops the finance 'white_paper' and
    # carries 'faq'); an explicit content_types from the caller still wins. Fail-safe -> module default.
    _default_types = None
    try:
        from . import business_profile as _bp
        _default_types = _bp.for_business(business_id).get("default_content_types")
    except Exception:  # noqa: BLE001
        _default_types = None
    types = content_types or _types_for_gap(gap, _default_types)
    topic = gap.get("topic") or ""
    # Resolve LLM-authored gap prompts to the actual battery prompt text so impact measures a real
    # cluster (not a silent 0-row match). Empty -> whole-run fallback (coarser but valid).
    prompts = resolve_prompts(business_id, gap.get("target_prompts") or [])
    baseline = capture_baseline(business_id, prompts)
    with db() as conn:
        biz_row = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz_row:
            raise SystemExit(f"No business id {business_id}")
        biz = dict(biz_row)
        b = conn.execute(
            "INSERT INTO content_batches (business_id, gap_key, gap_source, label, target_topic, "
            "target_prompts, content_types, baseline, status, created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'generating',%s) RETURNING id",
            (business_id, gap.get("gap_key") or _tu.gid("moc", topic), gap.get("gap_source") or "",
             f"Fill gap: {topic}", topic, json.dumps(prompts), json.dumps(types),
             json.dumps(baseline), created_by)).fetchone()
        batch_id = b["id"]
        conn.commit()

    geo_val = (biz.get("geo") if isinstance(biz, dict) else "") or ""
    # Link this gap's pieces to the content work order that tracks it, so approve() advances the plan
    # and the work order is prune-protected once a draft exists. None -> unlinked (still generates).
    matched_wo = _match_content_wo(business_id, topic, prompts[0] if prompts else topic)
    made, errors = [], []
    # Long-form pieces are generated directly; social posts are ATOMIZED from the primary long-form
    # piece (social_publishing isn't a generatable content capability -- social derives from a page).
    long_types = [t for t in types if t != "social_post"]
    want_social = "social_post" in types
    for ct in long_types:
        frame, _cap = _TYPE_FRAME.get(ct, ("{t}", "content_writing"))
        title = frame.format(t=topic, geo=geo_val or "your area")
        wo = {"title": title, "capability": "content_writing", "execution": "auto",
              "target_query": topic, "content_type": ct, "_db_id": matched_wo,
              "instruction": f"{gap.get('why') or ''} (content type: {ct})".strip(),
              # carry the gap linkage so the draft traces back to the weak answer it fixes
              "gap_specifics": {"source_query": (prompts[0] if prompts else topic)}}
        try:
            did = _cg.generate_for_wo(business_id, wo, biz, content_type=ct, batch_id=batch_id)
            if did:
                made.append({"draft_id": did, "content_type": ct})
            else:
                errors.append({"content_type": ct, "reason": "skipped (already covered / empty generation)"})
        except Exception as e:  # noqa: BLE001 -- collect per-piece errors, don't abort the batch
            log.warning("batch %d: %s piece failed: %s", batch_id, ct, e)
            errors.append({"content_type": ct, "reason": str(e)[:200]})
    # Keyword-driven local program: a supporting blog per RANKING KEYWORD/ANGLE so the geo goal is backed
    # by a real content cluster, not one page. `keywords` is already sized dynamically by competitiveness
    # (gaps_for_business -> local_spoke_target + _local_spokes), so NO fixed [:3] cap here — that was the
    # batch-vs-plan divergence (batch capped at 3 while the plan built the research-sized program).
    for kw in (gap.get("keywords") or []):
        if not kw or _norm(kw) == _norm(topic):
            continue
        wo = {"title": f"Blog: {kw}", "capability": "content_writing", "execution": "auto",
              "target_query": kw, "content_type": "blog", "_db_id": matched_wo,
              "instruction": f"Rank for '{kw}' as part of the local content program for '{topic}'.",
              "gap_specifics": {"source_query": kw}}
        try:
            did = _cg.generate_for_wo(business_id, wo, biz, content_type="blog", batch_id=batch_id)
            if did:
                made.append({"draft_id": did, "content_type": "blog"})
            else:
                errors.append({"content_type": f"blog:{kw}", "reason": "skipped (already covered / empty)"})
        except Exception as e:  # noqa: BLE001
            log.warning("batch %d: keyword blog '%s' failed: %s", batch_id, kw, e)
            errors.append({"content_type": f"blog:{kw}", "reason": str(e)[:200]})
    # Social: atomize the primary long-form piece into per-platform posts, tag them into the batch,
    # and give each its (social-profile) GEO grade.
    if want_social and made:
        try:
            src = made[0]["draft_id"]
            # batch_id is set atomically at insert -> a grading hiccup can't orphan the posts.
            res = _cg.atomize_draft(business_id, src, batch_id=batch_id) or {}
            sids = res.get("draft_ids") or []
            if sids:
                _grade_social(business_id, sids)   # grading only; linkage already done
                for sid in sids:
                    made.append({"draft_id": sid, "content_type": "social_post"})
            else:
                errors.append({"content_type": "social_post", "reason": "atomization produced no posts"})
        except Exception as e:  # noqa: BLE001
            log.warning("batch %d: social atomization failed: %s", batch_id, e)
            errors.append({"content_type": "social_post", "reason": str(e)[:200]})

    status = "drafted" if made else "failed"
    with db() as conn:
        conn.execute("UPDATE content_batches SET status=%s, updated_at=now() WHERE id=%s",
                     (status, batch_id))
        conn.commit()
    if not made:
        raise RuntimeError(
            f"content batch {batch_id} for gap '{topic}' produced 0 pieces from {len(types)} type(s): "
            f"{errors}. Not marking successful.")
    log.info("batch %d '%s': %d/%d pieces produced (%s)", batch_id, topic, len(made), len(types),
             ", ".join(m["content_type"] for m in made))
    return {"batch_id": batch_id, "topic": topic, "types": types, "produced": made,
            "errors": errors, "baseline": baseline}


def _default_spoke_cap() -> int:
    """Research-backed max supporting pieces per pillar. A hub earns topical authority at ~8-12 clusters
    (a strong pillar anchors 20-30); we cap generation at the top of the 'start' band (12) so a program
    is sized to actually rank + crowd out the negative narrative, not throttled to a check-the-box 4.
    Falls back to 12 if the KB is unavailable (dormant-safe)."""
    try:
        from . import content_research as _cr
    except Exception:  # noqa: BLE001
        try:
            import content_research as _cr  # type: ignore
        except Exception:  # noqa: BLE001
            return 12
    try:
        return int(_cr.cluster_count_for("topical_authority")[1])
    except Exception:  # noqa: BLE001
        return 12


def generate_cluster(business_id: int, cluster: dict, *, max_spokes: Optional[int] = None,
                     created_by: Optional[int] = None) -> dict:
    """Generate a topic CLUSTER as a connected hub: one comprehensive PILLAR page for the cluster's
    core topic + a focused SPOKE page per subtopic, CROSS-LINKED (pillar<->spokes). This is the
    research-backed content model — a pillar/cluster architecture with internal linking builds the
    topical authority AI answer engines reward (HubSpot: more internal links -> better rankings), vs.
    isolated one-off pieces. Each piece carries the pipeline's info-gain differentiators (real
    attributed stats + expert quotes + business specifics). Fail-loud if EVERY piece fails.

    `max_spokes=None` (the default) sizes the hub to the research target (`_default_spoke_cap`, =12) so a
    program uses ALL the real spokes the caller provides up to that band -- it is a ceiling on a large
    cluster, NOT a floor that pads a small one: a cluster with 3 real spokes still produces 3 (honoring
    'if the data says fewer, go with fewer')."""
    _budget_or_raise(business_id)
    if max_spokes is None:
        max_spokes = _default_spoke_cap()
    pillar_topic = (cluster.get("pillar") or cluster.get("topic") or "").strip()
    if not pillar_topic:
        raise ValueError("cluster has no pillar topic")
    spoke_topics = [s.strip() for s in (cluster.get("spokes") or []) if s and str(s).strip()][:max_spokes]
    # Capture a REAL baseline (like generate_batch) so this cluster's AI-visibility lift is MEASURABLE and
    # re-enters the strategist's content_performance loop. Was baseline={}/target_prompts=[], which made
    # every cluster / recommended-topic program permanently unmeasurable (measure_batch's guard skipped it)
    # -- the highest-VOLUME content earning zero gap-completion credit. Reuse a stamped gap_key from the
    # caller (so a recommended topic can join its canonical gap) else the cluster: lineage key.
    cluster_prompts = resolve_prompts(business_id, [pillar_topic] + spoke_topics)
    cluster_baseline = capture_baseline(business_id, cluster_prompts)
    with db() as conn:
        biz_row = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz_row:
            raise SystemExit(f"No business id {business_id}")
        biz = dict(biz_row)
        pillar_slug = _cg._slugify(pillar_topic)
        spoke_plan = [{"title": st, "slug": _cg._slugify(st), "query": st} for st in spoke_topics]
        _cluster_gk = (cluster.get("gap_key") or "").strip() or f"cluster:{pillar_slug}"
        _cluster_src = (cluster.get("gap_source") or "").strip() or "topical_authority"
        b = conn.execute(
            "INSERT INTO content_batches (business_id, gap_key, gap_source, label, target_topic, "
            "target_prompts, content_types, baseline, status, created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'generating',%s) RETURNING id",
            (business_id, _cluster_gk, _cluster_src,
             f"Topic cluster: {pillar_topic}", pillar_topic, json.dumps(cluster_prompts),
             json.dumps(["article"] + ["blog"] * len(spoke_plan)), json.dumps(cluster_baseline), created_by)).fetchone()
        batch_id = b["id"]
        conn.commit()

    made, errors = [], []
    # PILLAR first: a comprehensive page that links DOWN to each planned spoke.
    pillar_wo = {
        "title": pillar_topic, "capability": "content_writing", "execution": "auto",
        "target_query": pillar_topic, "content_type": "article",
        "instruction": (f"Comprehensive PILLAR page for the topic cluster '{pillar_topic}'. Cover the core "
                        f"topic thoroughly and orient the reader to its sub-topics: "
                        f"{', '.join(spoke_topics) or 'n/a'}."),
        "gap_specifics": {"source_query": pillar_topic},
        "cluster": {"role": "pillar", "pillar_title": pillar_topic, "pillar_slug": pillar_slug,
                    "spokes": spoke_plan},
    }
    try:
        did = _cg.generate_for_wo(business_id, pillar_wo, biz, content_type="article", batch_id=batch_id)
        if did:
            made.append({"draft_id": did, "content_type": "article", "role": "pillar"})
        else:
            errors.append({"role": "pillar", "reason": "skipped (already covered / empty)"})
    except Exception as e:  # noqa: BLE001
        log.warning("cluster %d: pillar failed: %s", batch_id, e)
        errors.append({"role": "pillar", "reason": str(e)[:200]})
    # SPOKES: one focused blog per subtopic, each linking UP to the pillar.
    for sp in spoke_plan:
        spoke_wo = {
            "title": sp["title"], "capability": "content_writing", "execution": "auto",
            "target_query": sp["query"], "content_type": "blog",
            "instruction": (f"Focused SPOKE page on '{sp['title']}', a sub-topic of the pillar guide "
                            f"'{pillar_topic}'. Go deep on this one angle only."),
            "gap_specifics": {"source_query": sp["query"]},
            "cluster": {"role": "spoke", "pillar_title": pillar_topic, "pillar_slug": pillar_slug},
        }
        try:
            did = _cg.generate_for_wo(business_id, spoke_wo, biz, content_type="blog", batch_id=batch_id)
            if did:
                made.append({"draft_id": did, "content_type": "blog", "role": "spoke", "topic": sp["title"]})
            else:
                errors.append({"role": f"spoke:{sp['title']}", "reason": "skipped (already covered / empty)"})
        except Exception as e:  # noqa: BLE001
            log.warning("cluster %d: spoke '%s' failed: %s", batch_id, sp["title"], e)
            errors.append({"role": f"spoke:{sp['title']}", "reason": str(e)[:200]})

    status = "drafted" if made else "failed"
    with db() as conn:
        conn.execute("UPDATE content_batches SET status=%s, updated_at=now() WHERE id=%s", (status, batch_id))
        conn.commit()
    if not made:
        raise RuntimeError(f"topic cluster '{pillar_topic}' produced 0 pieces: {errors}")
    log.info("cluster %d '%s': pillar + %d spoke(s) -> %d pieces", batch_id, pillar_topic,
             len(spoke_plan), len(made))
    return {"batch_id": batch_id, "pillar": pillar_topic, "spokes": spoke_topics,
            "pieces": len(made), "produced": made, "errors": errors}


def generate_clusters(business_id: int, max_clusters: Optional[int] = None, *,
                      max_spokes: Optional[int] = None, created_by: Optional[int] = None) -> dict:
    """Plan + generate the highest-leverage UNCOVERED topic clusters (pillar-first), using the
    topical-authority planner. This is the CLUSTER-DRIVEN content pipeline (vs. one-off gap pieces):
    it only builds real hubs (a pillar WITH subtopics), not lone keywords. `max_spokes=None` sizes EACH
    hub DYNAMICALLY by its own competitiveness (topical_authority's per-cluster avg_difficulty, via the
    shared difficulty_to_target curve) -- a hard, high-opportunity cluster earns more supporting pieces
    than an easy one, mirroring the local path -- instead of one flat check-the-box cap."""
    try:
        from . import topical_authority as _ta
    except ImportError:  # pragma: no cover
        import topical_authority as _ta  # type: ignore
    cl = _ta.clusters(business_id).get("clusters", [])
    targets = [c for c in cl if c.get("needs_content") and c.get("spokes")][:(max_clusters or 3)]
    results, errors = [], []
    for c in targets:
        # Per-cluster size from ITS competitiveness (shared curve) unless the caller forced max_spokes.
        _cap = max_spokes if max_spokes is not None else difficulty_to_target(c.get("avg_difficulty"))
        try:
            results.append(generate_cluster(business_id, c, max_spokes=_cap, created_by=created_by))
        except SystemExit as e:   # over-budget stop (BaseException) -> stop the sweep, like generate_all_gaps
            log.warning("generate_clusters: budget stop after %d cluster(s): %s", len(results), e)
            errors.append({"cluster": c.get("topic"), "reason": "monthly budget reached"})
            break
        except Exception as e:  # noqa: BLE001
            log.warning("generate_clusters: cluster '%s' failed: %s", c.get("topic"), e)
            errors.append({"cluster": c.get("topic"), "reason": str(e)[:200]})
    return {"clusters_generated": len(results), "planned": [c.get("topic") for c in targets],
            "results": results, "errors": errors}


def _over_budget(business_id: int) -> bool:
    try:
        from . import ai_state_audit as _llm
        return bool(_llm.cost.over_budget(business_id))
    except Exception:  # noqa: BLE001 -- budget check best-effort; don't block on a check failure
        return False


def _budget_or_raise(business_id: int) -> None:
    if _over_budget(business_id):
        raise SystemExit(
            f"Business {business_id} is at/over its monthly budget; batch content skipped. "
            f"Raise monthly_budget_usd in business_config to proceed.")


def generate_all_gaps(business_id: int, max_gaps: Optional[int] = None,
                      created_by: Optional[int] = None) -> dict:
    """Batch-produce content for every open content gap (the 'fill the plan' button). Budget-guarded:
    the cap is re-checked BEFORE EACH gap so a multi-gap sweep stops the moment it crosses the ceiling
    (each gap is several LLM-heavy pieces). Returns a summary; raises if nothing at all was produced."""
    _budget_or_raise(business_id)
    gaps = gaps_for_business(business_id)
    if max_gaps:
        gaps = gaps[:max_gaps]
    batches, total_pieces, budget_stopped = [], 0, False
    for gap in gaps:
        # stop cleanly the moment the batch spend crosses the monthly cap
        if _over_budget(business_id):
            log.warning("Budget cap reached mid-sweep for business %d after %d pieces; stopping.",
                        business_id, total_pieces)
            budget_stopped = True
            break
        try:
            res = generate_batch(business_id, gap, created_by=created_by)
            batches.append({"batch_id": res["batch_id"], "topic": res["topic"],
                            "pieces": len(res["produced"])})
            total_pieces += len(res["produced"])
        except SystemExit:  # budget hit inside generate_batch -> stop the sweep
            budget_stopped = True
            break
        except Exception as e:  # noqa: BLE001 -- one gap failing must not abort the rest
            log.warning("gap batch failed for '%s': %s", gap.get("topic"), e)
            batches.append({"topic": gap.get("topic"), "pieces": 0, "error": str(e)[:200]})
    # A budget-driven stop is NOT a failure (the cap did its job), so it doesn't trip the 0-piece guard.
    if gaps and total_pieces == 0 and not budget_stopped:
        raise RuntimeError(f"batch content produced 0 pieces across {len(gaps)} gap(s); check the "
                           "orchestrator LLM key/budget. Not marking successful.")
    return {"gaps": len(gaps), "batches": batches, "pieces": total_pieces, "budget_stopped": budget_stopped}
