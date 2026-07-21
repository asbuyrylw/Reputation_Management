"""6.1 business-agnostic seam -- regression lock.

Proves the whole engine is finance-free for a GENERIC tenant and reproduces the finance behavior for a
regulated-finance tenant, across every seam threaded in Slices A-F (license, compliance, gap prompts,
persona lenses, GEN exemplars, byline, atomize, authoritative sources, challenge thresholds,
target_alignment, negative lexicon, content-batch spreads).

The PURE tests (no DB) always run. The DB-backed test at the end runs generate_for_wo end-to-end for a
finance AND a generic business with a correctly-mocked LLM (catches a runtime NameError on the hot
path that import checks miss -- see the verify-jobs lesson), and asserts the per-tenant system prompt
is finance-worded for finance and finance-free for generic.
"""
from __future__ import annotations

import json

import pytest

from conftest import requires_db
from rep_engine import business_profile as bp

FIN = {"industry": "financial_services", "firm_type": "insurance", "geo": "Cincinnati, OH",
       "contested_terms": "MLM,pyramid scheme,scam", "name": "Team Unstoppable", "services": "life insurance"}
GEN = {"industry": "restaurant", "geo": "Denver, CO", "name": "Joe's Diner", "services": "restaurant"}
SAAS = {"industry": "b2b saas", "geo": "Seattle, WA", "name": "Acme Cloud", "services": "software"}

# Vocabulary that must NEVER appear in a generic tenant's prompts/behavior.
_FIN_LEAK = ["finra", "broker-dealer", "risk-free", "guaranteed return", "licensed insurance professionals",
             "limra", "sec/edgar", "income/compensation disclosure", "pyramid scheme"]


def _finprof():
    return bp.derive(FIN)


def _genprof():
    return bp.derive(GEN)


# --- compliance stack (Slice C) --------------------------------------------------------------------
def test_compliance_screener_generic_vs_finance():
    from rep_engine import content_generator as cg
    assert cg._compliance_system(None, _genprof()) == cg.UNIVERSAL_DECEPTIVE_SYSTEM
    assert cg._compliance_system(None, None) == cg.UNIVERSAL_DECEPTIVE_SYSTEM   # safe default = universal
    fin_sys = cg._compliance_system({"firm_type": "insurance"}, _finprof())
    assert "financial-services marketing compliance screener" in fin_sys
    # finance INDUSTRY vocab must be absent; note 'guaranteed results' is a UNIVERSAL deceptive claim
    # and legitimately appears in the universal screener, so it is not a leak.
    for leak in ("broker-dealer", "finra", "securities", "investment return"):
        assert leak not in cg.UNIVERSAL_DECEPTIVE_SYSTEM.lower(), f"universal screener leaked {leak!r}"


def test_deterministic_rules_gated():
    from rep_engine import content_generator as cg
    # 'risk-free trial' is fine for a generic tenant, a violation for finance
    assert cg._deterministic_compliance("Try our risk-free trial") == []
    assert cg._deterministic_compliance("Try our risk-free trial", regulated_financial=True)
    # '#1/best' is universal
    assert cg._deterministic_compliance("We are the best in town")
    assert cg._deterministic_compliance("We are the best in town", regulated_financial=True)


def test_compliance_fix_editor_gated():
    from rep_engine import content_generator as cg
    assert "financial-services compliance editor" not in cg._compliance_fix_system(regulated_financial=False)
    assert "financial-services compliance editor" in cg._compliance_fix_system(regulated_financial=True)
    assert cg.COMPLIANCE_FIX_SYSTEM == cg._compliance_fix_system()


def test_rich_media_compliance_and_templates():
    from rep_engine import rich_media_generator as rmg
    assert rmg._compliance_check("a risk-free trial")[0] is True
    assert rmg._compliance_check("a risk-free trial", regulated_financial=True)[0] is False
    for name, tmpl in rmg._LLM_PROMPTS.items():
        low = tmpl.lower()
        for leak in ("guaranteed return", "risk-free", "financial-services", "limra", "life insurance"):
            assert leak not in low, f"rich-media template {name} leaked {leak!r}"


