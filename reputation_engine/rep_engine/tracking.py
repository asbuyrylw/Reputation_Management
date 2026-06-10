"""
Reputation Crowding-Out Engine -- Module 5: Execution Tracking + Attribution
===========================================================================
Turns a generated strategy plan into a tracked, status-bearing program of work,
records what actually gets published, and correlates metric movement with the
assets shipped in each interval. This is the system of record that makes the
service a RETAINER (ongoing execution) rather than a one-time plan.

Capabilities
------------
- sync-plan      : materialize the latest strategy_plan's work orders into the
                   work_orders table (idempotent on wo_code).
- set-status     : move a work order through its lifecycle and timestamp it.
- log-asset      : record a published asset / corroboration event.
- attribute      : between the two most recent audit runs, compute metric deltas
                   and list the assets published in that window (correlational).
- check-alert    : flag a contested-rate spike above the business's threshold.
- status         : print a program status summary (counts by status, % complete).

Attribution is explicitly CORRELATIONAL and labeled as such in outputs and in the
client report -- we report "these actions preceded this change," never a causal claim.

Run:
    python -m rep_engine.tracking sync-plan   --business-id 1
    python -m rep_engine.tracking set-status   --wo 12 --status done --assignee "VA" --notes "Published"
    python -m rep_engine.tracking log-asset     --business-id 1 --type owned_page \
        --title "How we protect Cincinnati families" --url https://... --surface own_site --wo 12
    python -m rep_engine.tracking attribute     --business-id 1
    python -m rep_engine.tracking check-alert    --business-id 1
    python -m rep_engine.tracking status         --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("tracking")





VALID_STATUS = {"pending", "in_progress", "done", "verified", "skipped", "blocked"}


# ----------------------------------------------------------------------------
# sync-plan: materialize plan work orders into trackable rows
# ----------------------------------------------------------------------------
def sync_plan(business_id: int) -> int:
    with db() as conn:
        plan_row = conn.execute(
            "SELECT id, plan FROM strategy_plans WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
        if not plan_row:
            raise SystemExit("No strategy plan found -- generate one first.")
        plan = plan_row["plan"] if isinstance(plan_row["plan"], dict) else json.loads(plan_row["plan"])
        wos = plan.get("work_orders", []) or []
        created, skipped = 0, 0
        for w in wos:
            code = w.get("wo_id")
            exists = conn.execute(
                "SELECT id FROM work_orders WHERE business_id=%s AND plan_id=%s AND wo_code=%s",
                (business_id, plan_row["id"], code),
            ).fetchone()
            if exists:
                skipped += 1
                continue
            td = w.get("target_date")
            conn.execute(
                """INSERT INTO work_orders
                   (business_id, plan_id, wo_code, title, capability, execution,
                    recommended_tool, instruction, phase, target_date, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')""",
                (business_id, plan_row["id"], code, w.get("title"), w.get("capability"),
                 w.get("execution"), w.get("recommended_tool"), w.get("instruction"),
                 w.get("phase"), date.fromisoformat(td) if td else None),
            )
            created += 1
        conn.commit()
    log.info("sync-plan: %d created, %d already tracked", created, skipped)
    return created


# ----------------------------------------------------------------------------
# set-status: lifecycle transitions with timestamps
# ----------------------------------------------------------------------------
def set_status(wo_id: int, status: str, assignee: str | None, notes: str | None) -> None:
    if status not in VALID_STATUS:
        raise SystemExit(f"status must be one of {sorted(VALID_STATUS)}")
    now = datetime.now()
    sets = ["status=%s", "updated_at=now()"]
    params: list = [status]
    if assignee:
        sets.append("assignee=%s"); params.append(assignee)
    if notes:
        sets.append("result_notes=%s"); params.append(notes)
    if status == "in_progress":
        sets.append("started_at=COALESCE(started_at, %s)"); params.append(now)
    if status == "done":
        sets.append("completed_at=%s"); params.append(now)
    if status == "verified":
        sets.append("verified_at=%s"); params.append(now)
    params.append(wo_id)
    with db() as conn:
        conn.execute(f"UPDATE work_orders SET {', '.join(sets)} WHERE id=%s", tuple(params))
        conn.commit()
    log.info("WO %d -> %s", wo_id, status)


# ----------------------------------------------------------------------------
# log-asset: record what actually shipped
# ----------------------------------------------------------------------------
def log_asset(business_id: int, asset_type: str, title: str, url: str | None,
              surface: str | None, work_order_id: int | None,
              published_at: datetime | None = None) -> int:
    # published_at is the asset's real GO-LIVE moment. Pass it explicitly when
    # back-filling or when an asset went live earlier than the row is logged, so
    # attribution windows bucket it correctly; default (None) uses the DB's now().
    with db() as conn:
        if published_at is not None:
            row = conn.execute(
                """INSERT INTO assets (business_id, work_order_id, asset_type, title, url, surface, published_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (business_id, work_order_id, asset_type, title, url, surface, published_at),
            ).fetchone()
        else:
            row = conn.execute(
                """INSERT INTO assets (business_id, work_order_id, asset_type, title, url, surface)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (business_id, work_order_id, asset_type, title, url, surface),
            ).fetchone()
        # if tied to a work order, auto-advance it to done if still open
        if work_order_id:
            conn.execute(
                "UPDATE work_orders SET status='done', completed_at=COALESCE(completed_at, now()), "
                "updated_at=now() WHERE id=%s AND status IN ('pending','in_progress')",
                (work_order_id,),
            )
        conn.commit()
    log.info("Logged asset %d (%s)", row["id"], asset_type)
    return row["id"]


