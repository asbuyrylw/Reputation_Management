"""Audits + AI answers (Phase 2 reads).

GET /businesses/{id}/audit-runs                  -> runs over time with per-run metrics
GET /businesses/{id}/audit-runs/{run}/answers    -> the scored AI answers from one run
GET /businesses/{id}/answers/before-after        -> same-engine first-vs-latest comparison
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import authorize_business, get_conn, require_admin

try:
    from ... import ai_state_audit as _ai
    from ... import report_generator as _rg
except ImportError:  # pragma: no cover
    import ai_state_audit as _ai  # type: ignore
    import report_generator as _rg  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["audits"])


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
    return {"run_id": run_id, "items": items, "run_total": round(run_total, 4),
            "month_total": round(float(month["s"]), 4), "estimated": True}


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
