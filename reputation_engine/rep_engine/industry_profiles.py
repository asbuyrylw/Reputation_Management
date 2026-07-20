"""
Industry profile registry (Phase 0.1) -- DATA ONLY.
====================================================
The engine used to bake finance / insurance / Ohio / Team-Unstoppable specifics into module-level
globals (LICENSE_CONTENT_POLICY + "Ohio Department of Insurance", a financial-services compliance
screener, "licensed professionals" bylines, an MLM "pyramid scheme" persona probe, finance-only
authoritative sources, hand-tuned challenge thresholds). That makes the platform finance-shaped: a
dentist, nonprofit, SaaS, law firm, restaurant, or e-commerce brand got finance vocabulary leaked
into its prompts + wrong compliance rules.

This registry moves every one of those into DATA. The GENERIC profile is the business-agnostic
default -- ZERO finance vocabulary, a UNIVERSAL truthful-claims compliance posture, no
license-number suppression, an "editorial team" byline, dynamic (not finance-only) authoritative
sources, and a per-tenant success target. Each industry bucket lists ONLY what DIFFERS from GENERIC;
`business_profile.derive()` merges GENERIC <- bucket <- geo-derived <- per-tenant overrides. Finance
is exactly one bucket, so its rules apply to a financial_services tenant and NOBODY else.

Pure data + a few pure helpers -- no DB reads, no network, importable anywhere.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GENERIC -- the business-agnostic default. Finance-free by construction.
# ---------------------------------------------------------------------------
GENERIC: dict = {
    "industry": "generic",
    "archetype": "professional_services",   # local_service | b2b_saas | ecommerce | content_brand | nonprofit | professional_services
    "regulated": False,

    # --- compliance -------------------------------------------------------
    # A UNIVERSAL deceptive-claims screen applies to EVERY tenant (non-finance != no screen); the
    # heavier finance pack is added only for regulated_financial tenants.
    "compliance_screener_label": "truthful, non-deceptive marketing-claims screener",
    "compliance_packs": ["universal_deceptive"],           # + "financial" for regulated finance
    "credential_noun": "",                                  # e.g. "license" / "bar number" / "NPI" -- empty by default
    "suppress_specific_credential_numbers": False,          # only finance suppresses license numbers
    "regulator": "",                                        # a named regulator, when one applies
    "byline_reviewer": "editorial team",                    # generic; NOT "licensed professionals"
    # The SPECIFIC credential-number kinds a suppressing (finance) tenant must never publish, and the
    # noun for the "our agents are licensed <noun>" clause -- both compose license_policy_for(). Empty
    # for GENERIC (no license-number ban -> license_policy_for returns "").
    "credential_number_types": [],                          # finance: [FINRA CRD, NPN, state insurance license #s]
    "licensed_professional_noun": "",                       # finance: "insurance professionals"
    "regulated_financial": False,                           # finance-ONLY gate (derive() sets it firm_type-first)
    "required_disclosures": [],                             # surfaced from businesses.regulatory_profile.disclosures
    "authoritative_source_pack": "",                        # "" -> dynamic discovery; "financial" -> the finance registry
    "draft_tier_policy": "auto_owned",                      # owned-surface low-risk may auto-approve; finance = manual_all

    # --- authoritative sources / GEO -------------------------------------
    "authoritative_source_domains": [],                     # [] -> dynamic per-tenant discovery (no finance list)
    "require_stat_quotations": True,                        # AGNOSTIC GEO lever -- keep for ALL verticals

    # --- challenge calibration (start global; later calibrated to the tenant's own velocity) ---
    # All four low/material thresholds mirror challenge.py's module constants so profile-gating
    # _classify() can't KeyError. finance == generic here (a finance-specific value would itself be
    # a regression) -- the finance bucket deliberately does NOT override them.
    "void_high": 0.50,
    "void_low": 0.30,
    "neg_high": 0.40,
    "neg_low": 0.25,
    "void_material": 0.25,
    "neg_material": 0.30,
    "healthy_alignment": 0.40,
    "void_fill_factors": {"awareness_gap": 1.6, "mixed": 1.1, "negative_narrative": 0.8},
    "target_alignment": 0.5,                                # per-tenant success target (nonprofit/awareness differ)

    # --- audience personas / probes --------------------------------------
    "personas": ["generic", "local_customer", "prospective_client"],
    "audience_examples": ["a prospective customer", "someone comparing local options"],
    "contested_probe": False,                               # only when contested_terms declares one
    # Negative terms the mention/sentiment layer flags. EMPTY by default + never planted by industry:
    # derive() composes it from the tenant's OWN contested_terms, so no vertical is auto-accused (the
    # finance "pyramid/mlm" probe fires only because Team Unstoppable DECLARED those contested terms).
    "negative_lexicon": [],

    # --- content plan -----------------------------------------------------
    "default_content_types": ["blog", "article", "faq", "social_post"],
    "review_sites": ["google"],
    "social_channels": ["facebook", "instagram", "linkedin", "x"],
    "additional_content_cap": 20,                           # off-strategy content/month; None = unlimited
    "has_local_presence": True,                             # refined by derive() from real local signals
}

# ---------------------------------------------------------------------------
# Buckets -- ONLY the deltas from GENERIC. Finance's specifics live here.
# ---------------------------------------------------------------------------
BUCKETS: dict[str, dict] = {
    "financial_services": {
        "industry": "financial_services",
        "archetype": "professional_services",
        "regulated": True,
        "compliance_screener_label": "financial-services marketing compliance screener",
        "compliance_packs": ["universal_deceptive", "financial"],
        "credential_noun": "license",
        "suppress_specific_credential_numbers": True,       # no FINRA CRD / NPN / license numbers in content
        # The exact credential-number kinds + licensed-professional noun that compose the finance
        # license policy (reproduces LICENSE_CONTENT_POLICY's "no ... FINRA CRD ... NPN ..." + "licensed
        # insurance professionals" clauses). Order matters -- it is rendered "no A, no B, no C".
        "credential_number_types": ["individual/agent state insurance license numbers",
                                    "FINRA CRD numbers", "NPN numbers"],
        "licensed_professional_noun": "insurance professionals",
        "regulated_financial": True,                        # the finance-only gate
        "authoritative_source_pack": "financial",           # inject the authoritative_sources finance registry
        "draft_tier_policy": "manual_all",                  # every finance draft human-gated
        # Regulator is state-specific; derive() fills {state} from geo. Reproduces "the Ohio
        # Department of Insurance" for a Cincinnati OH tenant, not a hardcoded global.
        "regulator_template": "the {state} Department of Insurance",
        "byline_reviewer": "licensed professionals",
        "authoritative_source_domains": ["limra.com", "acli.com", "iii.org", "finra.org", "sec.gov"],
        "personas": ["generic", "local_customer", "prospective_client", "recruit"],
        "audience_examples": ["a middle-class family choosing an advisor", "a prospective recruit"],
        "default_content_types": ["blog", "article", "white_paper", "faq", "social_post"],
    },
    "medical_dental": {
        "industry": "medical_dental",
        "archetype": "local_service",
        "regulated": True,
        "compliance_screener_label": "healthcare marketing (HIPAA / no-outcome-guarantee) screener",
        "compliance_packs": ["universal_deceptive", "healthcare"],
        "credential_noun": "NPI / state board license",
        "regulator_template": "the {state} medical/dental board",
        "byline_reviewer": "a licensed clinician",
        "review_sites": ["google", "healthgrades", "zocdoc", "yelp"],
        "audience_examples": ["a patient choosing a provider", "someone comparing local clinics"],
        "default_content_types": ["local_page", "faq", "blog", "social_post"],
    },
    "legal": {
        "industry": "legal",
        "archetype": "professional_services",
        "regulated": True,
        "compliance_screener_label": "legal-advertising (bar rules / no-outcome-guarantee) screener",
        "compliance_packs": ["universal_deceptive", "legal"],
        "credential_noun": "bar number",
        "regulator_template": "the {state} state bar",
        "byline_reviewer": "a licensed attorney",
        "review_sites": ["google", "avvo", "yelp"],
        "audience_examples": ["a client seeking representation"],
        "default_content_types": ["article", "faq", "blog", "social_post"],
    },
    "home_services": {
        "industry": "home_services",
        "archetype": "local_service",
        "credential_noun": "contractor license",
        "review_sites": ["google", "yelp", "angi", "bbb"],
        "audience_examples": ["a homeowner needing a local pro"],
        "default_content_types": ["local_page", "blog", "faq", "social_post"],
    },
    "b2b_saas": {
        "industry": "b2b_saas",
        "archetype": "b2b_saas",
        "has_local_presence": False,
        "review_sites": ["g2", "capterra", "trustradius"],
        "social_channels": ["linkedin", "x"],
        "audience_examples": ["a buyer evaluating tools", "a technical evaluator"],
        "default_content_types": ["landing_page", "comparison", "article", "blog", "social_post"],
    },
    "ecommerce": {
        "industry": "ecommerce",
        "archetype": "ecommerce",
        "has_local_presence": False,
        "review_sites": ["google", "trustpilot", "yelp"],
        "social_channels": ["instagram", "facebook", "tiktok", "pinterest"],
        "audience_examples": ["a shopper comparing products"],
        "default_content_types": ["product_page", "comparison", "blog", "social_post"],
    },
    "hospitality_food": {
        "industry": "hospitality_food",
        "archetype": "local_service",
        "review_sites": ["google", "yelp", "tripadvisor", "opentable"],
        "social_channels": ["instagram", "facebook", "tiktok"],
        "audience_examples": ["a diner choosing where to eat"],
        "default_content_types": ["local_page", "blog", "social_post"],
    },
    "nonprofit": {
        "industry": "nonprofit",
        "archetype": "nonprofit",
        "target_alignment": 0.6,                            # success = share-of-voice + trust, not a 0.5 midpoint
        "review_sites": ["google", "charitynavigator", "guidestar"],
        "audience_examples": ["a prospective donor", "a volunteer", "a grantmaker"],
        "default_content_types": ["impact_story", "article", "faq", "social_post"],
    },
    "education": {
        "industry": "education",
        "archetype": "local_service",
        "review_sites": ["google", "niche", "greatschools"],
        "audience_examples": ["a prospective student or parent"],
        "default_content_types": ["local_page", "faq", "article", "social_post"],
    },
    "local_service": {
        "industry": "local_service",
        "archetype": "local_service",
        "review_sites": ["google", "yelp", "bbb"],
        "audience_examples": ["a local customer comparing options"],
        "default_content_types": ["local_page", "blog", "faq", "social_post"],
    },
    "professional_services": {
        "industry": "professional_services",
        "archetype": "professional_services",
        "audience_examples": ["a prospective client evaluating firms"],
    },
}

# Free-text industry -> bucket key. derive() lowercases + substring-matches; unknown -> generic.
INDUSTRY_ALIASES: dict[str, str] = {
    "financial": "financial_services", "finance": "financial_services", "insurance": "financial_services",
    "advisor": "financial_services", "wealth": "financial_services", "ria": "financial_services",
    "broker": "financial_services", "primerica": "financial_services",
    "dental": "medical_dental", "dentist": "medical_dental", "medical": "medical_dental",
    "doctor": "medical_dental", "physician": "medical_dental", "clinic": "medical_dental",
    "health": "medical_dental", "chiropract": "medical_dental", "veterinar": "medical_dental",
    "law": "legal", "legal": "legal", "attorney": "legal", "lawyer": "legal",
    "contractor": "home_services", "plumb": "home_services", "hvac": "home_services",
    "roofing": "home_services", "electric": "home_services", "landscap": "home_services",
    "home service": "home_services", "cleaning": "home_services",
    "saas": "b2b_saas", "software": "b2b_saas", "b2b": "b2b_saas", "platform": "b2b_saas",
    "tech": "b2b_saas", "app": "b2b_saas",
    "ecommerce": "ecommerce", "e-commerce": "ecommerce", "retail": "ecommerce", "shop": "ecommerce",
    "store": "ecommerce", "dtc": "ecommerce", "product": "ecommerce",
    "restaurant": "hospitality_food", "food": "hospitality_food", "cafe": "hospitality_food",
    "hotel": "hospitality_food", "hospitality": "hospitality_food", "bar": "hospitality_food",
    "catering": "hospitality_food",
    "nonprofit": "nonprofit", "non-profit": "nonprofit", "charity": "nonprofit", "ngo": "nonprofit",
    "foundation": "nonprofit",
    "education": "education", "school": "education", "tutor": "education", "university": "education",
    "college": "education", "academy": "education",
}

# US state name/abbr -> full name, so a geo string ("Cincinnati, OH") resolves a regulator's {state}.
_STATES: dict[str, str] = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas", "ca": "California",
    "co": "Colorado", "ct": "Connecticut", "de": "Delaware", "fl": "Florida", "ga": "Georgia",
    "hi": "Hawaii", "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland", "ma": "Massachusetts",
    "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi", "mo": "Missouri", "mt": "Montana",
    "ne": "Nebraska", "nv": "Nevada", "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico",
    "ny": "New York", "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
    "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah", "vt": "Vermont",
    "va": "Virginia", "wa": "Washington", "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming",
}


def bucket_for(industry: str | None, firm_type: str | None = None) -> str:
    """Resolve a bucket key from a free-text industry (+ an explicit finance firm_type). Unknown -> generic."""
    if (firm_type or "").strip().lower() in ("ria", "broker_dealer", "insurance"):
        return "financial_services"
    s = (industry or "").strip().lower()
    if not s:
        return "generic"
    if s in BUCKETS:
        return s
    for alias, key in INDUSTRY_ALIASES.items():
        if alias in s:
            return key
    return "generic"


def state_from_geo(geo: str | None) -> str:
    """Full state name from a geo string, tolerant of comma OR space separation ('Cincinnati, OH',
    'Cincinnati OH', 'Ohio', 'Brooklyn, New York'). '' when no US state is present (e.g. 'United
    States'). Prefers a full name / the trailing token so a common word ('in', 'or') inside a city
    name doesn't false-match a state abbreviation."""
    if not geo:
        return ""
    g = geo.strip()
    fulls = {full.lower(): full for full in _STATES.values()}
    segs = [s.strip().lower() for s in g.replace("/", ",").split(",") if s.strip()]
    # 1) a comma segment that IS a full state name ("Cincinnati, Ohio")
    for s in segs:
        if s in fulls:
            return fulls[s]
    # 2) a full state name as consecutive words anywhere ("New York City")
    gl = " " + " ".join(g.lower().replace(",", " ").replace("/", " ").split()) + " "
    for low, full in fulls.items():
        if f" {low} " in gl:
            return full
    # 3) a 2-letter abbreviation, preferring the LAST word of a segment (the state trails the city)
    for s in segs:
        words = s.split()
        if words and words[-1] in _STATES:
            return _STATES[words[-1]]
    # 4) any 2-letter abbreviation token (fallback)
    for w in g.lower().replace(",", " ").replace("/", " ").split():
        if w in _STATES:
            return _STATES[w]
    return ""
