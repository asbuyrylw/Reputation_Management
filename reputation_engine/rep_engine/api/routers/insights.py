"""SEO site audit + gap model (Phase 2 reads). Both return the latest persisted
JSONB document (or null when none exists yet)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, require_business_editor

router = APIRouter(prefix="/businesses/{business_id}", tags=["insights"])


def _gsc():
    try:
        from ... import gsc_data as g
    except ImportError:  # pragma: no cover
        import gsc_data as g  # type: ignore
    return g


@router.get("/llms-txt")
def llms_txt(business_id: int = Depends(authorize_business)):
    """Generate an llms.txt for the client's site (AEO/GEO lever -- tells AI crawlers what the site
    is + its most citable pages). Returns {content, page_count}. Place it at /llms.txt."""
    try:
        from ... import llms_txt as _lt
    except ImportError:  # pragma: no cover
        import llms_txt as _lt  # type: ignore
    return _lt.generate(business_id)


@router.get("/schema-verify")
def schema_verify(business_id: int = Depends(authorize_business)):
    """Fetch the live key pages and confirm which recommended JSON-LD schema is actually deployed
    vs still missing -- so 'add schema' tasks can be verified done."""
    try:
        from ... import schema_verify as _sv
    except ImportError:  # pragma: no cover
        import schema_verify as _sv  # type: ignore
    return _sv.check(business_id)


@router.get("/gsc-summary")
def gsc_summary(business_id: int = Depends(authorize_business)):
    return _gsc().latest(business_id)


@router.get("/gsc-trend")
def gsc_trend(days: Optional[int] = None, business_id: int = Depends(authorize_business)):
    return _gsc().trend(business_id, days)


@router.get("/gsc-queries")
def gsc_queries(limit: int = 25, business_id: int = Depends(authorize_business)):
    return _gsc().top_queries(business_id, limit)


@router.get("/gsc-pages")
def gsc_pages(limit: int = 25, ours_only: bool = False, business_id: int = Depends(authorize_business)):
    return _gsc().top_pages(business_id, limit, ours_only)


@router.get("/gsc-opportunities")
def gsc_opportunities(business_id: int = Depends(authorize_business)):
    return _gsc().opportunities(business_id)


@router.get("/gsc-roi")
def gsc_roi(business_id: int = Depends(authorize_business)):
    return _gsc().roi_summary(business_id)


def _ga():
    try:
        from ... import ga_data as g
    except ImportError:  # pragma: no cover
        import ga_data as g  # type: ignore
    return g


@router.get("/ga-summary")
def ga_summary(business_id: int = Depends(authorize_business)):
    return _ga().latest(business_id)


@router.get("/ga-trend")
def ga_trend(days: Optional[int] = None, business_id: int = Depends(authorize_business)):
    return _ga().trend(business_id, days)


@router.get("/ga-pages")
def ga_pages(limit: int = 25, ours_only: bool = False, business_id: int = Depends(authorize_business)):
    return _ga().top_pages(business_id, limit, ours_only)


@router.get("/ga-channels")
def ga_channels(business_id: int = Depends(authorize_business)):
    return _ga().channels(business_id)


def _ps():
    try:
        from ... import pagespeed as p
    except ImportError:  # pragma: no cover
        import pagespeed as p  # type: ignore
    return p


@router.get("/pagespeed")
def pagespeed(business_id: int = Depends(authorize_business)):
    """Latest PageSpeed / Core Web Vitals scores for owned (+ competitor) URLs, a rollup, and the
    structured technical-SEO gaps that feed the gap model + advisor. Dormant-safe: returns
    {has_data:false} until the ingest_pagespeed job has graded pages (needs PAGESPEED_API_KEY)."""
    p = _ps()
    out = p.latest(business_id)
    out["technical_gaps"] = p.technical_gaps(business_id)
    out["configured"] = p.configured()
    return out


@router.get("/data-sources")
def data_sources(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Live status of every data source that powers the new features, so the UI can show
    connected / needs-key / needs-connection instead of silently-empty cards. Env-key features
    (PageSpeed, keyword volume) report a `configured` bool; OAuth features report whether an active
    connection exists + the property. Read-only; never raises."""
    def _conn(kind: str):
        try:
            r = conn.execute("SELECT account_ref, meta, updated_at FROM platform_connections WHERE "
                             "business_id=%s AND kind=%s AND status='active' ORDER BY id DESC LIMIT 1",
                             (business_id, kind)).fetchone()
        except Exception:  # noqa: BLE001
            conn.rollback(); return {"connected": False}
        if not r:
            return {"connected": False}
        meta = r.get("meta") or {}
        return {"connected": True, "property": meta.get("gsc_property") or meta.get("ga_property") or r.get("account_ref"),
                "synced_at": r["updated_at"].isoformat() if r.get("updated_at") else None}
    try:
        from ... import pagespeed as _ps_m, keyword_research as _kr, dataforseo as _dfs
    except ImportError:  # pragma: no cover
        import pagespeed as _ps_m; import keyword_research as _kr; import dataforseo as _dfs  # type: ignore
    # DataForSEO powers competitor keyword intel + brand mentions/sentiment + cross-platform reviews.
    # Report configured + whether ingest has actually STORED anything yet (so the card says
    # "connected, last synced …" rather than a bare configured flag).
    dfs_configured = _dfs.configured()
    dfs_ment = _dfs.latest_mentions(business_id) if dfs_configured else None
    dfs_revs = _dfs.latest_reviews(business_id) if dfs_configured else []
    try:
        comp_gaps = conn.execute("SELECT COUNT(*) c FROM target_keywords WHERE business_id=%s AND "
                                 "source='dataforseo_competitor'", (business_id,)).fetchone()["c"]
    except Exception:  # noqa: BLE001
        conn.rollback(); comp_gaps = 0
    return {
        "google_search_console": {**_conn("google_search_console"), "unlocks": "real rankings, clicks & index/canonical health"},
        "google_analytics": {**_conn("google_analytics"), "unlocks": "traffic & conversions per published page"},
        "pagespeed": {"configured": _ps_m.configured(), "env_key": "PAGESPEED_API_KEY", "unlocks": "Core Web Vitals & technical-SEO grades"},
        "keyword_volume": {"configured": _kr.volume_configured(), "env_key": "KEYWORD_VOLUME_PROVIDER + DataForSEO/KeywordsEverywhere", "unlocks": "real search volume, difficulty & CPC"},
        "dataforseo": {"configured": dfs_configured, "env_key": "DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD",
                       "competitor_gaps": comp_gaps, "has_mentions": bool(dfs_ment),
                       "review_platforms": [r["platform"] for r in dfs_revs],
                       "synced_at": (dfs_ment or {}).get("created_at") if dfs_ment else (dfs_revs[0]["created_at"] if dfs_revs else None),
                       "unlocks": "competitor keyword gaps, brand mentions & cross-platform reviews"},
    }


