"""
Reputation Crowding-Out Engine -- Cost Tracking + Budget Caps
=============================================================
Lightweight helper to (a) estimate and record the cost of each model call into
the cost_ledger table, and (b) enforce a per-business monthly budget so audits
can't run away. Used by ai_state_audit's LLM/answer-engine calls.

Pricing is approximate and MUST be updated to current rates -- see PRICING.
Costs are estimates for budgeting/COGS visibility, not billing-grade figures.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger("cost")

DB_DSN = os.getenv("REP_DB_DSN", "postgresql://USER:PASSWORD@localhost:5432/reputation")  # PH 1

# Approx USD per 1K tokens (input, output). UPDATE to current provider pricing.  PH 2
PRICING = {
    # model substring : (input_per_1k, output_per_1k)
    # NOTE: more specific keys MUST come first (substring match stops at first hit).
    "haiku":       (0.0008, 0.004),  # cheap tier (Anthropic) -- approx, update to current
    "gpt-4o-mini": (0.00015, 0.0006),  # cheap tier (OpenAI) -- approx, update to current
    "claude":      (0.003, 0.015),
    "gpt-4o":      (0.005, 0.015),
    "gpt":         (0.005, 0.015),
    "sonar":       (0.001, 0.001),   # perplexity (approx; varies by model)
    "gemini":      (0.00125, 0.005),
    "_default":    (0.003, 0.015),
}


def db() -> psycopg.Connection:
    return psycopg.connect(DB_DSN, row_factory=dict_row)


def _rate(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, rate in PRICING.items():
        if key != "_default" and key in m:
            return rate
    return PRICING["_default"]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    ri, ro = _rate(model)
    return round((input_tokens / 1000.0) * ri + (output_tokens / 1000.0) * ro, 5)


def approx_tokens(text: str) -> int:
    """Rough token estimate when the provider doesn't return usage (~4 chars/token)."""
    return max(1, int(len(text or "") / 4))


def record(business_id: int | None, run_id: int | None, provider: str, operation: str,
           model: str, input_tokens: int, output_tokens: int) -> float:
    cost = estimate_cost(model, input_tokens, output_tokens)
    try:
        with db() as conn:
            conn.execute(
                """INSERT INTO cost_ledger
                   (business_id, run_id, provider, operation, model,
                    input_tokens, output_tokens, est_cost_usd)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (business_id, run_id, provider, operation, model,
                 input_tokens, output_tokens, cost),
            )
            conn.commit()
    except Exception as e:  # noqa: BLE001  -- never let cost logging break an audit
        log.warning("cost record failed: %s", e)
    return cost


def month_spend(business_id: int) -> float:
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(est_cost_usd),0) s FROM cost_ledger "
                "WHERE business_id=%s AND created_at >= date_trunc('month', now())",
                (business_id,),
            ).fetchone()
        return float(row["s"])
    except Exception:  # noqa: BLE001
        return 0.0


def budget_for(business_id: int) -> float:
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT monthly_budget_usd FROM business_config WHERE business_id=%s",
                (business_id,),
            ).fetchone()
        return float(row["monthly_budget_usd"]) if row else 50.0
    except Exception:  # noqa: BLE001
        return 50.0


def over_budget(business_id: int) -> bool:
    spent, cap = month_spend(business_id), budget_for(business_id)
    if spent >= cap:
        log.warning("Business %d over monthly budget: $%.2f / $%.2f", business_id, spent, cap)
        return True
    return False
