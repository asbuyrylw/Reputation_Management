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
    jobs_router,
    rankings,
    sustain,
)

log = logging.getLogger("rep_engine.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    return app


app = create_app()


def main() -> None:  # pragma: no cover -- convenience entrypoint
    import uvicorn
    uvicorn.run("rep_engine.api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":  # pragma: no cover
    main()
