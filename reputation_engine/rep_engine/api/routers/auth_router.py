"""Auth routes: login (issue JWT) + me (current user + accessible businesses)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .. import auth
from ..deps import get_conn, get_current_user
from ..schemas import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, conn=Depends(get_conn)):
    user = auth.authenticate(conn, body.email, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return {
        "access_token": auth.create_token(user),
        "token_type": "bearer",
        "user": auth.public_user(conn, user),
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    return auth.public_user(conn, user)
