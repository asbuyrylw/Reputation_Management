"""Auth routes: login (issue JWT + set httpOnly cookie, rate-limited), logout, and me."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from .. import auth, ratelimit
from ..deps import get_conn, get_current_user
from ..schemas import LoginRequest
from ..settings import api_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, conn=Depends(get_conn)):
    client = request.client.host if request.client else "?"
    if ratelimit.enabled() and not ratelimit.rate_check(client):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts; try again shortly.")
    user = auth.authenticate(conn, body.email, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = auth.create_token(user)
    s = api_settings()
    max_age = s.jwt_ttl_min * 60
    # httpOnly session cookie (XSS can't read it) + a readable double-submit CSRF token
    # the SPA echoes in the X-CSRF-Token header on writes. The bearer is still returned
    # for API/script clients. Secure + SameSite are env-driven (see settings): production
    # over HTTPS sets COOKIE_SECURE=1 so the session cookie is never sent in cleartext.
    response.set_cookie("rc_token", token, httponly=True, secure=s.cookie_secure,
                        samesite=s.cookie_samesite, path="/", max_age=max_age)
    response.set_cookie("csrf_token", secrets.token_urlsafe(32), httponly=False,
                        secure=s.cookie_secure, samesite=s.cookie_samesite, path="/", max_age=max_age)
    return {"access_token": token, "token_type": "bearer", "user": auth.public_user(conn, user)}


@router.post("/logout")
def logout(response: Response):
    s = api_settings()
    # Match the Set-Cookie attributes so the browser reliably clears the cookies.
    response.delete_cookie("rc_token", path="/", secure=s.cookie_secure, samesite=s.cookie_samesite)
    response.delete_cookie("csrf_token", path="/", secure=s.cookie_secure, samesite=s.cookie_samesite)
    return {"ok": True}


@router.post("/revoke-sessions")
def revoke_sessions(response: Response, user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    """Sign out EVERYWHERE: invalidate every outstanding token for the current user (this
    device included) by stamping the revocation time; also clear this response's cookies."""
    auth.revoke_sessions(conn, user["id"])
    s = api_settings()
    response.delete_cookie("rc_token", path="/", secure=s.cookie_secure, samesite=s.cookie_samesite)
    response.delete_cookie("csrf_token", path="/", secure=s.cookie_secure, samesite=s.cookie_samesite)
    return {"ok": True, "revoked_all_sessions": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    return auth.public_user(conn, user)


def _password_problem(pw: str) -> str | None:
    """Minimal password policy: length + at least two character classes."""
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    classes = sum(bool(c) for c in (
        any(ch.islower() for ch in pw),
        any(ch.isupper() for ch in pw),
        any(ch.isdigit() for ch in pw),
        any(not ch.isalnum() for ch in pw),
    ))
    if classes < 2:
        return "Use a mix of letters, numbers, or symbols."
    return None


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    problem = _password_problem(body.new_password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    row = conn.execute("SELECT email FROM users WHERE id=%s", (user["id"],)).fetchone()
    email = row["email"] if row else None
    if not email or not auth.authenticate(conn, email, body.current_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect.")
    conn.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                 (auth.hash_password(body.new_password), user["id"]))
    conn.commit()
    return {"ok": True}
