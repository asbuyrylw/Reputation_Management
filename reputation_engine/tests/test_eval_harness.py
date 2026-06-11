"""Tests for the offline scoring eval harness (eval_harness.py).

The agreement math is pure and tested with a fake judge (no key needed). The
live-judge regression test runs the real score_answer over the golden set and is
skipped automatically when no orchestrator key is configured.
"""

from __future__ import annotations

import os

import pytest


def test_evaluate_computes_agreement():
    from rep_engine import eval_harness as ev
    golden = [
        {"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p1",
         "answer": {"text": "a", "sources": []},
         "expected": {"sentiment": "positive", "goal_alignment_min": 0.3, "goal_alignment_max": 1.0}},
        {"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p2",
         "answer": {"text": "b", "sources": []},
         "expected": {"sentiment": "negative", "goal_alignment_min": -1.0, "goal_alignment_max": 0.0}},
    ]

    def fake_score(business, prompt, ans):
        if prompt == "p1":
            return {"sentiment": "positive", "goal_alignment": 0.8}   # both correct
        return {"sentiment": "positive", "goal_alignment": -0.5}      # sentiment wrong, band ok

    rep = ev.evaluate(golden, score_fn=fake_score)
    assert rep["n"] == 2 and rep["scored"] == 2
    assert rep["sentiment_accuracy"] == 0.5         # case1 ok, case2 wrong
    assert rep["goal_alignment_band_rate"] == 1.0   # both within band


def test_evaluate_counts_unscored_as_miss():
    from rep_engine import eval_harness as ev
    golden = [{"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p",
               "answer": {"text": "a", "sources": []},
               "expected": {"sentiment": "positive", "goal_alignment_min": 0.0, "goal_alignment_max": 1.0}}]
    rep = ev.evaluate(golden, score_fn=lambda *args: {})   # judge produced nothing
    assert rep["scored"] == 0
    assert rep["sentiment_accuracy"] == 0.0 and rep["goal_alignment_band_rate"] == 0.0


def test_builtin_golden_set_is_well_formed():
    from rep_engine import eval_harness as ev
    assert len(ev.GOLDEN) >= 3
    for c in ev.GOLDEN:
        assert {"business", "prompt", "answer", "expected"} <= set(c)
        assert c["expected"]["sentiment"] in {"positive", "neutral", "negative", "mixed"}
        assert c["expected"]["goal_alignment_min"] <= c["expected"]["goal_alignment_max"]


_NO_KEY = ("YOUR_" in os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY")
           and "YOUR_" in os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY"))


@pytest.mark.skipif(_NO_KEY, reason="no orchestrator API key set")
def test_live_scoring_meets_agreement_threshold():
    """Regression guard: with a real orchestrator key, the judge must agree with
    the golden labels above a threshold. Skipped automatically without a key."""
    from rep_engine import eval_harness as ev
    rep = ev.evaluate()
    assert rep["scored"] == rep["n"]              # the judge scored every case
    assert rep["sentiment_accuracy"] >= 0.66      # >= 2/3 sentiment agreement
    assert rep["goal_alignment_band_rate"] >= 0.66
