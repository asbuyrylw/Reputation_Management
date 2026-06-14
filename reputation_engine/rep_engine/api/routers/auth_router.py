"""Auth routes: login (issue JWT + set httpOnly cookie, rate-limited), logout, and me."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .. import auth, ratelimit
from ..deps import get_conn, get_current_user
from ..schemas import LoginRequest
from ..settings import api_settings

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.get("/me")
def me(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    return auth.public_user(conn, user)
