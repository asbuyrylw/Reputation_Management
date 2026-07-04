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
import re
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
def _norm_title(t: str | None) -> str:
    """Normalized task identity: lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (t or "").lower())).strip()


def _task_key(capability: str | None, title: str | None,
              gap_source: str | None = None, source_query: str | None = None) -> str:
    """Stable identity for a task. Computed the same way for a plan item and for an existing row,
    so the merge recognizes 'the same task' across regenerations.

    Prefer a GAP-ANCHORED identity when the task carries a gap linkage: (capability + gap_source +
    source_query) is stable across LLM plan regenerations, whereas the free-text TITLE gets reworded
    every revision -- which used to archive the live work order and spawn a duplicate (the root of
    the superseded-row churn). Fall back to (capability + normalized title) for items with no gap
    linkage, preserving the prior behavior. Because task_key is stored at creation, a gap-anchored
    key also survives a human renaming the displayed title."""
    cap = (capability or "").lower()
    gs = (gap_source or "").strip().lower()
    sq = (source_query or "").strip().lower()
    if gs and sq:
        return f"{cap}|gap|{gs}|{sq}"
    return f"{cap}|{_norm_title(title)}"


def sync_plan(business_id: int) -> dict:
    """Materialize the latest strategy plan into trackable work_orders -- as an ADDITIVE MERGE.

    - Existing tasks (and their status/progress) are PRESERVED; matched by stable task_key.
    - Only genuinely-new tasks are added, tagged with the current plan revision ("Revision N · new").
    - A not-yet-started, plan-generated task that the new plan no longer recommends is ARCHIVED
      (superseded=TRUE) rather than left to pile up; it REVIVES if a later plan recommends it again.
    - Done / in-progress / manual tasks are never archived.
    Idempotent. Returns {revision, created, carried_forward, retired, revived, done, drafted, open}.
    """
    with db() as conn:
        plan_row = conn.execute(
            "SELECT id, plan FROM strategy_plans WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
        if not plan_row:
            raise SystemExit("No strategy plan found -- generate one first.")
        plan = plan_row["plan"] if isinstance(plan_row["plan"], dict) else json.loads(plan_row["plan"])
        wos = plan.get("work_orders", []) or []
        revision = conn.execute(
            "SELECT COUNT(*) c FROM strategy_plans WHERE business_id=%s", (business_id,)
        ).fetchone()["c"]
        existing = conn.execute(
            "SELECT w.id, w.title, w.capability, w.status, w.plan_id, w.superseded, w.task_key, "
            "w.gap_specifics, w.why_helps_ai_rep, w.why_helps_seo, w.gap_source, "
            "EXISTS(SELECT 1 FROM content_drafts d WHERE d.work_order_id=w.id) AS has_draft "
            "FROM work_orders w WHERE w.business_id=%s",
            (business_id,),
        ).fetchall()
        # Compute the stable (gap-anchored) key for an EXISTING row from its stored columns.
        # This is the NEW scheme; we always recompute (never trust the stored task_key here) so
        # rows whose task_key was minted under the old title-based scheme migrate cleanly. The row
        # already SELECTs gap_source + gap_specifics, so gap linkage is available fail-safe.
        def _existing_key(e) -> str:
            src_q = (e.get("gap_specifics") or {}).get("source_query") if isinstance(
                e.get("gap_specifics"), dict) else None
            return _task_key(e["capability"], e["title"], e.get("gap_source"), src_q)

        # index existing by stable key
        by_key: dict = {}
        for e in existing:
            by_key.setdefault(_existing_key(e), e)

        plan_keys: set = set()
        created = 0
        revived = 0
        carried = {"done": 0, "drafted": 0, "open": 0}
        for w in wos:
            key = _task_key(
                w.get("capability"), w.get("title"),
                (w.get("rationale") or {}).get("gap_source"),
                (w.get("gap_specifics") or {}).get("source_query"),
            )
            plan_keys.add(key)
            match = by_key.get(key)
            if match:
                if match["status"] in ("done", "verified"):
                    carried["done"] += 1
                elif match["has_draft"]:
                    carried["drafted"] += 1
                else:
                    carried["open"] += 1
                # a task the plan recommends again should not stay archived
                if match["superseded"]:
                    conn.execute("UPDATE work_orders SET superseded=FALSE, updated_at=now() WHERE id=%s",
                                 (match["id"],))
                    revived += 1
                # backfill the worst-answer link (gap_specifics.source_query) onto a carried-forward
                # task so the "fix the worst things" deep-link works on existing tasks too, not just
                # freshly-created ones.
                src = (w.get("gap_specifics") or {}).get("source_query")
                if src and not (match.get("gap_specifics") or {}).get("source_query"):
                    conn.execute("UPDATE work_orders SET gap_specifics=%s, updated_at=now() WHERE id=%s",
                                 (json.dumps({"source_query": src}), match["id"]))
                # Backfill task CONTEXT onto carried-forward rows: older generator revisions left
                # why_helps_*/gap_source NULL, so the console showed no "why" + no "From:" for them.
                # COALESCE only fills what's currently missing -- never overwrites human/existing text.
                _bf_src = (w.get("rationale") or {}).get("gap_source") or ""
                if ((w.get("why_helps_ai_rep") and not match.get("why_helps_ai_rep"))
                        or (w.get("why_helps_seo") and not match.get("why_helps_seo"))
                        or (_bf_src and not (match.get("gap_source") or "").strip())):
                    conn.execute(
                        "UPDATE work_orders SET why_helps_ai_rep=COALESCE(why_helps_ai_rep, %s), "
                        "why_helps_seo=COALESCE(why_helps_seo, %s), "
                        "gap_source=COALESCE(NULLIF(gap_source,''), %s), updated_at=now() WHERE id=%s",
                        (w.get("why_helps_ai_rep"), w.get("why_helps_seo"), _bf_src or None, match["id"]))
                continue
            td = w.get("target_date")
            sd = w.get("start_date")
            rationale = w.get("rationale") or {}
            conn.execute(
                """INSERT INTO work_orders
                   (business_id, plan_id, wo_code, title, capability, execution,
                    recommended_tool, instruction, phase, target_date, status,
                    rationale, gap_source, why_helps_ai_rep, why_helps_seo, added_in_revision,
                    start_date, predicted_ai_points, predicted_seo_impact, predicted_basis, task_key,
                    area, platform, gap_specifics)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (business_id, plan_row["id"], w.get("wo_id"), w.get("title"), w.get("capability"),
                 w.get("execution"), w.get("recommended_tool"), w.get("instruction"),
                 w.get("phase"), date.fromisoformat(td) if td else None,
                 json.dumps(rationale), rationale.get("gap_source"),
                 w.get("why_helps_ai_rep"), w.get("why_helps_seo"), revision,
                 date.fromisoformat(sd) if sd else None, w.get("predicted_ai_points"),
                 w.get("predicted_seo_impact"), w.get("predicted_basis"), key,
                 w.get("area") or None, w.get("platform") or None,
                 json.dumps(w.get("gap_specifics") or {})),
            )
            created += 1

        # Retire: plan-generated, not-yet-started tasks the new plan dropped (preserve done/
        # in-progress/manual). RECOMPUTE each row's task_key to the NEW gap-anchored scheme and
        # persist the re-key when it changed -- a ONE-TIME migration so old title-based keys move to
        # gap-based keys and matching stays stable on the next run (not perpetual churn). Comparison
        # uses the recomputed key so it lines up with plan_keys computed under the same scheme.
        retired = 0
        for e in existing:
            k = _existing_key(e)
            if e["task_key"] != k:
                conn.execute("UPDATE work_orders SET task_key=%s WHERE id=%s", (k, e["id"]))
            if (e["plan_id"] is not None and e["status"] == "pending"
                    and not e["superseded"] and k not in plan_keys):
                conn.execute("UPDATE work_orders SET superseded=TRUE, updated_at=now() WHERE id=%s",
                             (e["id"],))
                retired += 1

        # Prune ancient cruft: plan-generated, never-drafted, still-pending tasks that were added
        # 2+ revisions ago AND are superseded won't realistically revive and just bloat the table
        # (title-churn across LLM regenerations mints near-duplicates). Keep anything with a draft,
        # a non-pending status, or added within the last 2 revisions (still revivable). Bounded delete.
        pruned = conn.execute(
            "DELETE FROM work_orders w WHERE w.business_id=%s AND w.superseded=TRUE "
            "AND w.plan_id IS NOT NULL AND w.status='pending' "
            "AND COALESCE(w.added_in_revision, 0) <= %s "
            "AND NOT EXISTS (SELECT 1 FROM content_drafts d WHERE d.work_order_id=w.id) "
            "RETURNING w.id",
            (business_id, max(0, revision - 2)),
        ).fetchall()
        conn.commit()
    carried_total = sum(carried.values())
    log.info("sync-plan rev %d: +%d new, carried %d (%d done/%d drafted/%d open), retired %d, "
             "revived %d, pruned %d", revision, created, carried_total, carried["done"],
             carried["drafted"], carried["open"], retired, revived, len(pruned))
    return {"revision": revision, "created": created, "carried_forward": carried_total,
            "retired": retired, "revived": revived, "pruned": len(pruned), **carried}


