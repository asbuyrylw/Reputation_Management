"""Businesses + the at-a-glance dashboard (Phase 1).

GET /businesses              -> list (admin: all; client: only theirs)
GET /businesses/{id}         -> one business (tenancy-guarded)
GET /businesses/{id}/dashboard -> the full dashboard bundle (reuses report_generator._load)
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .. import auth
from ..deps import authorize_business, get_conn, get_current_user, require_admin, require_business_editor

try:
    from ... import challenge as _challenge
    from ... import report_generator as _rg
except ImportError:  # pragma: no cover
    import challenge as _challenge  # type: ignore
    import report_generator as _rg  # type: ignore

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("")
def list_businesses(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    # `can_edit` lets the UI gate action buttons: platform admins edit everything; org
    # owners/admins edit every business in their org; otherwise an 'editor' access row.
    if user["role"] == "admin":
        rows = conn.execute(
            "SELECT id, name, domain, geo, goal, contested_terms, services, industry, "
            "regulatory_profile, owned_domains, created_at, true AS can_edit FROM businesses ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    ids = auth.accessible_business_ids(conn, user) or []   # incl. org businesses for managers
    if not ids:
        return []
    editable: set[int] = {
        r["business_id"] for r in conn.execute(
            "SELECT business_id FROM business_access WHERE user_id=%s AND access_role='editor'",
            (user["id"],)).fetchall()
    }
    if auth.is_org_manager(user):
        editable.update(r["id"] for r in conn.execute(
            "SELECT id FROM businesses WHERE org_id=%s", (user["org_id"],)).fetchall())
    rows = conn.execute(
        "SELECT id, name, domain, geo, goal, contested_terms, services, industry, "
        "regulatory_profile, owned_domains, created_at FROM businesses WHERE id = ANY(%s) ORDER BY name", (ids,),
    ).fetchall()
    return [{**dict(r), "can_edit": r["id"] in editable} for r in rows]


@router.get("/{business_id}")
def get_business(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    out = dict(row)
    # Structured locations (lightweight multi-location, #5a). Additive to `geo`.
    out["locations"] = [dict(r) for r in conn.execute(
        "SELECT id, label, address, city, state, postal, phone, is_primary "
        "FROM locations WHERE business_id=%s ORDER BY is_primary DESC, id", (business_id,),
    ).fetchall()]
    return out


class BusinessProfileUpdate(BaseModel):
    """The owner-editable business profile — the same fields onboarding captures. Every field is
    optional; only the ones sent are changed (a partial update)."""
    name: Optional[str] = None
    domain: Optional[str] = None
    services: Optional[str] = None
    industry: Optional[str] = None
    goal: Optional[str] = None
    contested_terms: Optional[str] = None
    geo: Optional[str] = None
    firm_type: Optional[str] = None   # merged into regulatory_profile jsonb (drives compliance checks)


_PROFILE_COLS = ("name", "domain", "services", "industry", "goal", "contested_terms", "geo")


@router.patch("/{business_id}")
def update_business_profile(body: BusinessProfileUpdate,
                           business_id: int = Depends(require_business_editor),
                           conn=Depends(get_conn)):
    """Owner-safe business-profile editor: lets an EDITOR (owner/operator) update the profile fields
    captured at onboarding — geo, services, industry, goal, contested terms, firm type — without the
    admin-only `/admin/businesses` surface. Tenancy + editor role are enforced by require_business_editor.
    Partial update: only the fields provided change; name can't be blanked."""
    sets, params = [], []
    for col in _PROFILE_COLS:
        v = getattr(body, col)
        if v is not None:
            v = v.strip()
            if col == "name" and not v:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Business name can't be empty")
            sets.append(f"{col}=%s")
            params.append(v)
    # firm_type lives inside the regulatory_profile jsonb (it drives which compliance screen runs);
    # merge it in without clobbering the rest of the object.
    if body.firm_type is not None:
        sets.append("regulatory_profile = COALESCE(regulatory_profile,'{}'::jsonb) || %s::jsonb")
        params.append(json.dumps({"firm_type": body.firm_type.strip()}))
    if not sets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No profile fields to update")
    params.append(business_id)
    row = conn.execute(
        f"UPDATE businesses SET {', '.join(sets)} WHERE id=%s "
        "RETURNING id, name, domain, services, industry, goal, contested_terms, geo, regulatory_profile",
        params,
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    conn.commit()
    return dict(row)


@router.get("/{business_id}/export")
def export_business_data(business_id: int = Depends(require_business_editor)):
    """GDPR data export (portability): everything we hold for this business as JSON. Editor/
    admin only, since it contains the full dataset."""
    try:
        from ... import gdpr as _gdpr
    except ImportError:  # pragma: no cover
        import gdpr as _gdpr  # type: ignore
    data = _gdpr.export_business(business_id)
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    return data


@router.delete("/{business_id}")
def delete_business_data(business_id: int, user: dict = Depends(require_admin)):
    """GDPR erasure: PERMANENTLY delete the business and ALL its data. Platform-admin only
    (irreversible)."""
    try:
        from ... import gdpr as _gdpr
    except ImportError:  # pragma: no cover
        import gdpr as _gdpr  # type: ignore
    result = _gdpr.delete_business(business_id)
    if result["deleted_business"] is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    return result


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
    # Primary-challenge profile (awareness gap vs negative narrative) -- pure read,
    # added here so the dashboard gets it without coupling report_generator._load.
    try:
        data["challenge"] = _challenge.challenge_profile(business_id, quiet=True)
    except Exception:  # never let the diagnostic break the dashboard
        data["challenge"] = None
    # Headline Narrative Crowding-Out Score + trend (Rec #1a) -- the one-number story.
    try:
        from ... import narrative_score as _ns
    except ImportError:  # pragma: no cover
        import narrative_score as _ns  # type: ignore
    try:
        data["narrative"] = _ns.trend(business_id)
    except Exception:
        data["narrative"] = None
    return data
