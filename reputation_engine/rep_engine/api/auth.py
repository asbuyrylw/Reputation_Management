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
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from .settings import api_settings

try:
    from ..db import db
    from . import flags
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import flags  # type: ignore

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


def token_is_revoked(payload: dict, revoked_at) -> bool:
    """True if this token (by its `iat`) predates the user's revocation time -- i.e. it was
    issued before a 'sign out everywhere' and must be rejected. JWT `iat` is whole-second, so
    we compare at WHOLE-SECOND granularity: a token minted later in the SAME second as the
    revoke (e.g. an immediate re-login) is NOT falsely killed, while every token from an
    earlier second is. Worst case a same-second pre-revoke token survives <1s -- acceptable."""
    iat = payload.get("iat")
    if iat is None or revoked_at is None:
        return False
    return int(iat) < int(revoked_at.timestamp())


def revoke_sessions(conn, user_id: int) -> None:
    """Invalidate ALL outstanding tokens for a user (stamp the revocation time = now)."""
    conn.execute("UPDATE users SET sessions_revoked_at=now() WHERE id=%s", (user_id,))
    conn.commit()


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
        # platform-level capability + the global billing master switch, so the SPA can gate UI
        "is_super_admin": bool(user.get("is_super_admin")),
        "billing_enabled": flags.billing_enabled(conn),
    }


# ---------------------------------------------------------------------------
# Single-use action tokens (invite / password reset / email verification)
# ---------------------------------------------------------------------------
def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_action_token(conn, user_id: int, kind: str, ttl_hours: int) -> str:
    """Create a single-use token of `kind` for a user and return the RAW token (emailed in
    the link). Only its hash is stored, so a DB read cannot reconstruct a working link."""
    raw = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO auth_tokens (user_id, kind, token_hash, expires_at) "
        "VALUES (%s,%s,%s, now() + make_interval(hours => %s))",
        (user_id, kind, _hash_token(raw), ttl_hours),
    )
    return raw


def consume_action_token(conn, kind: str, raw: str) -> Optional[int]:
    """Validate + single-use-consume a token. Returns the user_id on success, else None."""
    row = conn.execute(
        "SELECT id, user_id FROM auth_tokens WHERE kind=%s AND token_hash=%s "
        "AND used_at IS NULL AND expires_at > now() FOR UPDATE",
        (kind, _hash_token(raw)),
    ).fetchone()
    if not row:
        return None
    conn.execute("UPDATE auth_tokens SET used_at=now() WHERE id=%s", (row["id"],))
    return row["user_id"]


def set_password(conn, user_id: int, new_password: str) -> None:
    """Set a user's password and activate them (used by invite-accept + reset)."""
    conn.execute("UPDATE users SET password_hash=%s, is_active=TRUE WHERE id=%s",
                 (hash_password(new_password), user_id))


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


# The single platform owner who can flip the billing master switch (nobody else).
SUPER_ADMIN_EMAIL = "logan@nexgenixai.com"


def seed_super_admin() -> Optional[int]:
    """Ensure the platform super-admin (logan@nexgenixai.com) exists as an admin + is_super_admin,
    using the SAME password as the seed admin (ADMIN_SEED_PASSWORD). Idempotent: creates the user
    if missing, and always (re)asserts is_super_admin=TRUE so the switch can't be lost. No-op when
    ADMIN_SEED_PASSWORD is unset. Returns the user id, else None."""
    s = api_settings()
    if not s.admin_password:
        return None
    with db() as conn:
        existing = get_user_by_email(conn, SUPER_ADMIN_EMAIL)
        if existing:
            conn.execute("UPDATE users SET is_super_admin=TRUE, role='admin', is_active=TRUE WHERE id=%s",
                         (existing["id"],))
            conn.commit()
            return existing["id"]
        row = conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role, is_super_admin) "
            "VALUES (%s,%s,%s,'admin',TRUE) RETURNING id",
            (SUPER_ADMIN_EMAIL, hash_password(s.admin_password), "Logan (Platform Owner)"),
        ).fetchone()
        conn.commit()
        return row["id"]