# ----------------------------------------------------------------------------
# attribute: correlate metric deltas with assets shipped in the window
# ----------------------------------------------------------------------------
def _run_metrics(conn, run_id: int) -> dict:
    r = conn.execute(
        "SELECT AVG(goal_alignment) ga, "
        "AVG(CASE WHEN mentions_contested THEN 1 ELSE 0 END) contested_rate, "
        "AVG(CASE WHEN surfaces_owned THEN 1 ELSE 0 END) owned_rate "
        "FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)", (run_id,)
    ).fetchone()
    return r


def attribute(business_id: int) -> dict:
    with db() as conn:
        runs = conn.execute(
            "SELECT id, started_at, finished_at FROM audit_runs "
            "WHERE business_id=%s AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 2",
            (business_id,),
        ).fetchall()
        if len(runs) < 2:
            log.info("Need two completed runs to attribute.")
            return {}
        to_run, from_run = runs[0], runs[1]
        cur, prev = _run_metrics(conn, to_run["id"]), _run_metrics(conn, from_run["id"])

        # assets published in the half-open window [from_run, to_run): an asset at
        # exactly a run boundary belongs to the window it STARTS, never both/neither.
        window_start = from_run["finished_at"]
        window_end = to_run["finished_at"]
        assets = conn.execute(
            "SELECT id, asset_type, title, surface, published_at FROM assets "
            "WHERE business_id=%s AND published_at >= %s AND published_at < %s "
            "ORDER BY published_at",
            (business_id, window_start, window_end),
        ).fetchall()
        asset_list = [
            {"id": a["id"], "type": a["asset_type"], "title": a["title"],
             "surface": a["surface"], "published_at": a["published_at"].isoformat()}
            for a in assets
        ]

        def delta(a, b):
            return None if a is None or b is None else round(float(a) - float(b), 4)

        results = {}
        for metric, c, p in [
            ("goal_alignment", cur["ga"], prev["ga"]),
            ("contested_rate", cur["contested_rate"], prev["contested_rate"]),
            ("owned_rate", cur["owned_rate"], prev["owned_rate"]),
        ]:
            d = delta(c, p)
            results[metric] = d
            conn.execute(
                """INSERT INTO attribution (business_id, from_run_id, to_run_id, metric, delta, assets_in_window)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (business_id, from_run["id"], to_run["id"], metric, d, json.dumps(asset_list)),
            )
        conn.commit()
    out = {"deltas": results, "assets_in_window": asset_list,
           "note": "Correlational: assets listed were published between the two audits; "
                   "association is not proof of causation."}
    print(json.dumps(out, indent=2, default=str))
    return out


# ----------------------------------------------------------------------------
# check-alert: contested-rate spike detection
# ----------------------------------------------------------------------------
def check_alert(business_id: int) -> dict:
    with db() as conn:
        cfg = conn.execute(
            "SELECT alert_threshold FROM business_config WHERE business_id=%s", (business_id,)
        ).fetchone()
        threshold = float(cfg["alert_threshold"]) if cfg else 0.15
        runs = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 2", (business_id,),
        ).fetchall()
        if len(runs) < 2:
            return {"alert": False, "reason": "insufficient_runs"}
        cur = _run_metrics(conn, runs[0]["id"])["contested_rate"]
        prev = _run_metrics(conn, runs[1]["id"])["contested_rate"]
        jump = (float(cur) - float(prev)) if cur is not None and prev is not None else 0.0
    alert = jump >= threshold
    out = {"alert": alert, "contested_rate_jump": round(jump, 4), "threshold": threshold}
    if alert:
        out["action"] = ("Contested narrative rose past threshold. Trigger rapid response: "
                         "publish targeted clarifying content, strengthen corroboration, "
                         "review which sources the answer engines newly cited.")
        log.warning("ALERT for business %d: contested rate +%.3f", business_id, jump)
    print(json.dumps(out, indent=2))
    return out


# ----------------------------------------------------------------------------
# status: program summary
# ----------------------------------------------------------------------------
def status(business_id: int) -> dict:
    with db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) n FROM work_orders WHERE business_id=%s GROUP BY status",
            (business_id,),
        ).fetchall()
        assets_n = conn.execute(
            "SELECT COUNT(*) n FROM assets WHERE business_id=%s", (business_id,)
        ).fetchone()["n"]
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    done = counts.get("done", 0) + counts.get("verified", 0)
    out = {"work_orders": counts, "total": total,
           "pct_complete": round(100 * done / total, 1) if total else 0.0,
           "assets_published": assets_n}
    print(json.dumps(out, indent=2))
    return out


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Execution tracking + attribution")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sync-plan"); p.add_argument("--business-id", type=int, required=True)
    p = sub.add_parser("set-status")
    p.add_argument("--wo", type=int, required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--assignee")
    p.add_argument("--notes")
    p = sub.add_parser("log-asset")
    p.add_argument("--business-id", type=int, required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--url")
    p.add_argument("--surface")
    p.add_argument("--wo", type=int)
    p.add_argument("--published-at", help="ISO-8601 go-live timestamp (default: now)")
    for c in ("attribute", "check-alert", "status"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)

    args = ap.parse_args()
    if args.cmd == "sync-plan":
        sync_plan(args.business_id)
    elif args.cmd == "set-status":
        set_status(args.wo, args.status, args.assignee, args.notes)
    elif args.cmd == "log-asset":
        pub = datetime.fromisoformat(args.published_at) if args.published_at else None
        log_asset(args.business_id, args.type, args.title, args.url, args.surface, args.wo, pub)
    elif args.cmd == "attribute":
        attribute(args.business_id)
    elif args.cmd == "check-alert":
        check_alert(args.business_id)
    elif args.cmd == "status":
        status(args.business_id)


if __name__ == "__main__":
    main()
