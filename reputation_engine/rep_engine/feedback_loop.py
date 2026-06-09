"""
Reputation Crowding-Out Engine -- Module 9: Outcome Feedback Loop
=================================================================
Makes the system LEARN. Until now the timeline estimator and acceleration advisor
run on generic, literature-based assumptions. This module measures what actually
happened for each business and recalibrates those assumptions toward reality.

What it does:
  1. Walks every consecutive pair of completed audit runs for a business.
  2. For each window: measures the goal_alignment change, and counts the asset
     TYPES that were shipped in that window (from the assets table).
  3. Attributes the window's monthly gain across the units shipped, accumulating a
     per-type "gain per unit" signal and an overall learned baseline gain.
  4. Writes learned_effectiveness + learned_baseline, with a confidence that rises
     with the number of observation windows.

How it's used (wired in, with safe fallbacks):
  - timeline_estimator reads learned_baseline to prefer measured monthly gain.
  - acceleration_advisor reads learned_effectiveness to weight levers by what has
    actually worked for THIS business instead of the static defaults.
  - the planner can rank work orders toward higher-learned-effectiveness types.

HONESTY: correlation, not proof. Movement can have many causes; this is a learned
prior that improves with data, not a causal claim. Confidence stays LOW until
several windows accumulate, and the modules that consume it keep their disclaimers.

Run:
    python -m rep_engine.feedback_loop learn --business-id 1
    python -m rep_engine.feedback_loop show  --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import defaultdict

import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("feedback_loop")

DB_DSN = os.getenv("REP_DB_DSN", "postgresql://USER:PASSWORD@localhost:5432/reputation")  # PH 1

# Map raw asset_type / capability values onto the advisor's lever vocabulary so the
# learned signal can recalibrate the advisor directly. PH 2 (extend as types grow).
TYPE_TO_LEVER = {
    "article": "third_party_articles", "guest_post": "third_party_articles",
    "owned_page": "third_party_articles", "faq": "third_party_articles",
    "link": "earned_links", "citation": "earned_links", "backlink": "earned_links",
    "video": "videos",
    "press": "earned_press", "media_mention": "earned_press",
    "review": "reviews", "review_request": "reviews",
    "podcast": "podcasts", "interview": "podcasts",
    "schema": "third_party_articles",
}

MIN_GAIN_FLOOR = 0.0   # we don't learn negative per-unit gains (treat as 0 contribution)


def db() -> psycopg.Connection:
    return psycopg.connect(DB_DSN, row_factory=dict_row)


def _ensure_tables() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS learned_effectiveness (
            business_id BIGINT, lever_type TEXT, obs_windows INT, obs_units INT,
            gain_per_unit NUMERIC(8,5), confidence TEXT, updated_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (business_id, lever_type))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS learned_baseline (
            business_id BIGINT PRIMARY KEY, monthly_gain NUMERIC(8,5), obs_windows INT,
            confidence TEXT, updated_at TIMESTAMPTZ DEFAULT now())""")
        conn.commit()


def _confidence(n_windows: int) -> str:
    if n_windows >= 5:
        return "high"
    if n_windows >= 3:
        return "medium"
    return "low"


def _ga(conn, run_id: int):
    v = conn.execute("SELECT AVG(goal_alignment) g FROM answers WHERE run_id=%s "
                     "AND NOT COALESCE(failed,false)", (run_id,)).fetchone()["g"]
    return float(v) if v is not None else None