# --- gap prompts + persona lenses (Slice D) --------------------------------------------------------
def test_persona_lenses_profile_driven():
    from rep_engine import ai_state_audit as a
    gen_p = {p for p, _ in a._persona_lenses(GEN)}
    fin_p = {p for p, _ in a._persona_lenses(FIN)}
    saas = a._persona_lenses(SAAS)
    assert "recruit" not in gen_p and "recruit" in fin_p
    assert ("", "") in a._persona_lenses(GEN)                    # baseline lens always present
    assert not any(p == "local_customer" for p, _ in saas)      # saas: no local lens despite geo
    assert ("local_customer", "Denver, CO") in a._persona_lenses(GEN)


def test_contested_probe_declared_only():
    from rep_engine import ai_state_audit as a
    fin_txt = " ".join(p for p, _, _ in a.build_prompt_battery_lensed(FIN)).lower()
    gen_txt = " ".join(p for p, _, _ in a.build_prompt_battery_lensed(GEN)).lower()
    assert ("pyramid" in fin_txt or "mlm" in fin_txt)           # finance declared -> probe present
    assert "pyramid" not in gen_txt and "mlm" not in gen_txt    # generic -> no MLM probe


def test_gap_system_gated():
    from rep_engine import ai_state_audit as a
    gen = a._gap_system("")
    fin = a._gap_system(" LIC", has_local_presence=True, regulated_financial=True)
    nonlocal_ = a._gap_system("", has_local_presence=False)
    for leak in ("income/compensation disclosure", "scam/pyramid scheme/mlm"):
        assert leak not in gen.lower(), f"generic gap system leaked {leak!r}"
    assert "income/compensation disclosure" in fin.lower()
    assert "no local" in nonlocal_.lower() and "no local" not in gen.lower()
    assert a.GAP_SYSTEM == a._gap_system()


# --- GEN exemplars + byline + atomize (Slice E) ----------------------------------------------------
def test_gen_exemplars_gated():
    from rep_engine import content_generator as cg
    gen = cg._gen_system("")
    fin = cg._gen_system(" LIC", regulated_financial=True)
    for leak in ("broker-dealer", "limra", "life insurance", "sec/edgar", "income-disclosure"):
        assert leak not in gen.lower(), f"generic GEN leaked {leak!r}"
    assert "limra" in fin.lower() and "broker-dealer" in fin.lower()
    assert cg.GEN_SYSTEM == cg._gen_system()


def test_byline_profile_driven():
    from rep_engine import content_generator as cg
    body = "# Title\n\nEnough body text to place a byline under the heading."
    assert "editorial team" in cg._ensure_byline(body, "Joe's Diner", reviewer="editorial team")
    assert "licensed professionals" in cg._ensure_byline(body, "TU", reviewer="licensed professionals")
    law = cg._ensure_byline(body, "Smith Law", reviewer="a licensed attorney")
    assert "Reviewed by a licensed attorney" in law and "’s a licensed" not in law   # grammar


def test_atomize_channels_profile_driven():
    from rep_engine import content_generator as cg
    saas = cg._atomize_system(["linkedin", "x"]).lower()
    ecom = cg._atomize_system(["instagram", "facebook", "tiktok", "pinterest"]).lower()
    assert "instagram" not in saas and "linkedin" in saas
    assert "tiktok" in ecom and "pinterest" in ecom


# --- sources / thresholds / target / lexicon / batch (Slice F) -------------------------------------
def test_target_alignment_parity():
    from rep_engine import content_impact as ci, strategy_advisor as sa
    for biz, exp in [({"industry": "nonprofit"}, 0.6), (GEN, 0.5), (FIN, 0.5)]:
        assert ci._target_alignment(biz) == pytest.approx(exp)
        assert ci._target_alignment(biz) == sa._target_alignment_for(biz)   # lockstep parity


