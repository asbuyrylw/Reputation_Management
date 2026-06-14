"""SEO site audit + gap model (Phase 2 reads). Both return the latest persisted
JSONB document (or null when none exists yet)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import authorize_business, get_conn

router = APIRouter(prefix="/businesses/{business_id}", tags=["insights"])


@router.get("/site-audit")
def site_audit(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT summary, created_at FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/gap-model")
def gap_model(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT model, created_at FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None
