"""
Reputation Crowding-Out Engine -- Module 7: Timeline Estimator
==============================================================
Estimates how long it will take to DROWN OUT the negatives -- i.e., for the
accurate/positive narrative to dominate what AI assistants surface for a business.

HONESTY FIRST. This is a PROJECTION, not a promise. AI-visibility movement depends
on factors outside anyone's control (model re-crawl cadence, competitor activity,
platform changes). So the estimator:
  - returns a RANGE (optimistic / expected / conservative), never a single date;
  - attaches an explicit CONFIDENCE that starts LOW at baseline and rises only as
    the business's OWN measured velocity accumulates;
  - is driven by three signals it can actually reason about:
      1. ENTRENCHMENT of the negatives (how hard they'll be to out-produce)
      2. PLAN THROUGHPUT (how much accurate content/corroboration is being shipped)
      3. OBSERVED VELOCITY (the real rate of change for THIS business, once >=2 audits)
  - recalibrates to observed velocity as the dominant input the moment it exists,
    because a business's own trajectory beats any generic assumption.

It NEVER frames results as suppression. "Drown out" = out-produce/out-corroborate
so the good dominates; the negatives are not removed.

Run:
    python -m rep_engine.timeline_estimator estimate --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from datetime import date, timedelta


try:
    from .challenge import challenge_profile
    from .db import db
except ImportError:  # pragma: no cover
    from challenge import challenge_profile  # type: ignore
    from db import db  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("timeline_estimator")


# Target: the goal_alignment level at which we consider the accurate narrative to
# "dominate" local/branded queries. Tunable. PH 2.
DOMINANCE_TARGET = float(os.getenv("DOMINANCE_TARGET", "0.6"))
# Baseline literature-based monthly improvement in goal_alignment for a LOCAL brand
# under active crowding-out, before we have this client's own data. Conservative.
BASE_MONTHLY_GAIN = float(os.getenv("BASE_MONTHLY_GAIN", "0.12"))   # PH 3




# ----------------------------------------------------------------------------
# 1. Entrenchment grade -- how hard are the negatives to out-produce?
# ----------------------------------------------------------------------------
def _entrenchment(conn, business_id: int) -> dict:
    """Grade 0..1 (higher = more entrenched = slower). Built from the latest run:
    contested-mention rate, how many distinct sources carry the contested framing,
    and how authoritative/repeated those citations are."""
    run = conn.execute(
        "SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1", (business_id,),
    ).fetchone()
    if not run:
        return {"grade": 0.5, "basis": "no audit yet -- assumed moderate", "contested_rate": None}
    rid = run["id"]
    row = conn.execute(
        "SELECT AVG(CASE WHEN mentions_contested THEN 1 ELSE 0 END) contested_rate, "
        "COUNT(*) n FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)", (rid,),
    ).fetchone()
    contested_rate = float(row["contested_rate"]) if row["contested_rate"] is not None else 0.0

    # distinct cited source domains across answers that mention contested terms
    src_rows = conn.execute(
        "SELECT cited_sources FROM answers WHERE run_id=%s AND mentions_contested "
        "AND NOT COALESCE(failed,false)", (rid,),
    ).fetchall()
    domains = set()
    for r in src_rows:
        srcs = r["cited_sources"]
        items = srcs if isinstance(srcs, list) else (json.loads(srcs) if srcs else [])
        for s in items:
            d = s if isinstance(s, str) else (s.get("url") or s.get("domain") if isinstance(s, dict) else "")
            if d:
                # crude domain extract
                d = d.split("//")[-1].split("/")[0]
                domains.add(d)
    n_sources = len(domains)

    # grade: contested prevalence is the main driver; source breadth amplifies it
    grade = min(1.0, 0.6 * contested_rate + 0.1 * math.log1p(n_sources))
    return {
        "grade": round(grade, 3),
        "contested_rate": round(contested_rate, 3),
        "distinct_contested_sources": n_sources,
        "basis": "contested-mention rate + breadth of sources carrying it",
    }


# ----------------------------------------------------------------------------
# 2. Plan throughput -- how much accurate content/corroboration is being shipped?
# ----------------------------------------------------------------------------
def _throughput(conn, business_id: int) -> dict:
    """A multiplier >0. ~1.0 = an average plan cadence; >1 faster, <1 slower.
    Driven by count of content + corroboration work orders and how many are
    already moving (done/in-progress)."""
    rows = conn.execute(
        "SELECT capability, status FROM work_orders WHERE business_id=%s", (business_id,)
    ).fetchall()
    if not rows:
        return {"multiplier": 1.0, "basis": "no tracked work orders -- assumed average cadence",
                "content_wos": 0, "active_wos": 0}
    content_caps = {"content_writing", "schema_markup", "review_generation",
                    "press_outreach", "media_list_building", "link_building"}
    content_wos = sum(1 for r in rows if r["capability"] in content_caps)
    active = sum(1 for r in rows if r["status"] in ("in_progress", "done", "verified"))
    total = len(rows)
    # more content WOs => faster crowding-out; more already active => momentum
    volume_factor = min(1.6, 0.7 + 0.06 * content_wos)        # 0.7 .. 1.6
    momentum_factor = 0.8 + 0.4 * (active / total if total else 0)  # 0.8 .. 1.2
    mult = round(volume_factor * momentum_factor, 3)
    return {"multiplier": mult, "content_wos": content_wos, "active_wos": active,
            "basis": "content/corroboration volume x execution momentum"}


# ----------------------------------------------------------------------------
# 3. Observed velocity -- the real rate of change for THIS business
# ----------------------------------------------------------------------------
def _observed_velocity(conn, business_id: int) -> dict:
    """Monthly goal_alignment gain measured from this business's own audit history.
    None until there are >=2 completed runs. This is the strongest predictor once
    available and should dominate the estimate."""
    runs = conn.execute(
        "SELECT id, finished_at FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
        "ORDER BY id ASC", (business_id,),
    ).fetchall()
    if len(runs) < 2:
        return {"monthly_gain": None, "runs": len(runs),
                "basis": "need >=2 audits for measured velocity"}

    def ga(rid):
        v = conn.execute("SELECT AVG(goal_alignment) g FROM answers WHERE run_id=%s "
                         "AND NOT COALESCE(failed,false)", (rid,)).fetchone()["g"]
        return float(v) if v is not None else None

    first, last = runs[0], runs[-1]
    g0, g1 = ga(first["id"]), ga(last["id"])
    if g0 is None or g1 is None or not first["finished_at"] or not last["finished_at"]:
        return {"monthly_gain": None, "runs": len(runs), "basis": "insufficient scored data"}
    days = max((last["finished_at"] - first["finished_at"]).days, 1)
    monthly_gain = (g1 - g0) / days * 30.0
    return {"monthly_gain": round(monthly_gain, 4), "runs": len(runs),
            "current_alignment": round(g1, 3), "span_days": days,
            "basis": "measured goal_alignment change per 30 days for this business"}


# ----------------------------------------------------------------------------
# Combine -> phased range + confidence
# ----------------------------------------------------------------------------
def estimate(business_id: int, quiet: bool = False) -> dict:
    with db() as conn:
        biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            raise SystemExit(f"No business id {business_id}")
        ent = _entrenchment(conn, business_id)
        thr = _throughput(conn, business_id)
        vel = _observed_velocity(conn, business_id)

        # current alignment (start point)
        cur = vel.get("current_alignment")
        if cur is None:
            run = conn.execute("SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
                               "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
            if run:
                v = conn.execute("SELECT AVG(goal_alignment) g FROM answers WHERE run_id=%s "
                                 "AND NOT COALESCE(failed,false)", (run["id"],)).fetchone()["g"]
                cur = float(v) if v is not None else 0.0
            else:
                cur = 0.0

    # Primary-challenge profile: an awareness gap (a void to fill) closes FASTER than
    # an entrenched negative narrative (citations to out-produce). Opens its own
    # connection, so call it after the read block above closes.
    chal = challenge_profile(business_id, quiet=True)
    void_fill_factor = float(chal.get("void_fill_factor", 1.0))

    remaining = max(0.0, DOMINANCE_TARGET - cur)

    # --- choose the monthly-gain estimate ---
    if vel["monthly_gain"] is not None and vel["monthly_gain"] > 0:
        # observed velocity dominates once we have it -- it already reflects whether the
        # business is filling a void or fighting negatives, so no factor is applied.
        expected_gain = vel["monthly_gain"]
        confidence = "high" if vel["runs"] >= 4 else "medium"
        gain_basis = "observed velocity (this business)"
    else:
        # baseline literature gain, adjusted by entrenchment (slows), throughput (speeds),
        # and the challenge profile's void-fill factor (awareness gaps fill faster than
        # negative narratives crowd out).
        entrench_drag = 1.0 - 0.6 * ent["grade"]            # 0.4 .. 1.0
        expected_gain = BASE_MONTHLY_GAIN * entrench_drag * thr["multiplier"] * void_fill_factor
        confidence = "low"
        gain_basis = (f"baseline model (no measured velocity yet); challenge="
                      f"{chal.get('profile')} (void-fill x{void_fill_factor})")
        # if observed velocity exists but is <=0 (stalled), flag it
        if vel["monthly_gain"] is not None:
            gain_basis += " -- note: measured velocity is flat/negative; plan may need adjustment"
            confidence = "low"

    expected_gain = max(expected_gain, 1e-4)

    def months_for(gain):
        if remaining <= 0:
            return 0.0
        return remaining / gain

    expected_months = months_for(expected_gain)
    # range: optimistic = 35% faster, conservative = 75% slower
    optimistic_months = expected_months * 0.65
    conservative_months = expected_months * 1.75

    today = date.today()

    def to_window(months):
        weeks = round(months * 4.345)
        target = today + timedelta(weeks=weeks)
        return {"months": round(months, 1), "weeks": weeks, "target_date": target.isoformat()}

    result = {
        "business": biz["name"],
        "generated": today.isoformat(),
        "current_alignment": round(cur, 3),
        "dominance_target": DOMINANCE_TARGET,
        "remaining_gap": round(remaining, 3),
        "monthly_gain_estimate": round(expected_gain, 4),
        "gain_basis": gain_basis,
        "confidence": confidence,
        "challenge": chal,
        "projection": {
            "optimistic": to_window(optimistic_months),
            "expected": to_window(expected_months),
            "conservative": to_window(conservative_months),
        },
        "drivers": {"entrenchment": ent, "plan_throughput": thr,
                    "observed_velocity": vel, "challenge_profile": chal},
        "disclaimer": (
            "This is a PROJECTION, not a guarantee. It estimates how long until the "
            "accurate narrative DOMINATES what AI assistants surface (drowning out, not "
            "removing, the negatives). Confidence is low at baseline and rises as this "
            "business's own measured velocity accumulates. AI-platform behavior and "
            "competitor activity can shift the timeline."
        ),
    }
    if remaining <= 0:
        result["status"] = "Target already met -- focus shifts to holding/defending the position."
    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Timeline estimator (range-based projection)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate"); e.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "estimate":
        estimate(args.business_id)


if __name__ == "__main__":
    main()
