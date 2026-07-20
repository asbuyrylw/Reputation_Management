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

# The ABSOLUTE license / sensitive-ID policy scaffold. Written ONCE, verbatim from today's
# LICENSE_CONTENT_POLICY (ai_state_audit.py:150-163), with the three finance-specific bits pulled out
# as {noun}/{types}/{regulator} so it composes for any suppressing vertical. license_policy_for()
# returns "" for a non-suppressing tenant (the generic default -- no license-number ban at all).
_LICENSE_POLICY_TEMPLATE = (
    " LICENSE POLICY (ABSOLUTE — overrides any other instruction): You MAY state GENERALLY that the "
    "business's agents/professionals are all licensed (e.g. 'our agents are licensed {noun}'). You "
    "must NEVER include, request, recommend, or leave an [INSERT] placeholder for any SPECIFIC license "
    "identifier — {types} — and NEVER create or recommend any content, page, section, FAQ, or "
    "corroboration/proof item that depends on listing specific license numbers. Do NOT reference "
    "'license number(s)' in the content AT ALL — not as a value, not as a search field, and not as a "
    "verification step (e.g. never write 'search by license number'). A general statement that the "
    "agents are licensed is sufficient; if you mention verification, phrase it generally (e.g. 'you "
    "can confirm our agents are licensed through {regulator}'). Establish legitimacy through OTHER "
    "means (a general licensing statement, regulated-affiliate disclosure, third-party reviews/ratings, "
    "awards, transparent compensation) — never through license numbers."
)


def license_policy_for(profile: dict) -> str:
    """The absolute license / sensitive-ID policy appended to gap/generation/critic prompts. Empty for
    tenants that don't suppress specific credential numbers (the GENERIC default -- NO license-number
    ban). For a suppressing tenant it composes the policy from the profile's credential_number_types,
    licensed_professional_noun, and regulator -- reproducing today's finance literal for the pilot and
    adapting to any other suppressing vertical. Pure; safe to call at prompt-build time."""
    profile = profile or {}
    if not profile.get("suppress_specific_credential_numbers"):
        return ""
    types = profile.get("credential_number_types") or []
    types_clause = ", ".join("no " + t for t in types) if types else "no specific license/credential numbers"
    noun = profile.get("licensed_professional_noun") or profile.get("credential_noun") or "professionals"
    regulator = profile.get("regulator") or "the appropriate state regulator"
    return _LICENSE_POLICY_TEMPLATE.format(noun=noun, types=types_clause, regulator=regulator)


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def derive(biz: dict, *, overrides: Optional[dict] = None, local_signal: Optional[bool] = None) -> dict:
    """Build the StrategyProfile for a business. Pure -- no DB / network.

    biz keys used (all optional): industry, firm_type OR regulatory_profile.firm_type, geo,
    contested_terms, name, services. overrides: the persisted per-tenant strategy_profile JSONB
    (operator edits, applied LAST). local_signal: a REAL local-presence signal read by for_business()
    (a connected/discovered GBP) -- None means "unknown, use the archetype default"."""
    biz = biz or {}
    rp = biz.get("regulatory_profile") if isinstance(biz.get("regulatory_profile"), dict) else {}
    firm_type = (biz.get("firm_type") or (rp or {}).get("firm_type") or "").strip().lower()
    bucket_key = _ip.bucket_for(biz.get("industry"), firm_type)
    profile = _deep_merge(_ip.GENERIC, _ip.BUCKETS.get(bucket_key, {}))

    # finance sub-type carried through; regulated derived (explicit firm_type wins, else bucket default)
    profile["firm_type"] = firm_type
    if firm_type in _FINANCE_FIRMS:
        profile["regulated"] = True
    # regulated_financial is the FINANCE-ONLY gate (medical/legal keep regulated True but this False),
    # computed firm_type-FIRST so a biz with firm_type='insurance' but vague free-text industry still
    # gets the finance treatment. This is what license/finance-compliance/finance-byline key off.
    profile["regulated_financial"] = (firm_type in _FINANCE_FIRMS) or (bucket_key == "financial_services")

    # Surface any required regulatory disclosures the tenant persisted (e.g. Team Unstoppable's
    # broker-dealer/representative disclosure) so downstream compliance can require them instead of the
    # old hardcoded finance text -- prevents dropping them when the profile replaces _reg_profile.
    profile["required_disclosures"] = list(rp.get("disclosures") or []) if isinstance(rp, dict) else []

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
    # Compose the negative lexicon from the tenant's OWN contested terms (merged onto the bucket's, which
    # is empty by default) -- so "mlm"/"pyramid scheme"/"scam" flag for Team Unstoppable because THEY
    # declared them, and no vertical is auto-accused.
    _ct_tokens = [t.strip().lower() for t in contested.replace(";", ",").split(",") if t.strip()]
    profile["negative_lexicon"] = list(dict.fromkeys(list(profile.get("negative_lexicon") or []) + _ct_tokens))

    # has_local_presence: a REAL local signal wins over the archetype default -- a mere HQ geo does NOT
    # grant local-SEO presence (b2b_saas/ecommerce default False; local-service/professional default
    # True). local_signal (a connected/discovered GBP, read by for_business) forces True when present;
    # None leaves the archetype default. An operator override still wins last (below).
    if local_signal is not None:
        profile["has_local_presence"] = bool(local_signal)

    # Per-tenant operator overrides win last (e.g. Team Unstoppable: {"additional_content_cap": null}).
    if overrides:
        profile = _deep_merge(profile, overrides)
    return profile


def _local_signal(conn, business_id: int) -> Optional[bool]:
    """A REAL local-presence signal for has_local_presence: a live Google Business Profile connection
    (bare geo does NOT count). True when one exists; None ('unknown') otherwise so derive() falls back
    to the archetype default. Fail-safe: a missing table/column -> None. (Discovered-GBP via
    social_presence is a later enhancement; a connected GBP is the strongest signal.)"""
    try:
        r = conn.execute(
            "SELECT 1 FROM platform_connections WHERE business_id=%s AND kind='google_business_profile' "
            "AND COALESCE(status,'active') <> 'revoked' LIMIT 1", (business_id,)).fetchone()
        return True if r else None
    except Exception:  # noqa: BLE001 -- table/column absent -> unknown, use the archetype default
        return None


def for_business(business_id: int) -> dict:
    """Load a business row (+ its persisted strategy_profile override + a real local signal) and derive
    the StrategyProfile. Fail-safe: any read error / pre-migration column -> the GENERIC-derived
    profile; never raises."""
    biz: dict = {}
    local_signal: Optional[bool] = None
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
            local_signal = _local_signal(conn, business_id)
    except Exception:  # noqa: BLE001
        biz = {}
    overrides = biz.get("strategy_profile") if isinstance(biz.get("strategy_profile"), dict) else None
    return derive(biz, overrides=overrides, local_signal=local_signal)


def license_policy_for_business(business_id: int) -> str:
    """Convenience for prompt-build call sites: the license/sensitive-ID policy string for a business
    id (loads + derives its profile). Fail-safe -> '' on any error. On hot paths where the biz dict is
    already loaded, call license_policy_for(derive(biz)) directly to avoid the extra query."""
    try:
        return license_policy_for(for_business(business_id))
    except Exception:  # noqa: BLE001
        return ""


def enrich_at_onboarding(business_id: int) -> dict:
    """Off-hot-path onboarding hook: derive the profile (the alias table + derive() resolve a
    free-text industry deterministically today; a future version may add an LLM normalization pass
    for truly ambiguous free text). Best-effort -- returns the derived profile, never raises."""
    return for_business(business_id)
