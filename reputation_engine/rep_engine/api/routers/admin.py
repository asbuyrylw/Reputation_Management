"""Admin (Phase 5): manage users + their business access, and create/update
businesses. Admin-only. Passwords are hashed; access_role gates client editing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .. import auth
from ..deps import get_conn, require_admin
from ..schemas import (
    AssignSubscriptionRequest,
    CreateBusinessRequest,
    CreateOrganizationRequest,
    CreateUserRequest,
    GrantAccessRequest,
    LocationRequest,
    UpdateBusinessRequest,
)

try:
    from ... import billing as _billing
except ImportError:  # pragma: no cover
    import billing as _billing  # type: ignore

router = APIRouter(prefix="/admin", tags=["admin"])

_BUSINESS_FIELDS = ("name", "domain", "services", "industry", "goal", "contested_terms", "geo",
                    "regulatory_profile", "owned_domains", "neuronwriter_project")
# JSONB business columns -- wrapped with psycopg Json so a dict/list adapts to jsonb.
_BUSINESS_JSONB = ("regulatory_profile", "owned_domains")


@router.get("/organizations")
def list_organizations(_: dict = Depends(require_admin), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT o.id, o.name, o.status, o.created_at, "
        "COUNT(DISTINCT b.id) AS business_count, COUNT(DISTINCT u.id) AS user_count "
        "FROM organizations o "
        "LEFT JOIN businesses b ON b.org_id = o.id "
        "LEFT JOIN users u ON u.org_id = o.id "
        "GROUP BY o.id ORDER BY o.id"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
def create_organization(body: CreateOrganizationRequest, _: dict = Depends(require_admin),
                        conn=Depends(get_conn)):
    row = conn.execute(
        "INSERT INTO organizations (name) VALUES (%s) RETURNING id, name, status, created_at",
        (body.name,),
    ).fetchone()
    conn.commit()
    return dict(row)


@router.post("/organizations/{org_id}/subscription", status_code=status.HTTP_201_CREATED)
def assign_subscription(org_id: int, body: AssignSubscriptionRequest,
                        _: dict = Depends(require_admin), conn=Depends(get_conn)):
    if body.status not in ("trialing", "active", "past_due", "canceled"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid subscription status")
    if not conn.execute("SELECT 1 FROM organizations WHERE id=%s", (org_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    try:
        sub = _billing.subscribe(conn, org_id, body.plan_code, status=body.status)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    conn.commit()
    return dict(sub)


@router.get("/users")
def list_users(_: dict = Depends(require_admin), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT u.id, u.email, u.full_name, u.role, u.is_active, u.created_at, u.last_login_at, "
        "COALESCE(json_agg(json_build_object('business_id', ba.business_id, "
        "'access_role', ba.access_role)) FILTER (WHERE ba.business_id IS NOT NULL), '[]') AS access "
        "FROM users u LEFT JOIN business_access ba ON ba.user_id = u.id "
        "GROUP BY u.id ORDER BY u.id"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, _: dict = Depends(require_admin), conn=Depends(get_conn)):
    if body.role not in ("admin", "client"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "role must be admin|client")
    if body.org_role not in ("owner", "admin", "member"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "org_role must be owner|admin|member")
    if body.org_id is not None and not conn.execute(
            "SELECT 1 FROM organizations WHERE id=%s", (body.org_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    if auth.get_user_by_email(conn, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")
    row = conn.execute(
        "INSERT INTO users (email, password_hash, full_name, role, org_id, org_role) "
        "VALUES (%s,%s,%s,%s,%s,%s) "
        "RETURNING id, email, full_name, role, is_active, org_id, org_role",
        (body.email, auth.hash_password(body.password), body.full_name, body.role,
         body.org_id, body.org_role),
    ).fetchone()
    conn.commit()
    return dict(row)


@router.post("/users/{user_id}/access", status_code=status.HTTP_201_CREATED)
def grant_access(user_id: int, body: GrantAccessRequest, _: dict = Depends(require_admin), conn=Depends(get_conn)):
    if body.access_role not in ("viewer", "editor"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "access_role must be viewer|editor")
    u = conn.execute("SELECT 1 FROM users WHERE id=%s", (user_id,)).fetchone()
    b = conn.execute("SELECT 1 FROM businesses WHERE id=%s", (body.business_id,)).fetchone()
    if not u or not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user or business not found")
    conn.execute(
        "INSERT INTO business_access (user_id, business_id, access_role) VALUES (%s,%s,%s) "
        "ON CONFLICT (user_id, business_id) DO UPDATE SET access_role=EXCLUDED.access_role",
        (user_id, body.business_id, body.access_role),
    )
    conn.commit()
    return {"ok": True, "user_id": user_id, "business_id": body.business_id, "access_role": body.access_role}


@router.delete("/users/{user_id}/access/{business_id}")
def revoke_access(user_id: int, business_id: int, _: dict = Depends(require_admin), conn=Depends(get_conn)):
    conn.execute("DELETE FROM business_access WHERE user_id=%s AND business_id=%s", (user_id, business_id))
    conn.commit()
    return {"ok": True}


@router.post("/businesses", status_code=status.HTTP_201_CREATED)
def create_business(body: CreateBusinessRequest, _: dict = Depends(require_admin), conn=Depends(get_conn)):
    if body.org_id is not None and not conn.execute(
            "SELECT 1 FROM organizations WHERE id=%s", (body.org_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    from psycopg.types.json import Json
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, industry, goal, contested_terms, geo, "
        "owned_domains, org_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (body.name, body.domain, body.services, body.industry, body.goal,
         body.contested_terms, body.geo, Json(body.owned_domains or []), body.org_id),
    ).fetchone()
    conn.commit()
    return dict(row)


@router.patch("/businesses/{business_id}")
def update_business(business_id: int, body: UpdateBusinessRequest, _: dict = Depends(require_admin), conn=Depends(get_conn)):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in _BUSINESS_FIELDS}
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    # keys are restricted to the fixed _BUSINESS_FIELDS whitelist (not user-supplied
    # column names); all values are bound parameters.
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    # JSONB columns must be wrapped so psycopg adapts a dict -> jsonb (not a bare Python dict).
    from psycopg.types.json import Json
    params = [Json(v) if k in _BUSINESS_JSONB else v for k, v in fields.items()] + [business_id]
    row = conn.execute(
        f"UPDATE businesses SET {set_clause} WHERE id=%s RETURNING *", params  # nosec B608
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business not found")
    conn.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# Locations (lightweight multi-location -- deferred #5a). Additive: `geo` still works.
# ---------------------------------------------------------------------------
_LOC_FIELDS = ("label", "address", "city", "state", "postal", "phone", "is_primary")


@router.get("/businesses/{business_id}/locations")
def list_locations(business_id: int, _: dict = Depends(require_admin), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, label, address, city, state, postal, phone, is_primary, created_at "
        "FROM locations WHERE business_id=%s ORDER BY is_primary DESC, id", (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _clear_primary(conn, business_id: int, keep_id: int | None = None) -> None:
    conn.execute("UPDATE locations SET is_primary=FALSE WHERE business_id=%s AND is_primary "
                 "AND (%s IS NULL OR id<>%s)", (business_id, keep_id, keep_id))


@router.post("/businesses/{business_id}/locations", status_code=status.HTTP_201_CREATED)
def add_location(business_id: int, body: LocationRequest, _: dict = Depends(require_admin),
                 conn=Depends(get_conn)):
    if not conn.execute("SELECT 1 FROM businesses WHERE id=%s", (business_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business not found")
    if body.is_primary:
        _clear_primary(conn, business_id)
    row = conn.execute(
        "INSERT INTO locations (business_id, label, address, city, state, postal, phone, is_primary) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (business_id, body.label, body.address, body.city, body.state, body.postal,
         body.phone, body.is_primary),
    ).fetchone()
    conn.commit()
    return dict(row)


@router.patch("/businesses/{business_id}/locations/{loc_id}")
def update_location(business_id: int, loc_id: int, body: LocationRequest,
                    _: dict = Depends(require_admin), conn=Depends(get_conn)):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in _LOC_FIELDS}
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    if fields.get("is_primary"):
        _clear_primary(conn, business_id, keep_id=loc_id)
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    params = list(fields.values()) + [loc_id, business_id]
    row = conn.execute(
        f"UPDATE locations SET {set_clause} WHERE id=%s AND business_id=%s RETURNING *",  # nosec B608
        params,
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "location not found")
    conn.commit()
    return dict(row)


@router.delete("/businesses/{business_id}/locations/{loc_id}")
def delete_location(business_id: int, loc_id: int, _: dict = Depends(require_admin),
                    conn=Depends(get_conn)):
    row = conn.execute("DELETE FROM locations WHERE id=%s AND business_id=%s RETURNING id",
                       (loc_id, business_id)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "location not found")
    conn.commit()
    return {"deleted": loc_id}
