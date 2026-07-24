"""Review Batch A — correctness bug fixes (regression lock)."""
from __future__ import annotations

from decimal import Decimal

from rep_engine import strategy_generator as sg


def test_capability_maps_cover_richmedia():
    """#3 — every rich-media/video capability now has an ROI lever + effort + SEO weight, so
    predict_impact scores them (they no longer collapse to roi_score=0 and sort last)."""
    for cap in ("explainer_video", "podcast_creation", "deep_content", "slide_deck",
                "infographic", "research_brief", "video_creation"):
        assert sg._CAPABILITY_TO_LEVER.get(cap), f"{cap} has no ROI lever"
        assert cap in sg._EFFORT, f"{cap} missing effort"
        assert cap in sg._CAPABILITY_SEO, f"{cap} missing SEO weight"
    # structural tasks stay lever-less (correctly scored via SEO points, not AI points)
    assert sg._CAPABILITY_TO_LEVER.get("schema_markup") is None
    assert sg._CAPABILITY_TO_LEVER.get("ai_visibility_tracking") is None


def test_strat_tokens_keeps_three_letter_terms():
    """tokenizer len>2 keeps 3-letter domain terms (was >3, dropping tax/ira/roi/seo/gbp)."""
    toks = sg._strat_tokens("Roth IRA vs 401k, tax planning, SEO and GBP")
    assert {"ira", "tax", "seo", "gbp"} <= toks


def test_gap_answer_priority_uses_decimal_alignment():
    """#1 — goal_alignment arrives as Decimal (NUMERIC); it must drive prioritization, not default
    to 0.5. A weak low-alignment answer sorts AHEAD of a strong one."""
    from rep_engine import ai_state_audit as a
    weak = a._gap_answer_priority({"sentiment": "neutral", "goal_alignment": Decimal("0.10")})
    strong = a._gap_answer_priority({"sentiment": "positive", "goal_alignment": Decimal("0.90")})
    assert weak < strong                 # weak (more gap-relevant) sorts first
    assert weak[1] == 0.10               # the real Decimal value, not the silent 0.5 default
