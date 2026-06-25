"""
Answer lenses (NEXT): cross-engine divergence + persona/location lens
=====================================================================
Derivations over the latest audit's answers (no new storage):
  - divergence: prompts where the AI engines most DISAGREE (one says fiduciary, another contested),
                so a single drifting engine is caught before it drags the overall score.
  - lenses:     how different audiences (persona / location) see you — does a local Cincinnati
                prospect get a worse/contested answer than a generic one?
"""

from __future__ import annotations

import logging

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("lenses")


def _latest_run(conn, business_id: int):
    r = conn.execute(
        "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' "
        "AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    return r["id"] if r else None


def _score(ga) -> int:
    return round((float(ga) + 1) / 2 * 100)


def divergence(business_id: int) -> dict:
    """Top prompts where engines disagree most (spread of goal-alignment across engines)."""
    with db() as conn:
        run = _latest_run(conn, business_id)
        if not run:
            return {"run_id": None, "items": []}
        rows = conn.execute(
            "SELECT prompt, engine, goal_alignment, mentions_contested FROM answers "
            "WHERE run_id=%s AND NOT COALESCE(failed,false) AND goal_alignment IS NOT NULL",
            (run,)).fetchall()
    by_prompt: dict = {}
    for r in rows:
        by_prompt.setdefault(r["prompt"], []).append(r)
    items = []
    for prompt, ans in by_prompt.items():
        scored = sorted(((a["engine"], float(a["goal_alignment"])) for a in ans), key=lambda x: x[1])
        if len(scored) < 2:
            continue
        worst, best = scored[0], scored[-1]
        spread = round((best[1] - worst[1]) / 2 * 100)   # ga in [-1,1] -> 0-100-scale spread
        if spread <= 0:
            continue
        items.append({
            "prompt": (prompt or "")[:160], "spread": spread,
            "best_engine": best[0], "best": _score(best[1]),
            "worst_engine": worst[0], "worst": _score(worst[1]),
            "contested_engines": [a["engine"] for a in ans if a["mentions_contested"]],
        })
    items.sort(key=lambda x: x["spread"], reverse=True)
    return {"run_id": run, "items": items[:10]}


def lenses(business_id: int) -> dict:
    """Average score + contested rate by persona and by location for the latest run."""
    with db() as conn:
        run = _latest_run(conn, business_id)
        if not run:
            return {"run_id": None, "by_persona": [], "by_location": []}

        def grp(col: str):
            # `col` is one of the two fixed literals below -- never user input.
            rows = conn.execute(
                f"SELECT {col} k, AVG(goal_alignment) ga, "  # nosec B608
                "AVG(CASE WHEN mentions_contested THEN 1 ELSE 0 END) contested, COUNT(*) n "
                f"FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false) "  # nosec B608
                f"AND {col} IS NOT NULL AND {col} <> '' GROUP BY {col} ORDER BY ga",  # nosec B608
                (run,)).fetchall()
            return [{"lens": r["k"], "score": _score(r["ga"]) if r["ga"] is not None else None,
                     "contested_rate": round(float(r["contested"]), 2) if r["contested"] is not None else None,
                     "n": r["n"]} for r in rows]

        return {"run_id": run, "by_persona": grp("persona"), "by_location": grp("location")}


def summary(business_id: int) -> dict:
    return {"divergence": divergence(business_id), "lenses": lenses(business_id)}
