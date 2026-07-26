"""
Strategy Advisor -- the Plan-Do-Check-Act closed loop (the "consultant in the app")
==================================================================================
Everything else in the engine produces a PIECE of the picture -- the gap model (PLAN: where we're
losing + the goal), the strategy work orders + content batches (DO: what we produced), content_impact
(CHECK: did a batch move its gap), and the GA/GSC/PageSpeed/keyword layers (the real-world outcome
data). This module SYNTHESIZES them into one advisor view that answers the questions an owner
actually asks:

    "Is the strategy working? How is the content performing? At this pace, will we hit the goal --
     and if not, exactly what (and how much) content do we still need to produce?"

It is deterministic at the core (velocity, % gap closed, pieces-still-needed, projected ETA are
computed from real content_impact + audit rows, not guessed) with an optional LLM narrative layer on
top that reads the same computed numbers and writes the plain-English recommendation. Every read is
fail-safe: a missing signal degrades the advice, it never raises. Nothing here writes content or
publishes -- it advises; the human acts.

PDCA mapping:
  PLAN  -> the goal + the gaps that stand between the business and it (gap_models)
  DO    -> content produced per gap (content_batches -> drafts/assets, published state)
  CHECK -> measured movement (content_impact) + traffic/rank/technical outcomes (GA/GSC/PageSpeed)
  ACT   -> per-gap verdict + impact prediction + the specific next content to produce (fed back to plan)

Run:  python -m rep_engine.strategy_advisor advise --business-id 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("strategy_advisor")

# The goal_alignment level that counts as "goal reached" (shared with content_impact so the advisor's
# % and the per-batch % agree). -1..1; default 0.5. Env-configurable, never hard-coded.
_TARGET_ALIGNMENT = max(-1.0, min(1.0, float(os.getenv("CONTENT_IMPACT_TARGET_ALIGNMENT", "0.5"))))
# Below this weekly velocity (fraction of the gap closed per week) a worked gap is "stalled".
_STALL_VELOCITY = float(os.getenv("ADVISOR_STALL_VELOCITY", "0.02"))
# Diminishing-returns damping: each additional piece is assumed ~15% less effective than observed
# average, so the pieces-needed estimate isn't naively linear.
_DIMINISH = float(os.getenv("ADVISOR_DIMINISH", "0.85"))
# Cap on recommended additional pieces per gap (a sanity backstop for the estimator).
_MAX_PIECES = int(os.getenv("ADVISOR_MAX_PIECES_PER_GAP", "8"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _weeks_since(dt) -> float:
    if not dt:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (_now() - dt).total_seconds() / (7 * 86400))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# PLAN -- goal + current standing
# ---------------------------------------------------------------------------
def _target_alignment_for(biz: dict) -> float:
    """The goal_alignment 'goal reached' bar for this business, profile-aware (nonprofit 0.6 vs generic
    0.5). Fall back to the env/module default. Matches content_impact._target_alignment so the advisor
    % and the per-batch % agree (both derive from the same StrategyProfile). Fail-safe -> default."""
    try:
        from . import business_profile as _bp
        v = _bp.derive(biz or {}).get("target_alignment")
        if v is not None:
            return max(-1.0, min(1.0, float(v)))
    except Exception:  # noqa: BLE001
        pass
    return _TARGET_ALIGNMENT


def _goal_state(business_id: int) -> dict:
    with db() as conn:
        biz = conn.execute("SELECT name, goal, domain, industry, geo, regulatory_profile, contested_terms "
                           "FROM businesses WHERE id=%s", (business_id,)).fetchone()
        gm = conn.execute("SELECT model, run_id, created_at FROM gap_models WHERE business_id=%s "
                          "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND status='complete' AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
        cur_align = None
        if run:
            r = conn.execute("SELECT AVG(goal_alignment) a FROM answers WHERE run_id=%s AND "
                             "goal_alignment IS NOT NULL AND NOT COALESCE(failed,false) "
                             "AND NOT COALESCE(entity_confusion,false)", (run["id"],)).fetchone()
            cur_align = _f(r["a"]) if r else None
    model = {}
    if gm:
        model = gm["model"] if isinstance(gm["model"], dict) else json.loads(gm["model"] or "{}")
    target = _target_alignment_for(dict(biz) if biz else {})
    remaining = None
    if cur_align is not None:
        remaining = max(0.0, target - cur_align)
    return {
        "goal": (biz["goal"] if biz else "") or "",
        "business": biz["name"] if biz else "",
        "current_alignment": round(cur_align, 4) if cur_align is not None else None,
        "target_alignment": target,
        "gap_to_goal": round(remaining, 4) if remaining is not None else None,
        "summary": model.get("summary", ""),
        "has_gap_model": bool(model),
        "gap_model_age_days": round(_weeks_since(gm["created_at"]) * 7, 1) if gm else None,
    }


# ---------------------------------------------------------------------------
# DO + CHECK -- content produced per gap and how far it moved the gap
# ---------------------------------------------------------------------------
def _gap_progress(business_id: int) -> list[dict]:
    with db() as conn:
        batches = conn.execute(
            "SELECT id, gap_key, gap_source, label, target_topic, content_types, baseline, status, created_at "
            "FROM content_batches WHERE business_id=%s ORDER BY id DESC", (business_id,)).fetchall()
        out = []
        for b in batches:
            # pieces produced + published for this gap
            drafts = conn.execute(
                "SELECT d.status, (a.published_status='live') AS live FROM content_drafts d "
                "LEFT JOIN assets a ON a.id=d.published_asset_id WHERE d.batch_id=%s", (b["id"],)).fetchall()
            pieces = len(drafts)
            approved = sum(1 for d in drafts if d["status"] == "approved")
            published = sum(1 for d in drafts if d["live"])
            # latest measured impact for this batch
            imp = conn.execute(
                "SELECT gap_pct_closed, alignment_delta, sov_delta, measured_at, notes, run_after "
                "FROM content_impact WHERE batch_id=%s ORDER BY id DESC LIMIT 1", (b["id"],)).fetchone()
            base = b["baseline"] if isinstance(b["baseline"], dict) else json.loads(b["baseline"] or "{}")
            ctypes = b["content_types"] if isinstance(b["content_types"], list) else json.loads(b["content_types"] or "[]")

            gp = _f(imp["gap_pct_closed"]) if imp else None
            weeks = _weeks_since(b["created_at"])
            velocity = (gp / weeks) if (gp is not None and weeks > 0.5) else None
            adl = _f(imp["alignment_delta"]) if imp else None

            # status verdict
            if published == 0:
                status = "not_published"
            elif imp is None:
                status = "awaiting_measurement"
            elif adl is not None and adl < -0.02:
                status = "regressing"
            elif gp is not None and gp >= 0.75:
                status = "gap_closing"
            elif velocity is not None and velocity < _STALL_VELOCITY:
                status = "stalled"
            else:
                status = "on_track"

            out.append({
                "batch_id": b["id"], "gap_key": b["gap_key"], "gap_source": b["gap_source"],
                "topic": b["target_topic"] or b["label"] or b["gap_key"],
                "content_types": ctypes, "pieces": pieces, "approved": approved, "published": published,
                "batch_status": b["status"], "weeks_live": round(weeks, 1),
                "gap_pct_closed": round(gp, 4) if gp is not None else None,
                "alignment_delta": round(adl, 4) if adl is not None else None,
                "velocity_per_week": round(velocity, 4) if velocity is not None else None,
                "status": status,
                "measured_at": imp["measured_at"].isoformat() if imp and imp["measured_at"] else None,
            })
    return out


def _predict_gap(g: dict) -> dict:
    """From observed pieces_published + % gap closed, estimate additional pieces to close the gap and
    an ETA. Damped for diminishing returns; deterministic and clearly-bounded."""
    published, gp = g["published"], g["gap_pct_closed"]
    pred = {"pieces_needed": None, "eta_weeks": None, "confidence": "low", "basis": ""}
    if published <= 0:
        pred["basis"] = "nothing published yet — publish the drafted pieces to start moving the gap"
        return pred
    if gp is None:
        pred["basis"] = "published but not yet measured — the next full audit will size the impact"
        return pred
    remaining = max(0.0, 1.0 - gp)
    if remaining <= 0.05:
        pred.update(pieces_needed=0, eta_weeks=0, confidence="high",
                    basis="gap effectively closed — hold and monitor")
        return pred
    close_per_piece = gp / published if published else 0.0
    if close_per_piece <= 0.001:
        # published but no movement -> the current content isn't working; recommend a change, not "more of the same"
        pred.update(pieces_needed=_MAX_PIECES, eta_weeks=None, confidence="low",
                    basis="published content hasn't moved the gap — change the approach (stronger "
                          "citations / entity clarity / a different content type), don't just add more")
        return pred
    # damped geometric sum: each extra piece ~_DIMINISH as effective as the last
    need, closed_extra, eff = 0, 0.0, close_per_piece
    while closed_extra < remaining and need < _MAX_PIECES:
        closed_extra += eff
        eff *= _DIMINISH
        need += 1
    rate = g["velocity_per_week"]
    eta = None
    if g["weeks_live"] and published:
        pieces_per_week = published / max(0.5, g["weeks_live"])
        if pieces_per_week > 0:
            eta = round(need / pieces_per_week, 1)
    pred.update(pieces_needed=need, eta_weeks=eta,
                confidence="medium" if published >= 2 else "low",
                basis=f"{published} live piece(s) closed {round(gp*100)}% of this gap "
                      f"(~{round(close_per_piece*100)}%/piece); ~{need} more should close it")
    return pred


# ---------------------------------------------------------------------------
# CHECK -- real-world outcome signals
# ---------------------------------------------------------------------------
def _signals(business_id: int) -> dict:
    sig: dict = {}
    try:
        from . import ga_data as _ga
        sig["ga"] = _ga.latest(business_id)
    except Exception as e:  # noqa: BLE001
        log.debug("advisor GA signal off: %s", e)
    try:
        from . import gsc_data as _g
        sig["gsc"] = _g.latest(business_id)
    except Exception as e:  # noqa: BLE001
        log.debug("advisor GSC signal off: %s", e)
    try:
        from . import pagespeed as _ps
        sig["pagespeed"] = _ps.latest(business_id)
        sig["technical_issues"] = _ps.technical_gaps(business_id)
    except Exception as e:  # noqa: BLE001
        log.debug("advisor PageSpeed signal off: %s", e)
    try:
        from . import gsc_inspect as _gi
        sig["index_health"] = _gi.latest(business_id)
        sig["index_issues"] = _gi.technical_gaps(business_id)
    except Exception as e:  # noqa: BLE001
        log.debug("advisor GSC-inspection signal off: %s", e)
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT keyword, search_volume, keyword_difficulty FROM target_keywords "
                "WHERE business_id=%s AND search_volume IS NOT NULL ORDER BY search_volume DESC "
                "NULLS LAST LIMIT 10", (business_id,)).fetchall()
        sig["keyword_demand"] = [{"keyword": r["keyword"], "search_volume": r["search_volume"],
                                  "difficulty": r["keyword_difficulty"]} for r in rows]
    except Exception as e:  # noqa: BLE001
        log.debug("advisor keyword-demand off: %s", e)
    return sig


# ---------------------------------------------------------------------------
# ACT -- deterministic recommendations (LLM narrative layered on top, optional)
# ---------------------------------------------------------------------------
def _recommendations(goal: dict, gaps: list[dict], signals: dict) -> list[dict]:
    recs: list[dict] = []
    for g in gaps:
        pred = g.get("prediction") or {}
        if g["status"] == "not_published" and g["approved"] > 0:
            recs.append({"priority": 1, "action": "publish", "gap": g["topic"],
                         "detail": f"{g['approved']} approved piece(s) not live — publish to start closing this gap.",
                         "expected_impact": "unlocks measurement + ranking of already-produced content"})
        elif g["status"] == "regressing":
            recs.append({"priority": 1, "action": "revise", "gap": g["topic"],
                         "detail": "AI answers for this gap got WORSE since publishing — strengthen citations + "
                                   "entity disambiguation before producing more.",
                         "expected_impact": "stops the regression; protects share of voice"})
        elif g["status"] in ("stalled",) and pred.get("pieces_needed"):
            recs.append({"priority": 2, "action": "change_approach", "gap": g["topic"],
                         "detail": pred.get("basis", ""),
                         "expected_impact": "re-starts gap movement that current content isn't achieving"})
        elif g["status"] == "on_track" and pred.get("pieces_needed"):
            ct = (g["content_types"] or ["article"])
            recs.append({"priority": 3, "action": "produce_more", "gap": g["topic"],
                         "detail": f"On track — produce ~{pred['pieces_needed']} more ({', '.join(ct[:3])}) to "
                                   f"close the remaining gap"
                                   + (f"; ~{pred['eta_weeks']} wks at current pace." if pred.get("eta_weeks") else "."),
                         "expected_impact": f"~{round((g.get('gap_pct_closed') or 0)*100)}%→100% gap closed"})
    # technical fixes (PageSpeed) — non-content actions that unblock ranking
    for t in (signals.get("technical_issues") or [])[:5]:
        recs.append({"priority": 2, "action": "technical_fix", "gap": t.get("url"),
                     "detail": "Fix page technical health: " + "; ".join(t.get("issues") or []),
                     "expected_impact": "removes a ranking/AI-citation suppressor on an owned page"})
    # index / canonical / schema fixes (GSC URL Inspection) — highest-leverage: an owned page Google
    # won't index or has canonical-swapped can't crowd out anything until it's fixed.
    for t in (signals.get("index_issues") or [])[:5]:
        recs.append({"priority": 1, "action": "index_fix", "gap": t.get("url"),
                     "detail": "Fix indexing/canonical/schema: " + "; ".join(t.get("issues") or []),
                     "expected_impact": "gets an owned page indexed + canonically preferred so it can rank"})
    # high-demand keywords with no worked gap (opportunity)
    covered = " ".join((g["topic"] or "").lower() for g in gaps)
    for k in (signals.get("keyword_demand") or [])[:5]:
        kw = (k.get("keyword") or "").lower()
        if kw and kw.split()[0] not in covered and (k.get("search_volume") or 0) >= 100:
            recs.append({"priority": 3, "action": "new_content", "gap": k.get("keyword"),
                         "detail": f"High demand ({k.get('search_volume')} searches/mo) with no owned content — "
                                   f"produce a piece targeting '{k.get('keyword')}'.",
                         "expected_impact": "captures existing search demand you're not yet visible for"})
    recs.sort(key=lambda r: r["priority"])
    return recs[:12]


def _pdca_status(goal: dict, gaps: list[dict]) -> str:
    measured = [g for g in gaps if g["gap_pct_closed"] is not None]
    if not gaps or not any(g["published"] for g in gaps):
        return "insufficient_data"
    if not measured:
        return "awaiting_measurement"
    if any(g["status"] == "regressing" for g in measured):
        return "needs_action"
    stalled = sum(1 for g in measured if g["status"] == "stalled")
    if stalled and stalled >= len(measured) / 2:
        return "stalled"
    if all(g["status"] in ("gap_closing", "on_track") for g in measured):
        return "on_track"
    return "needs_action"


def _overall(goal: dict, gaps: list[dict]) -> dict:
    measured = [g for g in gaps if g["gap_pct_closed"] is not None]
    avg_closed = (sum(g["gap_pct_closed"] for g in measured) / len(measured)) if measured else None
    vels = [g["velocity_per_week"] for g in measured if g["velocity_per_week"] is not None]
    avg_vel = (sum(vels) / len(vels)) if vels else None
    # weeks to close the average remaining gap at current velocity
    eta = None
    if avg_closed is not None and avg_vel and avg_vel > 0:
        eta = round((1.0 - avg_closed) / avg_vel, 1)
    total_needed = sum((g.get("prediction") or {}).get("pieces_needed") or 0 for g in gaps)
    return {
        "gaps_worked": len(gaps),
        "gaps_measured": len(measured),
        "avg_gap_closed": round(avg_closed, 4) if avg_closed is not None else None,
        "avg_velocity_per_week": round(avg_vel, 4) if avg_vel is not None else None,
        "projected_weeks_to_goal": eta,
        "total_pieces_recommended": total_needed,
        "published_pieces": sum(g["published"] for g in gaps),
    }


def _narrative(business_id: int, goal: dict, overall: dict, gaps: list[dict],
               recs: list[dict], signals: dict) -> str:
    """Optional LLM plain-English advisor summary over the computed numbers. Dormant-safe: returns a
    deterministic fallback sentence if the LLM path is unavailable or fails."""
    fallback = _fallback_narrative(goal, overall, recs)
    try:
        from .ai_state_audit import NO_NEGATIVE_DISAMBIGUATION_POLICY, orchestrator_json
        from . import business_profile as _bp
    except Exception:  # noqa: BLE001
        return fallback
    payload = json.dumps({"goal": goal, "overall": overall,
                          "gaps": [{k: g[k] for k in ("topic", "status", "gap_pct_closed",
                                                       "velocity_per_week", "published", "prediction")}
                                   for g in gaps[:12]],
                          "recommended_actions": recs[:8],
                          "signals": {"ga": signals.get("ga"), "gsc": signals.get("gsc"),
                                      "pagespeed": (signals.get("pagespeed") or {}).get("avg_performance")}},
                         default=str)
    system = (
        "You are a reputation-strategy advisor. Given the goal, the measured progress, per-gap status, "
        "and recommended actions (all pre-computed from real data), write a concise, decisive briefing "
        "(120-180 words) for the business owner: open with 1-2 sentences on whether we're winning + "
        "what's working/stalled (reference the ACTUAL numbers), THEN a markdown numbered list titled "
        "'**Highest-leverage moves next:**' with the 2-3 top moves — put each move on its OWN line "
        "starting with '1.' / '2.' / '3.' (real newlines '\\n' between items, not one run-on sentence). "
        "No hype, no guarantees, no invented facts. Return ONE JSON object: {\"briefing\": \"...\"}."
        # Business-agnostic license/sensitive-ID ban ('' for a generic tenant, finance policy for a
        # regulated-finance tenant). Fail-safe -> '' on any lookup error.
        + _bp.license_policy_for_business(business_id) + NO_NEGATIVE_DISAMBIGUATION_POLICY)
    try:
        out = orchestrator_json(system, payload, tier="cheap", max_tokens=700, timeout=90,
                                bill={"business_id": business_id, "operation": "advisor"})
        if isinstance(out, dict) and out.get("briefing"):
            return str(out["briefing"]).strip()
    except Exception as e:  # noqa: BLE001
        log.debug("advisor narrative LLM unavailable: %s", e)
    return fallback


def _fallback_narrative(goal: dict, overall: dict, recs: list[dict]) -> str:
    parts = []
    if overall.get("avg_gap_closed") is not None:
        parts.append(f"Across {overall['gaps_measured']} measured gap(s), an average of "
                     f"{round(overall['avg_gap_closed']*100)}% of the gap is closed.")
    if overall.get("projected_weeks_to_goal"):
        parts.append(f"At the current pace, ~{overall['projected_weeks_to_goal']} weeks to the goal.")
    elif overall.get("published_pieces", 0) == 0:
        parts.append("No content is live yet — publish the drafted pieces to start moving the goal.")
    if recs:
        parts.append("Top move: " + recs[0]["detail"])
    return " ".join(parts) or "Not enough measured data yet — run an audit after publishing to measure impact."


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------
def advise(business_id: int, *, with_narrative: bool = True) -> dict:
    """The full PDCA advisor view. Deterministic core + optional LLM briefing. Never raises."""
    goal = _goal_state(business_id)
    gaps = _gap_progress(business_id)
    for g in gaps:
        g["prediction"] = _predict_gap(g)
    signals = _signals(business_id)
    recs = _recommendations(goal, gaps, signals)
    overall = _overall(goal, gaps)
    status = _pdca_status(goal, gaps)
    narrative = _narrative(business_id, goal, overall, gaps, recs, signals) if with_narrative else \
        _fallback_narrative(goal, overall, recs)
    return {
        "business_id": business_id,
        "pdca_status": status,
        "goal": goal,
        "overall": overall,
        "gaps": gaps,
        "recommended_actions": recs,
        "signals": signals,
        "briefing": narrative,
        "generated_at": _now().isoformat(),
    }


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="Strategy advisor (PDCA loop)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("advise"); a.add_argument("--business-id", type=int, required=True)
    a.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    print(json.dumps(advise(args.business_id, with_narrative=not args.no_llm), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
