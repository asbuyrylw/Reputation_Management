"""Durable background worker: poll api_jobs and run queued jobs out-of-process.

Use this (JOB_WORKER=worker) instead of inline BackgroundTasks for anything that
survives a web-process restart -- and run it with AGENT_CHECKPOINT_PG=1 so the
human-gated graphs (incident/remediation) can resume across processes. run_job()
claims atomically, so N workers are safe.

Durability: each tick writes a heartbeat (used by /readyz) and reaps stale 'running'
jobs so a crash mid-job cannot permanently deadlock a tenant's job type. The loop body
is wrapped so a transient DB error never kills the worker.

    python -m rep_engine.api.worker
"""

from __future__ import annotations

import logging
import time
from typing import Optional

try:
    from ..db import db
    from . import jobs
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import jobs  # type: ignore

log = logging.getLogger("rep_engine.api.worker")


def _ensure_heartbeat() -> None:
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS worker_heartbeat ("
                     "id INT PRIMARY KEY, last_seen TIMESTAMPTZ DEFAULT now())")
        conn.execute("INSERT INTO worker_heartbeat (id, last_seen) VALUES (1, now()) "
                     "ON CONFLICT (id) DO NOTHING")
        conn.commit()


def heartbeat() -> None:
    with db() as conn:
        conn.execute("UPDATE worker_heartbeat SET last_seen=now() WHERE id=1")
        conn.commit()


def seconds_since_heartbeat() -> Optional[float]:
    """Age of the worker heartbeat in seconds, or None if never seen (used by /readyz)."""
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT EXTRACT(EPOCH FROM (now() - last_seen)) AS age FROM worker_heartbeat WHERE id=1"
            ).fetchone()
        return float(row["age"]) if row and row["age"] is not None else None
    except Exception:  # noqa: BLE001
        return None


def _next_queued() -> Optional[int]:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM api_jobs WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
    return row["id"] if row else None


def run_forever(poll_seconds: float = 3.0) -> None:  # pragma: no cover -- long-running loop
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    _ensure_heartbeat()
    log.info("api worker started; polling every %.1fs", poll_seconds)
    last_reap = 0.0
    while True:
        try:
            heartbeat()
            now = time.monotonic()
            if now - last_reap > 60:
                jobs.reap_stale()
                try:
                    from .. import scheduler
                    scheduler.tick()   # enqueue any due recurring jobs
                except Exception as e:  # noqa: BLE001
                    log.warning("scheduler tick failed: %s", e)
                last_reap = now
            job_id = _next_queued()
            if job_id is None:
                time.sleep(poll_seconds)
                continue
            log.info("running job %s", job_id)
            jobs.run_job(job_id)   # atomic claim makes this safe even with multiple workers
        except Exception as e:  # noqa: BLE001 -- a transient DB blip must not kill the worker
            log.exception("worker loop error: %s", e)
            time.sleep(poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    run_forever()
