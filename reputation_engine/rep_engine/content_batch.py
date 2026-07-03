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
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import content_generator as _cg  # type: ignore

log = logging.getLogger("content_batch")

# A sensible default multi-type spread per gap. Tailored by gap intent in _types_for_gap().
_DEFAULT_TYPES = ["blog", "article", "white_paper", "social_post"]
_LOCAL_TYPES = ["local_page", "blog", "social_post"]
_COMMERCIAL_TYPES = ["landing_page", "article", "social_post"]

# How each content type frames the same gap topic (title lens + capability).
_TYPE_FRAME = {
    "blog":         ("Blog: {t}", "content_writing"),
    "article":      ("{t}", "content_writing"),
    "white_paper":  ("White paper: {t} — an in-depth, cited guide", "content_writing"),
    "landing_page": ("{t} — overview page", "content_writing"),
    "local_page":   ("{t} in {geo}", "content_writing"),
    "faq":          ("{t}: frequently asked questions", "content_writing"),
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
    ttoks = {w for w in re.findall(r"[a-z]{4,}", tl) if w not in _STOPW}
    out: list[str] = []
    for w in weak:
        p = w.get("prompt")
        if not p:
            continue
        ab = (w.get("addressed_by") or "").strip().lower()
        if ab and (ab == tl or ab in tl or tl in ab):
            out.append(p)
            continue
        cmp_toks = {x for x in re.findall(r"[a-z]{4,}", (ab or "") + " " + p.lower()) if x not in _STOPW}
        if ttoks and len(ttoks & cmp_toks) >= max(2, len(ttoks) // 3):
            out.append(p)
    # dedupe, preserve order
    seen, ded = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            ded.append(p)
    return ded


def gaps_for_business(business_id: int) -> list[dict]:
    """Enumerate the content-fillable gaps: each missing_owned_content topic + the weak AI answers
    (prompts) that name it via weak_query.addressed_by. Returns [{gap_key, topic, asset_type,
    gap_source, why, target_prompts}]."""
    with db() as conn:
        gm = _latest_gap_model(conn, business_id)
    moc = gm.get("missing_owned_content") or []
    weak = gm.get("weak_queries") or []
    out = []
    for i, item in enumerate(moc):
        topic = (item.get("topic") or f"topic {i+1}").strip()
        prompts = _match_prompts(topic, weak)
        out.append({
            "gap_key": f"moc:{topic.lower()}",
            "topic": topic,
            "asset_type": (item.get("asset_type") or "article").lower(),
            "gap_source": "audited gap: missing_owned_content",
            "why": item.get("why") or "",
            "target_prompts": prompts,
        })
    return out


def _types_for_gap(gap: dict) -> list[str]:
    at = (gap.get("asset_type") or "").lower()
    topic = (gap.get("topic") or "").lower()
    if "local" in at or "local" in topic or "landing" in topic and "cincinnati" in topic:
        return _LOCAL_TYPES
    if at in ("landing_page", "comparison") or any(k in topic for k in ("best", "vs", "compare", "top ")):
        return _COMMERCIAL_TYPES
    return _DEFAULT_TYPES


def capture_baseline(business_id: int, target_prompts: list[str]) -> dict:
    """Snapshot the gap's current Share-of-Voice + alignment from the latest COMPLETE full audit,
    over the specific prompts the gap owns (or the whole battery if none are named)."""
    with db() as conn:
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND status='complete' AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
        if not run:
            return {"run_id": None, "sov": None, "alignment": None, "owned_rate": None,
                    "contested_rate": None, "n": 0}
        return {**_cluster_metrics(conn, business_id, run["id"], target_prompts), "run_id": run["id"]}


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


def _grade_social(business_id: int, draft_ids: list[int], batch_id: int) -> None:
    """Tag atomized social posts into the batch + give each its social GEO grade (atomize_draft
    doesn't run the grader). Best-effort."""
    try:
        from . import content_quality as _cq
    except ImportError:  # pragma: no cover
        import content_quality as _cq  # type: ignore
    with db() as conn:
        for sid in draft_ids:
            row = conn.execute("SELECT body, quality_notes FROM content_drafts WHERE id=%s", (sid,)).fetchone()
            if not row:
                continue
            qn = row["quality_notes"] if isinstance(row["quality_notes"], dict) else json.loads(row["quality_notes"] or "{}")
            geo = None
            try:
                g = _cq.geo_score(row["body"] or "", content_type="social_post")
                qn["geo"] = g
                geo = g.get("score")
            except Exception:  # noqa: BLE001
                pass
            conn.execute("UPDATE content_drafts SET batch_id=%s, content_type='social_post', "
                         "geo_score=%s, quality_notes=%s WHERE id=%s",
                         (batch_id, geo, json.dumps(qn), sid))
        conn.commit()


def generate_batch(business_id: int, gap: dict, content_types: Optional[list[str]] = None,
                   created_by: Optional[int] = None) -> dict:
    """Create a content batch for one gap and generate a piece per content type. Fail-loud: raises
    if EVERY piece failed (so the job is marked failed, never a silent 'complete')."""
    types = content_types or _types_for_gap(gap)
    topic = gap.get("topic") or ""
    prompts = gap.get("target_prompts") or []
    baseline = capture_baseline(business_id, prompts)
    with db() as conn:
        biz = dict(conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone())
        b = conn.execute(
            "INSERT INTO content_batches (business_id, gap_key, gap_source, label, target_topic, "
            "target_prompts, content_types, baseline, status, created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'generating',%s) RETURNING id",
            (business_id, gap.get("gap_key") or f"moc:{topic.lower()}", gap.get("gap_source") or "",
             f"Fill gap: {topic}", topic, json.dumps(prompts), json.dumps(types),
             json.dumps(baseline), created_by)).fetchone()
        batch_id = b["id"]
        conn.commit()

    geo_val = (biz.get("geo") if isinstance(biz, dict) else "") or ""
    made, errors = [], []
    # Long-form pieces are generated directly; social posts are ATOMIZED from the primary long-form
    # piece (social_publishing isn't a generatable content capability -- social derives from a page).
    long_types = [t for t in types if t != "social_post"]
    want_social = "social_post" in types
    for ct in long_types:
        frame, _cap = _TYPE_FRAME.get(ct, ("{t}", "content_writing"))
        title = frame.format(t=topic, geo=geo_val or "your area")
        wo = {"title": title, "capability": "content_writing", "execution": "auto",
              "target_query": topic, "content_type": ct,
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
    # Social: atomize the primary long-form piece into per-platform posts, tag them into the batch,
    # and give each its (social-profile) GEO grade.
    if want_social and made:
        try:
            src = made[0]["draft_id"]
            res = _cg.atomize_draft(business_id, src) or {}
            sids = res.get("draft_ids") or []
            if sids:
                _grade_social(business_id, sids, batch_id)
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


def generate_all_gaps(business_id: int, max_gaps: Optional[int] = None,
                      created_by: Optional[int] = None) -> dict:
    """Batch-produce content for every open content gap (the 'fill the plan' button). Budget-guarded
    via the same monthly cap generate() honors (each generate_for_wo checks nothing itself, so we
    check here up front). Returns a summary; raises if nothing at all was produced."""
    try:
        from . import ai_state_audit as _llm
        if _llm.cost.over_budget(business_id):
            raise SystemExit(
                f"Business {business_id} is at/over its monthly budget; batch content skipped. "
                f"Raise monthly_budget_usd to proceed.")
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 -- budget check best-effort
        pass
    gaps = gaps_for_business(business_id)
    if max_gaps:
        gaps = gaps[:max_gaps]
    batches, total_pieces = [], 0
    for gap in gaps:
        try:
            res = generate_batch(business_id, gap, created_by=created_by)
            batches.append({"batch_id": res["batch_id"], "topic": res["topic"],
                            "pieces": len(res["produced"])})
            total_pieces += len(res["produced"])
        except Exception as e:  # noqa: BLE001 -- one gap failing must not abort the rest
            log.warning("gap batch failed for '%s': %s", gap.get("topic"), e)
            batches.append({"topic": gap.get("topic"), "pieces": 0, "error": str(e)[:200]})
    if gaps and total_pieces == 0:
        raise RuntimeError(f"batch content produced 0 pieces across {len(gaps)} gap(s); check the "
                           "orchestrator LLM key/budget. Not marking successful.")
    return {"gaps": len(gaps), "batches": batches, "pieces": total_pieces}
