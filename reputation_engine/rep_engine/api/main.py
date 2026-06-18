"""FastAPI application for the Reputation Console.

Run:  uvicorn rep_engine.api.main:app --reload
Env:  REP_DB_DSN (db), JWT_SECRET (auth), optional ADMIN_SEED_EMAIL/ADMIN_SEED_PASSWORD
      (seed a first admin on startup), API_CORS_ORIGINS (default http://localhost:3000).
"""

from __future__ import annotations

import logging
import os
import threading
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
    billing_router,
    businesses,
    content,
    insights,
    integrations,
    jobs_router,
    onboarding_router,
    prompts_router,
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


_scheduler_stop = threading.Event()


def _scheduler_loop() -> None:
    """In-process scheduler + job runner for single-process (inline) deployments like the
    demo, where there is no separate worker. Each minute: enqueue due recurring jobs, then
    drain the queue. Worker-mode deployments leave this off and let the worker do it."""
    from .. import scheduler
    from . import jobs as _jobs
    while not _scheduler_stop.is_set():
        try:
            scheduler.tick()
            drained = 0
            while drained < 20 and _jobs.pump():
                drained += 1
        except Exception as e:  # noqa: BLE001
            log.warning("in-process scheduler loop error: %s", e)
        _scheduler_stop.wait(60)


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
    try:
        from .. import billing
        billing.seed_plans()
        log.info("Plan catalog seeded")
    except Exception as e:  # noqa: BLE001 -- never let seeding crash startup
        log.warning("seed_plans skipped: %s", e)
    # Run the scheduler in-process when there's no separate worker (inline mode) and it
    # hasn't been explicitly disabled. Worker-mode deployments run scheduler.tick() in the
    # worker instead.
    run_inproc = (api_settings().job_worker == "inline"
                  and os.getenv("SCHEDULER_IN_API", "1").lower() not in ("0", "false", "no"))
    if run_inproc:
        _scheduler_stop.clear()
        threading.Thread(target=_scheduler_loop, daemon=True, name="rc-scheduler").start()
        log.info("In-process scheduler started")
    yield
    _scheduler_stop.set()
    close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Reputation Console API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        # Only the headers the SPA actually sends -- not a wildcard. (A wildcard is also
        # invalid alongside allow_credentials=True per the CORS spec.)
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def _security_headers(request, call_next):
        # Baseline hardening headers on every response. HSTS only matters over HTTPS and is
        # gated on the same flag as Secure cookies so it isn't sent in local http dev.
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # API responses carry tenant data -- never let a shared cache hold them.
        response.headers.setdefault("Cache-Control", "no-store")
        if api_settings().cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Public, token-based flows carry their own credential in the body (a single-use token)
    # and never rely on an ambient session cookie, so CSRF protection is moot for them.
    _CSRF_EXEMPT = {"/auth/login", "/auth/logout", "/auth/accept-invite",
                    "/auth/reset-password", "/auth/forgot-password", "/billing/webhook"}

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

    @app.get("/livez", tags=["meta"])
    def livez():
        # Liveness: the process is up and serving. (No dependency checks.)
        return {"status": "ok"}

    @app.get("/readyz", tags=["meta"])
    def readyz():
        # Readiness: DB reachable, and (in worker mode) the worker heartbeat is fresh.
        from fastapi.responses import JSONResponse
        checks: dict = {}
        try:
            from ..db import db
            with db() as c:
                c.execute("SELECT 1")
            checks["db"] = "ok"
        except Exception as e:  # noqa: BLE001
            checks["db"] = f"error: {str(e)[:120]}"
        if api_settings().job_worker == "worker":
            from .worker import seconds_since_heartbeat
            age = seconds_since_heartbeat()
            checks["worker"] = "ok" if (age is not None and age < 120) else (
                f"stale ({int(age)}s)" if age is not None else "no heartbeat")
        healthy = all(v == "ok" for v in checks.values())
        return JSONResponse(status_code=200 if healthy else 503,
                            content={"status": "ok" if healthy else "degraded", "checks": checks})

    app.include_router(auth_router.router)
    app.include_router(onboarding_router.router)
    app.include_router(billing_router.router)
    app.include_router(businesses.router)
    app.include_router(audits.router)
    app.include_router(insights.router)
    app.include_router(content.router)
    app.include_router(rankings.router)
    app.include_router(sustain.router)
    app.include_router(prompts_router.router)
    app.include_router(jobs_router.router)
    app.include_router(admin.router)
    app.include_router(integrations.router)
    return app


app = create_app()


def main() -> None:  # pragma: no cover -- convenience entrypoint
    import uvicorn
    # Bind localhost by default (don't expose the dev server on all interfaces); a
    # container/host that needs 0.0.0.0 sets API_HOST explicitly.
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("rep_engine.api.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":  # pragma: no cover
    main()
