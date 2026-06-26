"""
Reputation Crowding-Out Engine -- AI answer-change alerts (Wave 4, item 17)
===========================================================================
Diffs the two latest audit runs per (engine, prompt) and surfaces MATERIAL changes in what AI says
about the business: a score drop, a swing to negative sentiment, a newly-contested mention, or a
newly-named competitor. The "we're watching for you" retention signal. Read + alert; emits a
high-signal notification when something gets materially worse.

    python -m rep_engine.answer_changes show --business-id 2
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

_DROP = 0.3  # goal_alignment drop that counts as material


def _two_runs(conn, business_id: int):
    return conn.execute(
        "SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL AND status='complete' "
        "ORDER BY id DESC LIMIT 2", (business_id,)).fetchall()


def _answers(conn, run_id: int) -> dict:
    rows = conn.execute(
        "SELECT engine, prompt, goal_alignment, sentiment, mentions_contested, answer_text "
        "FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)", (run_id,)).fetchall()
    return {(r["engine"], r["prompt"]): dict(r) for r in rows}


def _competitors(conn, business_id: int) -> list[str]:
    try:
        rows = conn.execute("SELECT name FROM competitors WHERE business_id=%s", (business_id,)).fetchall()
        return [r["name"] for r in rows if r.get("name")]
    except Exception:  # noqa: BLE001
        return []


def detect(business_id: int) -> dict:
    """Return material answer changes between the two latest runs."""
    with db() as conn:
        runs = _two_runs(conn, business_id)
        if len(runs) < 2:
            return {"changes": [], "summary": {"compared": False}}
        cur, prev = _answers(conn, runs[0]["id"]), _answers(conn, runs[1]["id"])
        comps = _competitors(conn, business_id)
    changes = []
    for key, c in cur.items():
        p = prev.get(key)
        if not p:
            continue
        engine, prompt = key
        ga_c = c.get("goal_alignment")
        ga_p = p.get("goal_alignment")
        reasons = []
        if ga_c is not None and ga_p is not None and (ga_p - ga_c) >= _DROP:
            reasons.append(f"score dropped {round((ga_p - ga_c) * 50)} pts")
        if c.get("sentiment") == "negative" and p.get("sentiment") != "negative":
            reasons.append("turned negative")
        if c.get("mentions_contested") and not p.get("mentions_contested"):
            reasons.append("a concern/complaint now appears")
        # newly-named competitor in the answer text
        ct = (c.get("answer_text") or "")
        pt = (p.get("answer_text") or "")
        for comp in comps:
            if comp and re.search(re.escape(comp), ct, re.I) and not re.search(re.escape(comp), pt, re.I):
                reasons.append(f"now names competitor “{comp}”")
                break
        if reasons:
            changes.append({"engine": engine, "prompt": prompt, "reasons": reasons,
                            "before": {"goal_alignment": ga_p, "sentiment": p.get("sentiment")},
                            "after": {"goal_alignment": ga_c, "sentiment": c.get("sentiment")}})
    changes.sort(key=lambda x: len(x["reasons"]), reverse=True)
    return {"changes": changes[:25], "summary": {"compared": True, "changed": len(changes)}}


def check_and_alert(business_id: int) -> dict:
    """Detect changes + emit a notification if anything got materially worse (for the alert job)."""
    out = detect(business_id)
    n = out["summary"].get("changed", 0)
    if n:
        try:
            from .notifications import notify
            top = out["changes"][0]
            notify(business_id, "answer_changed",
                   f"AI changed what it says about you ({n} answer{'s' if n != 1 else ''})",
                   f"e.g. for “{top['prompt']}” — {', '.join(top['reasons'])}. Review and respond.",
                   severity="high", dedup_key=f"answer-change:{business_id}:{n}")
        except Exception:  # noqa: BLE001
            pass
    return out


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="AI answer-change detection")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show"); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    print(json.dumps(detect(args.business_id), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