# ----------------------------------------------------------------------------
# create: a manual (ad-hoc) work order outside the generated plan
# ----------------------------------------------------------------------------
def create_work_order(business_id: int, title: str, *, instruction: str | None = None,
                      capability: str | None = None, recommended_tool: str | None = None,
                      target_date: str | None = None, assignee: str | None = None,
                      gap_source: str | None = None, source_query: str | None = None,
                      area: str | None = None, why_helps_ai_rep: str | None = None,
                      why_helps_seo: str | None = None) -> int:
    """Add a manual work order (an ad-hoc task the owner/admin wants tracked alongside the
    plan-generated ones), carrying gap lineage when it comes from a gap item ("turn into task").
    plan_id is NULL; wo_code is a per-business MANUAL-<n>. IDEMPOTENT: if an OPEN task with the same
    title already exists (e.g. the plan already materialized it, or the owner clicked twice), returns
    that id instead of creating a duplicate. Returns the work-order id."""
    title = (title or "").strip()
    if not title:
        raise ValueError("title required")
    td: date | None = None
    if target_date:
        td = target_date if isinstance(target_date, date) else date.fromisoformat(str(target_date))
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM work_orders WHERE business_id=%s AND lower(title)=lower(%s) "
            "AND NOT COALESCE(superseded,false) AND status NOT IN ('done','verified','skipped') "
            "ORDER BY id DESC LIMIT 1", (business_id, title)).fetchone()
        if existing:
            return existing["id"]
        n = conn.execute(
            "SELECT COUNT(*) c FROM work_orders WHERE business_id=%s AND wo_code LIKE 'MANUAL-%%'",
            (business_id,),
        ).fetchone()["c"]
        gs = json.dumps({"source_query": source_query}) if source_query else None
        row = conn.execute(
            """INSERT INTO work_orders (business_id, wo_code, title, capability, instruction,
                recommended_tool, target_date, assignee, gap_source, gap_specifics, area,
                why_helps_ai_rep, why_helps_seo, phase, status, planned)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual','pending',TRUE) RETURNING id""",
            (business_id, f"MANUAL-{n + 1}", title, capability, instruction,
             recommended_tool, td, assignee, gap_source, gs, area, why_helps_ai_rep, why_helps_seo),
        ).fetchone()
        conn.commit()
    log.info("Created manual work order %d for business %d", row["id"], business_id)
    return row["id"]