@router.get("/reputation-signals")
def reputation_signals(business_id: int = Depends(authorize_business)):
    """Stored off-audit reputation signals (DataForSEO): latest brand-mention volume + sentiment and
    the latest review ratings per platform. Powers the console reputation panel; empty until the
    dataforseo_intel / dataforseo_reviews ingest jobs have run. Never raises."""
    try:
        from ... import dataforseo as _dfs
    except ImportError:  # pragma: no cover
        import dataforseo as _dfs  # type: ignore
    return {"mentions": _dfs.latest_mentions(business_id), "reviews": _dfs.latest_reviews(business_id)}


class PageSpeedRun(BaseModel):
    urls: Optional[list[str]] = None
    strategy: Optional[str] = None


@router.post("/pagespeed/run")
def pagespeed_run(body: PageSpeedRun, business_id: int = Depends(require_business_editor)):
    """Grade owned (+ competitor) URLs now — enqueues the ingest_pagespeed job (each URL ~30-60s, so
    it runs in the background). Needs PAGESPEED_ENABLED + a PAGESPEED_API_KEY for live scores."""
    try:
        from .. import jobs as _jobs
    except ImportError:  # pragma: no cover
        import api.jobs as _jobs  # type: ignore
    args = {k: v for k, v in {"urls": body.urls, "strategy": body.strategy}.items() if v}
    job = _jobs.enqueue(business_id, "ingest_pagespeed", args=args or None)
    return {"enqueued": True, "job": job}


