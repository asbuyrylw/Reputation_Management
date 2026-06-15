"""Auth core: password hashing (stdlib pbkdf2), JWT tokens, user + tenancy queries.

Password hashing uses hashlib.pbkdf2_hmac (sha256, 600k iterations) so there is NO
native/bcrypt dependency -- robust across Python 3.12 (CI) and 3.14 (local). Tokens
are HS256 JWTs signed with JWT_SECRET. Tenancy: admins see every business; a client
sees only businesses linked via `business_access`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from .settings import api_settings

try:
    from ..db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

_PBKDF2_ITERATIONS = 600_000


# ---------------------------------------------------------------------------
# Password hashing (stdlib only)
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:  # noqa: BLE001 -- any malformed hash is a non-match, never an error
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_token(user: dict) -> str:
    s = api_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_ttl_min),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode + verify a token. Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, api_settings().jwt_secret, algorithms=["HS256"])


# ---------------------------------------------------------------------------
# User + tenancy queries
# ---------------------------------------------------------------------------
def get_user_by_id(conn, user_id: int) -> Optional[dict]:
    return conn.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()


def get_user_by_email(conn, email: str) -> Optional[dict]:
    return conn.execute("SELECT * FROM users WHERE lower(email)=lower(%s)", (email,)).fetchone()


def authenticate(conn, email: str, password: str) -> Optional[dict]:
    user = get_user_by_email(conn, email)
    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    conn.execute("UPDATE users SET last_login_at=now() WHERE id=%s", (user["id"],))
    conn.commit()
    return user


def is_org_manager(user: dict) -> bool:
    """True if the user is an owner/admin of their organization -- they manage org
    settings/billing and implicitly access every business in their org. (Platform staff,
    role='admin', are handled separately and sit above all orgs.)"""
    return bool(user.get("org_id")) and user.get("org_role") in ("owner", "admin")


def accessible_business_ids(conn, user: dict) -> Optional[list[int]]:
    """Business ids this user may access. None means ALL (platform admin)."""
    if user["role"] == "admin":
        return None
    ids: set[int] = set()
    rows = conn.execute(
        "SELECT business_id FROM business_access WHERE user_id=%s", (user["id"],),
    ).fetchall()
    ids.update(r["business_id"] for r in rows)
    # org owners/admins implicitly see every business in their org
    if is_org_manager(user):
        rows = conn.execute("SELECT id FROM businesses WHERE org_id=%s", (user["org_id"],)).fetchall()
        ids.update(r["id"] for r in rows)
    return sorted(ids)


def can_edit_business(conn, user: dict, business_id: int) -> bool:
    """True if the user may perform write/trigger actions on this business."""
    if user["role"] == "admin":
        return True
    # an org owner/admin can edit any business in their own org
    if is_org_manager(user):
        row = conn.execute("SELECT 1 FROM businesses WHERE id=%s AND org_id=%s",
                           (business_id, user["org_id"])).fetchone()
        if row:
            return True
    row = conn.execute(
        "SELECT 1 FROM business_access WHERE user_id=%s AND business_id=%s AND access_role='editor'",
        (user["id"], business_id),
    ).fetchone()
    return row is not None


def public_user(conn, user: dict) -> dict:
    """User shape safe to return to the client (no password_hash)."""
    ids = accessible_business_ids(conn, user)
    return {
        "id": user["id"], "email": user["email"], "full_name": user.get("full_name"),
        "role": user["role"], "is_active": user["is_active"],
        "org_id": user.get("org_id"), "org_role": user.get("org_role"),
        "business_ids": ids,   # None => all (admin)
    }


# ---------------------------------------------------------------------------
# Seed admin (local-first bootstrap)
# ---------------------------------------------------------------------------
def seed_admin() -> Optional[int]:
    """Create the seed admin from ADMIN_SEED_EMAIL/PASSWORD if no admin exists.
    Idempotent and a no-op when the seed env vars are unset. Returns the admin id
    if created/found, else None."""
    s = api_settings()
    if not (s.admin_email and s.admin_password):
        return None
    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        if existing:
            return existing["id"]
        row = conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role) "
            "VALUES (%s,%s,%s,'admin') RETURNING id",
            (s.admin_email, hash_password(s.admin_password), "Seed Admin"),
        ).fetchone()
        conn.commit()
        return row["id"]
