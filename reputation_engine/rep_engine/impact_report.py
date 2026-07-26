"""
"Prove it worked" report (Recommendation #1b)
=============================================
The renewal artifact: between two audits, WHAT did we do, and how much did the needle move? Joins
the actions_taken log (work actually completed, in or out of the platform) to the before/after
movement in the metrics that matter -- the Narrative Crowding-Out Score, owned AI-citation share,
average goal-alignment, and the contested frame -- and writes a plain-English summary a client
instantly understands. Correlation, not causal proof (stated honestly), but it is the single most
persuasive renewal story the product can tell.

Run:  python -m rep_engine.impact_report show --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("impact_report")


def _owned_share(conn, business_id: int, run_id: int):
    r = conn.execute("SELECT COALESCE(SUM(share),0) s FROM citation_momentum "
                     "WHERE business_id=%s AND run_id=%s AND classification='owned'",
                     (business_id, run_id)).fetchone()
    return round(float(r["s"]) * 100, 1) if r and r["s"] is not None else None


def _avg_ga(conn, run_id: int):
    r = conn.execute("SELECT AVG(goal_alignment) g FROM answers WHERE run_id=%s "
                     "AND NOT COALESCE(failed,false) AND NOT COALESCE(entity_confusion,false)",
                     (run_id,)).fetchone()
    return round(float(r["g"]), 3) if r and r["g"] is not None else None


def _narr(conn, business_id: int, run_id: int):
    r = conn.execute("SELECT score, contested_pct FROM narrative_scores WHERE business_id=%s AND run_id=%s",
                     (business_id, run_id)).fetchone()
    return (float(r["score"]) if r and r["score"] is not None else None,
            float(r["contested_pct"]) if r and r["contested_pct"] is not None else None)


def _delta(after, before):
    if after is None or before is None:
        return None
    return round(after - before, 1) if isinstance(after, float) else after - before


def build(business_id: int) -> dict:
    """Before/after impact between the two latest completed audits, with the actions done in between."""
    with db() as conn:
        runs = conn.execute(
            "SELECT id, finished_at, to_char(finished_at,'YYYY-MM-DD') d FROM audit_runs "
            "WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 2", (business_id,),
        ).fetchall()
        if len(runs) < 2:
            return {"ready": False, "reason": "Need at least two completed audits to show movement.",
                    "audits": len(runs)}
        cur, prev = runs[0], runs[1]
        # actions completed in the window [prev, cur]
        acts = conn.execute(
            "SELECT capability, area, platform, title, completed_on, source FROM actions_taken "
            "WHERE business_id=%s AND completed_on >= %s::date AND completed_on <= %s::date "
            "ORDER BY completed_on", (business_id, prev["finished_at"], cur["finished_at"]),
        ).fetchall()
        narr_c, cont_c = _narr(conn, business_id, cur["id"])
        narr_p, cont_p = _narr(conn, business_id, prev["id"])
        metrics = {
            "narrative_score": {"before": narr_p, "after": narr_c, "delta": _delta(narr_c, narr_p)},
            "contested_pct": {"before": cont_p, "after": cont_c, "delta": _delta(cont_c, cont_p)},
            "owned_citation_share_pct": {
                "before": _owned_share(conn, business_id, prev["id"]),
                "after": _owned_share(conn, business_id, cur["id"]),
                "delta": _delta(_owned_share(conn, business_id, cur["id"]),
                                _owned_share(conn, business_id, prev["id"]))},
            "avg_goal_alignment": {"before": _avg_ga(conn, prev["id"]), "after": _avg_ga(conn, cur["id"]),
                                   "delta": _delta(_avg_ga(conn, cur["id"]), _avg_ga(conn, prev["id"]))},
        }
    by_area = Counter((a["area"] or "other") for a in acts)
    actions = {"total": len(acts), "by_area": dict(by_area),
               "items": [{"title": a["title"], "area": a["area"], "platform": a["platform"],
                          "capability": a["capability"], "completed_on": str(a["completed_on"]),
                          "source": a["source"]} for a in acts[:50]]}
    return {"ready": True, "window": {"from_run": prev["id"], "to_run": cur["id"],
                                      "from_date": prev["d"], "to_date": cur["d"]},
            "actions": actions, "metrics": metrics, "summary": _summary(actions, metrics)}


def _arrow(delta, good_up=True):
    if delta is None:
        return ""
    up = delta > 0
    better = up if good_up else not up
    return f"{'+' if up else ''}{delta} ({'improved' if better else 'declined'})"


def _summary(actions: dict, metrics: dict) -> str:
    n = actions["total"]
    if n == 0:
        return ("No completed actions were logged between these two audits, so any score movement "
                "can't be attributed to work done in the platform. Mark tasks/content complete as you "
                "do them to build this story.")
    areas = ", ".join(f"{c} {a}" for a, c in sorted(actions["by_area"].items(), key=lambda x: -x[1]))
    ns = metrics["narrative_score"]
    own = metrics["owned_citation_share_pct"]
    bits = [f"You completed {n} action(s) between audits ({areas})."]
    if ns["delta"] is not None:
        bits.append(f"Narrative Crowding-Out Score {ns['before']}->{ns['after']} ({_arrow(ns['delta'])}).")
    if own["delta"] is not None:
        bits.append(f"Owned AI-citation share {own['before']}%->{own['after']}% ({_arrow(own['delta'])}).")
    bits.append("Correlation, not proof -- movement can have several causes -- but this links the work "
                "you shipped to how the needle moved.")
    return " ".join(bits)


def main() -> None:
    ap = argparse.ArgumentParser(description="Prove-it-worked impact report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show"); s.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "show":
        print(json.dumps(build(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
