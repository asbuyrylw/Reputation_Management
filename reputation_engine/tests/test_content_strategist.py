"""Content Strategist (Phase 1) -- regression lock.

Proves the new planning brain: the LLM plan is post-processed into ranked cluster CAMPAIGNS (pillar +
clamped clusters + comparison + cadence weeks, severity-ranked by SoV-gap x business value), those
campaigns REPLACE the old 1-WO-per-gap content loops in build_work_orders while preserving the
technical reroute + rich-media + no-strategist fallback, and the strategist inherits the SAME
business-agnostic compliance guardrails as the gap model (finance-worded for finance, finance-free for
generic). All PURE -- no LLM, no DB.
"""
from __future__ import annotations

import pytest

from rep_engine import content_strategist as cs
from rep_engine import strategy_generator as sg
from rep_engine import business_profile as bp

GEN = {"industry": "restaurant", "geo": "Denver, CO", "name": "Joe's Diner", "services": "restaurant"}
FIN = {"industry": "financial_services", "firm_type": "insurance", "geo": "Cincinnati, OH",
       "contested_terms": "MLM,pyramid scheme", "name": "Team Unstoppable", "services": "life insurance"}

# A realistic LLM plan (what orchestrator_json would return) + the gap it was built from.
_GAP = {
    "summary": "AI barely recognizes the business and a competitor wins local queries.",
    "weak_queries": [
        {"prompt": "what is term life insurance", "addressed_by": "term life insurance guide"},
        {"prompt": "best life insurance agent in cincinnati", "addressed_by": ""},
    ],
    "missing_owned_content": [
        {"topic": "page speed optimization", "asset_type": "article"},    # TECHNICAL -> must reroute
        {"topic": "term life insurance guide", "asset_type": "article"},  # COVERED by campaign -> absorbed
        {"topic": "About us", "asset_type": "article"},                   # UNCOVERED -> retained (safety net)
    ],
    "competitor_defense": [{"query": "best life insurance agents in cincinnati", "competitor": "BigCo"}],
}
_MODEL = {
    "summary": "Two campaigns: an informational pillar and a commercial comparison.",
    "campaigns": [
        {"topic": "Term life insurance basics", "intent": "informational", "funnel_stage": "awareness",
         "why": "AI can't explain the business's core service.", "gap_source": "missing owned content",
         "target_queries": ["what is term life insurance"], "priority": 3,
         "pillar": {"title": "The complete guide to term life insurance", "content_type": "article",
                    "why": "Definitive owned overview."},
         # 14 clusters -> must clamp to <= 12
         "clusters": [{"title": f"Term life FAQ {i}", "content_type": "faq", "intent": "informational",
                       "target_query": f"term life question {i}", "why": "answers a sub-question"}
                      for i in range(14)],
         "comparison_page": None,
         "atomization": {"social_posts": 6, "video_script": True, "infographic": True, "email": True}},
        {"topic": "Best life insurance in Cincinnati", "intent": "commercial", "funnel_stage": "decision",
         "why": "A competitor wins the local commercial query.", "gap_source": "competitor analysis",
         "target_queries": ["best life insurance agent in cincinnati"], "priority": 1,
         "pillar": {"title": "Best life insurance agents in Cincinnati", "content_type": "article",
                    "why": "Own the local commercial query."},
         "clusters": [{"title": "How to choose a Cincinnati insurer", "content_type": "blog",
                       "intent": "commercial", "target_query": "choose insurer cincinnati", "why": "w"}],
         "comparison_page": {"title": "Cincinnati life insurance: compare the top options"},
         "atomization": {"social_posts": 8, "video_script": False, "infographic": True, "email": True}},
    ],
}


# --- post-processing: campaigns, clamp, ranking, cadence -------------------------------------------
def test_postprocess_shape_and_clamp():
    s = cs._postprocess(_MODEL, _GAP)
    assert s["counts"]["campaigns"] == 2
    for c in s["campaigns"]:
        assert c["id"].startswith("C")
        pieces = c["pieces"]
        assert pieces and pieces[0]["role"] == "pillar"
        clusters = [p for p in pieces if p["role"] == "cluster"]
        assert len(clusters) <= cs._MAX_CLUSTERS               # 14 clamped to 12
        # pillar publishes on/before its clusters (burst-then-drip within a campaign)
        assert all(pieces[0]["week"] <= cl["week"] for cl in clusters)


def test_postprocess_ranks_commercial_first():
    """SoV-gap x business value: the commercial campaign (converts + higher LLM priority) outranks the
    informational one, so it becomes C01 and its pillar rolls out earliest."""
    s = cs._postprocess(_MODEL, _GAP)
    assert s["campaigns"][0]["intent"] == "commercial"
    assert s["campaigns"][0]["priority_rank"] == 0
    # earlier rank -> earlier pillar week (the initial-dump front-load)
    assert s["campaigns"][0]["pieces"][0]["week"] <= s["campaigns"][1]["pieces"][0]["week"]


