"""
Reputation Engine -- billing: plans, subscriptions, usage metering, quota/entitlement gates
===========================================================================================
The organization (Phase 2a) is the account a customer pays under. This module seeds the plan
catalog (from the COGS model), manages one subscription per org, meters usage (audits/month),
and provides the gate that stops LLM-spending work when an org is inactive or over quota.

BACKWARD-COMPATIBLE: a business with no org, or an org with no subscription, is UNMETERED
(legacy / grandfathered) -- existing flows and tests are unaffected. Enforcement applies only
once an org is actually on a plan. Stripe wiring (status transitions from webhooks) is Phase 2c;
here, status is set directly (admin assign / trial).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

try:
    from .db import db
    from . import cogs as _cogs
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import cogs as _cogs  # type: ignore

log = logging.getLogger("billing")

ACTIVE_STATUSES = ("trialing", "active")
# job types that consume one "audit" against the monthly audit quota (they create audit_runs)
AUDIT_JOB_TYPES = ("audit", "cycle")


# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------
def seed_plans() -> None:
    """Idempotently seed plan_catalog from the COGS-derived tiers (prices are proposals,
    editable by the operator). Safe to call on every startup."""
    with db() as conn:
        for i, t in enumerate(_cogs.propose_tiers()):
            conn.execute(
                """INSERT INTO plan_catalog
                   (code, name, price_usd_month, max_businesses, max_audits_per_month,
                    max_engines, max_samples_per_prompt, seats, trial_days, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (code) DO UPDATE SET
                     name=EXCLUDED.name, price_usd_month=EXCLUDED.price_usd_month,
                     max_businesses=EXCLUDED.max_businesses,
                     max_audits_per_month=EXCLUDED.max_audits_per_month,
                     max_engines=EXCLUDED.max_engines,
                     max_samples_per_prompt=EXCLUDED.max_samples_per_prompt,
                     seats=EXCLUDED.seats, trial_days=EXCLUDED.trial_days,
                     sort_order=EXCLUDED.sort_order""",
                (t["code"], t["name"], t["price_usd_month"], t["max_businesses"],
                 t["max_audits_per_month"], t["max_engines"], t["max_samples_per_prompt"],
                 t["seats"], t["trial_days"], i),
            )
        conn.commit()


def list_plans(conn) -> list:
    return conn.execute(
        "SELECT * FROM plan_catalog WHERE is_active ORDER BY sort_order, price_usd_month"
    ).fetchall()


def get_plan(conn, code: str) -> Optional[dict]:
    return conn.execute("SELECT * FROM plan_catalog WHERE code=%s", (code,)).fetchone()


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------
def org_for_business(conn, business_id: int) -> Optional[int]:
    row = conn.execute("SELECT org_id FROM businesses WHERE id=%s", (business_id,)).fetchone()
    return row["org_id"] if row else None


def get_subscription(conn, org_id: Optional[int]) -> Optional[dict]:
    if not org_id:
        return None
    return conn.execute("SELECT * FROM subscriptions WHERE org_id=%s", (org_id,)).fetchone()


def subscribe(conn, org_id: int, plan_code: str, status: str = "trialing",
              trial_days: Optional[int] = None) -> dict:
    """Assign/replace an org's plan (one subscription per org). When status is 'trialing',
    trial_end defaults to the plan's trial_days from now. Caller commits."""
    plan = get_plan(conn, plan_code)
    if not plan:
        raise ValueError(f"unknown plan: {plan_code}")
    td = plan["trial_days"] if trial_days is None else trial_days
    return conn.execute(
        """INSERT INTO subscriptions
              (org_id, plan_code, status, current_period_start, current_period_end, trial_end)
           VALUES (%s,%s,%s, now(), now() + interval '1 month',
                   CASE WHEN %s = 'trialing' THEN now() + make_interval(days => %s) ELSE NULL END)
           ON CONFLICT (org_id) DO UPDATE SET
              plan_code=EXCLUDED.plan_code, status=EXCLUDED.status,
              current_period_start=EXCLUDED.current_period_start,
              current_period_end=EXCLUDED.current_period_end,
              trial_end=EXCLUDED.trial_end, updated_at=now()
           RETURNING *""",
        (org_id, plan_code, status, status, td),
    ).fetchone()


def is_active(sub: Optional[dict]) -> bool:
    """Active if status is trialing/active AND (for a trial) the trial hasn't expired."""
    if not sub or sub["status"] not in ACTIVE_STATUSES:
        return False
    if sub["status"] == "trialing" and sub.get("trial_end"):
        return sub["trial_end"] >= datetime.now(timezone.utc)
    return True


# ---------------------------------------------------------------------------
# Usage metering + quota gate
# ---------------------------------------------------------------------------
def audits_used(conn, org_id: int) -> int:
    """Audit runs started this calendar month across all of the org's businesses."""
    row = conn.execute(
        "SELECT COUNT(*) n FROM audit_runs ar JOIN businesses b ON b.id = ar.business_id "
        "WHERE b.org_id=%s AND ar.started_at >= date_trunc('month', now() AT TIME ZONE 'UTC')",
        (org_id,),
    ).fetchone()
    return int(row["n"])


def usage_summary(conn, org_id: Optional[int]) -> dict:
    sub = get_subscription(conn, org_id)
    plan = get_plan(conn, sub["plan_code"]) if sub and sub.get("plan_code") else None
    used = audits_used(conn, org_id) if org_id else 0
    n_biz = 0
    if org_id:
        n_biz = int(conn.execute("SELECT COUNT(*) n FROM businesses WHERE org_id=%s",
                                 (org_id,)).fetchone()["n"])
    return {
        "subscription": dict(sub) if sub else None,
        "plan": dict(plan) if plan else None,
        "active": is_active(sub),
        "usage": {"audits_this_month": used, "businesses": n_biz},
    }


def check_can_trigger(conn, business_id: int, job_type: str) -> tuple[bool, str, int]:
    """Gate for LLM-spending job triggers. Returns (ok, reason, http_code).

    Order: no org or no subscription => unmetered/grandfathered (ok); inactive subscription
    => 402; audit-type job over the monthly audit quota => 429; otherwise ok."""
    org_id = org_for_business(conn, business_id)
    if not org_id:
        return True, "", 0
    sub = get_subscription(conn, org_id)
    if not sub:
        return True, "", 0
    if not is_active(sub):
        return (False,
                "Your subscription is inactive or the trial has ended -- update billing to continue.",
                402)
    if job_type in AUDIT_JOB_TYPES:
        plan = get_plan(conn, sub["plan_code"]) if sub.get("plan_code") else None
        cap = plan["max_audits_per_month"] if plan else None
        if cap is not None and audits_used(conn, org_id) >= cap:
            return (False,
                    f"Monthly audit limit reached for the {sub['plan_code']} plan ({cap}). "
                    "Upgrade your plan to run more.",
                    429)
    return True, "", 0