def learn(business_id: int, quiet: bool = False) -> dict:
    """Recompute learned effectiveness + baseline for one business from its history."""
    _ensure_tables()
    with db() as conn:
        runs = conn.execute(
            "SELECT id, finished_at FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
            "ORDER BY id ASC", (business_id,),
        ).fetchall()
        if len(runs) < 2:
            if not quiet:
                log.info("Need >=2 completed runs to learn; have %d.", len(runs))
            return {"windows": 0, "levers": {}, "baseline": None}

        # accumulators
        lever_gain = defaultdict(float)     # summed attributed monthly-gain per lever
        lever_units = defaultdict(int)      # summed units shipped per lever
        lever_windows = defaultdict(int)    # windows in which this lever appeared
        total_monthly_gain = 0.0
        n_windows = 0

        for prev, cur in zip(runs, runs[1:]):
            g0, g1 = _ga(conn, prev["id"]), _ga(conn, cur["id"])
            if g0 is None or g1 is None or not prev["finished_at"] or not cur["finished_at"]:
                continue
            days = max((cur["finished_at"] - prev["finished_at"]).days, 1)
            monthly_gain = (g1 - g0) / days * 30.0
            n_windows += 1
            total_monthly_gain += monthly_gain

            # assets shipped in this window, grouped to levers
            assets = conn.execute(
                "SELECT asset_type, COUNT(*) n FROM assets WHERE business_id=%s "
                "AND published_at > %s AND published_at <= %s GROUP BY asset_type",
                (business_id, prev["finished_at"], cur["finished_at"]),
            ).fetchall()
            window_units = defaultdict(int)
            for a in assets:
                lever = TYPE_TO_LEVER.get((a["asset_type"] or "").lower(), "third_party_articles")
                window_units[lever] += a["n"]
            total_units = sum(window_units.values())
            if total_units == 0:
                continue
            # attribute this window's positive gain proportionally across units shipped
            attributable = max(monthly_gain, MIN_GAIN_FLOOR)
            for lever, units in window_units.items():
                share = units / total_units
                lever_gain[lever] += attributable * share
                lever_units[lever] += units
                lever_windows[lever] += 1

        # write learned_effectiveness
        levers_out = {}
        for lever, units in lever_units.items():
            gpu = (lever_gain[lever] / units) if units else 0.0
            conf = _confidence(lever_windows[lever])
            conn.execute(
                """INSERT INTO learned_effectiveness
                   (business_id, lever_type, obs_windows, obs_units, gain_per_unit, confidence, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s, now())
                   ON CONFLICT (business_id, lever_type) DO UPDATE SET
                     obs_windows=EXCLUDED.obs_windows, obs_units=EXCLUDED.obs_units,
                     gain_per_unit=EXCLUDED.gain_per_unit, confidence=EXCLUDED.confidence,
                     updated_at=now()""",
                (business_id, lever, lever_windows[lever], units, round(gpu, 5), conf),
            )
            levers_out[lever] = {"gain_per_unit": round(gpu, 5), "units": units,
                                 "windows": lever_windows[lever], "confidence": conf}

        # write learned_baseline (overall mean monthly gain)
        baseline = None
        if n_windows:
            mean_gain = total_monthly_gain / n_windows
            conf = _confidence(n_windows)
            conn.execute(
                """INSERT INTO learned_baseline (business_id, monthly_gain, obs_windows, confidence, updated_at)
                   VALUES (%s,%s,%s,%s, now())
                   ON CONFLICT (business_id) DO UPDATE SET
                     monthly_gain=EXCLUDED.monthly_gain, obs_windows=EXCLUDED.obs_windows,
                     confidence=EXCLUDED.confidence, updated_at=now()""",
                (business_id, round(mean_gain, 5), n_windows, conf),
            )
            baseline = {"monthly_gain": round(mean_gain, 5), "windows": n_windows, "confidence": conf}
        conn.commit()

    out = {"windows": n_windows, "levers": levers_out, "baseline": baseline}
    if not quiet:
        log.info("Learned from %d window(s); %d lever type(s).", n_windows, len(levers_out))
        print(json.dumps(out, indent=2, default=str))
    return out


# ----------------------------------------------------------------------------
# Read helpers used by the estimator / advisor (with safe fallbacks)
# ----------------------------------------------------------------------------
def learned_baseline(business_id: int):
    """Return (monthly_gain, confidence) or (None, None) if not learned yet."""
    _ensure_tables()
    with db() as conn:
        r = conn.execute("SELECT monthly_gain, confidence FROM learned_baseline WHERE business_id=%s",
                         (business_id,)).fetchone()
    if r and r["monthly_gain"] is not None:
        return float(r["monthly_gain"]), r["confidence"]
    return None, None


def learned_lever_weights(business_id: int) -> dict:
    """Return {lever_type: gain_per_unit} learned for this business (may be empty)."""
    _ensure_tables()
    with db() as conn:
        rows = conn.execute(
            "SELECT lever_type, gain_per_unit FROM learned_effectiveness "
            "WHERE business_id=%s AND gain_per_unit > 0", (business_id,)
        ).fetchall()
    return {r["lever_type"]: float(r["gain_per_unit"]) for r in rows}


def show(business_id: int) -> None:
    bl, blc = learned_baseline(business_id)
    weights = learned_lever_weights(business_id)
    print(f"Learned baseline monthly gain: {bl} (confidence: {blc})")
    if weights:
        print("Learned lever effectiveness (gain per unit):")
        for k, v in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            print(f"  {k:24} {v}")
    else:
        print("No learned lever weights yet (need shipped assets across >=1 window).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Outcome feedback loop (learns lever effectiveness)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    le = sub.add_parser("learn"); le.add_argument("--business-id", type=int, required=True)
    sh = sub.add_parser("show"); sh.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "learn":
        learn(args.business_id)
    elif args.cmd == "show":
        show(args.business_id)


if __name__ == "__main__":
    main()
