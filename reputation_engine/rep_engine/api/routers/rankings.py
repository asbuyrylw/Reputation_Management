"""Rankings / share-of-voice (Phase 4 reads): owned-vs-contested citation share,
domain momentum, root-cause of the contested narrative, and asset attribution.
Share-of-voice reads the persisted citation_momentum table (NOT citation_analytics.
analyze, which WRITES). momentum() is a pure read called with quiet=True.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import authorize_business, get_conn

try:
    from ... import citation_analytics as _ca
except ImportError:  # pragma: no cover
    import citation_analytics as _ca  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["rankings"])


@router.get("/citations/share-of-voice")
def share_of_voice(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    latest = conn.execute(
        "SELECT MAX(run_id) AS r FROM citation_momentum WHERE business_id=%s", (business_id,)
    ).fetchone()
    run_id = latest["r"] if latest else None
    if run_id is None:
        return {"run_id": None, "by_classification": {}, "top_domains": []}
    by_class = conn.execute(
        "SELECT classification, SUM(cite_count) AS cites, SUM(share) AS share "
        "FROM citation_momentum WHERE business_id=%s AND run_id=%s GROUP BY classification",
        (business_id, run_id),
    ).fetchall()
    top = conn.execute(
        "SELECT domain, cite_count, share, classification FROM citation_momentum "
        "WHERE business_id=%s AND run_id=%s ORDER BY cite_count DESC LIMIT 20",
        (business_id, run_id),
    ).fetchall()
    # source TYPE (review/social/news/...) is a pure function of the domain, so we type it at
    # read time -- no extra column. Roll it up across ALL of the run's domains (not just the
    # top 20) so the by-source-type mix is complete.
    biz = conn.execute("SELECT domain FROM businesses WHERE id=%s", (business_id,)).fetchone()
    bizd = {"domain": (biz or {}).get("domain") if biz else ""}
    all_domains = conn.execute(
        "SELECT domain, cite_count, share FROM citation_momentum "
        "WHERE business_id=%s AND run_id=%s", (business_id, run_id),
    ).fetchall()
    by_source: dict = {}
    for r in all_domains:
        st = _ca._source_type(r["domain"], bizd)
        b = by_source.setdefault(st, {"cites": 0, "share": 0.0})
        b["cites"] += int(r["cite_count"] or 0)
        b["share"] = round(b["share"] + float(r["share"] or 0), 4)
    return {
        "run_id": run_id,
        "by_classification": {
            r["classification"]: {"cites": int(r["cites"] or 0), "share": float(r["share"] or 0)}
            for r in by_class
        },
        "by_source_type": by_source,
        "top_domains": [
            {"domain": r["domain"], "cite_count": r["cite_count"],
             "share": float(r["share"] or 0), "classification": r["classification"],
             "source_type": _ca._source_type(r["domain"], bizd)}
            for r in top
        ],
    }


@router.get("/citations/momentum")
def momentum(business_id: int = Depends(authorize_business)):
    return _ca.momentum(business_id, quiet=True)


@router.get("/root-cause")
def root_cause(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT model, created_at FROM root_cause WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/attribution")
def attribution(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT metric, delta, assets_in_window, created_at FROM attribution "
        "WHERE business_id=%s ORDER BY id DESC LIMIT 10",
        (business_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["delta"] = float(d["delta"]) if d["delta"] is not None else None
        out.append(d)
    return out
