"""
Reputation Crowding-Out Engine -- Offline scoring eval (regression guard)
========================================================================
The product's headline metrics -- sentiment and goal_alignment -- come from an
LLM "judge" (ai_state_audit.score_answer) that is otherwise unvalidated against
ground truth. A prompt tweak, a model swap (e.g. routing scoring to the cheap
Haiku tier), or a provider change could silently degrade scoring and no test
would notice.

This harness runs the judge over a small GOLDEN set of (answer -> expected
human label) cases and reports agreement (sentiment accuracy + goal_alignment
band rate), so a regression is caught before it ships. It is intentionally
dependency-free; a heavier LLM-as-judge framework (deepeval / promptfoo / ragas)
can be layered on the same GOLDEN set later.

Grow GOLDEN with real labeled examples -- the signal scales with size. The live
judge needs an orchestrator key; the agreement math is pure and unit-tested.

Run:  python -m rep_engine.eval_harness
"""

from __future__ import annotations

from typing import Callable, Optional

try:
    from . import ai_state_audit as a
except ImportError:  # pragma: no cover
    import ai_state_audit as a  # type: ignore

# Seed golden set. Each case: a business context, a prompt, a (text, sources)
# answer, and the expected human label (sentiment + a goal_alignment band).
# EXPAND with real labeled examples -- this is a starting point, not a benchmark.
GOLDEN: list[dict] = [
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "Is Team Unstoppable a legitimate life-insurance business?",
        "answer": {"text": "Team Unstoppable is a licensed life-insurance agency with "
                           "strong local reviews and clear disclosures.",
                   "sources": ["teamunstoppable.com"]},
        "expected": {"sentiment": "positive", "goal_alignment_min": 0.3, "goal_alignment_max": 1.0},
    },
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "Is Team Unstoppable an MLM scam?",
        "answer": {"text": "Several forum posts call Team Unstoppable an MLM pyramid "
                           "scheme to avoid.",
                   "sources": ["reddit.com/r/antimlm"]},
        "expected": {"sentiment": "negative", "goal_alignment_min": -1.0, "goal_alignment_max": -0.1},
    },
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "What does Team Unstoppable do?",
        "answer": {"text": "Team Unstoppable appears to be a company; details are limited.",
                   "sources": []},
        "expected": {"sentiment": "neutral", "goal_alignment_min": -0.2, "goal_alignment_max": 0.3},
    },
]


def evaluate(golden: Optional[list] = None,
             score_fn: Optional[Callable[[dict, str, dict], dict]] = None) -> dict:
    """Run the scoring judge over `golden` and report agreement with the labels.

    `score_fn(business, prompt, answer) -> score dict` defaults to the live
    ai_state_audit.score_answer; inject a fake for testing. A case the judge
    could not score (empty/None result -> sentiment or goal_alignment missing) is
    counted as unscored, never as agreement."""
    golden = GOLDEN if golden is None else golden
    score_fn = score_fn or a.score_answer
    n = len(golden)
    sentiment_hits = band_hits = scored = 0
    details = []
    for case in golden:
        s = score_fn(case["business"], case["prompt"], case["answer"]) or {}
        exp = case["expected"]
        got_sent = s.get("sentiment")
        got_ga = s.get("goal_alignment")
        is_scored = got_sent is not None and got_ga is not None
        sent_ok = bool(is_scored and got_sent == exp["sentiment"])
        band_ok = bool(is_scored
                       and exp["goal_alignment_min"] <= float(got_ga) <= exp["goal_alignment_max"])
        scored += int(is_scored)
        sentiment_hits += int(sent_ok)
        band_hits += int(band_ok)
        details.append({"prompt": case["prompt"], "expected": exp,
                        "got_sentiment": got_sent, "got_goal_alignment": got_ga,
                        "sentiment_ok": sent_ok, "band_ok": band_ok})
    return {
        "n": n,
        "scored": scored,
        "sentiment_accuracy": (sentiment_hits / n) if n else 0.0,
        "goal_alignment_band_rate": (band_hits / n) if n else 0.0,
        "details": details,
    }


def main() -> None:
    rep = evaluate()
    print(f"Scoring eval over {rep['n']} golden case(s) ({rep['scored']} scored):")
    print(f"  sentiment accuracy:        {rep['sentiment_accuracy']:.2f}")
    print(f"  goal_alignment band rate:  {rep['goal_alignment_band_rate']:.2f}")
    for d in rep["details"]:
        mark = "ok  " if (d["sentiment_ok"] and d["band_ok"]) else "DIFF"
        print(f"  [{mark}] {d['prompt'][:48]:48} -> sent={d['got_sentiment']} "
              f"ga={d['got_goal_alignment']}")
    if rep["scored"] == 0:
        print("\nNo cases scored -- set an orchestrator key (e.g. ANTHROPIC_API_KEY) "
              "to run the judge.")


if __name__ == "__main__":
    main()
