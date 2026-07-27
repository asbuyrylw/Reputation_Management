"""
Scoring + safety regression tests (no DB required)
==================================================
Locks in the fixes from the full-engine audit (2026-07-27):
  * video_score is business-AGNOSTIC (credits the tenant's own service_terms + parses city/state; no
    hardcoded finance words or the pilot's Cincinnati/Ohio) -- the audit flagged ZERO tests here, which
    is how the finance hardcode shipped undetected.
  * podcast/report_audio use the SPOKEN GEO profile, not the markdown-article rubric.
  * the GEO quotation signal is case-insensitive on attributions but not over-broad.
  * the NAP email guard matches on a label boundary (no competitor look-alike leak).
  * strategy sizing scales with goal ambition, negatives, and competitiveness.
All pure -> runs without a DB.
"""
from __future__ import annotations

import importlib

cq = importlib.import_module("rep_engine.content_quality")
cr = importlib.import_module("rep_engine.content_research")
cs = importlib.import_module("rep_engine.content_strategist")
cb = importlib.import_module("rep_engine.content_batch")
cg = importlib.import_module("rep_engine.content_generator")


# --- video_score: business-agnostic (HIGH #4) ------------------------------------------------------
_PLUMBER = (
    "[0:00] Narrator: Got a burst pipe? Apex Plumbing in Dallas fixes burst pipes, water heaters, and "
    "clogged drains fast. [0:20] We are licensed and serve the Dallas area. Call us or visit to book. "
    "Captions included. According to the EPA, household leaks waste ~1 trillion gallons a year."
)


def _info_check(v, label_frag):
    for c in v.get("dimensions", {}).get("information", {}).get("checks", []):
        if label_frag in c["label"].lower():
            return c["ok"]
    return None


def test_video_score_credits_tenant_services_not_finance_words():
    v = cq.video_score(_PLUMBER, target_query="plumber Dallas", business_name="Apex Plumbing",
                       geo="Dallas, TX", asset_type="explainer_video",
                       service_terms=["burst", "pipes", "water", "heaters", "drains"])
    assert _info_check(v, "core services") is True   # was False (finance word list) before the fix


def test_video_score_credits_state_when_city_absent():
    # City ("dallas") never appears, but the STATE does -> the fix parses state from geo and credits it
    # (the old city-only split dropped the state entirely).
    body = "Narrator: We proudly serve all of Texas. Licensed and insured. Call today."
    v = cq.video_score(body, target_query="roofing", business_name="Lone Star Roofing",
                       geo="Dallas, Texas", asset_type="explainer_video", service_terms=["roofing"])
    assert _info_check(v, "location") is True


def test_video_score_no_cincinnati_ohio_hardcode():
    # A non-Cincinnati tenant whose script never says a location must NOT earn the location credit from a
    # baked-in 'cincinnati'/'ohio' literal.
    body = "Narrator: We fix cars. Great service. Call us."
    v = cq.video_score(body, target_query="auto repair", business_name="Speedy Auto",
                       geo="Miami, FL", asset_type="explainer_video", service_terms=["auto", "repair"])
    assert _info_check(v, "location") is False


# --- podcast GEO profile (HIGH #3) ------------------------------------------------------------------
def test_podcast_routes_to_spoken_profile_not_article():
    assert cq._geo_type_for("podcast") == "podcast"
    assert cq._geo_type_for("report_audio") == "podcast"
    assert "podcast" in cq._GEO_PROFILES
    # spoken profile must not weight the markdown-structure signals a transcript can't have
    prof = cq._GEO_PROFILES["podcast"]
    assert "citation_density" not in prof and "chunkability" not in prof and "schema" not in prof


