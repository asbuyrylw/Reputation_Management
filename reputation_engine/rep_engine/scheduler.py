"""
Recurring-job scheduler -- the "managed service" spine.
=======================================================
A `schedules` row = "run job_type for business_id every interval_hours". tick() finds every
due schedule (enabled AND next_run_at <= now), atomically advances its next_run_at, and
enqueues the job via the existing api_jobs queue (which dedups + is run by the worker or the
in-process runner). This is what makes continuous monitoring actually continuous instead of
depending on a human clicking Run.

Idempotent + crash-safe: the UPDATE ... RETURNING claims each due schedule in one statement,
so two schedulers can't both fire the same one, and jobs.enqueue refuses a duplicate while a
prior run is still active.

CLI:
    python -m rep_engine.scheduler tick            # run one tick
    python -m rep_engine.scheduler set --business-id 1 --job cycle --hours 720
"""

from __future__ import annotations

import argparse
import logging

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("rep_engine.scheduler")

# Sensible default cadences (hours) for a managed account, used when seeding/UX defaults.
DEFAULT_CADENCES = {
    "cycle": 720,          # full monthly cycle ~ every 30 days
    "mentions_scan": 24,   # daily mention sweep
    "incident_scan": 24,   # daily incident triage
    "citation_analyze": 168,  # weekly
}


def list_schedules(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, job_type, interval_hours, enabled, next_run_at, last_run_at, created_at "
            "FROM schedules WHERE business_id=%s ORDER BY job_type", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def upsert_schedule(business_id: int, job_type: str, interval_hours: int,
                    enabled: bool = True) -> dict:
    from .api import jobs
    if job_type not in jobs.JOB_DISPATCH:
        raise ValueError(f"unknown job_type: {job_type}")
    interval_hours = max(1, int(interval_hours))
    with db() as conn:
        row = conn.execute(
            "INSERT INTO schedules (business_id, job_type, interval_hours, enabled, next_run_at) "
            "VALUES (%s,%s,%s,%s, now() + make_interval(hours => %s)) "
            "ON CONFLICT (business_id, job_type) DO UPDATE SET "
            "interval_hours=EXCLUDED.interval_hours, enabled=EXCLUDED.enabled "
            "RETURNING id, job_type, interval_hours, enabled, next_run_at, last_run_at",
            (business_id, job_type, interval_hours, enabled, interval_hours)).fetchone()
        conn.commit()
    return dict(row)


def delete_schedule(business_id: int, schedule_id: int) -> bool:
    with db() as conn:
        r = conn.execute("DELETE FROM schedules WHERE id=%s AND business_id=%s RETURNING id",
                         (schedule_id, business_id)).fetchone()
        conn.commit()
    return bool(r)


def tick(quiet: bool = True) -> int:
    """Enqueue every due schedule, advancing its next_run_at. Returns the count enqueued.
    Atomic claim + enqueue-dedup make this safe to call from multiple processes."""
    from .api import jobs
    with db() as conn:
        due = conn.execute(
            "UPDATE schedules SET last_run_at=now(), "
            "next_run_at = now() + make_interval(hours => interval_hours) "
            "WHERE enabled AND next_run_at <= now() "
            "RETURNING business_id, job_type"
        ).fetchall()
        conn.commit()
    enq = 0
    for d in due:
        try:
            jid, _active = jobs.enqueue(d["business_id"], d["job_type"])
            if jid:
                enq += 1
        except Exception as e:  # noqa: BLE001 -- one bad schedule must not stop the rest
            log.warning("schedule enqueue failed (%s/%s): %s", d["business_id"], d["job_type"], e)
    if enq and not quiet:
        log.info("scheduler tick enqueued %d job(s)", enq)
    return enq


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description="Recurring-job scheduler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tick")
    s = sub.add_parser("set")
    s.add_argument("--business-id", type=int, required=True)
    s.add_argument("--job", required=True)
    s.add_argument("--hours", type=int, required=True)
    s.add_argument("--disabled", action="store_true")
    args = ap.parse_args()
    if args.cmd == "tick":
        print(f"enqueued {tick(quiet=False)} job(s)")
    elif args.cmd == "set":
        print(upsert_schedule(args.business_id, args.job, args.hours, enabled=not args.disabled))


if __name__ == "__main__":  # pragma: no cover
    main()
