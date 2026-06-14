"""Auth routes: login (issue JWT + set httpOnly cookie, rate-limited), logout, and me."""

from __future__ import annotations

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
    # httpOnly cookie hardens against XSS token theft; the SPA may still use the bearer.
    response.set_cookie(
        "rc_token", token, httponly=True, samesite="lax", path="/",
        max_age=api_settings().jwt_ttl_min * 60,
    )
    return {"access_token": token, "token_type": "bearer", "user": auth.public_user(conn, user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("rc_token", path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    return auth.public_user(conn, user)
