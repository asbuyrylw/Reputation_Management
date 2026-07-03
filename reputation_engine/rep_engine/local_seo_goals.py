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
# Cap the cold-start estimate so the projected date stays believable (never multi-year on the hero).
LOCAL_SEO_MONTHS_CAP = float(os.getenv("LOCAL_SEO_MONTHS_CAP", "18"))
# Last-resort monthly gain if EVERY grounded signal is unavailable (kept for backward compat). The
# normal cold-start path now uses the grounded _coldstart_months() model instead of this flat guess.
_BASE_MONTHLY_GAIN = float(os.getenv("LOCAL_SEO_BASE_GAIN", "0.06"))

# gain_basis emitted only when EVERY grounded cold-start signal was unavailable (the legacy flat
# guess). A stored goal carrying this basis predates the grounded cold-start model and is stale --
# the read-path uses it to self-heal (recompute + re-persist) on the next read.
LEGACY_GAIN_BASIS = "baseline model (no measured local velocity yet)"

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


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _coldstart_months(business_id: int, summ: dict, cur: float, target: float) -> tuple[float, str]:
    """Research-grounded time-to-page-1 (in months) for when we have NO measured local velocity yet
    -- so the first estimate is defensible, not a flat guess.

    Anchored to published local-SEO ranking timelines: local-pack visibility ~2-4mo, organic map
    ~4-6mo, new/cold or competitive 6-12+mo (Ahrefs 2025: <2% of new pages reach the top 10 within a
    year). We start from DISTANCE-to-page-1 (current average rank), then adjust for keyword DIFFICULTY
    and Google Business Profile STRENGTH (GBP + reviews are the primary/fastest local levers). Every
    signal is optional and None-safe -- a missing one is neutral, never an error.
    """
    avg_rank = summ.get("avg_organic_rank")
    # 1) distance -> base months (whole-journey anchor from the current position)
    if avg_rank is not None:
        ar = float(avg_rank)
        base = 3.0 if ar <= 12 else 5.0 if ar <= 20 else 8.0 if ar <= 30 else 11.0
    else:
        # nothing ranks yet -> lean on how much of page 1 is already won
        base = 4.0 if cur >= 0.5 else 6.0 if cur >= 0.25 else 8.0 if cur > 0 else 11.0
    # shorten as current progress approaches the target
    base *= _clamp((target - cur) / target, 0.15, 1.0) if target > 0 else 1.0

    # 2) keyword-difficulty multiplier (0-100 competition index -> 0.75x easy .. 1.65x hard)
    kd = None
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT AVG(keyword_difficulty) AS kd FROM target_keywords "
                "WHERE business_id=%s AND keyword_difficulty IS NOT NULL", (business_id,)).fetchone()
        kd = float(row["kd"]) if row and row["kd"] is not None else None
    except Exception:  # noqa: BLE001 -- difficulty is optional
        kd = None
    difficulty_mult = 1.0 if kd is None else _clamp(0.75 + (kd / 100.0) * 0.9, 0.75, 1.65)
    # Be honest when there's no metrics provider: a null difficulty means UNMEASURED, not "easy".
    # We still apply a neutral 1.0x, but say so plainly instead of implying we measured it.
    difficulty_txt = ("keyword difficulty (not available)" if kd is None
                      else f"keyword difficulty (×{difficulty_mult:.2f})")

    # 3) Google Business Profile strength (the primary local ranking factor; complete + reviewed = faster)
    gbp_mult = 1.0
    try:
        try:
            from . import gbp_reviews as _gbp
        except ImportError:  # pragma: no cover
            import gbp_reviews as _gbp  # type: ignore
        curr = (_gbp.latest(business_id) or {}).get("current")
        if not curr:
            gbp_mult = 1.2                      # no GBP found -> slower
        else:
            rc = int(curr.get("review_count") or 0)
            rt = float(curr.get("rating") or 0)
            if rc >= 10 and rt >= 4.0:
                gbp_mult = 0.80                 # credible, active profile -> faster
            elif rc < 5 or rt < 3.5:
                gbp_mult = 1.10                 # thin/weak profile
    except Exception:  # noqa: BLE001 -- GBP is optional
        gbp_mult = 1.0
    gbp_mult = _clamp(gbp_mult, 0.7, 1.3)

    months = _clamp(base * difficulty_mult * gbp_mult, 1.0, LOCAL_SEO_MONTHS_CAP)
    rank_txt = f"~#{round(float(avg_rank))}" if avg_rank is not None else "not yet ranking"
    basis = (f"your current local rank ({rank_txt}), {difficulty_txt} "
             f"and Google Business Profile strength (×{gbp_mult:.2f}), anchored to typical local-SEO "
             f"ranking timelines")
    return months, basis


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

    remaining = max(0.0, target - cur)

    monthly_gain: Optional[float] = None
    basis, confidence = "", "low"
    if len(history) >= 2:
        _, t0, v0 = history[0]
        _, t1, v1 = history[-1]
        months = max(0.25, (t1 - t0).days / 30.0)
        delta = v1 - v0
        if delta > 0:
            monthly_gain = delta / months
            basis = "measured from your own local-rank movement"
            confidence = "high" if len(history) >= 4 else "medium"
    if not monthly_gain or monthly_gain <= 0:
        # No measured velocity yet -> a research-grounded estimate from current position + keyword
        # difficulty + Google Business Profile strength (not a flat guess). Back-solve the monthly
        # gain the projection math below expects so all downstream windows stay consistent.
        try:
            cs_months, basis = _coldstart_months(business_id, summ, cur, target)
            monthly_gain = max(remaining / cs_months, 1e-4) if remaining > 0 else _BASE_MONTHLY_GAIN
        except Exception:  # noqa: BLE001 -- never let optional-signal reads break the projection
            monthly_gain = _BASE_MONTHLY_GAIN
            basis = LEGACY_GAIN_BASIS
        confidence = "low"

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