@router.get("/advisor")
def advisor(llm: bool = True, business_id: int = Depends(authorize_business)):
    """The PDCA strategy advisor: the goal + per-gap progress (DO/CHECK) + impact predictions +
    the specific recommended next content (ACT), synthesized from the gap model, content batches,
    measured impact, and the GA/GSC/PageSpeed/keyword-demand signals. Pass llm=false to skip the
    LLM briefing (deterministic fallback) for a faster response."""
    try:
        from ... import strategy_advisor as _sa
    except ImportError:  # pragma: no cover
        import strategy_advisor as _sa  # type: ignore
    return _sa.advise(business_id, with_narrative=llm)


@router.get("/our-content-impact")
def our_content_impact(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Causal proof loop (Wave 1 item 3): for content WE published, did it start earning search
    clicks (GSC) + sessions (GA), and is our domain now cited by AI? Joins assets -> latest-window
    gsc_page_stats + ga_top_pages by asset_id, plus the owned citation share. Graceful when the
    analytics tables are empty (collecting)."""
    assets = conn.execute(
        "SELECT id, title, published_url, published_at FROM assets "
        "WHERE business_id=%s AND published_url IS NOT NULL AND published_status='live' "
        "ORDER BY published_at DESC NULLS LAST, id DESC LIMIT 50", (business_id,)).fetchall()

    def _latest_map(table, metric):
        try:
            win = conn.execute(f"SELECT MAX(period_end) m FROM {table} WHERE business_id=%s",
                               (business_id,)).fetchone()["m"]
            if not win:
                return {}
            rows = conn.execute(
                f"SELECT asset_id, {metric} v FROM {table} WHERE business_id=%s AND period_end=%s "
                "AND asset_id IS NOT NULL", (business_id, win)).fetchall()
            return {r["asset_id"]: r["v"] for r in rows}
        except Exception:  # noqa: BLE001 -- table absent
            return {}

    gsc_clicks = _latest_map("gsc_page_stats", "clicks")
    gsc_impr = _latest_map("gsc_page_stats", "impressions")
    ga_sessions = _latest_map("ga_top_pages", "sessions")
    # owned citation share from the latest citation_momentum run
    owned_share = 0.0
    try:
        run = conn.execute("SELECT MAX(run_id) r FROM citation_momentum WHERE business_id=%s",
                           (business_id,)).fetchone()["r"]
        if run:
            s = conn.execute("SELECT COALESCE(SUM(share),0) s FROM citation_momentum WHERE "
                             "business_id=%s AND run_id=%s AND classification='owned'",
                             (business_id, run)).fetchone()["s"]
            owned_share = min(1.0, max(0.0, float(s or 0)))
    except Exception:  # noqa: BLE001
        pass

    out_assets = []
    for a in assets:
        clk = int(gsc_clicks.get(a["id"]) or 0)
        imp = int(gsc_impr.get(a["id"]) or 0)
        ctr = round(clk / imp, 4) if imp else None
        ses = int(ga_sessions.get(a["id"]) or 0)
        out_assets.append({"asset_id": a["id"], "title": a["title"], "published_url": a["published_url"],
                           "published_at": a["published_at"].isoformat() if a["published_at"] else None,
                           "gsc_clicks": clk, "gsc_impressions": imp, "gsc_ctr": ctr,
                           "ga_sessions": ses, "has_traffic": (clk + ses) > 0})
    with_traffic = sum(1 for a in out_assets if a["has_traffic"])
    return {"assets": out_assets, "owned_citation_share": owned_share,
            "totals": {"assets_published": len(out_assets), "assets_with_traffic": with_traffic,
                       "our_content_clicks": sum(a["gsc_clicks"] for a in out_assets),
                       "our_content_sessions": sum(a["ga_sessions"] for a in out_assets)}}


@router.get("/freshness-queue")
def freshness_queue(months: int = 12, business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Published pieces old enough to be worth refreshing (Phase-5 freshness lever): live assets whose
    publish date is older than `months` (default 12), oldest first. Read-only recommendations — a
    visible 'Last updated' refresh keeps AI/Google freshness signals warm. Never auto-edits anything."""
    months = max(1, min(60, int(months or 12)))
    rows = conn.execute(
        "SELECT id, title, published_url, published_at, "
        "  EXTRACT(DAY FROM (now() - published_at))::int AS age_days "
        "FROM assets WHERE business_id=%s AND published_status='live' AND published_at IS NOT NULL "
        "  AND published_at < now() - make_interval(months => %s) "
        "ORDER BY published_at ASC LIMIT 50",
        (business_id, months)).fetchall()
    items = [{"asset_id": r["id"], "title": r["title"], "published_url": r["published_url"],
              "published_at": r["published_at"].isoformat() if r["published_at"] else None,
              "age_days": int(r["age_days"] or 0), "age_months": round((r["age_days"] or 0) / 30.4)}
             for r in rows]
    return {"threshold_months": months, "count": len(items), "items": items}


@router.get("/keyword-intent")
def keyword_intent(business_id: int = Depends(authorize_business)):
    """Keywords mapped by search intent + which intents lack owned content (Wave 5, item 19)."""
    try:
        from ... import topical_authority as _ta
    except ImportError:  # pragma: no cover
        import topical_authority as _ta  # type: ignore
    return _ta.by_intent(business_id)


def _pr():
    try:
        from ... import public_report as p
    except ImportError:  # pragma: no cover
        import public_report as p  # type: ignore
    return p


@router.get("/public-summary")
def public_summary(business_id: int = Depends(authorize_business)):
    """Sanitized lead-magnet teaser (score + band + top gaps) (Wave 5, item 20)."""
    return _pr().public_summary(business_id)


@router.get("/branding")
def get_branding(business_id: int = Depends(authorize_business)):
    """The resolved white-label branding for this business (GTM item 21)."""
    return _pr().branding(business_id)


class BrandingUpdate(BaseModel):
    brand_name: Optional[str] = None
    logo_url: Optional[str] = None
    accent: Optional[str] = None


@router.patch("/branding")
def set_branding(body: BrandingUpdate, business_id: int = Depends(require_business_editor)):
    """Set the white-label branding (agency mode). Applies to the report + the public page."""
    return _pr().set_branding(business_id, brand_name=body.brand_name, logo_url=body.logo_url,
                              accent=body.accent)


@router.post("/share-link")
def share_link(business_id: int = Depends(require_business_editor)):
    """Get-or-create the public lead-magnet share link for this business (GTM item 20)."""
    return _pr().ensure_share_token(business_id)


@router.get("/leads")
def leads(business_id: int = Depends(authorize_business)):
    """Emails captured by the public lead-magnet page (GTM item 20)."""
    return {"leads": _pr().list_leads(business_id)}


@router.get("/topical-authority")
def topical_authority(business_id: int = Depends(authorize_business)):
    """Topic clusters (pillar/spokes) + coverage + what to write next (Wave 2)."""
    try:
        from ... import topical_authority as _ta
    except ImportError:  # pragma: no cover
        import topical_authority as _ta  # type: ignore
    out = _ta.clusters(business_id)
    out["next_to_write"] = _ta.next_to_write(business_id)
    return out


@router.get("/internal-links")
def internal_links(business_id: int = Depends(authorize_business)):
    """Under-linked pages + internal-link suggestions (Wave 2)."""
    try:
        from ... import internal_links as _il
    except ImportError:  # pragma: no cover
        import internal_links as _il  # type: ignore
    return _il.analyze(business_id)


@router.get("/directory-citations")
def directory_citations(business_id: int = Depends(authorize_business)):
    """Curated white-hat directory list pre-filled with the canonical NAP (Wave 3)."""
    try:
        from ... import directory_citations as _dc
    except ImportError:  # pragma: no cover
        import directory_citations as _dc  # type: ignore
    return _dc.recommend(business_id)


@router.get("/indexing-status")
def indexing_status(business_id: int = Depends(authorize_business)):
    """Which owned URLs Google has indexed + which need a manual 'Request indexing' (Wave 3)."""
    try:
        from ... import indexing as _ix
    except ImportError:  # pragma: no cover
        import indexing as _ix  # type: ignore
    return _ix.check_index_status(business_id)


def _gi():
    try:
        from ... import gsc_inspect as g
    except ImportError:  # pragma: no cover
        import gsc_inspect as g  # type: ignore
    return g


@router.get("/index-health")
def index_health(business_id: int = Depends(authorize_business)):
    """GSC full-surface URL Inspection: per-owned-page index status + canonical loss (Google prefers a
    different URL) + structured-data/schema validity + crawl/fetch reason codes, plus a rollup and the
    structured technical gaps that feed the gap model + advisor. Dormant-safe: {has_data:false} until
    the index_own_content job has inspected pages (needs a live GSC connection)."""
    g = _gi()
    out = g.latest(business_id)
    out["technical_gaps"] = g.technical_gaps(business_id)
    return out


@router.get("/sitemaps")
def gsc_sitemaps(business_id: int = Depends(authorize_business)):
    """Submitted sitemaps + per-sitemap submitted/indexed/warning/error counts (GSC Sitemaps resource)."""
    return _gi().sitemaps(business_id)


@router.post("/sitemaps/submit")
def gsc_submit_sitemap(business_id: int = Depends(require_business_editor)):
    """Submit our owned-content feed to Google for faster discovery (complements IndexNow, which
    Google ignores). Needs a live GSC connection + PUBLIC_APP_ORIGIN."""
    return _gi().submit_content_feed(business_id)


@router.get("/answer-changes")
def answer_changes(business_id: int = Depends(authorize_business)):
    """Material changes in what AI says about you, run-over-run (Wave 4, item 17)."""
    try:
        from ... import answer_changes as _ac
    except ImportError:  # pragma: no cover
        import answer_changes as _ac  # type: ignore
    return _ac.detect(business_id)


@router.get("/review-sla")
def review_sla(business_id: int = Depends(authorize_business)):
    """Negative reviews awaiting a reply + SLA breach status (Wave 4, item 16)."""
    try:
        from ... import gbp_reviews as _gbp
    except ImportError:  # pragma: no cover
        import gbp_reviews as _gbp  # type: ignore
    return _gbp.negative_pending(business_id)


class ReviewRequestSend(BaseModel):
    recipients: list[dict]


@router.post("/review-requests/send")
def review_requests_send(body: ReviewRequestSend,
                         business_id: int = Depends(require_business_editor)):
    """Send review-request emails to the given recipients (Wave 4, item 15). Keyless-safe."""
    try:
        from ... import review_requests as _rr
    except ImportError:  # pragma: no cover
        import review_requests as _rr  # type: ignore
    return _rr.send(business_id, body.recipients)


@router.get("/content-feed.xml")
def content_feed(business_id: int = Depends(authorize_business)):
    """RSS feed of owned published URLs (Wave 3 indexing — preview/host this for search discovery)."""
    try:
        from ... import indexing as _ix
    except ImportError:  # pragma: no cover
        import indexing as _ix  # type: ignore
    from fastapi.responses import Response
    return Response(content=_ix.rss(business_id), media_type="application/rss+xml")


@router.get("/backlink-profile")
def backlink_profile(business_id: int = Depends(authorize_business)):
    """Backlink-profile summary + lost-link detection from the latest ingested report (Wave 3)."""
    try:
        from ... import external_signals as _es
    except ImportError:  # pragma: no cover
        import external_signals as _es  # type: ignore
    return _es.latest_backlinks(business_id)


@router.get("/review-request")
def review_request(business_id: int = Depends(authorize_business)):
    """Review-capture kit: a ready 'write a review' link, SMS/email templates, and the canonical
    NAP block for citation consistency (LATER: review-request loop + GBP NAP)."""
    try:
        from ... import review_requests as _rr
    except ImportError:  # pragma: no cover
        import review_requests as _rr  # type: ignore
    return {"link": _rr.review_link(business_id), "templates": _rr.templates(business_id),
            "nap": _rr.nap(business_id)}


class CompetitorCreate(BaseModel):
    name: str
    domain: Optional[str] = ""


@router.get("/site-audit")
def site_audit(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT summary, created_at FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/gap-model")
def gap_model(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT model, created_at FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/strategy")
def strategy(business_id: int = Depends(authorize_business)):
    """The detailed, per-section strategy the console's Strategy page renders: three areas
    (AI Visibility / SEO / Search), each with the gaps it closes, the approach to close each, the
    tasks doing it, and the concrete content specs to produce. Assembled from the existing gap
    model + work orders + piece briefs (no new LLM work)."""
    try:
        from ... import strategy_generator as _sg
    except ImportError:  # pragma: no cover
        import strategy_generator as _sg  # type: ignore
    return _sg.strategy_view(business_id)


@router.get("/report-view")
def report_view(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """A viewable, in-console report bundle (score, biggest gaps, Local Reputation, this-month
    work) — so the client can read the report in the browser, not just download a docx."""
    b = conn.execute("SELECT name, goal FROM businesses WHERE id=%s", (business_id,)).fetchone()
    rm = conn.execute("SELECT goal_alignment FROM run_metrics WHERE business_id=%s "
                      "ORDER BY run_id DESC LIMIT 1", (business_id,)).fetchone()
    score = round((float(rm["goal_alignment"]) + 1) / 2 * 100) if rm and rm["goal_alignment"] is not None else None
    gm = conn.execute("SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                      (business_id,)).fetchone()
    gaps = []
    if gm and isinstance(gm["model"], dict):
        gaps = [w.get("prompt") for w in (gm["model"].get("weak_queries") or [])[:5]
                if isinstance(w, dict) and w.get("prompt")]
    tasks_done = conn.execute(
        "SELECT COUNT(*) c FROM work_orders WHERE business_id=%s AND status IN ('done','verified') "
        "AND COALESCE(completed_at, updated_at) >= date_trunc('month', now())", (business_id,)).fetchone()["c"]
    try:
        from ... import gbp_reviews as _gr
    except ImportError:  # pragma: no cover
        import gbp_reviews as _gr  # type: ignore
    return {
        "business": b["name"] if b else None,
        "goal": b["goal"] if b else None,
        "score": score,
        "biggest_gaps": gaps,
        "tasks_done_this_month": tasks_done,
        "local_reputation": _gr.latest(business_id),   # the Local Reputation section
    }


@router.get("/site-health-trend")
def site_health_trend(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Per-audit AI-crawler readiness (0-100) over time — makes site health a TRACKABLE trend
    like the AI reputation score. Source: site_audits.summary.avg_semantic_readiness."""
    rows = conn.execute(
        "SELECT summary, created_at FROM site_audits WHERE business_id=%s ORDER BY id ASC",
        (business_id,),
    ).fetchall()
    out = []
    for r in rows:
        s = r["summary"] if isinstance(r["summary"], dict) else {}
        v = s.get("avg_semantic_readiness")
        if v is None:
            continue
        d = r["created_at"]
        out.append({"date": d.date().isoformat() if d else None, "score": round(float(v))})
    return out


@router.get("/local-rank-trend")
def local_rank_trend(business_id: int = Depends(authorize_business)):
    """Per-run local page-one rate (0-100) over time — a trackable local-visibility trend."""
    try:
        from ... import local_seo as _ls
    except ImportError:  # pragma: no cover
        import local_seo as _ls  # type: ignore
    return _ls.trend(business_id)


@router.get("/answer-lenses")
def answer_lenses(business_id: int = Depends(authorize_business)):
    """Cross-engine divergence (where engines disagree) + persona/location lens (how different
    audiences see you) — derived from the latest audit's answers."""
    try:
        from ... import lenses as _l
    except ImportError:  # pragma: no cover
        import lenses as _l  # type: ignore
    return _l.summary(business_id)


@router.get("/metrics-trend")
def metrics_trend(business_id: int = Depends(authorize_business)):
    """Per-run series of overall + per-engine reputation scores (0-100) over time, so the client
    sees each AI engine's trajectory, not just today's snapshot."""
    try:
        from ... import run_metrics as _rm
    except ImportError:  # pragma: no cover
        import run_metrics as _rm  # type: ignore
    return _rm.trend(business_id)


@router.get("/reviews")
def reviews(business_id: int = Depends(authorize_business)):
    """Current Google rating snapshot + delta + recent reviews (from the ingest_gbp_reviews job)."""
    try:
        from ... import gbp_reviews as _gr
    except ImportError:  # pragma: no cover
        import gbp_reviews as _gr  # type: ignore
    return _gr.latest(business_id)


@router.get("/activity-summary")
def activity_summary(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Client-facing 'this month's work' counts (audits, content, tasks, monitoring, outreach)
    for the current calendar month — the retention narrative that shows the needle moving.
    Per-metric counts are resilient: a missing table/column degrades that count to 0."""
    month = "date_trunc('month', now())"

    def c(sql: str) -> int:
        try:
            return conn.execute(sql, (business_id,)).fetchone()["c"]
        except Exception:  # noqa: BLE001 -- one bad count must not sink the panel
            conn.rollback()
            return 0

    return {
        "audits": c(f"SELECT COUNT(*) c FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND started_at >= {month}"),
        "drafts": c(f"SELECT COUNT(*) c FROM content_drafts WHERE business_id=%s AND created_at >= {month}"),
        "published": c(f"SELECT COUNT(*) c FROM assets WHERE business_id=%s AND COALESCE(published_at, created_at) >= {month}"),
        "tasks_done": c(f"SELECT COUNT(*) c FROM work_orders WHERE business_id=%s AND status IN ('done','verified') AND COALESCE(completed_at, updated_at) >= {month}"),
        "mentions": c(f"SELECT COUNT(*) c FROM mentions WHERE business_id=%s AND created_at >= {month}"),
        "outreach": c(f"SELECT COUNT(*) c FROM discovery_targets WHERE business_id=%s AND created_at >= {month}"),
    }


@router.get("/seo-keywords")
def seo_keywords(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """The SEO keyword-intelligence set (target_keywords) to rank for, highest priority first.
    Produced by the keyword_research job (LLM seed + Serper grounding). Distinct from
    /keywords, which is the brand-monitoring keyword list."""
    rows = conn.execute(
        "SELECT keyword, kind, source, intent, priority, rationale, "
        "search_volume, keyword_difficulty, cpc FROM target_keywords "
        "WHERE business_id=%s ORDER BY search_volume DESC NULLS LAST, priority DESC NULLS LAST, keyword",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/social-presence")
def social_presence(business_id: int = Depends(authorize_business)):
    """Latest best-effort verification of which social profiles the business actually has,
    so the social recommendations can show confirmed 'create' vs 'improve'."""
    from ... import social_presence as _sp
    return _sp.latest(business_id)


# ---- competitor benchmarking (share-of-voice vs rivals) ----
@router.get("/competitors")
def competitors(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, name, domain, created_at FROM competitors WHERE business_id=%s ORDER BY id",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/competitors/compare")
def competitors_compare(business_id: int = Depends(authorize_business)):
    """Latest benchmark: how often AI surfaces YOU vs each competitor for category questions."""
    from ... import competitor as _c
    return _c.compare(business_id, quiet=True)


@router.get("/visibility-trend")
def visibility_trend(business_id: int = Depends(authorize_business)):
    """Subject vs competitor appearance rate over time (one point per benchmark run) --
    backs the visibility-over-time chart with competitor lines."""
    from ... import competitor as _c
    return _c.trend(business_id)


@router.get("/onboarding")
def onboarding(business_id: int = Depends(authorize_business)):
    """Getting-started checklist state for this business (derived from existing data)."""
    from ... import onboarding as _o
    return _o.status(business_id)


@router.get("/prompt-results")
def prompt_results(business_id: int = Depends(authorize_business)):
    """Per-prompt visibility/sentiment/goal-alignment for the latest completed audit run --
    how each tracked question performs, with a per-engine split. Null prompts list when no
    completed run exists yet."""
    from ...ai_state_audit import per_prompt_metrics
    return per_prompt_metrics(business_id)


@router.get("/local-rankings")
def local_rankings(business_id: int = Depends(authorize_business)):
    """Latest local Google rank snapshot (organic + map pack) for the category-local
    queries -- our rank vs competitors, plus page-1 / local-pack roll-ups. Null when no
    run has been captured yet (needs SERPER_API_KEY)."""
    from ... import local_seo as _ls
    return _ls.latest(business_id)


@router.post("/competitors", status_code=201)
def add_competitor(payload: CompetitorCreate, business_id: int = Depends(require_business_editor)):
    from ... import competitor as _c
    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name required")
    cid = _c.register_competitor(business_id, name, (payload.domain or "").strip())
    return {"id": cid, "name": name}


@router.delete("/competitors/{competitor_id}")
def delete_competitor(competitor_id: int, business_id: int = Depends(require_business_editor),
                      conn=Depends(get_conn)):
    r = conn.execute("DELETE FROM competitors WHERE id=%s AND business_id=%s RETURNING id",
                     (competitor_id, business_id)).fetchone()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competitor not found")
    conn.commit()
    return {"deleted": competitor_id}