def test_cadence_burst_then_drip():
    """Pieces spread across a real calendar: the initial dump front-loads weeks 1..BURST_WEEKS, then
    a drip tail extends past it (posts out gradually, not all clumped)."""
    s = cs._postprocess(_MODEL, _GAP)
    weeks = [pc["week"] for c in s["campaigns"] for pc in c["pieces"]]
    assert min(weeks) == 1                              # the initial dump starts week 1
    assert max(weeks) > cs._BURST_WEEKS + 1            # a genuine drip tail beyond the burst window
    assert len([w for w in weeks if w <= cs._BURST_WEEKS]) >= 4   # front-loaded burst
    assert len(set(weeks)) >= 4                         # gradual rollout, not one big clump
    assert s["cadence"]["last_week"] == max(weeks)


def test_video_plan_per_campaign():
    """Every campaign gets VIDEO options (pillar + top clusters) as opt-in explainer_video plans, so
    video is a big per-campaign part of the mix (not 1 for the whole strategy)."""
    s = cs._postprocess(_MODEL, _GAP)
    assert s["counts"]["videos"] >= 2
    for c in s["campaigns"]:
        vids = [p for p in c["pieces"] if p["role"] == "video"]
        assert vids, f"campaign {c['id']} has no video plan"
        assert all(p["capability"] == "explainer_video" and p.get("on_click") for p in vids)
        # Video count is RESEARCH-sized (content_research.video_count_for): 1 flagship pillar video + the
        # high-video-intent share (~40-60%) of clusters, scaled by severity -- so it can exceed the old
        # flat cap, but never more than a video per pillar+cluster.
        n_cl = len([p for p in c["pieces"] if p["role"] == "cluster"])
        assert 1 <= len(vids) <= 1 + max(1, round(0.6 * n_cl))
        # a video sits beside its source article (inherits its cadence week, within the plan range)
        assert all(isinstance(p["week"], int) for p in vids)


def test_postprocess_comparison_piece_for_commercial():
    s = cs._postprocess(_MODEL, _GAP)
    commercial = next(c for c in s["campaigns"] if c["intent"] == "commercial")
    assert any(p["role"] == "comparison" for p in commercial["pieces"])
    informational = next(c for c in s["campaigns"] if c["intent"] == "informational")
    assert not any(p["role"] == "comparison" for p in informational["pieces"])


def test_postprocess_empty_on_no_campaigns():
    assert cs._postprocess({"campaigns": []}, _GAP) == {}
    assert cs._postprocess({}, _GAP) == {}


# --- build_work_orders integration: campaigns REPLACE flat loops, keep everything else -------------
def test_build_work_orders_with_strategy():
    strategy = cs._postprocess(_MODEL, _GAP)
    biz = {"id": 1, "geo": "Cincinnati, OH", "industry": "financial_services"}
    wos = sg.build_work_orders(_GAP, biz, strategy=strategy)
    titles = [w.title for w in wos]

    # campaign pieces present, tagged with a campaign_id in gap_specifics
    assert any((w.gap_specifics or {}).get("campaign_id") for w in wos)
    assert "The complete guide to term life insurance" in titles          # pillar
    assert any(t.startswith("Best life insurance agents in Cincinnati") for t in titles)

    # a COVERED owned-content topic is absorbed by its campaign; an UNCOVERED foundational topic is
    # RETAINED (never dropped) -- the safety net. The competitor query is covered -> absorbed.
    assert not any(t.startswith("Create owned asset: term life insurance guide") for t in titles)
    assert any(t.startswith("Create owned asset: About us") for t in titles)
    assert not any(t.startswith("Compete for") for t in titles)

    # but the TECHNICAL reroute still fires (page-speed -> website-fixes board), and the
    # always-on rich-media + baseline channels remain
    assert any(w.capability == "technical_seo" and "page speed" in w.title.lower() for w in wos)
    assert any(w.capability == "podcast_creation" for w in wos)
    assert any(w.capability == "ai_visibility_tracking" for w in wos)
    # campaign content pieces are 'content' area -> render in the Content section
    camp_pieces = [w for w in wos if (w.gap_specifics or {}).get("campaign_id")]
    assert camp_pieces and all(w.area == "content" for w in camp_pieces)

    # per-campaign video plans materialize as OPT-IN (manual) explainer_video WOs (generate on click)
    vids = [w for w in wos if w.capability == "explainer_video"
            and (w.gap_specifics or {}).get("campaign_id")]
    assert vids and all(w.execution == "manual" for w in vids)