# ----------------------------------------------------------------------------
# set-status: lifecycle transitions with timestamps
# ----------------------------------------------------------------------------
_DONE_STATES = ("done", "verified")


def log_action(conn, *, business_id: int, capability: str | None, title: str | None,
               completed_on: date, work_order_id: int | None = None,
               production_brief_id: int | None = None, source: str = "work_order",
               area: str | None = None, platform: str | None = None,
               logged_by: str | None = None, notes: str | None = None) -> None:
    """Upsert a row into the actions_taken log -- the task-type-aware unit the feedback loop
    correlates to audit-over-audit needle movement. Idempotent per work_order/brief (re-marking
    done just updates the date), so completing a task ALWAYS leaves a durable, dated trace even when
    the actual work was done outside the platform. Uses the caller's connection (no commit here)."""
    key_col = "work_order_id" if work_order_id is not None else (
        "production_brief_id" if production_brief_id is not None else None)
    cols = ("business_id, work_order_id, production_brief_id, source, capability, area, platform, "
            "title, completed_on, logged_by, notes")
    vals = (business_id, work_order_id, production_brief_id, source, capability, area, platform,
            title, completed_on, logged_by, notes)
    if key_col:  # upsert on the work_order/brief unique index
        conn.execute(
            f"INSERT INTO actions_taken ({cols}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            f"ON CONFLICT ({key_col}) DO UPDATE SET completed_on=EXCLUDED.completed_on, "
            f"capability=EXCLUDED.capability, area=EXCLUDED.area, platform=EXCLUDED.platform, "
            f"title=EXCLUDED.title, source=EXCLUDED.source, notes=EXCLUDED.notes, logged_at=now()",
            vals)
    else:  # manual one-off action (no FK) -- plain insert
        conn.execute(f"INSERT INTO actions_taken ({cols}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", vals)


