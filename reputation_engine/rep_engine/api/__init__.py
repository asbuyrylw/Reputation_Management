"""
rep_engine.api -- a read+write FastAPI layer over the verified Reputation Engine.

PURELY ADDITIVE: this package never modifies the CLI engine. It reuses db.db()
and the engine's existing aggregation functions, and adds auth + multi-tenancy +
a background-job runner. Hard rules (see the console plan):
  * no LLM spend inside a request -- engine-spending work runs as a background job
    so cost.over_budget and audit()'s advisory lock stay the backstops;
  * human gates (draft/incident/reply approval) only advance via explicit endpoints;
  * every scoped route enforces business_id authorization.

Run:  uvicorn rep_engine.api.main:app --reload    (needs REP_DB_DSN + JWT_SECRET)
"""


def _load_local_dotenv() -> None:
    """Load reputation_engine/.env into the environment so the API "just works" with
    `uvicorn rep_engine.api.main:app` (config.py reads os.environ; it doesn't auto-load
    .env). Never overrides an already-set var, and is skipped under pytest so a dev
    .env can't bleed into the test database."""
    import os
    import sys
    from pathlib import Path

    if "pytest" in sys.modules:
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"   # reputation_engine/.env
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:  # noqa: BLE001 -- a malformed .env must not block startup
        pass


_load_local_dotenv()
