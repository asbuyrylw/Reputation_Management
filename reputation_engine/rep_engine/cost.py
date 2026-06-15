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


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("cost")


# Approx USD per 1K tokens (input, output). UPDATE to current provider pricing.  PH 2
PRICING = {
    # model substring : (input_per_1k, output_per_1k). Rates current as of 2026-06.
    # NOTE: more specific keys MUST come first (substring match stops at first hit).
    # Anthropic ids look like claude-opus-4-8 / claude-sonnet-4-6 / claude-haiku-4-5,
    # so 'opus'/'sonnet'/'haiku' MUST precede the generic 'claude' fallback -- otherwise
    # 'claude' would catch claude-opus-4-8 at Sonnet's cheaper rate and UNDER-count Opus.
    "haiku":       (0.001, 0.005),   # Haiku 4.5 cheap tier (Anthropic)
    "gpt-4o-mini": (0.00015, 0.0006),  # cheap tier (OpenAI)
    "opus":        (0.005, 0.025),   # Opus 4.8 full tier (Anthropic)
    "sonnet":      (0.003, 0.015),   # Sonnet 4.6 mid tier (Anthropic)
    "claude":      (0.003, 0.015),   # generic Anthropic fallback (Sonnet-equivalent)
    "gpt-4o":      (0.005, 0.015),
    "gpt":         (0.005, 0.015),
    "sonar":       (0.001, 0.001),   # perplexity (approx; varies by model)
    "gemini":      (0.00125, 0.005),
    "_default":    (0.003, 0.015),
}




# Per-business count of cost rows we failed to persist this process. While a business
# has > 0 unrecorded writes its ledger under-counts real spend, so over_budget(business)
# fails CLOSED -- but for THAT business only. A single transient DB blip therefore no
# longer bricks every tenant for the process lifetime, and the flag SELF-HEALS: the next
# successful cost write for a business clears its entry. (A write with business_id=None is
# unattributable to a tenant, so we log it loudly but never let it fail-close other tenants.)
_unrecorded_writes: dict[int, int] = {}


def reset_unrecorded() -> None:
    """Clear the fail-closed flags (test isolation / operational recovery)."""
    _unrecorded_writes.clear()


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
        # A good write means this business's ledger is healthy again: self-heal so a
        # transient blip doesn't fail-close it for the rest of the process.
        if business_id is not None:
            _unrecorded_writes.pop(business_id, None)
    except Exception as e:  # noqa: BLE001  -- never let cost logging crash an audit...
        # ...but DO remember we lost a write for THIS business, so over_budget() fails closed
        # for it (and only it) until a subsequent write succeeds.
        if business_id is not None:
            _unrecorded_writes[business_id] = _unrecorded_writes.get(business_id, 0) + 1
        log.error("cost record FAILED for business %s (spend now under-counted; budget fails "
                  "closed for this business): %s", business_id, e)
    return cost


def month_spend(business_id: int) -> float:
    """Sum of this calendar month's recorded spend, with a UTC month boundary so the
    window doesn't drift by hours when the DB session timezone differs from UTC.
    Raises on DB error so over_budget() can decide policy (it fails closed)."""
    with db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(est_cost_usd),0) s FROM cost_ledger "
            "WHERE business_id=%s "
            "AND created_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
            (business_id,),
        ).fetchone()
    return float(row["s"])


def budget_for(business_id: int) -> float:
    """Configured monthly cap (USD); defaults to 50.0 when no config row exists.
    Raises on DB error (over_budget() fails closed)."""
    with db() as conn:
        row = conn.execute(
            "SELECT monthly_budget_usd FROM business_config WHERE business_id=%s",
            (business_id,),
        ).fetchone()
    return float(row["monthly_budget_usd"]) if row else 50.0


def over_budget(business_id: int) -> bool:
    """True if the business is at/over its monthly cap. Fails CLOSED: if spend can't be
    verified -- a DB error, or a cost write was lost this process -- report over-budget so
    a runaway can't slip through a degraded ledger. The cap is the only runaway guard."""
    lost = _unrecorded_writes.get(business_id, 0)
    if lost:
        log.error("Business %d: %d unrecorded cost write(s) this process -- failing closed.",
                  business_id, lost)
        return True
    try:
        spent, cap = month_spend(business_id), budget_for(business_id)
    except Exception as e:  # noqa: BLE001
        log.error("Business %d: budget check failed (%s) -- failing closed.", business_id, e)
        return True
    if spent >= cap:
        log.warning("Business %d over monthly budget: $%.2f / $%.2f", business_id, spent, cap)
        return True
    return False
