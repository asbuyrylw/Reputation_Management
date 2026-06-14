"""FastAPI application for the Reputation Console.

Run:  uvicorn rep_engine.api.main:app --reload
Env:  REP_DB_DSN (db), JWT_SECRET (auth), optional ADMIN_SEED_EMAIL/ADMIN_SEED_PASSWORD
      (seed a first admin on startup), API_CORS_ORIGINS (default http://localhost:3000).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .pool import close_pool, get_pool
from .settings import api_settings
from . import auth
from .routers import (
    admin,
    audits,
    auth_router,
    businesses,
    content,
    insights,
    integrations,
    jobs_router,
    rankings,
    sustain,
)

log = logging.getLogger("rep_engine.api")


def _auto_migrate() -> None:
    """Run `alembic upgrade head` on startup so the API works on a fresh DB without a
    separate migration step (idempotent). REP_DB_DSN must be set (alembic env.py reads
    it). Best-effort: a failure logs a warning rather than crashing startup."""
    try:
        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        root = Path(__file__).resolve().parents[2]   # reputation_engine/
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "alembic"))
        command.upgrade(cfg, "head")
        log.info("Database migrated to head")
    except Exception as e:  # noqa: BLE001 -- don't let migration crash startup
        log.warning("auto-migrate skipped (%s); ensure migrations are applied manually", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _auto_migrate()
    get_pool()              # open the connection pool eagerly (fails fast on bad DSN)
    try:
        admin_id = auth.seed_admin()
        if admin_id:
            log.info("Seed admin ready (user id=%s)", admin_id)
    except Exception as e:  # noqa: BLE001 -- never let seeding crash startup
        log.warning("seed_admin skipped: %s", e)
    yield
    close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Reputation Console API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _CSRF_EXEMPT = {"/auth/login", "/auth/logout"}

    @app.middleware("http")
    async def _csrf_protect(request, call_next):
        # Double-submit CSRF: cookie-authenticated writes must echo the csrf_token cookie
        # in the X-CSRF-Token header. Bearer (API/script) clients are exempt (a bearer is
        # never auto-sent cross-site), as are login/logout.
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
            has_cookie = bool(request.cookies.get("rc_token"))
            if has_cookie and not has_bearer and request.url.path not in _CSRF_EXEMPT:
                from fastapi.responses import JSONResponse
                header = request.headers.get("x-csrf-token")
                cookie = request.cookies.get("csrf_token")
                if not header or not cookie or header != cookie:
                    return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})
        return await call_next(request)

    @app.middleware("http")
    async def _audit_writes(request, call_next):
        response = await call_next(request)
        # Record every mutating request with the acting user (best-effort; never breaks
        # the request). GETs are not logged.
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            try:
                authz = request.headers.get("authorization", "")
                tok = authz[7:] if authz.lower().startswith("bearer ") else request.cookies.get("rc_token")
                uid = None
                if tok:
                    try:
                        uid = int(auth.decode_token(tok).get("sub"))
                    except Exception:  # noqa: BLE001
                        uid = None
                from ..db import db
                with db() as conn:
                    conn.execute(
                        "INSERT INTO audit_log (user_id, method, path, status_code) VALUES (%s,%s,%s,%s)",
                        (uid, request.method, request.url.path, response.status_code),
                    )
                    conn.commit()
            except Exception as e:  # noqa: BLE001 -- auditing must never break a request
                log.warning("audit_log write skipped: %s", e)
        return response

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(auth_router.router)
    app.include_router(businesses.router)
    app.include_router(audits.router)
    app.include_router(insights.router)
    app.include_router(content.router)
    app.include_router(rankings.router)
    app.include_router(sustain.router)
    app.include_router(jobs_router.router)
    app.include_router(admin.router)
    app.include_router(integrations.router)
    return app


app = create_app()


def main() -> None:  # pragma: no cover -- convenience entrypoint
    import uvicorn
    uvicorn.run("rep_engine.api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":  # pragma: no cover
    main()
