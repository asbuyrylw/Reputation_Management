"""
Narrative Crowding-Out Score (Recommendation #1a)
=================================================
ONE client-legible headline metric: across all AI-answer-engine responses about the business, how
much does the DESIRED narrative dominate versus the CONTESTED one. This is the number a client
renews for -- "MLM-narrative dominance 64% -> 41% over 3 audits" tells the whole story at a glance.

Per non-failed answer we classify the narrative that WON that answer:
  - desired   : the business's accurate/positive narrative leads (high goal_alignment, or owned
                content surfaced without a contested frame and non-negative sentiment),
  - contested : the negative/contested frame dominates (a contested mention plus negative sentiment
                or clearly negative goal_alignment),
  - neutral   : neither dominates (e.g. the engine is unaware / generic).

Score (0-100) = 100 * (desired - contested + total) / (2*total): 100 = the desired narrative wins
everywhere, 50 = even, 0 = the contested narrative wins everywhere. Persisted per run so the trend
is durable. Honest: this is a measurement of what engines return, not a manipulation target.

Run:  python -m rep_engine.narrative_score compute --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("narrative_score")

_DESIRED_GA = 0.15      # goal_alignment above this = the desired narrative clearly leads
_CONTESTED_GA = -0.15   # at/below this with a contested frame = the contested narrative dominates


def _classify(a: dict) -> str:
    ga = a.get("goal_alignment")
    ga = float(ga) if ga is not None else 0.0
    contested = bool(a.get("mentions_contested"))
    owned = bool(a.get("surfaces_owned"))
    sentiment = (a.get("sentiment") or "").lower()
    if contested and (sentiment == "negative" or ga <= _CONTESTED_GA):
        return "contested"
    if ga >= _DESIRED_GA or (owned and not contested and sentiment in ("positive", "neutral")):
        return "desired"
    return "neutral"


def _score_rows(rows: list[dict]) -> dict:
    total = len(rows)
    if not total:
        return {"score": None, "desired_pct": None, "contested_pct": None, "neutral_pct": None,
                "n_answers": 0, "by_engine": {}}
    counts: defaultdict = defaultdict(int)
    per_engine: dict = defaultdict(lambda: defaultdict(int))
    for a in rows:
        c = _classify(a)
        counts[c] += 1
        per_engine[a.get("engine") or "?"][c] += 1
    desired, contested, neutral = counts["desired"], counts["contested"], counts["neutral"]
    score = round(100.0 * (desired - contested + total) / (2 * total), 1)
    by_engine = {}
    for eng, ec in per_engine.items():
        et = sum(ec.values())
        by_engine[eng] = {
            "score": round(100.0 * (ec["desired"] - ec["contested"] + et) / (2 * et), 1) if et else None,
            "desired": ec["desired"], "contested": ec["contested"], "neutral": ec["neutral"],
        }
    return {
        "score": score,
        "desired_pct": round(100.0 * desired / total, 1),
        "contested_pct": round(100.0 * contested / total, 1),
        "neutral_pct": round(100.0 * neutral / total, 1),
        "n_answers": total, "by_engine": by_engine,
    }


def compute(business_id: int, run_id: int | None = None, persist: bool = True, quiet: bool = True) -> dict:
    """Compute (and persist) the Narrative Crowding-Out Score for a run (latest completed if None)."""
    with db() as conn:
        if run_id is None:
            r = conn.execute("SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' "
                             "AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
            if not r:
                return {"run_id": None, "score": None, "n_answers": 0}
            run_id = r["id"]
        rows = conn.execute(
            "SELECT engine, sentiment, goal_alignment, mentions_contested, surfaces_owned "
            "FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)", (run_id,),
        ).fetchall()
        out = _score_rows([dict(r) for r in rows])
        out["run_id"] = run_id
        if persist and out["score"] is not None:
            conn.execute(
                """INSERT INTO narrative_scores
                   (business_id, run_id, score, desired_pct, contested_pct, neutral_pct, n_answers, by_engine)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (business_id, run_id) DO UPDATE SET
                     score=EXCLUDED.score, desired_pct=EXCLUDED.desired_pct,
                     contested_pct=EXCLUDED.contested_pct, neutral_pct=EXCLUDED.neutral_pct,
                     n_answers=EXCLUDED.n_answers, by_engine=EXCLUDED.by_engine, computed_at=now()""",
                (business_id, run_id, out["score"], out["desired_pct"], out["contested_pct"],
                 out["neutral_pct"], out["n_answers"], json.dumps(out["by_engine"])),
            )
            conn.commit()
    if not quiet:
        print(json.dumps(out, indent=2, default=str))
    return out


def trend(business_id: int) -> dict:
    """The score over time (durable -- reads the persisted rollup, not the prunable answers)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT ns.run_id, ns.score, ns.desired_pct, ns.contested_pct, ns.neutral_pct, "
            "to_char(r.finished_at,'YYYY-MM-DD') AS date "
            "FROM narrative_scores ns LEFT JOIN audit_runs r ON r.id=ns.run_id "
            "WHERE ns.business_id=%s ORDER BY ns.run_id", (business_id,),
        ).fetchall()
    series = [{"run_id": r["run_id"], "date": r["date"], "score": float(r["score"]) if r["score"] is not None else None,
               "desired_pct": float(r["desired_pct"]) if r["desired_pct"] is not None else None,
               "contested_pct": float(r["contested_pct"]) if r["contested_pct"] is not None else None}
              for r in rows]
    latest = series[-1] if series else None
    delta = None
    if len(series) >= 2 and series[-1]["score"] is not None and series[-2]["score"] is not None:
        delta = round(series[-1]["score"] - series[-2]["score"], 1)
    return {"latest": latest, "delta": delta, "series": series}


def main() -> None:
    ap = argparse.ArgumentParser(description="Narrative Crowding-Out Score")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compute"); c.add_argument("--business-id", type=int, required=True)
    t = sub.add_parser("trend"); t.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "compute":
        compute(args.business_id, quiet=False)
    elif args.cmd == "trend":
        print(json.dumps(trend(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
