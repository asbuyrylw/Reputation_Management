"""
Run-state -- resumable pipeline execution with per-step checkpointing.

Wraps the orchestrator's steps so that a failed or interrupted run can be resumed
without re-spending API budget on steps that already completed. Each step is
recorded in pipeline_steps; on resume, completed steps are skipped.

Also provides a structured, run-scoped logger so every line in a run is tagged
with the pipeline_run_id and business_id -- making multi-client logs filterable.

Usage:
    rs = RunState.start(business_id, kind="cycle")          # or .resume_latest(...)
    rs.step("audit", lambda: m1.audit(bid))
    rs.step("gap_model", lambda: m1.build_gap_model(bid))
    ...
    rs.finish()
"""

from __future__ import annotations

import logging
from typing import Callable, Optional


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

try:
    from . import logging_setup
    log = logging_setup.get_logger("runstate")
    _bind = logging_setup.bind
except ImportError:  # pragma: no cover
    log = logging.getLogger("runstate")
    def _bind(**kwargs):  # type: ignore
        pass





class RunState:
    def __init__(self, run_id: int, business_id: int, kind: str, resumed: bool = False):
        self.run_id = run_id
        self.business_id = business_id
        self.kind = kind
        self.resumed = resumed
        self._done_keys: set[str] = set()
        _bind(business_id=business_id, run_id=run_id)
        self._load_done()

    # ----- lifecycle -----
    @classmethod
    def start(cls, business_id: int, kind: str, resume: bool = True) -> "RunState":
        """Start a new run, or resume the most recent unfinished run of this kind
        for this business when resume=True."""
        _ensure_tables()
        if resume:
            with db() as conn:
                row = conn.execute(
                    "SELECT id FROM pipeline_runs WHERE business_id=%s AND kind=%s "
                    "AND status IN ('in_progress','failed') ORDER BY id DESC LIMIT 1",
                    (business_id, kind),
                ).fetchone()
            if row:
                # re-open the run so it's in_progress again while we retry
                with db() as conn:
                    conn.execute("UPDATE pipeline_runs SET status='in_progress', finished_at=NULL WHERE id=%s",
                                 (row["id"],))
                    conn.commit()
                log.info("Resuming %s run %d for business %d", kind, row["id"], business_id)
                return cls(row["id"], business_id, kind, resumed=True)
        with db() as conn:
            row = conn.execute(
                "INSERT INTO pipeline_runs (business_id, kind, status) VALUES (%s,%s,'in_progress') RETURNING id",
                (business_id, kind),
            ).fetchone()
            conn.commit()
        log.info("Started %s run %d for business %d", kind, row["id"], business_id)
        return cls(row["id"], business_id, kind)

    def _load_done(self) -> None:
        with db() as conn:
            rows = conn.execute(
                "SELECT step_key FROM pipeline_steps WHERE pipeline_run_id=%s AND status='done'",
                (self.run_id,),
            ).fetchall()
        self._done_keys = {r["step_key"] for r in rows}
        if self._done_keys:
            log.info("Run %d already completed steps: %s", self.run_id, ", ".join(sorted(self._done_keys)))

    # ----- step execution -----
    def step(self, key: str, fn: Callable[[], object], label: Optional[str] = None) -> object:
        """Run a step unless already done. Records status; re-raises on failure
        after marking the step failed so the run can be resumed later."""
        if key in self._done_keys:
            log.info("[run %d] skip '%s' (already done)", self.run_id, key)
            return None
        with db() as conn:
            conn.execute(
                """INSERT INTO pipeline_steps (pipeline_run_id, step_key, status, started_at)
                   VALUES (%s,%s,'pending', now())
                   ON CONFLICT (pipeline_run_id, step_key) DO UPDATE SET started_at=now(), status='pending'""",
                (self.run_id, key),
            )
            conn.commit()
        log.info("[run %d] %s", self.run_id, label or key)
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001
            with db() as conn:
                conn.execute(
                    "UPDATE pipeline_steps SET status='failed', error=%s, finished_at=now() "
                    "WHERE pipeline_run_id=%s AND step_key=%s",
                    (str(e)[:1000], self.run_id, key),
                )
                conn.execute("UPDATE pipeline_runs SET status='failed' WHERE id=%s", (self.run_id,))
                conn.commit()
            log.error("[run %d] step '%s' FAILED: %s -- run is resumable", self.run_id, key, e)
            raise
        with db() as conn:
            conn.execute(
                "UPDATE pipeline_steps SET status='done', finished_at=now() "
                "WHERE pipeline_run_id=%s AND step_key=%s",
                (self.run_id, key),
            )
            conn.commit()
        self._done_keys.add(key)
        return result

    def finish(self) -> None:
        with db() as conn:
            conn.execute("UPDATE pipeline_runs SET status='complete', finished_at=now() WHERE id=%s",
                         (self.run_id,))
            conn.commit()
        log.info("[run %d] complete (%s for business %d)", self.run_id, self.kind, self.business_id)


def runs_status(business_id: int) -> list[dict]:
    """List recent pipeline runs + their step states for a business (diagnostics)."""
    _ensure_tables()
    with db() as conn:
        runs = conn.execute(
            "SELECT id, kind, status, started_at, finished_at FROM pipeline_runs "
            "WHERE business_id=%s ORDER BY id DESC LIMIT 10", (business_id,),
        ).fetchall()
        out = []
        for r in runs:
            steps = conn.execute(
                "SELECT step_key, status, error FROM pipeline_steps WHERE pipeline_run_id=%s ORDER BY id",
                (r["id"],),
            ).fetchall()
            out.append({**dict(r), "steps": [dict(s) for s in steps]})
    return out


def _ensure_tables() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS pipeline_runs (
            id BIGSERIAL PRIMARY KEY, business_id BIGINT, kind TEXT, status TEXT DEFAULT 'in_progress',
            started_at TIMESTAMPTZ DEFAULT now(), finished_at TIMESTAMPTZ)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS pipeline_steps (
            id BIGSERIAL PRIMARY KEY, pipeline_run_id BIGINT REFERENCES pipeline_runs(id),
            step_key TEXT, status TEXT DEFAULT 'pending', error TEXT,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, UNIQUE (pipeline_run_id, step_key))""")
        conn.commit()
