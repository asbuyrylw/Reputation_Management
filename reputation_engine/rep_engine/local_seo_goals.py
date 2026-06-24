"""Local-SEO goal + timeline.

A first-class "get to page 1 of Google" goal that mirrors the AI-reputation timeline
(timeline_estimator) but for LOCAL search rankings. Reads the local_rankings history and
projects when the business will rank on page one for most of its category-local searches
("financial advisor in Cincinnati", "... near me"). Gracefully returns a no-data state until a
local-rank check has run (those need a SERP key).
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

# Target: share of category-local searches where the business is on Google's first page.
LOCAL_SEO_TARGET = float(os.getenv("LOCAL_SEO_TARGET", "0.8"))
# Baseline monthly gain in page-one rate before we have this business's own measured velocity.
_BASE_MONTHLY_GAIN = float(os.getenv("LOCAL_SEO_BASE_GAIN", "0.06"))

_DISCLAIMER = (
    "This is a PROJECTION, not a guarantee. It estimates when you'll rank on Google's first "
    "page for most of your local category searches. Confidence is low until your own measured "
    "rank movement accumulates across local-rank checks, and Google/competitor activity can "
    "shift the timeline."
)


def _page_one_rate_by_run(conn, business_id: int) -> list[tuple]:
    """page-one rate for the subject per local-rank run, oldest first (for velocity)."""
    rows = conn.execute(
        "SELECT run_id, MIN(created_at) AS ts, "
        "AVG(CASE WHEN on_page_one THEN 1.0 ELSE 0.0 END) AS rate "
        "FROM local_rankings WHERE business_id=%s AND is_subject "
        "GROUP BY run_id ORDER BY MIN(created_at)",
        (business_id,),
    ).fetchall()
    return [(r["run_id"], r["ts"], float(r["rate"])) for r in rows if r["rate"] is not None]


def estimate(business_id: int, quiet: bool = False, persist: bool = False) -> dict:
    """Project the time to reach the page-one target. persist=True stores a local_seo_goals row
    (use from a job, never from a GET request)."""
    try:
        from . import local_seo as _ls
    except ImportError:  # pragma: no cover
        import local_seo as _ls  # type: ignore
    latest = _ls.latest(business_id) or {}
    summ = latest.get("summary") or {}
    cur = summ.get("page_one_rate")
    target = LOCAL_SEO_TARGET
    target_searches = [q.get("query") for q in (latest.get("queries") or []) if q.get("query")][:8]

    if cur is None:
        result = {
            "business": latest.get("business"),
            "current_page_one_rate": None,
            "target_page_one_rate": target,
            "no_data": True,
            "target_searches": target_searches,
            "note": "Run a local-rank check (needs a SERP key) to start this projection.",
            "disclaimer": _DISCLAIMER,
        }
        if not quiet:
            print(json.dumps(result, indent=2, default=str))
        return result

    with db() as conn:
        history = _page_one_rate_by_run(conn, business_id)

    monthly_gain: Optional[float] = None
    basis, confidence = "", "low"
    if len(history) >= 2:
        _, t0, v0 = history[0]
        _, t1, v1 = history[-1]
        months = max(0.25, (t1 - t0).days / 30.0)
        delta = v1 - v0
        if delta > 0:
            monthly_gain = delta / months
            basis = "observed velocity (this business)"
            confidence = "high" if len(history) >= 4 else "medium"
    if not monthly_gain or monthly_gain <= 0:
        monthly_gain = _BASE_MONTHLY_GAIN
        basis = "baseline model (no measured local velocity yet)"
        confidence = "low"

    remaining = max(0.0, target - cur)
    expected_months = 0.0 if remaining <= 0 else remaining / monthly_gain
    today = date.today()

    def win(months: float) -> dict:
        weeks = round(months * 4.345)
        return {"months": round(months, 1), "weeks": weeks,
                "target_date": (today + timedelta(weeks=weeks)).isoformat()}

    result = {
        "business": latest.get("business"),
        "current_page_one_rate": round(cur, 3),
        "target_page_one_rate": target,
        "remaining_gap": round(remaining, 3),
        "avg_organic_rank": summ.get("avg_organic_rank"),
        "monthly_gain_estimate": round(monthly_gain, 4),
        "gain_basis": basis,
        "confidence": confidence,
        "target_searches": target_searches,
        "projection": {
            "optimistic": win(expected_months * 0.65),
            "expected": win(expected_months),
            "conservative": win(expected_months * 1.75),
        },
        "disclaimer": _DISCLAIMER,
    }
    if remaining <= 0:
        result["status"] = "Already on page 1 for most local searches -- focus on holding the position."

    if persist:
        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO local_seo_goals (business_id, run_id, goal) VALUES (%s,%s,%s)",
                    (business_id, latest.get("run_id"), json.dumps(result, default=str)),
                )
                conn.commit()
        except Exception:  # noqa: BLE001 -- persistence is best-effort
            pass

    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result
