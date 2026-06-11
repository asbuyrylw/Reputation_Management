"""
Reputation Crowding-Out Engine -- Module 8: Acceleration Advisor
================================================================
Answers the client's real question: "what would it take to get there FASTER?"

It takes the timeline estimate and runs what-if scenarios on the levers that the
engine CANNOT do for them -- the third-party / human actions that require outside
effort or spend:
    - third-party article / guest posts
    - third-party links / citations (earned placements)
    - videos (YouTube etc.)
    - earned press / media mentions
    - genuine reviews
    - podcast / interview appearances

For each lever it shows the modeled effect of adding a quantity range, and it
assembles 3 bundled scenarios (light / moderate / aggressive) showing how the
expected window compresses. Same honesty discipline as the estimator: these are
PROJECTIONS with explicit ranges, never promises, and the framing is drown-out
(out-produce/out-corroborate), never removal/suppression.

The per-lever weights below are deliberately conservative and centralized so they
are easy to tune as real outcome data accrues (and the planned outcome-feedback
loop can eventually learn them per-business).

Run:
    python -m rep_engine.acceleration_advisor advise --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

try:
    from . import timeline_estimator as te
except ImportError:  # pragma: no cover
    import timeline_estimator as te  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("acceleration_advisor")


# ---------------------------------------------------------------------------
# LEVERS: third-party / human actions the engine cannot automate.
#   weight   = monthly-gain contribution PER UNIT, before entrenchment drag.
#              (Conservative, tunable. Earned/authoritative actions weigh more
#               than owned content because they corroborate from outside.)
#   typical  = a sensible per-month quantity range to suggest.
#   unit     = label for the client.
# These are intentionally centralized and conservative -- they are PH 2 and are
# the right thing to recalibrate once outcome data exists.
# ---------------------------------------------------------------------------
LEVERS = {
    "third_party_articles": {"weight": 0.005, "typical": (2, 6), "unit": "guest/third-party articles",
        "note": "Bylined posts on relevant third-party sites; each corroborates the accurate narrative from outside your own domain."},
    "earned_links": {"weight": 0.004, "typical": (3, 10), "unit": "earned third-party links/citations",
        "note": "Editorial links/citations from credible sites; raises how often AI engines surface and trust your sources."},
    "videos": {"weight": 0.0035, "typical": (2, 5), "unit": "videos (YouTube/explainer)",
        "note": "Indexed video content answering the questions people ask; widens surfaces AI can cite."},
    "earned_press": {"weight": 0.005, "typical": (1, 3), "unit": "earned press / media mentions",
        "note": "Coverage in news/industry outlets; the highest-authority corroboration, hardest to get."},
    "reviews": {"weight": 0.002, "typical": (5, 20), "unit": "genuine client reviews",
        "note": "Authentic reviews on Google/industry platforms; must be genuine -- never fabricated or incentivized against platform rules."},
    "podcasts": {"weight": 0.005, "typical": (1, 3), "unit": "podcast / interview appearances",
        "note": "Guest appearances; create third-party transcripts and mentions that models pick up."},
}




def _baseline(business_id: int) -> dict:
    """Pull the current estimate + the pieces we need to re-model gain."""
    est = te.estimate(business_id, quiet=True)
    with db() as conn:
        ent = te._entrenchment(conn, business_id)
    return {"est": est, "entrench_grade": ent["grade"]}


def _months_for(remaining: float, gain: float) -> float:
    if remaining <= 0:
        return 0.0
    return remaining / max(gain, 1e-4)


def _window(months: float) -> dict:
    weeks = round(months * 4.345)
    return {"months": round(months, 1), "weeks": weeks,
            "target_date": (date.today() + timedelta(weeks=weeks)).isoformat()}


def advise(business_id: int, quiet: bool = False) -> dict:
    base = _baseline(business_id)
    est = base["est"]
    remaining = est["remaining_gap"]
    base_gain = est["monthly_gain_estimate"]
    # entrenchment drags the *effectiveness* of added levers the same way it drags
    # baseline gain, so added units are appropriately discounted for tough cases.
    entrench_drag = 1.0 - 0.6 * base["entrench_grade"]      # 0.4 .. 1.0
    base_expected = _window(_months_for(remaining, base_gain))

    # learned per-lever effectiveness (this business's own history), if available.
    # Blend learned gain-per-unit toward the static default by confidence so early,
    # noisy signals don't swing the numbers; high confidence trusts the data fully.
    try:
        from . import feedback_loop as fb
        learned = fb.learned_lever_weights(business_id)
    except Exception:  # noqa: BLE001
        learned = {}
    _CONF_BLEND = {"low": 0.25, "medium": 0.6, "high": 0.9}

    def eff_weight(key: str, spec: dict) -> tuple[float, str]:
        """Return (effective per-unit weight, basis)."""
        if key in learned and learned[key] > 0:
            # we only stored weights with gain>0; confidence is implicit in presence,
            # use a moderate blend by default (the feedback loop gates by sample size)
            blended = 0.5 * learned[key] + 0.5 * spec["weight"]
            return blended, "learned (this business) blended with default"
        return spec["weight"], "default"

    # ---- per-lever marginal effect (add the LOW and HIGH of its typical range) ----
    per_lever = []
    for key, spec in LEVERS.items():
        weight, weight_basis = eff_weight(key, spec)
        lo, hi = spec["typical"]
        gain_lo = base_gain + weight * entrench_drag * lo
        gain_hi = base_gain + weight * entrench_drag * hi
        # adding units shortens time -> hi units gives the shorter (faster) window
        w_with_lo = _window(max(_months_for(remaining, gain_lo), base_expected["months"] * 0.4))
        w_with_hi = _window(max(_months_for(remaining, gain_hi), base_expected["months"] * 0.4))
        saved_weeks_lo = base_expected["weeks"] - w_with_lo["weeks"]
        saved_weeks_hi = base_expected["weeks"] - w_with_hi["weeks"]
        per_lever.append({
            "lever": key,
            "unit": spec["unit"],
            "suggested_per_month": {"low": lo, "high": hi},
            "weeks_saved_range": {"low": max(0, saved_weeks_lo), "high": max(0, saved_weeks_hi)},
            "weight_basis": weight_basis,
            "note": spec["note"],
        })
    # rank by max weeks saved (impact-per-effort signal)
    per_lever.sort(key=lambda x: x["weeks_saved_range"]["high"], reverse=True)

    # ---- 3 bundled scenarios: light / moderate / aggressive ----
    def bundle(intensity: float) -> dict:
        """Add `intensity` (0..1) of each lever's typical range on top of the plan.
        A realism floor caps total compression at 40% of the baseline window -- added
        outside corroboration accelerates, but cannot collapse the timeline."""
        added_gain = 0.0
        composition = {}
        for key, spec in LEVERS.items():
            weight, _ = eff_weight(key, spec)
            lo, hi = spec["typical"]
            qty = round(lo + (hi - lo) * intensity)
            added_gain += weight * entrench_drag * qty
            composition[spec["unit"]] = qty
        gain = base_gain + added_gain
        months = max(_months_for(remaining, gain), base_expected["months"] * 0.4)
        return {"window": _window(months),
                "monthly_added_actions": composition,
                "new_monthly_gain_estimate": round(gain, 4)}

    scenarios = {
        "current_plan_only": {"window": base_expected,
                              "monthly_added_actions": {}, "note": "No added third-party actions."},
        "light_lift": {**bundle(0.2),
                       "note": "A modest amount of outside corroboration on top of the plan."},
        "moderate_lift": {**bundle(0.55),
                          "note": "Steady third-party content + a few earned placements monthly."},
        "aggressive_lift": {**bundle(1.0),
                            "note": "Full court press: top of the suggested ranges across all levers."},
    }

    result = {
        "business": est["business"],
        "generated": date.today().isoformat(),
        "current_alignment": est["current_alignment"],
        "dominance_target": est["dominance_target"],
        "confidence": est["confidence"],
        "baseline_expected_window": base_expected,
        "levers_ranked_by_impact": per_lever,
        "scenarios": scenarios,
        "how_to_read": (
            "Each lever shows how many weeks could come off the EXPECTED window if you "
            "add that many third-party/human actions per month. Levers are ranked by "
            "potential impact. The scenarios bundle several levers together. Entrenchment "
            "of the negatives discounts added effort, so tougher cases save fewer weeks per unit."
        ),
        "disclaimer": (
            "PROJECTION, not a guarantee. These model how added third-party corroboration "
            "would compress the timeline to DOMINANCE (drowning out, not removing, the "
            "negatives). Reviews and placements must be genuine and within each platform's "
            "rules -- never fabricated, never incentivized against policy. Actual results "
            "depend on the quality and authority of what's published, not just the count."
        ),
    }

    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Acceleration advisor (third-party levers to compress the timeline)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("advise"); a.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "advise":
        advise(args.business_id)


if __name__ == "__main__":
    main()
