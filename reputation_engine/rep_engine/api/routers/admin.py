"""Admin (Phase 5): manage users + their business access, and create/update
businesses. Admin-only. Passwords are hashed; access_role gates client editing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .. import auth
from ..deps import get_conn, require_admin
from ..schemas import CreateBusinessRequest, CreateUserRequest, GrantAccessRequest, UpdateBusinessRequest

router = APIRouter(prefix="/admin", tags=["admin"])

_BUSINESS_FIELDS = ("name", "domain", "services", "goal", "contested_terms", "geo")


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
    if auth.get_user_by_email(conn, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")
    row = conn.execute(
        "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s,%s,%s,%s) "
        "RETURNING id, email, full_name, role, is_active",
        (body.email, auth.hash_password(body.password), body.full_name, body.role),
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
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
        (body.name, body.domain, body.services, body.goal, body.contested_terms, body.geo),
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
    params = list(fields.values()) + [business_id]
    row = conn.execute(
        f"UPDATE businesses SET {set_clause} WHERE id=%s RETURNING *", params  # nosec B608
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business not found")
    conn.commit()
    return dict(row)