def test_challenge_thresholds_default_preserving():
    from rep_engine import challenge as ch
    # generic/nonprofit don't override thresholds -> same classification as the module defaults
    assert ch._classify(0.6, 0.1, 0.2) == ch._classify(0.6, 0.1, 0.2, thresholds=bp.derive({"industry": "nonprofit"}))
    assert ch._classify(0.6, 0.1, 0.2) == "awareness_gap"
    assert ch._classify(0.1, 0.5, 0.2) == "negative_narrative"


def test_mention_lexicon_declared_only():
    from rep_engine import mention_monitor as mm
    assert mm._sentiment("looks like a pyramid scheme") == "neutral"                 # generic
    assert mm._sentiment("looks like a pyramid scheme", {"pyramid", "scheme"}) == "negative"
    assert mm._sentiment("total scam and fraud") == "negative"                       # universal words


def test_content_batch_spread_profile_driven():
    from rep_engine import content_batch as cbatch
    gen = cbatch._types_for_gap({"topic": "about us"}, bp.derive({}).get("default_content_types"))
    fin = cbatch._types_for_gap({"topic": "about us"}, bp.derive(FIN).get("default_content_types"))
    assert "white_paper" not in gen and "faq" in gen
    assert "white_paper" in fin
    assert cbatch._types_for_gap({"topic": "best plumber near me", "asset_type": "local"}) == cbatch._LOCAL_TYPES


# --- DB-backed end-to-end: generate_for_wo for finance AND generic ---------------------------------
def _seed(conn, biz: dict) -> int:
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo, industry, "
        "regulatory_profile) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (biz["name"], "example.com", biz.get("services", ""), "win queries",
         biz.get("contested_terms", ""), biz.get("geo", ""), biz.get("industry", ""),
         json.dumps({"firm_type": biz["firm_type"]} if biz.get("firm_type") else {})),
    ).fetchone()
    conn.commit()
    return row["id"]


@requires_db
def test_generate_for_wo_finance_vs_generic(fresh_schema, monkeypatch):
    """End-to-end hot-path smoke: a draft is produced for BOTH a finance and a generic business, the
    per-tenant GEN system prompt is captured, and it is finance-worded for finance / finance-free for
    generic. Mocks the LLM (accepting **kwargs, unlike the older stale mocks) so no network is hit."""
    conn = fresh_schema
    from rep_engine import content_generator as cg

    captured: dict = {}

    def _fake_text(system, user, *a, **k):
        # capture the GEN system prompt (the long generation prompt) per business
        if "answer-engine-optimization" in system or "AEO/GEO" in system:
            captured.setdefault("gen_systems", []).append(system)
        return "# How We Help\n\nA clear, specific answer for the reader. We serve our community."

    def _fake_json(system, user, *a, **k):
        if "QA reviewer" in system or "score" in system.lower():
            return {"score": 0.9, "accuracy": True, "answers_query": True, "structure": True,
                    "tone": True, "issues": [], "fixes": []}
        return {"pass": True, "flags": []}

    monkeypatch.setattr(cg.llm, "orchestrator_text", _fake_text)
    monkeypatch.setattr(cg.llm, "orchestrator_json", _fake_json)

    for biz in (FIN, GEN):
        captured["gen_systems"] = []
        bid = _seed(conn, biz)
        biz_row = dict(conn.execute("SELECT * FROM businesses WHERE id=%s", (bid,)).fetchone())
        wo = {"title": "About us page", "capability": "content_writing", "execution": "auto",
              "instruction": "write it", "content_type": "article"}
        draft_id = cg.generate_for_wo(bid, wo, biz_row, content_type="article")
        assert draft_id, f"no draft produced for {biz['name']}"
        gen_systems = " ".join(captured.get("gen_systems", [])).lower()
        assert gen_systems, "GEN system prompt was never captured"
        if biz is FIN:
            assert "broker-dealer" in gen_systems or "limra" in gen_systems, "finance GEN missing finance module"
        else:
            for leak in _FIN_LEAK:
                assert leak not in gen_systems, f"generic {biz['name']} GEN leaked {leak!r}"
