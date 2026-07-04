"""
Canonical audit-run selectors
==============================
ONE place that decides "which run does this reader see", so the fast-tier / kind='ai_audit'
guards can never silently drift across the many inline pickers again (they did -- twice; see the
engine-hardening review). Three reader classes:

- FULL-run readers (deltas, trends, durable scores, attribution, learning, baselines): compare or
  persist ACROSS runs, so a thin 'fast' first-look run would produce a bogus delta. They exclude
  fast:  latest_full_run / recent_full_runs.
- DISPLAY readers (a single latest run for current-state KPIs): SHOW a fast run so a brand-new
  tenant sees their first-look score before the ~30-50 min full audit lands:  latest_display_run.
- SCORED / other readers (re-score or root-cause a specific run): a run_id is normally passed; the
  auto-latest fallback is kind-scoped + finished, fast-agnostic:  latest_scored_run.

Every helper scopes `kind='ai_audit' AND finished_at IS NOT NULL`. A competitor / local_rank run
is not an AI audit and deliberately leaves finished_at NULL, so it can never leak into any of
these. Helpers take an open connection (callers are already inside a `with db() as conn` block).
"""
from __future__ import annotations

# Canonical guard fragments -- kept as named constants so the intent is greppable and single-source.
_AI_FINISHED = "kind='ai_audit' AND finished_at IS NOT NULL"
_FULL = _AI_FINISHED + " AND COALESCE(mode,'full')<>'fast'"


def latest_full_run(conn, business_id: int, *, after: int | None = None) -> int | None:
    """Newest full (non-fast) ai_audit run id -- the pick for deltas / durable scores / baselines.
    `after` bounds it to runs strictly newer than a given run id (content_impact re-measure)."""
    sql = "SELECT id FROM audit_runs WHERE business_id=%s AND " + _FULL
    params: list = [business_id]
    if after is not None:
        sql += " AND id > %s"
        params.append(after)
    sql += " ORDER BY id DESC LIMIT 1"
    r = conn.execute(sql, tuple(params)).fetchone()
    return r["id"] if r else None


def recent_full_runs(conn, business_id: int, *, limit: int | None = 2,
                     order: str = "desc", cols: str = "id") -> list:
    """The most recent full (non-fast) ai_audit runs, for a two-run delta (limit=2) or a full
    time-series (limit=None). `cols` lets a caller also select finished_at / started_at; `order`
    'asc' returns them chronologically. Rows are returned as-is (dict rows)."""
    o = "ASC" if order == "asc" else "DESC"
    sql = f"SELECT {cols} FROM audit_runs WHERE business_id=%s AND {_FULL} ORDER BY id {o}"
    if limit is not None:
        sql += " LIMIT %s"
        return conn.execute(sql, (business_id, limit)).fetchall()
    return conn.execute(sql, (business_id,)).fetchall()


def latest_display_run(conn, business_id: int, *, require_complete: bool = False,
                       extra_sql: str = "", extra_params: tuple = ()) -> int | None:
    """Newest ai_audit run for a CURRENT-STATE display (per-engine/per-prompt KPIs, lenses,
    challenge, public teaser, COGS, citation SoV). A 'fast' first-look IS eligible so a brand-new
    tenant sees something. `extra_sql` appends a predicate (e.g. \"AND COALESCE(failed_count,0)>0\"
    or a freshness window) with its `extra_params`."""
    sql = "SELECT id FROM audit_runs WHERE business_id=%s AND " + _AI_FINISHED
    params: list = [business_id]
    if require_complete:
        sql += " AND status='complete'"
    if extra_sql:
        sql += " " + extra_sql
        params.extend(extra_params)
    sql += " ORDER BY id DESC LIMIT 1"
    r = conn.execute(sql, tuple(params)).fetchone()
    return r["id"] if r else None


def latest_scored_run(conn, business_id: int) -> int | None:
    """Auto-latest fallback for re-score / root-cause / attach helpers (a run_id is normally
    passed explicitly). kind-scoped + finished, fast-agnostic -- a fast run is still scoreable and
    a valid attach target."""
    r = conn.execute(
        "SELECT id FROM audit_runs WHERE business_id=%s AND " + _AI_FINISHED +
        " ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    return r["id"] if r else None
