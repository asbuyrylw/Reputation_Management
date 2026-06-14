"""Businesses + the at-a-glance dashboard (Phase 1).

GET /businesses              -> list (admin: all; client: only theirs)
GET /businesses/{id}         -> one business (tenancy-guarded)
GET /businesses/{id}/dashboard -> the full dashboard bundle (reuses report_generator._load)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import authorize_business, get_conn, get_current_user

try:
    from ... import report_generator as _rg
except ImportError:  # pragma: no cover
    import report_generator as _rg  # type: ignore

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("")
def list_businesses(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    # `can_edit` lets the UI gate action buttons: admins edit everything; a client
    # edits a business only with an 'editor' access row.
    if user["role"] == "admin":
        rows = conn.execute(
            "SELECT id, name, domain, geo, goal, contested_terms, created_at, true AS can_edit "
            "FROM businesses ORDER BY name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT b.id, b.name, b.domain, b.geo, b.goal, b.contested_terms, b.created_at, "
            "(ba.access_role = 'editor') AS can_edit "
            "FROM businesses b JOIN business_access ba ON ba.business_id = b.id "
            "WHERE ba.user_id = %s ORDER BY b.name",
            (user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{business_id}")
def get_business(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    return dict(row)


@router.get("/{business_id}/dashboard")
def get_dashboard(
    business_id: int = Depends(authorize_business),
    user: dict = Depends(get_current_user),
):
    # report_generator._load opens its own db() connection and returns the full
    # bundle (business, gap, plan, series, before_after, wo_counts, assets_n,
    # month_cost, attribution). It raises SystemExit when the business is missing.
    try:
        data = _rg._load(business_id)
    except SystemExit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    # Clients don't see internal cost-of-goods; admins do.
    if user["role"] != "admin":
        data.pop("month_cost", None)
    return data
