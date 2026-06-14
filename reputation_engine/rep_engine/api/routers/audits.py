"""Audits + AI answers (Phase 2 reads).

GET /businesses/{id}/audit-runs                  -> runs over time with per-run metrics
GET /businesses/{id}/audit-runs/{run}/answers    -> the scored AI answers from one run
GET /businesses/{id}/answers/before-after        -> same-engine first-vs-latest comparison
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import authorize_business, get_conn

try:
    from ... import report_generator as _rg
except ImportError:  # pragma: no cover
    import report_generator as _rg  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["audits"])


@router.get("/audit-runs")
def list_audit_runs(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        """SELECT r.id, r.started_at, r.finished_at, r.status,
                  AVG(a.goal_alignment) FILTER (WHERE NOT COALESCE(a.failed,false)) AS goal_alignment,
                  AVG((a.mentions_contested)::int) FILTER (WHERE NOT COALESCE(a.failed,false)) AS contested_rate,
                  AVG((a.surfaces_owned)::int) FILTER (WHERE NOT COALESCE(a.failed,false)) AS owned_rate,
                  COUNT(a.id) FILTER (WHERE NOT COALESCE(a.failed,false)) AS n_answers
             FROM audit_runs r
             LEFT JOIN answers a ON a.run_id = r.id
            WHERE r.business_id = %s
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
    rows = conn.execute(
        "SELECT id, engine, prompt, answer_text, sentiment, goal_alignment, cited_sources, "
        "mentions_contested, surfaces_owned, persona, location, failed "
        "FROM answers WHERE " + " AND ".join(where) + " ORDER BY engine, id",
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
