"""Audits + AI answers (Phase 2 reads).

GET /businesses/{id}/audit-runs                  -> runs over time with per-run metrics
GET /businesses/{id}/audit-runs/{run}/answers    -> the scored AI answers from one run
GET /businesses/{id}/answers/before-after        -> same-engine first-vs-latest comparison
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..deps import authorize_business, get_conn, require_admin

try:
    from ... import ai_state_audit as _ai
    from ... import report_generator as _rg
except ImportError:  # pragma: no cover
    import ai_state_audit as _ai  # type: ignore
    import report_generator as _rg  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["audits"])


@router.get("/narrative-score")
def narrative_score(business_id: int = Depends(authorize_business)):
    """The Narrative Crowding-Out Score (0-100: how much the DESIRED narrative dominates AI answers
    vs the CONTESTED one) + its trend over runs. The one-number headline a client renews for."""
    try:
        from ... import narrative_score as _ns
    except ImportError:  # pragma: no cover
        import narrative_score as _ns  # type: ignore
    out = _ns.trend(business_id)
    try:
        out["latest_detail"] = _ns.compute(business_id, persist=False)  # incl. by_engine breakdown
    except Exception:
        out["latest_detail"] = None
    return out


@router.get("/impact-report")
def impact_report(business_id: int = Depends(authorize_business)):
    """'Prove it worked': actions completed between the two latest audits joined to the before/after
    movement in the Narrative Score, owned-citation share, and goal-alignment (Rec #1b)."""
    try:
        from ... import impact_report as _ir
    except ImportError:  # pragma: no cover
        import impact_report as _ir  # type: ignore
    return _ir.build(business_id)


@router.get("/roadmap")
def roadmap(business_id: int = Depends(authorize_business)):
    """The impact-ranked roadmap: every open task ordered by predicted impact / effort, with the
    learned/cross-client basis -- the 'do these in this order' list that powers the to-do hub."""
    try:
        from ... import roi_predictor as _rp
    except ImportError:  # pragma: no cover
        import roi_predictor as _rp  # type: ignore
    return _rp.roadmap(business_id)


@router.get("/roi-forecast")
def roi_forecast(business_id: int = Depends(authorize_business)):
    """Predicted score lift from finishing the open plan, using this client's learned effectiveness
    first, then the anonymized cross-client prior, then an industry baseline (Rec #1c)."""
    try:
        from ... import roi_predictor as _rp
    except ImportError:  # pragma: no cover
        import roi_predictor as _rp  # type: ignore
    return _rp.predict_plan(business_id)


@router.get("/per-engine")
def per_engine_latest(business_id: int = Depends(authorize_business)):
    """Per-engine KPI breakdown for the latest completed run: what EACH AI engine says,
    with sample sizes, confidence intervals, grounding coverage, and a partial-coverage
    flag (which of the 4 engines actually ran)."""
    return _ai.per_engine_metrics(business_id)


@router.get("/audit-runs/{run_id}/per-engine")
def per_engine_for_run(run_id: int, business_id: int = Depends(authorize_business)):
    return _ai.per_engine_metrics(business_id, run_id)


@router.get("/cost-breakdown")
def cost_breakdown(business_id: int = Depends(authorize_business),
                   _: dict = Depends(require_admin), conn=Depends(get_conn)):
    """Estimated COGS for the latest audit: per engine + operation, the run total, and this
    month's total. ADMIN-ONLY -- this is OUR provider cost (cost_ledger.est_cost_usd), not the
    client's billing. Figures are ESTIMATES (token counts x a list-price table), not invoiced
    amounts, so the response flags estimated=true."""
    run = conn.execute(
        "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' "
        "AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1", (business_id,),
    ).fetchone()
    run_id = run["id"] if run else None
    items: list[dict] = []
    run_total = 0.0
    if run_id:
        for r in conn.execute(
            "SELECT provider, operation, count(*) AS calls, COALESCE(sum(input_tokens),0) AS in_tok, "
            "COALESCE(sum(output_tokens),0) AS out_tok, COALESCE(sum(est_cost_usd),0) AS cost "
            "FROM cost_ledger WHERE run_id=%s GROUP BY provider, operation ORDER BY cost DESC",
            (run_id,),
        ).fetchall():
            items.append({
                "provider": r["provider"], "operation": r["operation"], "calls": r["calls"],
                "input_tokens": int(r["in_tok"]), "output_tokens": int(r["out_tok"]),
                "cost": round(float(r["cost"]), 4),
            })
            run_total += float(r["cost"])
    month = conn.execute(
        "SELECT COALESCE(SUM(est_cost_usd),0) AS s FROM cost_ledger WHERE business_id=%s "
        "AND created_at >= date_trunc('month', now() AT TIME ZONE 'UTC')", (business_id,),
    ).fetchone()
    month_total = round(float(month["s"]), 4)
    # The monthly budget CAP (the runaway guard that build_gap_model/generate/audit now enforce).
    # Surfaced here so the cap is VISIBLE + the operator can see how close MTD spend is to it,
    # instead of the cap living only in SQL (rec 8). Default matches cost.budget_for (50.0).
    cap_row = conn.execute(
        "SELECT monthly_budget_usd FROM business_config WHERE business_id=%s", (business_id,)
    ).fetchone()
    cap = float(cap_row["monthly_budget_usd"]) if cap_row and cap_row["monthly_budget_usd"] is not None else 50.0
    return {"run_id": run_id, "items": items, "run_total": round(run_total, 4),
            "month_total": month_total, "monthly_budget_usd": round(cap, 2),
            "budget_pct": round(month_total / cap, 4) if cap > 0 else None,
            "over_budget": month_total >= cap, "estimated": True}


class BudgetUpdate(BaseModel):
    monthly_budget_usd: float = Field(ge=0, le=100000)


@router.patch("/budget")
def set_budget(body: BudgetUpdate, business_id: int = Depends(authorize_business),
               _: dict = Depends(require_admin), conn=Depends(get_conn)):
    """Set the per-business monthly spend CAP (business_config.monthly_budget_usd) -- the runaway
    guard audit/gap-model/content generation enforce. ADMIN-ONLY (it governs OUR provider COGS, like
    the cost breakdown). Upsert so a business with no config row gets one. (rec 8)"""
    val = round(float(body.monthly_budget_usd), 2)
    conn.execute(
        "INSERT INTO business_config (business_id, monthly_budget_usd) VALUES (%s,%s) "
        "ON CONFLICT (business_id) DO UPDATE SET monthly_budget_usd=EXCLUDED.monthly_budget_usd, "
        "updated_at=now()", (business_id, val))
    conn.commit()
    return {"business_id": business_id, "monthly_budget_usd": val}


@router.get("/audit-runs")
def list_audit_runs(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        """SELECT r.id, r.started_at, r.finished_at, r.status,
                  AVG(a.goal_alignment) FILTER (WHERE NOT COALESCE(a.failed,false)) AS goal_alignment,
                  AVG((a.mentions_contested)::int) FILTER (WHERE NOT COALESCE(a.failed,false)) AS contested_rate,
                  AVG((a.surfaces_owned)::int) FILTER (WHERE NOT COALESCE(a.failed,false)) AS owned_rate,
                  COUNT(a.id) FILTER (WHERE NOT COALESCE(a.failed,false)) AS n_answers,
                  COUNT(a.id) FILTER (WHERE COALESCE(a.failed,false)) AS failed_count,
                  COUNT(DISTINCT a.engine) FILTER (WHERE COALESCE(a.failed,false)) AS failed_engines
             FROM audit_runs r
             LEFT JOIN answers a ON a.run_id = r.id
            WHERE r.business_id = %s AND r.kind = 'ai_audit'
            GROUP BY r.id
            ORDER BY r.id DESC
            LIMIT 100""",
        (business_id,),
    ).fetchall()
    # numeric AVGs come back as Decimal/None -> floats for clean JSON
    out = []
    for r in rows:
        d = dict(r)
        for k in ("goal_alignment", "contested_rate", "owned_rate"):
            d[k] = float(d[k]) if d[k] is not None else None
        out.append(d)
    return out


@router.get("/audit-runs/{run_id}/answers")
def run_answers(
    run_id: int,
    business_id: int = Depends(authorize_business),
    conn=Depends(get_conn),
    engine: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
):
    where = ["business_id = %s", "run_id = %s"]
    params: list = [business_id, run_id]
    if engine:
        where.append("engine = %s")
        params.append(engine)
    if sentiment:
        where.append("sentiment = %s")
        params.append(sentiment)
    # `where` is composed ONLY of hardcoded predicate fragments ("engine = %s", ...); every
    # value is bound through `params`. No user input reaches the SQL string. # nosec B608
    rows = conn.execute(
        "SELECT id, engine, prompt, answer_text, sentiment, goal_alignment, cited_sources, "
        "mentions_contested, surfaces_owned, awareness, entity_confusion, persona, location, failed "
        "FROM answers WHERE " + " AND ".join(where) + " ORDER BY engine, id",  # nosec B608
        params,
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["goal_alignment"] = float(d["goal_alignment"]) if d["goal_alignment"] is not None else None
        out.append(d)
    return out


@router.get("/answers/before-after")
def before_after(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    return _rg._before_after(conn, business_id)
