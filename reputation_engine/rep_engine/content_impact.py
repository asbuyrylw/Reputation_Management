"""
Content impact measurement (content-program Phase 4 — the wedge)
================================================================
Closes the loop no standalone writing tool closes: for each gap-driven content batch, measure how
far it moved the gap it was built to fix. We snapshot the gap's Share-of-Voice + goal-alignment at
batch creation (the baseline), then after a LATER audit re-measure the same prompt cluster and
report the delta and the % of the gap closed toward the goal — collectively, with the per-type
published state so the reader sees what was actually live. That measured lift both proves ROI and
feeds the "keep producing / adjust" decision.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

try:
    from .db import db
    from . import content_batch as _cb
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import content_batch as _cb  # type: ignore

log = logging.getLogger("content_impact")

# Below this fraction of the gap closed, a published batch that didn't move the number gets an
# "adjust: produce more / different content" recommendation (the closed-loop signal).
_LOW_MOVEMENT = 0.15


def _target_alignment(biz: dict) -> float:
    """The alignment level that counts as 'goal reached' for % gap closed. Uses the dominance target
    if present, else a sensible net-positive default."""
    try:
        dt = (biz or {}).get("dominance_target")
        if dt is not None:
            return max(-1.0, min(1.0, float(dt)))
    except Exception:  # noqa: BLE001
        pass
    return 0.4  # net-positive alignment


def _clamp01(x) -> Optional[float]:
    if x is None:
        return None
    return round(max(0.0, min(1.0, float(x))), 4)


def measure_batch(business_id: int, batch_id: int) -> dict:
    """Measure one batch against the latest full audit newer than its baseline. Returns the impact
    record, or {pending: reason} when there's nothing new to measure against yet."""
    with db() as conn:
        b = conn.execute("SELECT * FROM content_batches WHERE id=%s AND business_id=%s",
                         (batch_id, business_id)).fetchone()
        if not b:
            return {"pending": True, "reason": "batch not found"}
        baseline = b["baseline"] if isinstance(b["baseline"], dict) else json.loads(b["baseline"] or "{}")
        prompts = b["target_prompts"] if isinstance(b["target_prompts"], list) else json.loads(b["target_prompts"] or "[]")
        base_run = baseline.get("run_id")
        # the newest COMPLETE full audit strictly after the baseline run
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND status='complete' AND COALESCE(mode,'full')<>'fast' AND id > %s ORDER BY id DESC LIMIT 1",
            (business_id, base_run or 0)).fetchone()
        if not run:
            return {"pending": True, "reason": "no audit newer than the batch baseline yet",
                    "baseline_run": base_run}
        # idempotent: don't re-insert a measurement for a run we've already measured this batch against
        dup = conn.execute("SELECT id FROM content_impact WHERE batch_id=%s AND run_after=%s LIMIT 1",
                           (batch_id, run["id"])).fetchone()
        if dup:
            return {"already_measured": True, "batch_id": batch_id, "run_after": run["id"], "impact_id": dup["id"]}
        measured = _cb._cluster_metrics(conn, business_id, run["id"], prompts)
        biz = dict(conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone())
        # per-type published state (was the piece actually live to have any effect?)
        rows = conn.execute(
            "SELECT d.content_type, d.status, a.published_status "
            "FROM content_drafts d LEFT JOIN assets a ON a.id = d.published_asset_id "
            "WHERE d.batch_id=%s", (batch_id,)).fetchall()

    per_type: dict = {}
    for r in rows:
        ct = r["content_type"] or "unknown"
        t = per_type.setdefault(ct, {"pieces": 0, "approved": 0, "published": 0})
        t["pieces"] += 1
        if r["status"] == "approved":
            t["approved"] += 1
        if (r["published_status"] or "") == "live":
            t["published"] += 1
    published_total = sum(t["published"] for t in per_type.values())

    base_sov, meas_sov = baseline.get("sov"), measured.get("sov")
    base_al, meas_al = baseline.get("alignment"), measured.get("alignment")
    sov_delta = (meas_sov - base_sov) if (base_sov is not None and meas_sov is not None) else None
    al_delta = (meas_al - base_al) if (base_al is not None and meas_al is not None) else None
    # % of the gap closed, measured on goal-alignment toward the target (the score the client cares about)
    tgt = _target_alignment(biz)
    gap_pct = None
    if base_al is not None and meas_al is not None:
        denom = tgt - base_al
        gap_pct = _clamp01((meas_al - base_al) / denom) if denom > 0.02 else (1.0 if meas_al >= tgt else 0.0)

    # the adjust signal
    if published_total == 0:
        rec = "Not measurable yet — approve & publish the batch, then the next audit will show its lift."
    elif gap_pct is not None and gap_pct < _LOW_MOVEMENT:
        rec = "Published but the gap barely moved — produce more/different content for this gap or strengthen citations/entity clarity."
    elif gap_pct is not None and gap_pct >= 0.75:
        rec = "Gap largely closed — hold and monitor; redeploy effort to the next gap."
    else:
        rec = "Moving in the right direction — keep producing for this gap and re-measure next audit."

    with db() as conn:
        rowid = conn.execute(
            "INSERT INTO content_impact (business_id, batch_id, run_before, run_after, baseline_sov, "
            "measured_sov, sov_delta, baseline_alignment, measured_alignment, alignment_delta, "
            "gap_pct_closed, per_type, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (business_id, batch_id, base_run, run["id"], base_sov, meas_sov, sov_delta,
             base_al, meas_al, al_delta, gap_pct, json.dumps(per_type), rec)).fetchone()
        conn.execute("UPDATE content_batches SET status='measured', updated_at=now() WHERE id=%s",
                     (batch_id,))
        conn.commit()
    log.info("batch %d impact: SoV %s->%s (Δ%s), align Δ%s, %% gap closed %s (%d live pieces)",
             batch_id, base_sov, meas_sov, sov_delta, al_delta, gap_pct, published_total)
    return {"impact_id": rowid["id"], "batch_id": batch_id, "run_before": base_run, "run_after": run["id"],
            "baseline_sov": base_sov, "measured_sov": meas_sov, "sov_delta": sov_delta,
            "baseline_alignment": base_al, "measured_alignment": meas_al, "alignment_delta": al_delta,
            "gap_pct_closed": gap_pct, "per_type": per_type, "published_pieces": published_total,
            "recommendation": rec}


def measure_all(business_id: int) -> dict:
    """Re-measure every batch that has an audit newer than its baseline. Called after an audit
    completes so impact refreshes automatically. Best-effort per batch."""
    with db() as conn:
        batches = conn.execute(
            "SELECT id FROM content_batches WHERE business_id=%s AND status IN "
            "('drafted','published','measured') ORDER BY id", (business_id,)).fetchall()
    measured, pending = [], []
    for b in batches:
        try:
            res = measure_batch(business_id, b["id"])
            (pending if res.get("pending") else measured).append(b["id"])
        except Exception as e:  # noqa: BLE001 -- one batch must not abort the sweep
            log.warning("impact measure failed for batch %d: %s", b["id"], e)
    return {"measured": measured, "pending": pending, "batches": len(batches)}
