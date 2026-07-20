"""
Business strategy profile (Phase 0.1).
======================================
`derive(biz)` -> a business-agnostic StrategyProfile dict that every downstream layer will read to
self-tune: compliance rules, credential/byline phrasing, persona lenses + contested probes,
authoritative sources, challenge calibration + success target, content-type mix, review sites,
social channels, and the off-strategy content cap. GENERIC is the default; the resolved industry
bucket + geo-derived regulator + the persisted per-tenant override (businesses.strategy_profile
JSONB) layer on top.

PURE + DB-free: `derive()` takes a biz dict the caller already loaded (zero added queries on the
audit/generation/scoring hot paths). `for_business(id)` is a fail-safe loader. `enrich_at_onboarding`
is the only place that could call an LLM to normalize a truly free-text industry -- off the hot path.

Phase 0.1 lands the deriver + registry + the cache column with ZERO behavior change -- NOTHING reads
the profile yet. Later tasks thread it into the seams (compliance stack, GAP/GEN prompts, challenge
thresholds, ...). The GENERIC profile reproduces today's generic behavior and the financial_services
bucket reproduces the finance pilot's, so those seam swaps won't regress the pilot.
"""

from __future__ import annotations

import copy
from typing import Optional

try:
    from . import industry_profiles as _ip
    from .db import db
except ImportError:  # pragma: no cover
    import industry_profiles as _ip  # type: ignore
    from db import db  # type: ignore

_FINANCE_FIRMS = ("ria", "broker_dealer", "insurance")


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def derive(biz: dict, *, overrides: Optional[dict] = None) -> dict:
    """Build the StrategyProfile for a business. Pure -- no DB / network.

    biz keys used (all optional): industry, firm_type OR regulatory_profile.firm_type, geo,
    contested_terms, name, services. overrides: the persisted per-tenant strategy_profile JSONB
    (operator edits, applied LAST)."""
    biz = biz or {}
    rp = biz.get("regulatory_profile") if isinstance(biz.get("regulatory_profile"), dict) else {}
    firm_type = (biz.get("firm_type") or (rp or {}).get("firm_type") or "").strip().lower()
    bucket_key = _ip.bucket_for(biz.get("industry"), firm_type)
    profile = _deep_merge(_ip.GENERIC, _ip.BUCKETS.get(bucket_key, {}))

    # finance sub-type carried through; regulated derived (explicit firm_type wins, else bucket default)
    profile["firm_type"] = firm_type
    if firm_type in _FINANCE_FIRMS:
        profile["regulated"] = True

    # Resolve a state-specific regulator from geo when the bucket declares a template (so a Cincinnati
    # OH finance tenant reads "the Ohio Department of Insurance" -- derived, not a global constant).
    tmpl = profile.pop("regulator_template", "")
    if tmpl:
        state = _ip.state_from_geo(biz.get("geo"))
        profile["regulator"] = tmpl.format(state=state or "your state's")

    # A contested probe (MLM/"pyramid scheme", or anything) fires ONLY when the tenant declared
    # contested terms -- NEVER planted by industry. Kills the finance-only pyramid probe leaking out.
    contested = (biz.get("contested_terms") or "").strip()
    profile["contested_probe"] = bool(contested)
    profile["contested_terms"] = contested

    # has_local_presence follows the ARCHETYPE (bucket default): local-service/professional verticals
    # are local; b2b_saas/ecommerce are not -- a mere HQ geo does NOT grant local-SEO presence (per the
    # plan: derive it from a REAL local signal). A later task refines it from a connected GBP /
    # social_presence; an operator override can force it. Nothing to do here beyond the bucket default.

    # Per-tenant operator overrides win last (e.g. Team Unstoppable: {"additional_content_cap": null}).
    if overrides:
        profile = _deep_merge(profile, overrides)
    return profile


def for_business(business_id: int) -> dict:
    """Load a business row (+ its persisted strategy_profile override) and derive the StrategyProfile.
    Fail-safe: any read error / pre-migration column -> the GENERIC-derived profile; never raises."""
    biz: dict = {}
    try:
        with db() as conn:
            r = conn.execute(
                "SELECT id, name, industry, geo, contested_terms, services, regulatory_profile "
                "FROM businesses WHERE id=%s", (business_id,)).fetchone()
            biz = dict(r) if r else {}
            try:   # strategy_profile column may not be migrated yet -> ignore quietly
                sp = conn.execute("SELECT strategy_profile FROM businesses WHERE id=%s",
                                  (business_id,)).fetchone()
                if sp and isinstance(sp.get("strategy_profile"), dict):
                    biz["strategy_profile"] = sp["strategy_profile"]
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        biz = {}
    overrides = biz.get("strategy_profile") if isinstance(biz.get("strategy_profile"), dict) else None
    return derive(biz, overrides=overrides)


def enrich_at_onboarding(business_id: int) -> dict:
    """Off-hot-path onboarding hook: derive the profile (the alias table + derive() resolve a
    free-text industry deterministically today; a future version may add an LLM normalization pass
    for truly ambiguous free text). Best-effort -- returns the derived profile, never raises."""
    return for_business(business_id)
