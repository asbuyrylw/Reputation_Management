"""
Per-audit-run metric rollup + trends (NEXT)
===========================================
Persists a small snapshot of each audit run's metrics (overall goal-alignment / contested /
owned / grounded + per-engine goal-alignment) so per-engine TREND survives answer pruning and
re-scoring. `trend()` lazily back-fills any finished run missing a rollup, so existing history
shows up immediately.

Run:
    python -m rep_engine.run_metrics persist --business-id 2
    python -m rep_engine.run_metrics trend   --business-id 2
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
from psycopg.types.json import Json

log = logging.getLogger("run_metrics")


def _f(v) -> Optional[float]:
    return round(float(v), 4) if v is not None else None


def _compute(conn, run_id: int):
    o = conn.execute(
        "SELECT AVG(goal_alignment) ga, "
        "AVG(CASE WHEN mentions_contested THEN 1 ELSE 0 END) contested, "
        "AVG(CASE WHEN surfaces_owned THEN 1 ELSE 0 END) owned, "
        "AVG(CASE WHEN grounded THEN 1 ELSE 0 END) grounded "
        "FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)", (run_id,)).fetchone()
    per = conn.execute(
        "SELECT engine, AVG(goal_alignment) ga, COUNT(*) n FROM answers "
        "WHERE run_id=%s AND NOT COALESCE(failed,false) GROUP BY engine", (run_id,)).fetchall()
    per_engine = {r["engine"]: {"ga": _f(r["ga"]), "n": r["n"]} for r in per if r["engine"]}
    return o, per_engine


def persist(business_id: int, run_id: int) -> Optional[int]:
    """Compute + upsert the rollup for one run. Returns the run_id, or None if it has no scored answers.
    Single choke point for both persist_latest and trend()'s lazy back-fill."""
    with db() as conn:
        # Skip the 'fast' first-look tier (rec 9): its reduced, unlensed battery is not comparable to
        # a full audit, so it must never enter the durable per-run trend/rollup the metrics chart reads
        # (guarding here covers both persist_latest AND trend's back-fill in one place).
        m = conn.execute("SELECT COALESCE(mode,'full') AS mode FROM audit_runs WHERE id=%s",
                         (run_id,)).fetchone()
        if m and m["mode"] == "fast":
            return None
        o, per_engine = _compute(conn, run_id)
        if not o or o["ga"] is None:
            return None
        conn.execute(
            "INSERT INTO run_metrics (business_id, run_id, goal_alignment, contested_rate, owned_rate, "
            "grounded_rate, metrics) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id) DO UPDATE SET "
            "goal_alignment=EXCLUDED.goal_alignment, contested_rate=EXCLUDED.contested_rate, "
            "owned_rate=EXCLUDED.owned_rate, grounded_rate=EXCLUDED.grounded_rate, metrics=EXCLUDED.metrics",
            (business_id, run_id, _f(o["ga"]), _f(o["contested"]), _f(o["owned"]), _f(o["grounded"]),
             Json({"per_engine": per_engine})))
        conn.commit()
    return run_id


def persist_latest(business_id: int) -> Optional[int]:
    """Persist the rollup for the most recent finished AI audit (called at audit-complete)."""
    with db() as conn:
        r = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' "
            "AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    return persist(business_id, r["id"]) if r else None


def _score(ga) -> Optional[int]:
    return round((float(ga) + 1) / 2 * 100) if ga is not None else None


def trend(business_id: int) -> dict:
    """Per-run series of overall + per-engine scores (0-100). Lazily back-fills missing rollups."""
    with db() as conn:
        runs = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' "
            "AND finished_at IS NOT NULL ORDER BY id", (business_id,)).fetchall()
        have = {r["run_id"] for r in conn.execute(
            "SELECT run_id FROM run_metrics WHERE business_id=%s", (business_id,)).fetchall()}
    for r in runs:
        if r["id"] not in have:
            persist(business_id, r["id"])
    with db() as conn:
        rows = conn.execute(
            "SELECT rm.run_id, rm.goal_alignment, rm.metrics, ar.finished_at "
            "FROM run_metrics rm JOIN audit_runs ar ON ar.id=rm.run_id "
            "WHERE rm.business_id=%s ORDER BY rm.run_id", (business_id,)).fetchall()
    series, engines = [], set()
    for r in rows:
        pe = (r["metrics"] or {}).get("per_engine", {}) if isinstance(r["metrics"], dict) else {}
        engines.update(pe.keys())
        series.append({
            "run_id": r["run_id"],
            "date": r["finished_at"].date().isoformat() if r["finished_at"] else None,
            "score": _score(r["goal_alignment"]),
            "per_engine": {e: _score(v.get("ga")) for e, v in pe.items()},
        })
    return {"series": series, "engines": sorted(engines)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-run metric rollup + trend")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("persist", "trend"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    print(json.dumps(persist_latest(args.business_id) if args.cmd == "persist" else trend(args.business_id),
                     indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