def set_status(wo_id: int, status: str, assignee: str | None, notes: str | None,
               completed_on: date | str | None = None, actor: str | None = None) -> None:
    """Set a work order's status. When it moves to done/verified, stamp completion and log an
    actions_taken row (the impact-learning unit). `completed_on` is the REAL completion date -- it
    may be BACK-DATED for work done outside the system; defaults to today. Reverting away from a
    done state removes the logged action so the impact correlation stays honest."""
    if status not in VALID_STATUS:
        raise SystemExit(f"status must be one of {sorted(VALID_STATUS)}")
    now = datetime.now()
    cdate = _coerce_date(completed_on) or date.today()
    completed_ts = datetime(cdate.year, cdate.month, cdate.day)  # back-dated completion timestamp
    sets = ["status=%s", "updated_at=now()"]
    params: list = [status]
    if assignee:
        sets.append("assignee=%s"); params.append(assignee)
    if notes:
        sets.append("result_notes=%s"); params.append(notes)
    if status == "in_progress":
        sets.append("started_at=COALESCE(started_at, %s)"); params.append(now)
    if status == "done":
        sets.append("completed_at=%s"); params.append(completed_ts)
    if status == "verified":
        sets.append("verified_at=%s"); params.append(completed_ts)
        sets.append("completed_at=COALESCE(completed_at, %s)"); params.append(completed_ts)
    params.append(wo_id)
    with db() as conn:
        # B608 false positive: every element of `sets` is a literal "col=%s" fragment
        # built above (no user input in the SQL text); all values are bound parameters.
        conn.execute(f"UPDATE work_orders SET {', '.join(sets)} WHERE id=%s", tuple(params))  # nosec B608
        if status in _DONE_STATES:
            wo = conn.execute("SELECT business_id, capability, title FROM work_orders WHERE id=%s",
                              (wo_id,)).fetchone()
            if wo and wo["business_id"]:
                log_action(conn, business_id=wo["business_id"], capability=wo["capability"],
                           title=wo["title"], completed_on=cdate, work_order_id=wo_id,
                           source="work_order", logged_by=actor, notes=notes)
        else:
            # reverted from done -> drop the logged action so it no longer counts toward impact
            conn.execute("DELETE FROM actions_taken WHERE work_order_id=%s", (wo_id,))
        conn.commit()
    log.info("WO %d -> %s", wo_id, status)


# ----------------------------------------------------------------------------
# promote / progress notes: move a recommendation onto the managed board
# ----------------------------------------------------------------------------
def _coerce_date(v) -> date | None:
    if not v:
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def promote_work_order(wo_id: int, business_id: int, *, assignee: str | None = None,
                       assignee_user_id: int | None = None,
                       start_date=None, target_date=None, note: str | None = None,
                       actor: str | None = None) -> bool:
    """Promote a recommendation onto the managed 'Improvement tasks' board: mark it planned,
    set the owner + start/due dates, stamp promoted_at/by, and log the first progress note.
    Idempotent -- re-promoting just updates the fields (promoted_at/by are kept from first time).
    Returns False if the work order isn't in this business."""
    sd, td = _coerce_date(start_date), _coerce_date(target_date)
    sets = ["planned=TRUE", "updated_at=now()", "promoted_at=COALESCE(promoted_at, now())"]
    params: list = []
    if actor:
        sets.append("promoted_by=COALESCE(promoted_by, %s)"); params.append(actor)
    if assignee is not None:
        sets.append("assignee=%s"); params.append(assignee.strip() or None)
    if assignee_user_id is not None:
        sets.append("assignee_user_id=%s"); params.append(assignee_user_id or None)
    if start_date is not None:
        sets.append("start_date=%s"); params.append(sd)
    if target_date is not None:
        sets.append("target_date=%s"); params.append(td)
    if note and note.strip():
        entry = {"text": note.strip(), "author": actor or "", "at": datetime.now().isoformat()}
        sets.append("progress_notes = COALESCE(progress_notes,'[]'::jsonb) || %s::jsonb")
        params.append(json.dumps([entry]))
    params.append(wo_id); params.append(business_id)
    with db() as conn:
        # B608 false positive: `sets` elements are literal "col=..." fragments; values are bound.
        row = conn.execute(
            f"UPDATE work_orders SET {', '.join(sets)} WHERE id=%s AND business_id=%s RETURNING id",  # nosec B608
            tuple(params),
        ).fetchone()
        conn.commit()
    if row:
        log.info("WO %d promoted to managed board", wo_id)
    return bool(row)


def add_progress_note(wo_id: int, business_id: int, text: str, author: str | None = None) -> bool:
    """Append a {text, author, at} entry to a task's progress-notes log. Returns False if the
    work order isn't in this business."""
    text = (text or "").strip()
    if not text:
        raise ValueError("note text required")
    entry = {"text": text, "author": author or "", "at": datetime.now().isoformat()}
    with db() as conn:
        row = conn.execute(
            "UPDATE work_orders SET progress_notes = COALESCE(progress_notes,'[]'::jsonb) || %s::jsonb, "
            "updated_at=now() WHERE id=%s AND business_id=%s RETURNING id",
            (json.dumps([entry]), wo_id, business_id),
        ).fetchone()
        conn.commit()
    return bool(row)


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
            "WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 2",
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
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (business_id, from_run_id, to_run_id, metric) DO UPDATE SET
                     delta=EXCLUDED.delta, assets_in_window=EXCLUDED.assets_in_window""",
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
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "AND COALESCE(mode,'full')<>'fast' ORDER BY id DESC LIMIT 2", (business_id,),
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
