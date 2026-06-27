"""
Predictive ROI + cross-client effectiveness learning (Recommendation #1c)
=========================================================================
Two compounding moats:

  cross_client_priors():  aggregates the per-client learned_effectiveness (feedback_loop) ACROSS
    every business -- ANONYMIZED, keyed only by lever type (and industry when available) -- into a
    prior "gain per unit of work" for each lever. As you add clients this prior sharpens, and it
    bootstraps a brand-new client's plan with what has ACTUALLY worked across the book of business.
    No competitor has this data flywheel.

  predict_plan():  estimates the score lift a business should expect from finishing its open plan,
    preferring THIS client's learned effectiveness, then the cross-client prior, then the static
    per-capability estimate -- so the prediction gets more grounded the more data exists, and the
    `basis` is always disclosed honestly.

Honest framing: a learned prior, not a guarantee; confidence rises with observed windows.

Run:  python -m rep_engine.roi_predictor predict --business-id 1
      python -m rep_engine.roi_predictor priors
"""

from __future__ import annotations

import argparse
import json
import logging

try:
    from .db import db
    from .feedback_loop import TYPE_TO_LEVER, learned_lever_weights, learned_baseline
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from feedback_loop import TYPE_TO_LEVER, learned_lever_weights, learned_baseline  # type: ignore

log = logging.getLogger("roi_predictor")

# Static fallback gain-per-task (AI-score points) by capability, used only when neither this client
# nor the cross-client prior has learned the lever yet. Conservative.
_STATIC_GAIN = {
    "content_writing": 2.0, "video_creation": 2.5, "schema_markup": 1.5, "link_building": 3.0,
    "press_outreach": 3.0, "media_list_building": 0.5, "social_publishing": 1.0,
    "review_generation": 2.0, "local_content_creation": 2.0, "gbp_optimization": 2.0,
    "ai_visibility_tracking": 0.0,
}
_CONF_RANK = {"high": 3, "medium": 2, "low": 1, None: 0}


def cross_client_priors() -> dict:
    """Anonymized lever -> {gain_per_unit, businesses, obs_units, confidence} aggregated across all
    clients' learned_effectiveness. No business identifiers leave the aggregation."""
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT lever_type, AVG(gain_per_unit) g, COUNT(DISTINCT business_id) nb, "
                "SUM(obs_units) units, SUM(obs_windows) wins FROM learned_effectiveness "
                "WHERE gain_per_unit > 0 GROUP BY lever_type",
            ).fetchall()
    except Exception as e:  # noqa: BLE001 -- table may not exist yet on a fresh install
        log.debug("cross-client priors unavailable: %s", e)
        return {}
    out = {}
    for r in rows:
        wins = int(r["wins"] or 0)
        conf = "high" if wins >= 5 else "medium" if wins >= 3 else "low"
        out[r["lever_type"]] = {"gain_per_unit": round(float(r["g"]), 5),
                                "businesses": int(r["nb"] or 0), "obs_units": int(r["units"] or 0),
                                "confidence": conf}
    return out


def predict_plan(business_id: int) -> dict:
    """Predict the score lift from finishing this business's OPEN plan, using (in priority order)
    this client's learned effectiveness, the cross-client prior, then a static estimate."""
    own = learned_lever_weights(business_id)            # lever -> gain_per_unit (this client)
    priors = cross_client_priors()                      # lever -> {gain_per_unit, ...}
    bl_gain, bl_conf = learned_baseline(business_id)
    with db() as conn:
        tasks = conn.execute(
            "SELECT capability, COUNT(*) n FROM work_orders WHERE business_id=%s "
            "AND status IN ('pending','in_progress') AND NOT COALESCE(superseded,false) "
            "GROUP BY capability", (business_id,),
        ).fetchall()
    total = 0.0
    by_cap = []
    basis_counts = {"this client": 0, "cross-client": 0, "industry baseline": 0}
    for t in tasks:
        cap = t["capability"] or ""
        n = int(t["n"])
        lever = TYPE_TO_LEVER.get(cap, "third_party_articles")
        if lever in own:
            gpu, basis, conf = own[lever], "this client", "medium"
        elif lever in priors:
            gpu, basis, conf = priors[lever]["gain_per_unit"], "cross-client", priors[lever]["confidence"]
        else:
            gpu, basis, conf = _STATIC_GAIN.get(cap, 1.0), "industry baseline", "low"
        pts = round(gpu * n, 2)
        total += pts
        basis_counts[basis] += n
        by_cap.append({"capability": cap, "open_tasks": n, "gain_per_task": round(gpu, 3),
                       "predicted_points": pts, "basis": basis, "confidence": conf})
    by_cap.sort(key=lambda x: x["predicted_points"], reverse=True)
    # overall confidence = the strongest basis that carries most of the predicted lift
    dominant = max(basis_counts, key=basis_counts.get) if any(basis_counts.values()) else "industry baseline"
    overall_conf = {"this client": "medium", "cross-client": "low", "industry baseline": "low"}[dominant]
    # Horizon is only honest once we've MEASURED this client's velocity; without a learned baseline
    # we can't credibly predict timing, so we leave it null rather than invent a number.
    horizon_weeks = None
    if total > 0 and bl_gain and bl_gain > 0:
        horizon_weeks = max(2, round((total / 100.0) / bl_gain * 4.3))  # points->fraction->months->weeks
    return {
        "predicted_points": round(total, 1),
        "open_tasks": sum(int(t["n"]) for t in tasks),
        "by_capability": by_cap[:12],
        "basis_mix": basis_counts,
        "confidence": overall_conf,
        "horizon_weeks": horizon_weeks,
        "note": ("Predicted lift in AI-score points from finishing the open plan. Uses this client's "
                 "measured effectiveness first, then what's worked across all clients, then an "
                 "industry baseline. A learned prior, not a guarantee."),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Predictive ROI + cross-client learning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict"); p.add_argument("--business-id", type=int, required=True)
    sub.add_parser("priors")
    args = ap.parse_args()
    if args.cmd == "predict":
        print(json.dumps(predict_plan(args.business_id), indent=2, default=str))
    elif args.cmd == "priors":
        print(json.dumps(cross_client_priors(), indent=2, default=str))


if __name__ == "__main__":
    main()
