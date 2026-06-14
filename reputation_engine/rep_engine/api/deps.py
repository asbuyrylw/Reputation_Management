"""FastAPI dependencies: pooled connection, current user, and the tenancy guard.

`authorize_business` is the single chokepoint attached to every /businesses/{id}
route: admins pass; clients pass only if they have a `business_access` row. Handlers
ALSO pass business_id into the (already business_id-scoped) engine SQL, so even a
guard bug cannot leak across tenants.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth
from .pool import get_pool

_bearer = HTTPBearer(auto_error=False)


def get_conn():
    """Yield a pooled dict-row connection for inline read handlers."""
    with get_pool().connection() as conn:
        yield conn


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    rc_token: Optional[str] = Cookie(None),
    conn=Depends(get_conn),
) -> dict:
    # Bearer header (SPA today) OR the httpOnly rc_token cookie (hardened path).
    token = creds.credentials if creds else rc_token
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = auth.decode_token(token)
    except Exception:  # noqa: BLE001 -- any decode/expiry failure is a 401
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = auth.get_user_by_id(conn, int(payload["sub"]))
    if not user or not user["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def authorize_business(
    business_id: int,
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
) -> int:
    """Read authorization for a scoped route. Returns business_id on success."""
    if user["role"] == "admin":
        return business_id
    row = conn.execute(
        "SELECT 1 FROM business_access WHERE user_id=%s AND business_id=%s",
        (user["id"], business_id),
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this business")
    return business_id


def require_business_editor(
    business_id: int,
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
) -> int:
    """Write/trigger authorization: admin, or a client with editor access."""
    if not auth.can_edit_business(conn, user, business_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Editor access required for this business")
    return business_id