def test_build_work_orders_fallback_without_strategy():
    """No strategist -> the deterministic template runs. moc/competitor gaps now emit the SAME multi-type
    content spread the batch path fans them into (sharing the canonical gap_key), so plan and batch never
    diverge on the content-type set; the technical reroute still applies."""
    wos = sg.build_work_orders(_GAP, {"id": 1}, strategy=None)
    titles = [w.title for w in wos]
    assert any(t.startswith("Create owned asset: About us") for t in titles)   # uncovered moc -> content
    # the competitor gap produces content bound to its canonical comp: gap_key (was a single "Compete for"
    # WO; now the typed spread, matching the batch path)
    assert any((w.gap_specifics or {}).get("gap_key", "").startswith("comp:") for w in wos)
    assert any(w.capability == "technical_seo" for w in wos)
    assert not any((w.gap_specifics or {}).get("campaign_id") for w in wos)


# --- business-agnostic compliance guardrails (mirrors the gap-model gating) ------------------------
def test_system_prompt_finance_gated():
    gen = cs._system_prompt(bp.derive(GEN)).lower()
    fin = cs._system_prompt(bp.derive(FIN)).lower()
    for leak in ("finra", "broker-dealer", "licensed insurance professionals", "npn"):
        assert leak not in gen, f"generic strategist prompt leaked {leak!r}"
    assert "regulated-finance" in fin                     # finance note spliced in
    assert "finra crd" in fin                             # finance license policy composed in
    # positive-only self-distinction guardrail present for BOTH (inherited from the gap model)
    assert "self-distinction policy" in gen and "self-distinction policy" in fin


def test_plan_disabled_and_empty_gap(monkeypatch):
    monkeypatch.setenv("CONTENT_STRATEGIST_ENABLED", "0")
    assert cs.plan(1, _GAP) == {}                          # disabled -> {} (fallback to template)
    monkeypatch.setenv("CONTENT_STRATEGIST_ENABLED", "1")
    assert cs.plan(1, {}) == {}                            # no gap summary -> {} (no LLM call)


# --- DB-backed end-to-end: plan_cmd -> sync_plan -> strategy_view (mocked LLM, real DB) ------------
from conftest import requires_db  # noqa: E402


@requires_db
def test_plan_to_view_end_to_end(fresh_schema, monkeypatch):
    """Runs the ACTUAL job path (plan_cmd -> sync_plan -> strategy_view) against a real Postgres with
    the strategist LLM mocked -- catches runtime/wiring bugs pure tests miss (the verify-jobs lesson):
    the ContentStrategy persists, its campaigns MATERIALIZE into work_orders as content pieces, and the
    strategy view renders them as ONE campaign group (pillar + clusters), aligned with the plan."""
    import json
    conn = fresh_schema
    from rep_engine import strategy_generator as sgen
    from rep_engine import tracking, content_strategist as strat

    # deterministic: no network, no cost/budget coupling
    monkeypatch.setenv("CONTENT_STRATEGIST_ENABLED", "1")
    monkeypatch.setattr(strat.cost, "over_budget", lambda bid: False)
    monkeypatch.setattr(strat.cost, "record", lambda *a, **k: None)
    monkeypatch.setattr(strat._audit, "orchestrator_json", lambda system, user, *a, **k: _MODEL)

    bid = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, geo, industry) "
        "VALUES ('Acme Life','acme.com','life insurance','win queries','Cincinnati, OH','financial_services') "
        "RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO gap_models (business_id, model) VALUES (%s,%s)", (bid, json.dumps(_GAP)))
    conn.commit()

    # 1) plan: strategist runs (mocked) -> plan + ContentStrategy persisted
    sgen.plan_cmd(bid, None)
    saved = strat.latest(bid)
    assert saved.get("campaigns"), "ContentStrategy was not persisted"

    # 2) materialize into trackable work_orders
    tracking.sync_plan(bid)
    camp_rows = conn.execute(
        "SELECT title, capability, area, gap_specifics FROM work_orders WHERE business_id=%s "
        "AND gap_specifics ? 'campaign_id'", (bid,)).fetchall()
    assert len(camp_rows) >= 6, f"expected a multi-piece campaign program, got {len(camp_rows)}"
    assert all(r["area"] == "content" for r in camp_rows)          # campaign pieces are content
    assert any(r["gap_specifics"].get("role") == "pillar" for r in camp_rows)

    # 3) strategy view groups a campaign's pieces into ONE tree (pillar + clusters)
    view = sgen.strategy_view(bid)
    camp_groups = [g for s in view["sections"] for g in s["groups"] if g.get("campaign")]
    assert camp_groups, "strategy view shows no campaign groups"
    biggest = max(camp_groups, key=lambda g: len(g["tasks"]))
    roles = [t.get("role") for t in biggest["tasks"]]
    assert roles[0] == "pillar" and "cluster" in roles             # pillar-first tree
    assert biggest["specs"], "campaign pieces should carry content specs (aligned with content page)"
