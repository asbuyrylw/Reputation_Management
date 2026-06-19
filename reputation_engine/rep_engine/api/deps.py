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
    # Session revocation: a token issued BEFORE the user's revocation stamp is dead, so
    # "sign out everywhere" / an admin force-logout invalidates all outstanding tokens.
    revoked = user.get("sessions_revoked_at")
    if revoked is not None and auth.token_is_revoked(payload, revoked):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked -- please sign in again")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def require_org_manager(user: dict = Depends(get_current_user)) -> dict:
    """Org-management authorization (billing, members, org settings): platform admin, or
    an owner/admin of an organization."""
    if user["role"] == "admin" or auth.is_org_manager(user):
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization owner/admin access required")


def authorize_business(
    business_id: int,
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
) -> int:
    """Read authorization for a scoped route. Returns business_id on success.

    Order: platform admin -> any business; org owner/admin -> any business in their org;
    otherwise an explicit business_access grant. (Org columns default NULL, so a user with
    no org falls straight through to the business_access check -- unchanged behavior.)"""
    if user["role"] == "admin":
        return business_id
    if auth.is_org_manager(user):
        row = conn.execute("SELECT 1 FROM businesses WHERE id=%s AND org_id=%s",
                           (business_id, user["org_id"])).fetchone()
        if row:
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
