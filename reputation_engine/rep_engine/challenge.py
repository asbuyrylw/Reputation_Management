"""
Reputation Crowding-Out Engine -- Primary Challenge Profile
===========================================================
Diagnoses a business's PRIMARY reputation challenge from the latest audit so the
strategy and timeline can adapt to it. The core strategic insight:

    Filling an AWARENESS gap -- the AI engines simply don't KNOW the business yet,
    an information VOID -- is materially FASTER than crowding out a NEGATIVE
    narrative, where the AI already knows the business and is unfavorable and there
    are entrenched citations to out-produce.

So the two challenges are NOT the same amount of work, and the timeline/plan should
say so. We separate them with two signals over the latest completed run's non-failed
answers:

  - unaware_rate   = share of answers where the AI did NOT recognize the business
                     (awareness = False) -> the information VOID to fill
  - negative_score = max(contested-mention rate, negative-sentiment rate)
                     -> entrenched negativity to crowd out

Profiles:
  awareness_gap        high void, low negativity   -> FILL THE VOID (faster)
  negative_narrative   low void,  high negativity  -> CROWD OUT negatives (slower)
  mixed                meaningful amounts of both   -> two-track
  established_positive low void,  low negativity, healthy alignment -> DEFEND

``void_fill_factor`` is a timeline speed multiplier (>1 = faster) consumed by
``timeline_estimator``. ``challenge_profile`` is a PURE READ -- it writes nothing.

Run:
    python -m rep_engine.challenge profile --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Optional

try:
    from .db import db
    from .answer_flags import is_wrong_entity
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from answer_flags import is_wrong_entity  # type: ignore

log = logging.getLogger("challenge")

# Classification thresholds (tunable). Rates are 0..1 over the latest run's answers.
VOID_HIGH = 0.50          # unaware_rate at/above this = a real awareness void
VOID_LOW = 0.30           # unaware_rate below this = the AI generally knows the business
NEG_LOW = 0.25            # negative_score below this = negativity is not the problem
NEG_HIGH = 0.40           # negative_score at/above this = entrenched negativity dominates
HEALTHY_ALIGNMENT = 0.40  # avg goal_alignment at/above this = already a good position
# A single portfolio label is misleading when BOTH problems are materially present (e.g. a
# Primerica-affiliated org the engines half-recognize AND partly frame as MLM). If the void
# and the negatives each clear their "material" bar, the challenge is genuinely two-track.
VOID_MATERIAL = 0.25      # >=1 in 4 answers don't recognize the business -> a real void
NEG_MATERIAL = 0.30       # >=~1 in 3 aware answers genuinely unfavourable -> real negatives

# Timeline speed multipliers per profile (>1 = the accurate narrative dominates faster).
# Filling a void is actively faster than competing with entrenched citations; an
# entrenched negative narrative is slower than the neutral baseline.
VOID_FILL_FACTORS = {
    "awareness_gap": 1.6,
    "mixed": 1.1,
    "negative_narrative": 0.8,
    "established_positive": 1.0,
    "unknown": 1.0,
}

_LABELS = {
    "awareness_gap": "Awareness gap",
    "negative_narrative": "Negative narrative",
    "mixed": "Mixed",
    "established_positive": "Established / positive",
    "unknown": "Not enough data",
}
_TRACKS = {
    "awareness_gap": "fill_void",
    "negative_narrative": "crowd_out",
    "mixed": "both",
    "established_positive": "defend",
    "unknown": "none",
}


def _classify(unaware_rate: Optional[float], negative_score: float,
              avg_alignment: float, thresholds: Optional[dict] = None) -> str:
    """Pick the primary-challenge profile from the two diagnostic signals. `thresholds` (the tenant's
    StrategyProfile, or None) may override the module-constant defaults; GENERIC equals the constants,
    so behavior is unchanged for current buckets and adjusts only for a bucket that tunes them."""
    t = thresholds or {}
    void_high = t.get("void_high", VOID_HIGH)
    void_low = t.get("void_low", VOID_LOW)
    neg_low = t.get("neg_low", NEG_LOW)
    neg_high = t.get("neg_high", NEG_HIGH)
    healthy = t.get("healthy_alignment", HEALTHY_ALIGNMENT)
    void_material = t.get("void_material", VOID_MATERIAL)
    neg_material = t.get("neg_material", NEG_MATERIAL)
    if unaware_rate is None:
        # No awareness signal yet (legacy run scored before the awareness column).
        # Fall back to negativity alone.
        if negative_score >= neg_high:
            return "negative_narrative"
        if negative_score < neg_low and avg_alignment >= healthy:
            return "established_positive"
        return "mixed"
    # Both a real void AND real negatives -> genuinely two-track, regardless of which is
    # marginally larger. A sizable recognition gap means you cannot call the challenge a pure
    # "negative narrative" (and vice-versa); the strategy must run both tracks.
    if unaware_rate >= void_material and negative_score >= neg_material:
        return "mixed"
    # Dominant void, little negativity -> an awareness gap (a void to fill, faster).
    if unaware_rate >= void_high and negative_score < neg_low + 0.05:
        return "awareness_gap"
    # Dominant negativity with only a SMALL void -> an entrenched negative narrative.
    if negative_score >= neg_high and unaware_rate < void_material:
        return "negative_narrative"
    # Well-known, low negativity, healthy alignment -> defend the position.
    if unaware_rate < void_low and negative_score < neg_low and avg_alignment >= healthy:
        return "established_positive"
    return "mixed"


def _headline(profile: str, unaware_pct: Optional[int], negative_pct: int, biz: str) -> str:
    """One plain-English sentence the console leads with."""
    if profile == "awareness_gap":
        return (f"The AI engines mostly don't know {biz} yet -- about {unaware_pct}% of "
                f"answers showed no real awareness. This is an information VOID to fill, "
                f"which is faster than fighting an established negative story.")
    if profile == "negative_narrative":
        return (f"The AI engines already know {biz} and carry an unfavorable framing in "
                f"about {negative_pct}% of answers. Entrenched negatives have to be "
                f"crowded out, which takes longer than filling a void.")
    if profile == "mixed":
        return (f"{biz} faces BOTH an awareness gap (~{unaware_pct}% of answers showed no "
                f"real recognition) and some negative framing (~{negative_pct}%). The plan "
                f"runs two tracks: fill the void first, address negatives in parallel.")
    if profile == "established_positive":
        return (f"The AI engines know {biz} and largely frame it accurately/favorably. The "
                f"job here is to DEFEND and extend that position, not repair it.")
    return f"Not enough scored audit data yet to diagnose {biz}'s primary challenge."


def _recommendation(profile: str) -> str:
    return {
        "awareness_gap": ("Prioritize authoritative, factual, owned and third-party content that "
                          "establishes who the business is, what it does, and who it serves -- the "
                          "engines need source material to cite. Speed comes from volume of clear, "
                          "corroborated facts, not from disputing anything."),
        "negative_narrative": ("Out-produce and out-corroborate the negative sources with accurate "
                               "content across many independent, authoritative domains. This is "
                               "slower -- you are competing with entrenched citations, not filling "
                               "an empty space."),
        "mixed": ("Two-track: (1) fill the awareness void with foundational factual content to "
                  "establish recognition quickly, and (2) in parallel, out-corroborate the negative "
                  "framing so it gets drowned out as awareness rises."),
        "established_positive": ("Maintain freshness and breadth of accurate sources, monitor for new "
                                 "negative mentions, and defend share-of-voice so the position holds."),
        "unknown": ("Run a completed audit to diagnose whether the primary challenge is an awareness "
                    "gap or an entrenched negative narrative."),
    }[profile]


def _r3(v):
    """Round to 3 dp, passing None through (for JSON-friendly nullable rates)."""
    return round(v, 3) if v is not None else None


def _ec(r) -> bool:
    """entity_confusion as a hard bool (legacy rows store NULL -> treated as False).
    Canonical NULL-safe rule now lives in answer_flags (shared with narrative_score)."""
    return is_wrong_entity(r)


def _compute(rows: list) -> dict:
    """Compute challenge signals for a set of non-failed answer rows. The recognition gap
    (engine doesn't correctly know THIS business) is split into a genuine awareness VOID and
    ENTITY CONFUSION (wrong same-named entity); both fill via identity grounding but are
    reported apart. A negative narrative is counted only where the engine knows the RIGHT
    business and the framing is genuinely unfavourable."""
    n = len(rows)
    contested_rate = sum(1 for r in rows if r["mentions_contested"]) / n if n else 0.0
    negative_rate = sum(1 for r in rows if (r["sentiment"] or "").lower() == "negative") / n if n else 0.0
    ga_vals = [float(r["goal_alignment"]) for r in rows if r["goal_alignment"] is not None]
    avg_alignment = sum(ga_vals) / len(ga_vals) if ga_vals else 0.0

    aware_known = [r for r in rows if r["awareness"] is not None]
    if aware_known:
        nk = len(aware_known)
        entity_confusion_rate = sum(1 for r in aware_known if _ec(r)) / nk
        # genuine void = doesn't recognize the business AND not a wrong-entity mixup
        unaware_rate = sum(1 for r in aware_known if (not r["awareness"]) and not _ec(r)) / nk
        # aware = recognizes the RIGHT business (and is not a wrong-entity answer)
        aware_rows = [r for r in aware_known if r["awareness"] and not _ec(r)]
        awareness_rate = len(aware_rows) / nk
        recognition_gap = unaware_rate + entity_confusion_rate

        def _is_negative(r):
            if _ec(r):
                return False  # wrong entity -> not THIS business's negativity
            if (r["sentiment"] or "").lower() == "negative":
                return True
            ga = r["goal_alignment"]
            return bool(r["mentions_contested"]) and ga is not None and ga < 0

        negative_score = sum(1 for r in aware_rows if _is_negative(r)) / nk
        contested_rebutted_rate = (
            sum(1 for r in aware_rows if r["mentions_contested"] and not _is_negative(r))
            / len(aware_rows) if aware_rows else 0.0)
    else:
        # Legacy run with no awareness signal: fall back to global negativity.
        entity_confusion_rate = None
        unaware_rate = None
        awareness_rate = None
        recognition_gap = None
        negative_score = max(contested_rate, negative_rate)
        contested_rebutted_rate = None

    return {
        "n": n,
        "contested_rate": contested_rate,
        "contested_rebutted_rate": contested_rebutted_rate,
        "negative_rate": negative_rate,
        "negative_score": negative_score,
        "avg_alignment": avg_alignment,
        "unaware_rate": unaware_rate,
        "entity_confusion_rate": entity_confusion_rate,
        "awareness_rate": awareness_rate,
        "recognition_gap": recognition_gap,
        "awareness_known_n": len(aware_known),
    }


def challenge_profile(business_id: int, run_id: Optional[int] = None,
                      quiet: bool = True) -> dict:
    """Diagnose the business's PRIMARY reputation challenge from its latest completed
    audit (or a specific run_id). Pure read. Returns a dict with the profile, the
    diagnostic rates, a per-engine breakdown, a timeline ``void_fill_factor``, a
    plain-English headline and a recommendation. ``profile='unknown'`` when there is no
    scored audit yet."""
    with db() as conn:
        biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            raise SystemExit(f"No business id {business_id}")
        name = biz["name"]
        if run_id is None:
            run = conn.execute(
                "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
                "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
            run_id = run["id"] if run else None
        rows = []
        if run_id is not None:
            rows = conn.execute(
                "SELECT engine, awareness, entity_confusion, mentions_contested, sentiment, "
                "goal_alignment FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)",
                (run_id,)).fetchall()

    # Business-agnostic thresholds + timeline multipliers: the StrategyProfile carries the challenge
    # thresholds (void_high/low, neg_high/low, void/neg_material, healthy_alignment) and the
    # void_fill_factors. GENERIC defaults equal the module constants, so this is behavior-preserving for
    # current buckets; a bucket that overrides them shifts only its own classification. Fail-safe -> {}.
    try:
        from . import business_profile as _bp
        _sprofile = _bp.for_business(business_id)
    except Exception:  # noqa: BLE001
        _sprofile = {}
    _fill_factors = _sprofile.get("void_fill_factors") or VOID_FILL_FACTORS

    n = len(rows)
    if n == 0:
        profile = "unknown"
        out = {
            "business": name, "run_id": run_id, "profile": profile,
            "label": _LABELS[profile], "track": _TRACKS[profile],
            "void_fill_factor": _fill_factors.get(profile, VOID_FILL_FACTORS.get(profile, 1.0)),
            "sample_size": 0,
            "headline": _headline(profile, None, 0, name),
            "recommendation": _recommendation(profile),
            "signals": {"unaware_rate": None, "awareness_rate": None,
                        "entity_confusion_rate": None, "recognition_gap": None,
                        "contested_rate": None, "contested_rebutted_rate": None,
                        "negative_rate": None, "negative_score": None, "avg_alignment": None},
            "by_engine": {},
        }
        if not quiet:
            print(json.dumps(out, indent=2, default=str))
        return out

    c = _compute(rows)
    # Classification keys off the RECOGNITION GAP (genuine void + wrong-entity), since both
    # mean the engine doesn't correctly know THIS business and both fill via identity
    # grounding. Legacy runs (no awareness signal) pass recognition_gap=None -> the
    # negativity-only fallback in _classify.
    profile = _classify(c["recognition_gap"], c["negative_score"], c["avg_alignment"], thresholds=_sprofile)
    gap_pct = round(c["recognition_gap"] * 100) if c["recognition_gap"] is not None else None
    negative_pct = round(c["negative_score"] * 100)

    # Per-engine breakdown: the challenge is often bimodal (one engine doesn't know the
    # business, another knows it and is unfavourable). A single portfolio label hides that.
    by_engine: dict = {}
    engines = sorted({r["engine"] for r in rows})
    for e in engines:
        erows = [r for r in rows if r["engine"] == e]
        ec = _compute(erows)
        eprofile = _classify(ec["recognition_gap"], ec["negative_score"], ec["avg_alignment"],
                             thresholds=_sprofile)
        by_engine[e] = {
            "profile": eprofile,
            "label": _LABELS[eprofile],
            "track": _TRACKS[eprofile],
            "n": ec["n"],
            "unaware_rate": _r3(ec["unaware_rate"]),
            "entity_confusion_rate": _r3(ec["entity_confusion_rate"]),
            "recognition_gap": _r3(ec["recognition_gap"]),
            "negative_score": _r3(ec["negative_score"]),
            "contested_rebutted_rate": _r3(ec["contested_rebutted_rate"]),
            "avg_alignment": _r3(ec["avg_alignment"]),
        }

    out = {
        "business": name,
        "run_id": run_id,
        "profile": profile,
        "label": _LABELS[profile],
        "track": _TRACKS[profile],
        "void_fill_factor": _fill_factors.get(profile, VOID_FILL_FACTORS.get(profile, 1.0)),
        "sample_size": n,
        "headline": _headline(profile, gap_pct, negative_pct, name),
        "recommendation": _recommendation(profile),
        "signals": {
            "unaware_rate": _r3(c["unaware_rate"]),
            "awareness_rate": _r3(c["awareness_rate"]),
            "entity_confusion_rate": _r3(c["entity_confusion_rate"]),
            "recognition_gap": _r3(c["recognition_gap"]),
            "contested_rate": _r3(c["contested_rate"]),
            "contested_rebutted_rate": _r3(c["contested_rebutted_rate"]),
            "negative_rate": _r3(c["negative_rate"]),
            "negative_score": _r3(c["negative_score"]),
            "avg_alignment": _r3(c["avg_alignment"]),
            "awareness_known_n": c["awareness_known_n"],
        },
        "by_engine": by_engine,
        "basis": ("recognition_gap (share where the engine doesn't correctly know THIS business "
                  "= genuine awareness void + wrong-entity confusion) vs negative_score "
                  "(aware-of-the-RIGHT-business AND genuinely UNFAVOURABLE: negative sentiment, "
                  "or a contested mention with goal_alignment < 0). Contested mentions the engine "
                  "REBUTS (non-negative goal_alignment) count as contested_rebutted_rate, not "
                  "negatives; wrong-entity answers count as entity_confusion, not negatives. "
                  "Falls back to global contested/negative rates on legacy runs."),
    }
    if not quiet:
        print(json.dumps(out, indent=2, default=str))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Primary reputation-challenge profile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("profile"); p.add_argument("--business-id", type=int, required=True)
    p.add_argument("--run-id", type=int, default=None)
    args = ap.parse_args()
    if args.cmd == "profile":
        challenge_profile(args.business_id, args.run_id, quiet=False)


if __name__ == "__main__":
    main()
