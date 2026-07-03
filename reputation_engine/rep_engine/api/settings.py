"""API-only runtime settings, read from the environment.

Separate from the engine's `config.py` (which validates the DB/LLM config). These
are HTTP/auth concerns: the JWT secret, token TTL, CORS origins, the seed-admin
credentials, and the background-job mode. Read fresh each call so tests can set
env per-test; cheap enough to not cache.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiSettings:
    jwt_secret: str
    jwt_ttl_min: int
    cors_origins: list[str]
    admin_email: str
    admin_password: str
    job_worker: str       # 'inline' (dev: run jobs in-process) | 'worker' (separate process)
    cookie_secure: bool   # set the Secure flag on auth cookies (REQUIRED in prod / over HTTPS)
    cookie_samesite: str  # 'lax' (default) | 'strict' (same-site console) | 'none' (cross-site, forces Secure)


def api_settings() -> ApiSettings:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET is not set -- the console API needs a stable secret to sign "
            "auth tokens. Set JWT_SECRET in the environment (any long random string)."
        )
    origins = [o.strip() for o in os.getenv("API_CORS_ORIGINS", "http://localhost:3000").split(",")
               if o.strip()]
    # Cookie security is env-driven so local dev over http://localhost and the test client
    # keep working (defaults: not Secure, SameSite=Lax) while production hardens via env:
    #   same-site console+API -> COOKIE_SECURE=1, COOKIE_SAMESITE=strict
    #   cross-site (different registrable domains) -> COOKIE_SECURE=1, COOKIE_SAMESITE=none
    samesite = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    cookie_secure = os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")
    if samesite == "none":
        cookie_secure = True   # browsers reject SameSite=None cookies without the Secure flag
    return ApiSettings(
        jwt_secret=secret,
        jwt_ttl_min=int(os.getenv("JWT_TTL_MIN", "720")),
        cors_origins=origins,
        admin_email=os.getenv("ADMIN_SEED_EMAIL", "").strip(),
        admin_password=os.getenv("ADMIN_SEED_PASSWORD", ""),
        job_worker=os.getenv("JOB_WORKER", "inline").strip().lower(),
        cookie_secure=cookie_secure,
        cookie_samesite=samesite,
    )