def test_podcast_transcript_beats_article_rubric():
    transcript = (
        "Welcome. What makes a great local insurance team? According to LIMRA, 40 percent of families "
        "are underinsured. Our team, based in Cincinnati, is licensed and has served families for 20 "
        "years. Host: what should someone ask first? Ask about a needs analysis. Studies show 33 "
        "percent skip it. We keep it simple and plain so you understand your coverage."
    ) * 3
    spoken = cq.geo_score(transcript, target_query="local insurance team", content_type="podcast",
                          business_name="Team Unstoppable", geo="Cincinnati, OH").get("score")
    article = cq.geo_score(transcript, target_query="local insurance team", content_type="article",
                           business_name="Team Unstoppable", geo="Cincinnati, OH").get("score")
    assert spoken > article   # the article rubric under-scores audio; the spoken profile must not


# --- GEO quotation regex (MED #8) -------------------------------------------------------------------
def test_geo_quotation_regex_matches_sentence_initial_attribution():
    assert cq._ATTRIB.search("According to LIMRA, 40% of families are underinsured.")
    assert cq._ATTRIB.search("per the CDC, rates fell.")


def test_geo_quotation_regex_not_overbroad():
    # a blanket re.I would wrongly match this non-attribution
    assert not cq._ATTRIB.search("the report states that things happened")


# --- NAP email boundary guard (HIGH #1) -------------------------------------------------------------
def test_nap_email_domain_prefix_strip_and_boundary(monkeypatch):
    # A competitor look-alike email in the corpus must NOT be published as the client's own contact.
    monkeypatch.setattr(cg, "_verified_nap", cg._verified_nap)  # ensure real fn under test

    class _RR:
        @staticmethod
        def nap(_bid):
            return {"website": "https://www.wcapital.com"}

    class _SM:
        @staticmethod
        def corpus(_bid, max_tokens=6000):
            return "Contact a rival at info@bluecapital.com for details."

    import sys
    monkeypatch.setitem(sys.modules, "rep_engine.review_requests", _RR)
    monkeypatch.setitem(sys.modules, "rep_engine.source_material", _SM)
    out = cg._verified_nap(1, {"domain": "https://www.wcapital.com"})
    assert "bluecapital.com" not in out   # boundary-less endswith + lstrip mangle used to leak it


def test_nap_email_accepts_true_subdomain(monkeypatch):
    class _RR:
        @staticmethod
        def nap(_bid):
            return {"website": "wcapital.com"}

    class _SM:
        @staticmethod
        def corpus(_bid, max_tokens=6000):
            return "Reach us at hello@mail.wcapital.com anytime."

    import sys
    monkeypatch.setitem(sys.modules, "rep_engine.review_requests", _RR)
    monkeypatch.setitem(sys.modules, "rep_engine.source_material", _SM)
    out = cg._verified_nap(1, {"domain": "wcapital.com"})
    assert "hello@mail.wcapital.com" in out


# --- strategy sizing scales with ambition / negatives / competitiveness ----------------------------
def test_ambition_factor_tiers():
    assert cs._ambition_factor("aggressive growth and market domination") == 1.3
    assert cs._ambition_factor("maintain and protect our reputation") == 0.85
    assert cs._ambition_factor("") == 1.0


def test_review_velocity_scales_with_negatives_and_competition():
    base = cr.review_velocity_target(0, competitive=False)[:2]
    hot = cr.review_velocity_target(3, competitive=True)[:2]
    assert hot[0] > base[0] and hot[1] > base[1]


def test_displacement_high_authority_multiplier_fires():
    lo, hi, _ = cr.displacement_pages_for(2, high_authority=True)
    lo0, hi0, _ = cr.displacement_pages_for(2)
    assert lo > lo0 and hi > hi0


# --- pillar role: plan + batch agree (LOW pillar divergence) ----------------------------------------
def test_pillar_role_shared_rule():
    types = ["blog", "article", "white_paper", "faq"]
    roles = {t: cb.pillar_role(t, types) for t in types}
    assert roles["article"] == "pillar"        # first pillar-eligible type is the hub on BOTH paths
    assert roles["blog"] == "cluster"
    assert cb.pillar_role("local_page", ["local_page", "faq"]) == "pillar"
