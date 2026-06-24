"""
Notifications / alerting -- the proactive side of the managed service.
======================================================================
notify() records an in-app notification (deduped) and best-effort emails the business's
people. check_and_notify(business_id) inspects the latest state and raises alerts when
something needs attention:
  - score_drop        the reputation score fell meaningfully vs the prior audit
  - new_incident      a contested mention was triaged into a pending incident
  - negative_mention  a new negative mention was captured
  - drafts_waiting    content drafts are waiting for human review

It is safe to run on a schedule (the 'alert_check' job): dedup_key keeps it from re-alerting
the same thing. Email goes out only when email_service is configured; otherwise the in-app
feed still works.

CLI:
    python -m rep_engine.notifications check --business-id 1
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("rep_engine.notifications")

SCORE_DROP_POINTS = 5  # alert when the 0-100 score falls by at least this much


def _recipients(conn, business_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT email FROM users WHERE is_active AND ("
        " org_id = (SELECT org_id FROM businesses WHERE id=%s)"
        " OR id IN (SELECT user_id FROM business_access WHERE business_id=%s))",
        (business_id, business_id),
    ).fetchall()
    return [r["email"] for r in rows if r["email"]]


def notify(business_id: int, kind: str, title: str, body: str = "", severity: str = "info",
           dedup_key: Optional[str] = None, email: bool = True) -> Optional[int]:
    """Record a notification (deduped on dedup_key) and best-effort email recipients.
    Returns the new id, or None if it was a duplicate."""
    with db() as conn:
        row = conn.execute(
            "INSERT INTO notifications (business_id, kind, title, body, severity, dedup_key) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (business_id, dedup_key) DO NOTHING RETURNING id",
            (business_id, kind, title, body, severity, dedup_key),
        ).fetchone()
        if not row:
            return None
        recips = _recipients(conn, business_id) if email else []
        conn.commit()
    if recips:
        try:
            from . import email_service
            if email_service.enabled():
                for to in recips:
                    email_service.send_email(to, f"[Reputation] {title}", body or title)
        except Exception as e:  # noqa: BLE001 -- email must never break alerting
            log.debug("alert email skipped: %s", e)
    return row["id"]


def _avg_alignment(conn, run_id: int) -> Optional[float]:
    v = conn.execute("SELECT AVG(goal_alignment) g FROM answers WHERE run_id=%s "
                     "AND NOT COALESCE(failed,false)", (run_id,)).fetchone()["g"]
    return float(v) if v is not None else None


def check_and_notify(business_id: int, quiet: bool = True) -> dict:
    """Inspect the latest state and raise any needed alerts. Returns counts."""
    created = {"score_drop": 0, "new_incident": 0, "negative_mention": 0, "drafts_waiting": 0,
               "degraded_audit": 0}

    with db() as conn:
        runs = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 2", (business_id,)).fetchall()
        # latest completed run's provider-failure info (an AI provider was down/erroring)
        degraded = conn.execute(
            "SELECT id, failed_count, failed_engines FROM audit_runs WHERE business_id=%s "
            "AND finished_at IS NOT NULL AND kind='ai_audit' AND COALESCE(failed_count,0) > 0 "
            "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        incidents = conn.execute(
            "SELECT id, severity FROM incidents WHERE business_id=%s AND status='pending_human_review'",
            (business_id,)).fetchall()
        neg_mentions = conn.execute(
            "SELECT id, title FROM mentions WHERE business_id=%s AND status='new' AND sentiment='negative' "
            "ORDER BY id DESC LIMIT 25", (business_id,)).fetchall()
        drafts_n = conn.execute(
            "SELECT COUNT(*) c FROM content_drafts WHERE business_id=%s AND status='pending_review'",
            (business_id,)).fetchone()["c"]

    # 1. score drop
    if len(runs) == 2:
        with db() as conn:
            cur, prev = _avg_alignment(conn, runs[0]["id"]), _avg_alignment(conn, runs[1]["id"])
        if cur is not None and prev is not None:
            cur_s, prev_s = round((cur + 1) / 2 * 100), round((prev + 1) / 2 * 100)
            if prev_s - cur_s >= SCORE_DROP_POINTS:
                if notify(business_id, "score_drop",
                          f"Your AI reputation score dropped to {cur_s}/100",
                          f"Down {prev_s - cur_s} points from {prev_s} since the last audit. "
                          "Review what changed and prioritize the plan.",
                          severity="warning", dedup_key=f"score_drop_run_{runs[0]['id']}"):
                    created["score_drop"] += 1

    # 1b. degraded audit — an AI provider was down/erroring, so the run is partial
    if degraded:
        engines = degraded.get("failed_engines")
        eng_txt = ", ".join(engines) if isinstance(engines, list) and engines else "one or more AI engines"
        if notify(business_id, "degraded_audit", "Your last audit was partial",
                  f"{degraded['failed_count']} answer(s) failed ({eng_txt} was unavailable). The score "
                  "may be incomplete — retry the failed engines from the Audits page.",
                  severity="warning", dedup_key=f"degraded_run_{degraded['id']}", email=False):
            created["degraded_audit"] += 1

    # 2. new incidents
    for inc in incidents:
        if notify(business_id, "new_incident", "A serious negative mention needs your response",
                  f"Incident #{inc['id']} (severity {inc['severity']}) is waiting for approval of a drafted reply.",
                  severity="critical", dedup_key=f"incident_{inc['id']}"):
            created["new_incident"] += 1

    # 3. negative mentions
    for m in neg_mentions:
        if notify(business_id, "negative_mention", "New negative mention found",
                  (m["title"] or "A new negative mention was captured.")[:180],
                  severity="warning", dedup_key=f"mention_{m['id']}", email=False):
            created["negative_mention"] += 1

    # 4. drafts waiting (once/day)
    if drafts_n:
        import datetime
        # use the latest draft id as a stable key proxy (changes when new drafts arrive)
        with db() as conn:
            last_draft = conn.execute(
                "SELECT MAX(id) m FROM content_drafts WHERE business_id=%s AND status='pending_review'",
                (business_id,)).fetchone()["m"]
        del datetime
        if notify(business_id, "drafts_waiting", f"{drafts_n} content draft(s) waiting for review",
                  "Approve or send back the drafts to keep the plan moving.",
                  severity="info", dedup_key=f"drafts_waiting_{last_draft}"):
            created["drafts_waiting"] += 1

    if not quiet:
        log.info("alerts for business %d: %s", business_id, created)
    return created


def list_notifications(business_id: int, unread_only: bool = False, limit: int = 50) -> list[dict]:
    where = "business_id=%s" + (" AND NOT read" if unread_only else "")
    with db() as conn:
        rows = conn.execute(
            f"SELECT id, kind, title, body, severity, read, created_at FROM notifications "  # nosec B608
            f"WHERE {where} ORDER BY id DESC LIMIT %s", (business_id, limit)).fetchall()
    return [dict(r) for r in rows]


def unread_count(business_id: int) -> int:
    with db() as conn:
        return conn.execute("SELECT COUNT(*) c FROM notifications WHERE business_id=%s AND NOT read",
                            (business_id,)).fetchone()["c"]


def mark_read(business_id: int, notification_id: int) -> bool:
    with db() as conn:
        r = conn.execute("UPDATE notifications SET read=TRUE WHERE id=%s AND business_id=%s RETURNING id",
                         (notification_id, business_id)).fetchone()
        conn.commit()
    return bool(r)


def mark_all_read(business_id: int) -> int:
    with db() as conn:
        rows = conn.execute("UPDATE notifications SET read=TRUE WHERE business_id=%s AND NOT read RETURNING id",
                            (business_id,)).fetchall()
        conn.commit()
    return len(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description="Notifications / alerting")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "check":
        print(check_and_notify(args.business_id, quiet=False))


if __name__ == "__main__":  # pragma: no cover
    main()
