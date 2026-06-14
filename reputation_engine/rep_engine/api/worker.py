"""Durable background worker: poll api_jobs and run queued jobs out-of-process.

Use this (JOB_WORKER=worker) instead of inline BackgroundTasks for anything that
survives a web-process restart -- and run it with AGENT_CHECKPOINT_PG=1 so the
human-gated graphs (incident/remediation) can resume across processes. run_job()
claims atomically, so N workers are safe.

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


def _next_queued() -> Optional[int]:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM api_jobs WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
    return row["id"] if row else None


def run_forever(poll_seconds: float = 3.0) -> None:  # pragma: no cover -- long-running loop
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    log.info("api worker started; polling every %.1fs", poll_seconds)
    while True:
        job_id = _next_queued()
        if job_id is None:
            time.sleep(poll_seconds)
            continue
        log.info("running job %s", job_id)
        jobs.run_job(job_id)   # atomic claim makes this safe even with multiple workers


if __name__ == "__main__":  # pragma: no cover
    run_forever()
