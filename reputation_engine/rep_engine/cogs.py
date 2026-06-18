"""
Reputation Engine -- COGS model + plan-tier proposal
====================================================
Estimates the cost-of-goods (LLM spend) of one audit, then back-solves subscription
tiers so even the cheapest plan clears a target gross margin. LLM spend is the dominant
COGS, so pricing must be grounded in it.

An audit = (battery prompts x engines x samples) answers; each answer costs one engine
call + one cheap scoring call (+ a web-search surcharge for grounded engines), plus one
full-tier gap-model synthesis per audit. Token counts are representative estimates
(documented constants) -- tune them as real usage data arrives. Prices are PROPOSALS at a
target margin; the operator reviews/adjusts them.
"""

from __future__ import annotations

import math

try:
    from . import cost as _cost
except ImportError:  # pragma: no cover
    import cost as _cost  # type: ignore

# Representative per-call token sizes (input, output).
ANSWER_IN, ANSWER_OUT = 700, 500
SCORE_IN, SCORE_OUT = 1200, 200
GAP_IN, GAP_OUT = 9000, 1500

# ~$10 per 1,000 web searches (Anthropic web search; comparable for other grounded engines),
# charged on top of tokens for each grounded answer.
SEARCH_COST = 0.01
CHEAP_MODEL = "haiku"     # the high-volume scoring tier
GAP_MODEL = "opus"        # the full-tier synthesis
# answer-engine model ids, in the canonical order perplexity/openai/anthropic/gemini.
# NOTE: this COGS/tier model is priced for the FOUR CORE engines only. The expansion
# engines (Grok, Google AI Overview, Bing Copilot) are opt-in and OFF by default. They are
# enabled by GLOBAL env keys, so turning one on adds cost to EVERY tenant's audit (roughly:
# Grok/Bing ~= one extra core engine in tokens; Google AI Overview via Serper ~= $0.001 per
# query, negligible tokens). Before enabling any of them in production, raise the relevant
# tiers' max_engines and re-run propose_tiers() so prices aren't set against stale COGS.
DEFAULT_ENGINE_MODELS = ("sonar", "gpt-4o", "opus", "gemini")
# Per-engine model ids if/when the expansion engines are enabled and priced in (Serper has
# no token model -> treated as a flat surcharge, not a chat model, so it's omitted here).
EXPANSION_ENGINE_MODELS = ("grok", "gpt-4o")  # grok billed ~gpt-4o-class; bing via its endpoint

# Tier limits (capabilities) + value-based LIST price. The COGS model derives a margin
# FLOOR (propose_tiers); `list_price` is the headline price we actually charge (value-based,
# always >= floor). Adjust list_price freely -- the floor guards margin if you go too low.
# `max_engines` counts CORE engines (see DEFAULT_ENGINE_MODELS): raise it + recompute before
# enabling expansion engines for a tier.
TIERS = [
    {"code": "starter", "name": "Starter", "list_price": 99, "max_businesses": 1,
     "max_audits_per_month": 4, "max_engines": 2, "max_samples_per_prompt": 2, "battery": 12,
     "seats": 2, "trial_days": 14},
    {"code": "growth", "name": "Growth", "list_price": 299, "max_businesses": 3,
     "max_audits_per_month": 12, "max_engines": 4, "max_samples_per_prompt": 2, "battery": 14,
     "seats": 5, "trial_days": 14},
    {"code": "pro", "name": "Pro", "list_price": 899, "max_businesses": 10,
     "max_audits_per_month": 30, "max_engines": 4, "max_samples_per_prompt": 3, "battery": 16,
     "seats": 15, "trial_days": 14},
    {"code": "agency", "name": "Agency", "list_price": 2499, "max_businesses": 50,
     "max_audits_per_month": 100, "max_engines": 4, "max_samples_per_prompt": 3, "battery": 16,
     "seats": 50, "trial_days": 14},
]


def per_answer_cost(engine_models) -> float:
    """Blended cost of producing + scoring one answer: the average engine answer-call cost
    across the configured engines, plus the cheap scoring call, plus the web-search surcharge."""
    models = list(engine_models)
    eng = sum(_cost.estimate_cost(m, ANSWER_IN, ANSWER_OUT) for m in models) / max(1, len(models))
    score = _cost.estimate_cost(CHEAP_MODEL, SCORE_IN, SCORE_OUT)
    return eng + score + SEARCH_COST


def audit_cogs(*, battery: int = 14, engines: int = 4, samples: int = 2,
               engine_models=None) -> float:
    """Estimated LLM cost (USD) of a single audit at the given shape. For an accurate
    projection, `engines`/`engine_models` should reflect the ACTUAL engines a run uses --
    core only by default, or core + any enabled expansion engines (see EXPANSION_ENGINE_MODELS)."""
    engine_models = list(engine_models or DEFAULT_ENGINE_MODELS)[:max(1, engines)]
    answers = battery * len(engine_models) * samples
    gap = _cost.estimate_cost(GAP_MODEL, GAP_IN, GAP_OUT)
    return round(answers * per_answer_cost(engine_models) + gap, 4)


def _round_price(x: float) -> int:
    """Round a price floor UP to a marketable '...9' number (ceil to the next 50, minus 1)."""
    return max(49, int(math.ceil(x / 50.0) * 50) - 1)


def propose_tiers(target_margin: float = 0.80) -> list[dict]:
    """For each tier, compute monthly COGS at full utilization, the margin FLOOR that clears
    `target_margin`, and the headline price (value-based `list_price`, or the rounded floor if
    none). `price_usd_month` is the headline price; `price_floor` is the margin guardrail."""
    out = []
    for t in TIERS:
        per = audit_cogs(battery=t["battery"], engines=t["max_engines"],
                         samples=t["max_samples_per_prompt"])
        monthly_cogs = round(per * t["max_audits_per_month"], 2)
        floor = monthly_cogs / (1.0 - target_margin) if target_margin < 1 else float("inf")
        floor_price = _round_price(floor)
        price = t.get("list_price") or floor_price
        if price < floor_price:
            # value price dipped below the margin floor -- guardrail: never price under COGS+margin
            price = floor_price
        out.append({**t, "audit_cogs": per, "monthly_cogs": monthly_cogs,
                    "price_floor": round(floor, 2), "price_usd_month": price,
                    "target_margin": target_margin})
    return out
