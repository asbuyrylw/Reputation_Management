"""
Content-PROGRAM sizing regression tests (no DB required)
========================================================
Locks in the fixes from the content-pipeline code review: content programs must be sized to the
RESEARCH target (pillar + ~8-12 supporting pieces) so they can actually rank + crowd out the negative
narrative -- never throttled to a "check the box" handful. Also guards the research KB's goal-scoping
(a fixed no-op) and the measurement gap_key stamping. All pure / monkeypatched -> runs without a DB.
"""
from __future__ import annotations

import importlib


cr = importlib.import_module("rep_engine.content_research")
cs = importlib.import_module("rep_engine.content_strategist")
cb = importlib.import_module("rep_engine.content_batch")


# --- research KB: the programmatic sizing target + honest goal scoping ------------------------------
def test_cluster_count_for_returns_research_band():
    lo, hi, src = cr.cluster_count_for("topical_authority")
    assert (lo, hi) == (8, 12) and src
    lo2, hi2, _ = cr.cluster_count_for("topical_authority", strong=True)
    assert (lo2, hi2) == (12, 24)


def test_goal_scoping_is_not_a_noop():
    """A geo-scoped query must NOT leak seo-only claims (the old `g in _GOAL_TERMS` made it a no-op)."""
    geo = {r["applies_to"] for r in cr.research_for(goal="geo")}
    assert "goal:seo" not in geo
    assert "goal:geo" in geo


def test_broad_includes_intent_and_content_type_claims():
    """Plan-level (strategist) needs word-count-by-intent + which-type-moves-which-channel."""
    broad_kinds = {r["applies_to"].split(":")[0] for r in cr.research_for(broad=True, limit=99)}
    assert {"intent", "content_type"} <= broad_kinds
    narrow_kinds = {r["applies_to"].split(":")[0] for r in cr.research_for(limit=99)}
    assert "intent" not in narrow_kinds and "content_type" not in narrow_kinds


def test_editorial_tier_flagged_in_prompt_block():
    assert "lower-confidence" in cr.research_block(broad=True, limit=99)


# --- strategist cluster FLOOR: size a high-leverage hub up, respect a low one ------------------------
def test_high_severity_campaign_backfilled_to_floor():
    camp = {"_severity": 9, "topic": "life insurance for young families", "intent": "informational",
            "target_queries": ["term vs whole life", "how much life insurance do I need"],
            "clusters": [{"title": "What is term life"}, {"title": "Whole life explained"}]}
    out = cs._floor_clusters(camp, list(camp["clusters"]))
    assert len(out) >= cr.cluster_count_for("topical_authority")[0]  # >= 8
    titles = [c["title"] for c in out]
    assert "term vs whole life" in titles                            # grounded backfill first
    norms = [cs._norm_title(t) for t in titles]
    assert len(norms) == len(set(norms))                            # all distinct


def test_low_severity_campaign_not_padded():
    """'If the data says fewer, go with fewer' -- a narrow campaign keeps the LLM's small count."""
    camp = {"_severity": 3, "topic": "niche one-off", "intent": "commercial",
            "target_queries": ["x"], "clusters": [{"title": "A"}, {"title": "B"}]}
    out = cs._floor_clusters(camp, list(camp["clusters"]))
    assert len(out) == 2


# --- local PROGRAM: sized to the target, not to seed-keyword availability ---------------------------
def test_local_spokes_reaches_target_with_no_seed_keywords(monkeypatch):
    monkeypatch.setattr(cb, "_local_keywords", lambda business_id, query, limit=3: [])
    sp = cb._local_spokes(1, "financial advisor Blue Ash", 8)
    assert len(sp) == 8
    assert {s["kind"] for s in sp} == {"angle"}
    norms = [cb._norm(s["topic"]) for s in sp]
    assert len(norms) == len(set(norms))                            # distinct sub-topics, not dupes


def test_local_spokes_prefers_real_keywords_then_backfills(monkeypatch):
    monkeypatch.setattr(cb, "_local_keywords",
                        lambda business_id, query, limit=3: ["advisor fees", "fee only", "retirement"][:limit])
    sp = cb._local_spokes(1, "financial advisor Blue Ash", 8)
    assert len(sp) == 8
    assert [s["kind"] for s in sp][:3] == ["keyword"] * 3


def test_default_spoke_cap_is_research_max():
    assert cb._default_spoke_cap() == cr.cluster_count_for("topical_authority")[1]  # 12


# --- FE/BE capability drift guard (#30): the shared FE content.ts CONTENT_CAPS must equal the backend
#     strategy_generator.CONTENT_CAPABILITIES, so the 'what counts as content' set can never drift again.
def test_fe_content_caps_match_backend():
    import os
    import re as _re
    from rep_engine import strategy_generator as sg
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
    ts = os.path.join(here, "reputation-console", "src", "lib", "content.ts")
    if not os.path.exists(ts):
        import pytest as _pt
        _pt.skip("console content.ts not present in this checkout")
    src = open(ts, encoding="utf-8").read()
    m = _re.search(r"CONTENT_CAPS\s*=\s*new Set<string>\(\[(.*?)\]\)", src, _re.S)
    assert m, "could not find CONTENT_CAPS in content.ts"
    fe = set(_re.findall(r'"([a-z_]+)"', m.group(1)))
    assert fe == set(sg.CONTENT_CAPABILITIES), (
        f"FE content.ts CONTENT_CAPS drifted from backend CONTENT_CAPABILITIES: "
        f"FE-only={fe - set(sg.CONTENT_CAPABILITIES)}, BE-only={set(sg.CONTENT_CAPABILITIES) - fe}")
