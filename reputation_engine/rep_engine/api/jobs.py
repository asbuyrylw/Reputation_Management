"""Background job runner: enqueue engine work to api_jobs and run it OUT of the HTTP
request path. Engine functions open their own db(); audit()'s per-business advisory
lock + cost.over_budget stay the budget/concurrency backstops. run_job claims a job
atomically (UPDATE ... WHERE status='queued' RETURNING), so inline BackgroundTasks and
the worker process can't double-run the same job.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

try:
    from ..db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("rep_engine.api.jobs")


# ---------------------------------------------------------------------------
# Dispatch: job_type -> a callable(business_id, args) that runs an engine action.
# Each lazily imports its module so importing this file stays light.
# ---------------------------------------------------------------------------
def _run_audit(business_id: int, args: dict) -> None:
    try:
        from .. import ai_state_audit as m
    except ImportError:  # pragma: no cover
        import ai_state_audit as m  # type: ignore
    m.audit(business_id)
    _persist_audit_rollups(business_id)
    # A fresh full audit is new evidence: re-measure how far each content batch moved its gap
    # (SoV + alignment delta, % gap closed). DB-only + best-effort; never breaks the audit.
    try:
        _imp("content_impact").measure_all(business_id)
    except Exception as e:  # noqa: BLE001 -- impact refresh is best-effort
        log.debug("content impact measure skipped: %s", e)


def _run_fast_audit(business_id: int, args: dict) -> None:
    """Rec 9 -- the 'fast first look' tier: a reduced-battery audit that yields a real score cheaply
    (~a few min) so a new tenant sees something before the full ~30-50 min pipeline. Persists the
    same score rollups so it shows on the dashboard, but does NOT trigger the heavy gap/plan cascade
    (that's what the full audit + enqueue_downstream do). The full pipeline can run afterward."""
    try:
        from .. import ai_state_audit as m
    except ImportError:  # pragma: no cover
        import ai_state_audit as m  # type: ignore
    m.audit(business_id, fast=True)
    _persist_audit_rollups(business_id)


def _persist_audit_rollups(business_id: int) -> None:
    # Persist a durable per-run metric rollup so per-engine trends survive answer pruning.
    try:
        _imp("run_metrics").persist_latest(business_id)
    except Exception as e:  # noqa: BLE001 -- rollup is best-effort
        log.debug("run_metrics persist skipped: %s", e)
    # Persist the headline Narrative Crowding-Out Score (durable per-run rollup).
    try:
        _imp("narrative_score").compute(business_id)
    except Exception as e:  # noqa: BLE001 -- rollup is best-effort
        log.debug("narrative_score persist skipped: %s", e)


def _run_cycle(business_id: int, args: dict) -> None:
    import argparse
    try:
        from .. import orchestrator as o
    except ImportError:  # pragma: no cover
        import orchestrator as o  # type: ignore
    o.run_cycle(argparse.Namespace(business_id=business_id, resume=True))


def _run_production_briefs(business_id: int, args: dict) -> None:
    try:
        from .. import production_brief as p
    except ImportError:  # pragma: no cover
        import production_brief as p  # type: ignore
    p.plan(business_id)


def _run_citation_analyze(business_id: int, args: dict) -> None:
    try:
        from .. import citation_analytics as c
    except ImportError:  # pragma: no cover
        import citation_analytics as c  # type: ignore
    c.analyze(business_id, quiet=True)


def _run_light_sweep(business_id: int, args: dict) -> None:
    """Tiered cadence (#3d): a CHEAP weekly refresh -- re-check owned socials, recompute citation
    share, scan mentions, and run answer-change + incident alerts -- WITHOUT the expensive full
    AI-answer audit battery. Pair a weekly light_sweep with a monthly full `cycle` so monitoring
    stays fresh at a fraction of the cost. Each step is best-effort so one failure can't abort it."""
    for jt in ("audit_socials", "citation_analyze", "mentions_scan", "incident_scan", "alert_check"):
        fn = JOB_DISPATCH.get(jt)
        if not fn:
            continue
        try:
            fn(business_id, {})
        except Exception as e:  # noqa: BLE001 -- a light-sweep step must not abort the sweep
            log.warning("light_sweep step %s failed: %s", jt, e)


def _run_normalize_signals(business_id: int, args: dict) -> None:
    try:
        from .. import external_signals as es
    except ImportError:  # pragma: no cover
        import external_signals as es  # type: ignore
    es.normalize_pending(business_id)


def _imp(name: str):
    """Lazy import an engine module by name (package or loose-script fallback)."""
    try:
        import importlib
        return importlib.import_module(f"..{name}", __package__)
    except Exception:  # pragma: no cover -- loose-script fallback
        import importlib
        return importlib.import_module(name)


def _run_site_crawl(business_id: int, args: dict) -> None:
    # Default raised 15 -> 40 to match crawl_site()'s own default, so larger sites aren't
    # truncated mid-crawl. Small WordPress sites still finish well under the cap.
    _imp("site_crawl").crawl_cmd(business_id, int(args.get("max_pages", 40)))


def _run_ingest_source_material(business_id: int, args: dict) -> dict:
    # Auto-ingest the client's own website content into the grounding corpus (source_documents),
    # so generation is grounded in their real pages. Idempotent: replaces the prior site_crawl set.
    return _imp("source_ingest").ingest_site(
        business_id, max_pages=int(args.get("max_pages", 20)),
        created_by=args.get("created_by"))


def _run_gap_model(business_id: int, args: dict) -> None:
    _imp("ai_state_audit").build_gap_model(business_id)


def _run_neuron_enrich(business_id: int, args: dict) -> None:
    """Plan enrichment: run NeuronWriter SERP analyses for priority keywords (budget-guarded) and
    feed the terms/questions into the content briefs. Dormant-safe (no key -> no-op)."""
    _imp("neuron_enrich").enrich(business_id, max_keywords=int(args.get("max_keywords", 6)))


def _run_audit_socials(business_id: int, args: dict) -> None:
    """Phase B: discover + audit the business's OWN social profiles (website-link harvest + search +
    GBP), per platform. Standalone-runnable; the job cascade re-grounds the gap model + plan from
    just this fresh social info (cheap -- no AI-answer battery)."""
    _imp("social_audit").run(business_id, quiet=True)


def _run_plan(business_id: int, args: dict) -> None:
    _imp("strategy_generator").plan_cmd(business_id, args.get("start"))


def _run_sync_plan(business_id: int, args: dict) -> None:
    _imp("tracking").sync_plan(business_id)


def _run_generate_drafts(business_id: int, args: dict):
    # args.only_wo lets the UI generate a draft for a SINGLE content work order (the per-item
    # "Generate draft" button) instead of the whole batch. Return the created draft ids so the
    # produced_count convention (rec 12) sees a real count -- generate() raises on a 0-draft batch,
    # so a returned list is always non-empty, giving observability without a false 'empty' flag.
    created = _imp("content_generator").generate(business_id, only_wo=args.get("only_wo"),
                                                  content_type=args.get("content_type"))
    return {"created": created or []}


def _run_generate_content_batches(business_id: int, args: dict):
    """Gap-driven BATCH content: for each open content gap, produce MULTIPLE types (blog, article,
    white paper, social) at once and snapshot the gap's baseline Share-of-Voice for later impact
    measurement. args.gap_key generates one gap's batch; args.max_gaps caps the sweep."""
    cb = _imp("content_batch")
    created_by = args.get("requested_by")   # forwarded so content_batches.created_by isn't dropped
    if args.get("gap_key"):
        gap = next((g for g in cb.gaps_for_business(business_id) if g["gap_key"] == args["gap_key"]), None)
        if not gap:
            return {"batches": [], "pieces": 0, "reason": f"gap {args['gap_key']} not found"}
        res = cb.generate_batch(business_id, gap, content_types=args.get("content_types"),
                                created_by=created_by)
        return {"batches": [{"batch_id": res["batch_id"], "pieces": len(res["produced"])}],
                "pieces": len(res["produced"])}
    return cb.generate_all_gaps(business_id, max_gaps=args.get("max_gaps"), created_by=created_by)


def _run_generate_clusters(business_id: int, args: dict):
    """Cluster-driven content: plan the highest-leverage uncovered TOPIC CLUSTERS (pillar + spokes,
    cross-linked) from the topical-authority planner and generate each as a connected hub."""
    cb = _imp("content_batch")
    return cb.generate_clusters(business_id, max_clusters=args.get("max_clusters"),
                                max_spokes=args.get("max_spokes") or 4,
                                created_by=args.get("requested_by"))


def _run_render_video(business_id: int, args: dict):
    """Render a real MP4 for an explainer_video/video_script rich-media draft via HeyGen (avatar speaks
    the vetted script verbatim). Stores it as a video visual_asset + links it to the draft."""
    rm = _imp("rich_media_generator")
    return rm.render_video_for_draft(business_id, args.get("draft_id"), reviewer=args.get("requested_by"),
                                     provider=args.get("provider"))


def _run_publish_youtube(business_id: int, args: dict):
    """Publish a rendered `video` visual_asset to the owner's YouTube channel (+ SRT captions)."""
    yp = _imp("youtube_publish")
    return yp.publish_video(business_id, args.get("visual_id"),
                            privacy=args.get("privacy") or "unlisted")


def _run_poll_video_renders(business_id: int, args: dict):
    """Completion sweep for async v3 Video Agent renders: download + store the MP4 once the Agent
    finishes (~20-45 min), so the render never blocks the worker. Self-clears its schedule when idle."""
    rm = _imp("rich_media_generator")
    return rm.poll_pending_agent_renders(business_id)


def _run_measure_content_impact(business_id: int, args: dict):
    """Measure how far each content batch moved the gap it targets (SoV + alignment delta, % gap
    closed) against the latest audit. DB-only; safe to run after every audit."""
    return _imp("content_impact").measure_all(business_id)


def _run_report(business_id: int, args: dict) -> None:
    _imp("report_generator").generate(business_id)


def _run_discovery(business_id: int, args: dict) -> None:
    """Find outreach targets (journalists/outlets/podcasts/communities) via the Discovery agent."""
    _imp("agent_discovery").discover(business_id)


def _run_enrich_outreach(business_id: int, args: dict):
    """Best-effort: auto-find public contact info for outreach targets (marked unverified)."""
    return _imp("agent_discovery").enrich_contacts(business_id, quiet=True)


def _run_social_verify(business_id: int, args: dict):
    """Best-effort: check whether the business actually has a profile on each platform, so the
    social recommendations can become confirmed 'create' vs 'improve'."""
    return _imp("social_presence").verify(business_id, quiet=True)


def _run_mentions_scan(business_id: int, args: dict):
    """Scan the configured sources for new mentions, then draft (human-gated) replies.
    Returns the discovered/drafted counts so a scan that found nothing reads as such in the
    job result rather than a bare 'complete'."""
    mm = _imp("mention_monitor")
    found = mm.discover(business_id, quiet=True) or {}
    drafted = mm.draft_replies(business_id, quiet=True) or {}
    return {"discovered": found.get("found"), "drafted": drafted.get("drafted")}


def _run_incident_scan(business_id: int, args: dict) -> None:
    """Triage negative mentions into incidents with drafted, human-gated responses."""
    _imp("agent_incident").scan(business_id)


def _run_learn(business_id: int, args: dict) -> None:
    """Recompute 'what's working' from this business's own audit-to-audit results."""
    _imp("feedback_loop").learn(business_id, quiet=True)


def _run_alert_check(business_id: int, args: dict) -> None:
    """Raise proactive alerts (score drop, new incidents/negative mentions, drafts waiting,
    and AI answer-change alerts)."""
    _imp("notifications").check_and_notify(business_id, quiet=True)
    try:
        _imp("answer_changes").check_and_alert(business_id)  # Wave 4, item 17
    except Exception:  # noqa: BLE001 -- answer-change detection must not break the alert job
        pass


def _run_benchmark(business_id: int, args: dict):
    """Competitor benchmark: how often AI surfaces YOU vs each registered competitor."""
    return _imp("competitor").benchmark(business_id, quiet=True)


def _run_local_rank(business_id: int, args: dict):
    """Local SEO: capture Google front-page + local-pack rankings for the category-local
    queries (subject + competitors). No-op without SERPER_API_KEY. Returns a summary dict
    ({skipped, reason} or {run_id, rows, queries}) so the UI can explain what happened.
    Also refreshes the 'time to page 1' projection so the goal/timeline stays current."""
    out = _imp("local_seo").track(business_id, quiet=True)
    try:
        _imp("local_seo_goals").estimate(business_id, quiet=True, persist=True)
    except Exception:  # noqa: BLE001 -- the goal is best-effort; never fail the rank job
        pass
    return out


def _run_suggest_prompts(business_id: int, args: dict):
    """LLM proposes candidate tracking prompts (saved DISABLED for owner review)."""
    return _imp("prompts").suggest(business_id, n=int(args.get("n", 8)), quiet=True)


def _run_refresh_failed(business_id: int, args: dict):
    """Re-run only the failed answers in the latest audit (optionally limited to args['engines'],
    e.g. ['perplexity']) and merge them in, then rebuild the gap model. Lets a provider that was
    down during the audit be topped up later without re-paying for the answers that worked."""
    engines = args.get("engines") or None
    return _imp("ai_state_audit").refresh_failed_answers(business_id, engines=engines)


def _run_suggest_keywords(business_id: int, args: dict):
    """LLM proposes brand-monitoring keywords. Returns {keywords:[...]} in the job result for
    the owner to review and add (nothing is saved here)."""
    return _imp("mention_monitor").suggest_keywords(business_id, n=int(args.get("n", 10)), quiet=True)


def _run_keyword_research(business_id: int, args: dict):
    """SEO keyword intelligence: LLM-seed grounded with real Google data (Serper related/PAA/
    autocomplete) -> ranked target_keywords the content generator + gap model + UI consume.
    Returns a summary {seeds, serper_candidates, stored, serper_used}."""
    return _imp("keyword_research").research(business_id)


def _run_ingest_gbp_reviews(business_id: int, args: dict):
    """Snapshot the business's Google rating + review count and ingest recent reviews (Serper).
    Returns {rating, review_count, reviews_ingested, place} or {skipped, reason}."""
    return _imp("gbp_reviews").ingest(business_id)


def _run_refresh_connection_token(business_id: int, args: dict):
    """Integrations: refresh OAuth connection tokens expiring within 24h (re-encrypt). A hard
    failure marks the connection revoked + alerts + strands dependent publish targets."""
    return _imp("connections.vault").refresh_due(business_id)


def _run_publish_sweep(business_id: int, args: dict):
    """Integrations: publish every due owned-channel target for the business (network-grain drain).
    Returns {published, scheduled, failed, skipped}."""
    return _imp("publishing.runner").drain(business_id)


def _run_ingest_gsc(business_id: int, args: dict):
    """Search Console: ingest daily clicks/impressions/position + windowed top queries/pages.
    Keyless-safe no-op without an active GSC connection + selected property."""
    return _imp("gsc_data").ingest(business_id)


def _run_ingest_ga(business_id: int, args: dict):
    """Analytics (GA4): ingest daily sessions/users/conversions + windowed top pages + channel mix.
    Keyless-safe no-op without an active GA connection + selected property."""
    return _imp("ga_data").ingest(business_id)


def _run_dataforseo_intel(business_id: int, args: dict):
    """Competitor keyword gaps (what rivals rank for that we don't) + brand mentions/sentiment via
    DataForSEO. Cheap synchronous calls; dormant-safe without DataForSEO creds."""
    return _imp("dataforseo").run_intel(business_id)


def _run_dataforseo_reviews(business_id: int, args: dict):
    """Pull Google (+ optional Trustpilot) reviews for the business via DataForSEO (task-based)."""
    return _imp("dataforseo").run_reviews(business_id)


def _run_enrich_keyword_volume(business_id: int, args: dict):
    """Batch-enrich ALL of a business's stored target keywords with real search volume/CPC in the
    fewest provider calls (one request per <=700 keywords). Dormant-safe + balance-guarded."""
    return _imp("keyword_research").enrich_target_keywords(business_id)


def _run_ingest_pagespeed(business_id: int, args: dict):
    """PageSpeed Insights: grade owned (+ competitor) URLs on Lighthouse + Core Web Vitals.
    Gated by PAGESPEED_ENABLED; no-op without it. Live scores need a PAGESPEED_API_KEY."""
    urls = (args or {}).get("urls")
    strategy = (args or {}).get("strategy")
    return _imp("pagespeed").ingest(business_id, urls=urls, strategy=strategy)


def _run_index_own_content(business_id: int, args: dict):
    """White-hat indexing: ping search engines about the owned-content feed + report GSC index
    status. Keyless-safe (RSS/ping always work; index check no-ops without GSC). Also runs the GSC
    full-surface inspection (canonical/schema/index-reason harvest + sitemap submit) when a GSC
    connection exists -- no-ops otherwise."""
    out = _imp("indexing").run(business_id)
    try:
        out["gsc_inspect"] = _imp("gsc_inspect").run(business_id)
    except Exception as e:  # noqa: BLE001 -- inspection must never fail the indexing job
        out["gsc_inspect"] = {"error": str(e)[:200]}
    return out


def _run_post_review_replies(business_id: int, args: dict):
    """Integrations: post every approved Google review reply (drain). Keyless-safe no-op without
    an allowlist-approved GBP connection. Returns {posted, skipped, failed}."""
    return _imp("gbp_reviews").post_approved(business_id)


def _run_gbp_reconcile(business_id: int, args: dict):
    """Integrations: soft-delete stale reviews + redact replied-review author PII."""
    return _imp("gbp_reviews").reconcile(business_id)


def _run_post_mention_replies(business_id: int, args: dict):
    """Integrations: post owned-surface approved mention replies (drain). Keyless-safe no-op until
    the social reply transport lands. third_party never enters this path."""
    return _imp("mention_monitor").post_approved(business_id)


def _run_generate_visual(business_id: int, args: dict):
    """CI-4: generate a human-gated visual (image | quote_card | video_brief | video). Dormant-safe --
    image/video gen return {skipped} without a provider key; quote-cards always render locally."""
    vc = _imp("visual_content")
    kind = (args.get("kind") or "image").lower()
    wo = args.get("work_order_id")
    if kind == "quote_card":
        res = vc.generate_quote_card(business_id, args.get("text") or args.get("prompt") or "",
                                     attribution=args.get("attribution"), work_order_id=wo)
    elif kind == "video_brief":
        res = vc.generate_video_brief(business_id, args.get("topic") or args.get("prompt") or "",
                                      work_order_id=wo)
    elif kind == "video":
        res = vc.generate_video(business_id, args.get("prompt") or args.get("topic") or "",
                                work_order_id=wo, draft_id=args.get("draft_id"),
                                aspect_ratio=args.get("aspect_ratio") or "16:9")
    else:
        res = vc.generate_image(business_id, args.get("prompt") or "", kind=kind,
                                size=args.get("size") or "1024x1024", work_order_id=wo,
                                draft_id=args.get("draft_id"))
    # Surface a skipped/failed generation as a FAILED job. Unlike the text/rich path (which raises a
    # 0-draft RuntimeError), the visual generators RETURN {skipped}/{ok:False} dicts, which run_job
    # would otherwise record as a green 'complete' with no asset -- a silent failure. Raise so the
    # job is marked failed with the real reason. quote_card always renders locally (never skips).
    if isinstance(res, dict) and (res.get("skipped") or res.get("ok") is False):
        reason = res.get("reason") or res.get("error") or "generation produced no asset"
        raise RuntimeError(f"{kind} generation failed: {reason}")
    return res


def _run_katteb_seo(business_id: int, args: dict):
    """Run a Katteb SEO/competitor analysis on a draft (HEAVY, 1000 credits, human-triggered) and
    merge the result into the draft's quality_notes.katteb. Dormant-safe: {skipped} without a key.
    Takes 1-3 min (Katteb polls), which is why it's a job, not an inline request."""
    kb = _imp("katteb")
    if not kb.configured():
        return {"skipped": True, "reason": "Katteb not configured"}
    draft_id = args.get("draft_id")
    if not draft_id:
        return {"ok": False, "error": "draft_id required"}
    from ..db import db  # local import: keep jobs.py import-light
    import json as _json
    with db() as conn:
        row = conn.execute(
            "SELECT body, target_query FROM content_drafts WHERE id=%s AND business_id=%s",
            (draft_id, business_id)).fetchone()
    if not row:
        return {"ok": False, "error": "draft not found"}
    res = kb.seo_analyze_wait(row["body"] or "", keyword=row.get("target_query") or None, kind="text")
    if res.get("skipped") or not res.get("ok"):
        return res
    katteb_block = {
        "seo_score": (res.get("article_data") or {}).get("seo_score"),
        "competitor_scores": (res.get("competitor_data") or {}).get("scores"),
        "structure": (res.get("competitor_data") or {}).get("structure"),
        "competitors": (res.get("competitor_data") or {}).get("competitors") or [],
        "keyword": res.get("keyword"),
        "analyzed_at": res.get("analyzed_at"),
        "credits_charged": res.get("credits_charged"),
    }
    with db() as conn:
        conn.execute(
            "UPDATE content_drafts SET quality_notes = "
            "COALESCE(quality_notes, '{}'::jsonb) || jsonb_build_object('katteb', %s::jsonb) "
            "WHERE id=%s AND business_id=%s",
            (_json.dumps(katteb_block), draft_id, business_id))
        conn.commit()
    return {"ok": True, "draft_id": draft_id, "katteb": katteb_block}


JOB_DISPATCH = {
    # core pipeline (each step individually runnable, plus the full monthly cycle)
    "audit": _run_audit,
    "fast_audit": _run_fast_audit,   # rec 9: reduced-battery 'first look' (score fast, no cascade)
    "site_crawl": _run_site_crawl,
    "ingest_source_material": _run_ingest_source_material,   # crawl -> grounding corpus (G.1)
    "audit_socials": _run_audit_socials,
    "gap_model": _run_gap_model,
    "plan": _run_plan,
    "sync_plan": _run_sync_plan,
    "generate_drafts": _run_generate_drafts,
    "generate_content_batches": _run_generate_content_batches,
    "generate_clusters": _run_generate_clusters,
    "render_video": _run_render_video,
    "publish_youtube": _run_publish_youtube,
    "poll_video_renders": _run_poll_video_renders,   # multi-type content per gap
    "measure_content_impact": _run_measure_content_impact,       # did the content move the gap?
    "report": _run_report,
    "cycle": _run_cycle,
    # monitoring + outreach + learning
    "discovery": _run_discovery,
    "enrich_outreach": _run_enrich_outreach,
    "social_verify": _run_social_verify,
    "mentions_scan": _run_mentions_scan,
    "incident_scan": _run_incident_scan,
    "citation_analyze": _run_citation_analyze,
    "light_sweep": _run_light_sweep,
    "learn": _run_learn,
    "alert_check": _run_alert_check,
    "benchmark": _run_benchmark,
    "local_rank": _run_local_rank,
    "refresh_failed": _run_refresh_failed,
    "suggest_prompts": _run_suggest_prompts,
    "suggest_keywords": _run_suggest_keywords,
    "keyword_research": _run_keyword_research,
    "neuron_enrich": _run_neuron_enrich,
    "ingest_gbp_reviews": _run_ingest_gbp_reviews,
    "production_briefs": _run_production_briefs,
    "normalize_signals": _run_normalize_signals,
    # integrations drains (singleton per (business, job_type); each claims every due row)
    "refresh_connection_token": _run_refresh_connection_token,
    "publish_sweep": _run_publish_sweep,
    "post_review_replies": _run_post_review_replies,
    "gbp_reconcile": _run_gbp_reconcile,
    "post_mention_replies": _run_post_mention_replies,
    # visual content (CI-4)
    "generate_visual": _run_generate_visual,
    # Katteb SEO/competitor analysis (human-triggered, heavy)
    "katteb_seo": _run_katteb_seo,
    # search analytics (Wave 1)
    "ingest_gsc": _run_ingest_gsc,
    "ingest_ga": _run_ingest_ga,
    # technical SEO / Core Web Vitals (adopt batch)
    "ingest_pagespeed": _run_ingest_pagespeed,
    # batch keyword-volume enrichment (fewest DataForSEO calls)
    "enrich_keyword_volume": _run_enrich_keyword_volume,
    # DataForSEO intelligence: competitor keyword gaps + mentions/sentiment + reviews
    "dataforseo_intel": _run_dataforseo_intel,
    "dataforseo_reviews": _run_dataforseo_reviews,
    # white-hat own-content indexing (Wave 3)
    "index_own_content": _run_index_own_content,
}


# Generous enough to clear a genuinely crashed/wedged job, but comfortably longer than the
# worst-case real job (a full `cycle` = audit -> gap -> plan -> report can run many minutes).
# Too small and a legitimately long job gets reaped, the dedup frees up, and a re-trigger or the
# scheduler starts a second concurrent copy.
STALE_RUNNING_MINUTES = 90


def reap_stale(max_minutes: int = STALE_RUNNING_MINUTES) -> int:
    """Mark jobs stuck in 'running' beyond max_minutes as failed. The enqueue dedup treats
    'running' as active, so a process crash mid-job would otherwise PERMANENTLY block that
    (business, job_type) from running again. Self-heals both inline and worker modes."""
    with db() as conn:
        rows = conn.execute(
            "UPDATE api_jobs SET status='failed', "
            "error='timed out (worker restart or stuck job) -- please re-run', finished_at=now() "
            "WHERE status='running' AND started_at < now() - make_interval(mins => %s) RETURNING id",
            (max_minutes,),
        ).fetchall()
        conn.commit()
    if rows:
        log.warning("reaped %d stale running job(s)", len(rows))
    return len(rows)


# Per-(business, job_type) trigger rate limits: (max_attempts, window_seconds). The enqueue
# dedup already prevents two of the same job running at once; these cap how fast a client can
# re-trigger EXPENSIVE (LLM/search-spending) work over time, so a stuck finger can't run up spend.
_JOB_RATE_LIMITS = {
    "audit": (4, 3600), "fast_audit": (6, 3600), "cycle": (3, 3600), "benchmark": (6, 3600), "report": (6, 3600),
    "generate_content_batches": (4, 3600), "measure_content_impact": (12, 3600),
    "discovery": (8, 3600), "enrich_outreach": (6, 3600), "social_verify": (6, 3600),
    "gap_model": (10, 3600), "plan": (12, 3600), "production_briefs": (10, 3600),
    "generate_drafts": (20, 3600), "citation_analyze": (10, 3600), "mentions_scan": (12, 3600),
    "local_rank": (12, 3600), "suggest_prompts": (12, 3600), "suggest_keywords": (12, 3600),
    "keyword_research": (8, 3600), "ingest_gbp_reviews": (6, 3600), "neuron_enrich": (4, 3600),
    "refresh_failed": (6, 3600), "incident_scan": (10, 3600), "light_sweep": (4, 3600),
    # integrations drains: these cap how fast the SWEEP re-triggers, NOT how many posts happen
    # (per-post volume is enforced by integration_settings caps inside the runners).
    "refresh_connection_token": (4, 3600),
    "publish_sweep": (6, 3600),
    "post_review_replies": (12, 3600),
    "gbp_reconcile": (2, 3600),
    "post_mention_replies": (12, 3600),
    "generate_visual": (30, 3600),
    # video render (HeyGen/Veo, cost per render) + YouTube publish + cluster content (multi-piece LLM).
    "render_video": (6, 3600),
    "publish_youtube": (6, 3600),
    "poll_video_renders": (30, 3600),   # scheduled completion sweep for async Video Agent renders
    "generate_clusters": (4, 3600),
    # Katteb heavy op = 1000 credits + Katteb's own 6/hour cap; keep the trigger rate under that.
    "katteb_seo": (6, 3600),
    "ingest_gsc": (6, 3600),
    "ingest_ga": (6, 3600),
    "ingest_pagespeed": (6, 3600),
    "enrich_keyword_volume": (6, 3600),
    "dataforseo_intel": (6, 3600),
    "dataforseo_reviews": (6, 3600),
    "index_own_content": (4, 3600),
    "ingest_source_material": (6, 3600),   # crawl the client's site into the grounding corpus
    # "run everything" enqueues the whole pipeline (~$8-12 of LLM/search spend) — once a day.
    "run_everything": (1, 86400),
}


def rate_ok(business_id: int, job_type: str) -> bool:
    """True if triggering this job for this business is within its per-window rate limit.
    Cheap/internal jobs (not in the table) are unlimited. Disabled under pytest."""
    try:
        from . import ratelimit as _rl
    except ImportError:  # pragma: no cover
        import ratelimit as _rl  # type: ignore
    if not _rl.enabled():
        return True
    limit = _JOB_RATE_LIMITS.get(job_type)
    if not limit:
        return True
    return _rl.rate_check_window(f"job:{business_id}:{job_type}", limit[0], limit[1])


def enqueue(business_id: int, job_type: str, requested_by: Optional[int] = None,
            args: Optional[dict] = None,
            depends_on: Optional[list] = None) -> tuple[Optional[int], Optional[int]]:
    """Insert a queued job unless one of the same type is already active for this
    business. Returns (job_id, active_job_id): job_id set on success; otherwise
    active_job_id of the in-flight job (so the caller can 409).

    `depends_on` is a list of api_jobs.id this job must wait for: pump() will not claim it
    until ALL of them are 'complete'. This makes a multi-step pipeline's ordering explicit so
    it is correct with ANY number of workers (not just a single FIFO consumer)."""
    if job_type not in JOB_DISPATCH:
        raise ValueError(f"unknown job_type: {job_type}")
    reap_stale()  # clear any deadlocked 'running' job first, so a crash can't block forever
    deps = list(depends_on) if depends_on else None
    with db() as conn:
        active = conn.execute(
            "SELECT id FROM api_jobs WHERE business_id=%s AND job_type=%s "
            "AND status IN ('queued','running') ORDER BY id DESC LIMIT 1",
            (business_id, job_type),
        ).fetchone()
        if active:
            return None, active["id"]
        # Atomic dedup: the SELECT above is a fast path, but the partial UNIQUE index
        # uq_api_jobs_active(business_id, job_type) WHERE status IN ('queued','running') is the
        # real guard against two concurrent triggers both inserting (which would double the LLM
        # spend the dedup exists to prevent). ON CONFLICT DO NOTHING -> no row means we lost the
        # race, so return the winner's id.
        row = conn.execute(
            "INSERT INTO api_jobs (business_id, job_type, status, args, requested_by, depends_on) "
            "VALUES (%s,%s,'queued',%s,%s,%s) "
            "ON CONFLICT (business_id, job_type) WHERE status IN ('queued','running') DO NOTHING "
            "RETURNING id",
            (business_id, job_type, json.dumps(args or {}), requested_by, deps),
        ).fetchone()
        conn.commit()
        if row:
            return row["id"], None
        active = conn.execute(
            "SELECT id FROM api_jobs WHERE business_id=%s AND job_type=%s "
            "AND status IN ('queued','running') ORDER BY id DESC LIMIT 1",
            (business_id, job_type),
        ).fetchone()
        return None, (active["id"] if active else None)


# Rec 12: job types whose whole point is to PRODUCE something (rows, drafts, keywords, a plan...).
# For these, "complete" must imply "produced something" -- a 0-output run should NOT read as a clean
# green. We derive a produced_count from the handler's structured return and flag empty runs so the
# UI/logs can distinguish "ran and did work" from "ran and produced nothing". This is an
# observability signal only -- some 0-output runs (e.g. nothing new to do) are legitimately empty, so
# we never flip status to failed here.
_OUTPUT_PRODUCING_JOBS = frozenset({
    "audit", "gap_model", "plan", "sync_plan", "generate_drafts", "keyword_research",
    "production_briefs", "citation_analyze", "benchmark", "local_rank", "generate_content_batches",
    "ingest_source_material",
})

# Keys a handler's return dict commonly uses to report how many items it produced. First hit wins.
_PRODUCED_COUNT_KEYS = ("created", "count", "n", "rows", "drafts", "keywords", "items", "stored", "pieces", "ingested")


def _derive_produced_count(result) -> Optional[int]:
    """Best-effort produced_count from a handler's structured return. Returns an int when derivable,
    else None (meaning 'unknown', not zero). Prefers explicit count keys; falls back to the length of
    the first list-valued field. Never raises -- observability must not break job recording."""
    if not isinstance(result, dict):
        return None
    try:
        for k in _PRODUCED_COUNT_KEYS:
            if k in result:
                v = result[k]
                if isinstance(v, bool):  # bools are ints in Python; a flag isn't a count
                    continue
                if isinstance(v, (int, float)):
                    return int(v)
                if isinstance(v, (list, tuple, set, dict)):
                    return len(v)
        for v in result.values():
            if isinstance(v, (list, tuple)):
                return len(v)
    except Exception:  # noqa: BLE001 -- never let count derivation break recording
        return None
    return None


def _annotate_produced(job_type: str, status: str, result):
    """Rec 12: for OUTPUT-PRODUCING job types, attach produced_count and flag 0-output runs.
    Only acts when the job completed (a 'failed' run already reads red). Best-effort."""
    if status != "complete" or job_type not in _OUTPUT_PRODUCING_JOBS:
        return result
    produced = _derive_produced_count(result)
    # POSITIVELY empty only: an empty dict, or a derivable count of exactly 0. A None/unknown return
    # is NOT treated as empty -- several core handlers (audit, gap_model, plan, sync_plan) return None
    # on success, so flagging None as empty would false-positive EVERY successful run (the inversion
    # QA caught). We only flag when we can affirmatively see zero output.
    empty = (isinstance(result, dict) and not result) or (produced == 0)
    if produced is not None and isinstance(result, dict):
        result = {**result, "produced_count": produced}
    if empty:
        base = result if isinstance(result, dict) else {}
        result = {**base, "complete_empty": True}
    return result


def _annotate_budget(business_id: int, status: str, result):
    """If the business is over its monthly budget, tag the job result with {budget_exhausted,
    spent, cap} and fire a once-a-month 'budget_exhausted' notification. Best-effort: never let
    a budget check break job recording."""
    try:
        cost = _imp("cost")
        if not cost.over_budget(business_id):
            return result
        spent = round(float(cost.month_spend(business_id)), 2)
        cap = round(float(cost.budget_for(business_id)), 2)
        result = {**(result or {}), "budget_exhausted": True, "spent": spent, "cap": cap}
        import datetime as _dt
        month = _dt.date.today().strftime("%Y-%m")
        _imp("notifications").notify(
            business_id, "budget_exhausted", "You've used this month's AI budget",
            f"You've spent about ${spent:.2f} of your ${cap:.2f} monthly cap, so new audits and "
            "content generation will pause until it resets next month (or you raise the cap).",
            severity="warning", dedup_key=f"budget_exhausted_{business_id}_{month}")
    except Exception as e:  # noqa: BLE001
        log.debug("budget annotation skipped: %s", e)
    return result


def run_job(job_id: int) -> Optional[str]:
    """Atomically claim a queued job and execute it; record terminal status. Returns
    the final status, or None if the job was already claimed/finished."""
    with db() as conn:
        job = conn.execute(
            "UPDATE api_jobs SET status='running', started_at=now() "
            "WHERE id=%s AND status='queued' RETURNING *",
            (job_id,),
        ).fetchone()
        conn.commit()
    if not job:
        return None
    status, err, result = "complete", None, None
    try:
        handler = JOB_DISPATCH.get(job["job_type"])
        if handler is None:
            # A bare KeyError here means a long-lived worker cached its dispatch table before a
            # deploy that added this job type -- self-explain instead of an opaque "'job_type'".
            raise RuntimeError(
                f"unknown job_type {job['job_type']!r} -- the worker is likely running stale code "
                f"(known types: {len(JOB_DISPATCH)}); redeploy/restart the worker service.")
        ret = handler(job["business_id"], job.get("args") or {})
        # Persist the dispatch fn's structured return (e.g. local_rank's {skipped, reason} or
        # {rows, queries}) so a job that did nothing reportable doesn't read as a bare "complete".
        if isinstance(ret, dict):
            result = ret
        # Rec 12: "complete must imply produced-something." For output-producing job types, attach a
        # produced_count and flag a 0-output run so it stops reading as a clean green. Status stays
        # 'complete' (some empty runs are legitimate) -- this is an observability signal + WARNING.
        result = _annotate_produced(job["job_type"], status, result)
        if isinstance(result, dict) and result.get("complete_empty"):
            log.warning("job %s completed but produced nothing (business %s)",
                        job["job_type"], job["business_id"])
    except Exception as e:  # noqa: BLE001 -- record failure, never crash the runner
        status, err = "failed", str(e)[:2000]
        log.warning("job %s (%s) failed: %s", job_id, job["job_type"], e)
    # Budget-abort made LOUD: if this business is over its monthly cap, don't leave a cryptic red
    # "failed" -- annotate the result with the spend/cap and raise a clear, deduped alert so the
    # owner sees "you've used your budget" (and can self-serve an upgrade) instead of "it's broken".
    result = _annotate_budget(job["business_id"], status, result)
    if isinstance(result, dict) and result.get("budget_exhausted") and status == "failed":
        err = (f"Budget reached: ${result['spent']:.2f} of your ${result['cap']:.2f} monthly cap. "
               "It resets at the start of next month — or raise the cap to keep going.")
    with db() as conn:
        conn.execute(
            "UPDATE api_jobs SET status=%s, error=%s, result=%s, finished_at=now() WHERE id=%s",
            # default=str so a handler returning a Decimal/date can never raise out of run_job and
            # strand the job as 'running' until reap_stale (90m). Records the real status instead.
            (status, err, json.dumps(result, default=str) if result is not None else None, job_id),
        )
        conn.commit()
    # Fan out a job.finished event to the client's stack (GHL/Zapier/...). No-op until
    # WEBHOOK_URL is set; best-effort -- never let a webhook affect job recording.
    try:
        _imp("webhooks").emit(job["business_id"], "job.finished",
                              {"job_type": job["job_type"], "status": status, "result": result})
    except Exception as e:  # noqa: BLE001
        log.debug("job webhook skipped: %s", e)
    return status


def pump() -> bool:
    """Run the next RUNNABLE queued job, if any. Returns True if one ran. A job is runnable only
    once all of its `depends_on` jobs are 'complete' -- so a multi-step pipeline stays correctly
    ordered with any number of workers, not just a single FIFO consumer."""
    with db() as conn:
        # Cascade-fail a queued job whose prerequisite failed/aborted, so it can't wait forever.
        # (Runs each tick, so the failure propagates down the chain over successive pumps.)
        conn.execute(
            "UPDATE api_jobs SET status='failed', "
            "error='skipped: a prerequisite job failed', finished_at=now() "
            "WHERE status='queued' AND depends_on IS NOT NULL AND EXISTS ("
            "  SELECT 1 FROM api_jobs d WHERE d.id = ANY(api_jobs.depends_on) "
            "  AND d.status IN ('failed','aborted'))"
        )
        conn.commit()
        # Claim the oldest queued job whose dependencies are ALL complete (or it has none).
        row = conn.execute(
            "SELECT id FROM api_jobs j WHERE status='queued' "
            "AND NOT EXISTS (SELECT 1 FROM api_jobs d "
            "                WHERE d.id = ANY(j.depends_on) AND d.status <> 'complete') "
            "ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        return False
    run_job(row["id"])
    return True
