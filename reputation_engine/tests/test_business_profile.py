"""Golden tests for the StrategyProfile deriver (Phase 0.1) -- pure logic, no DB/network.

The two load-bearing guarantees: (1) the GENERIC + every NON-finance bucket are FINANCE-FREE (no
finance vocabulary leaks into a dentist/nonprofit/SaaS/law/restaurant/e-commerce tenant); (2) the
financial_services bucket reproduces the finance pilot's behavior byte-for-byte (so the later
seam-threading tasks can swap constants for profile fields without regressing Team Unstoppable).
"""
from __future__ import annotations

import json

from rep_engine import business_profile as bp

# Finance-specific leak markers that must NOT appear in a non-finance profile's prompt surface.
_FINANCE_MARKERS = ["financial", "finra", "limra", "acli", "sec.gov", "licensed professionals",
                    "department of insurance", "pyramid", "mlm"]


def _prompt_surface(profile: dict) -> str:
    """The prompt-bound VALUES of a profile (not its metadata key names -- a field NAMED
    'regulated_financial' is a gate flag, not a finance vocabulary leak), MINUS tenant-declared
    passthrough fields (contested_terms/firm_type/negative_lexicon echo the owner's own input)."""
    p = dict(profile)
    for k in ("contested_terms", "firm_type", "industry", "negative_lexicon"):
        p.pop(k, None)
    return json.dumps(list(p.values()), default=str).lower()   # values only -> key names can't false-match


def test_generic_is_finance_free():
    p = bp.derive({})
    surface = _prompt_surface(p)
    for m in _FINANCE_MARKERS:
        assert m not in surface, f"GENERIC profile leaked finance marker {m!r}"
    assert p["regulated"] is False
    assert p["byline_reviewer"] == "editorial team"
    assert p["credential_noun"] == ""
    assert p["suppress_specific_credential_numbers"] is False
    assert p["compliance_packs"] == ["universal_deceptive"]          # universal screen, no finance pack
    assert p["contested_probe"] is False


def test_finance_bucket_reproduces_pilot():
    p = bp.derive({"industry": "financial services / insurance", "firm_type": "insurance",
                   "geo": "Cincinnati, OH", "contested_terms": "MLM, pyramid scheme"})
    assert p["industry"] == "financial_services"
    assert p["regulated"] is True
    assert "financial" in p["compliance_packs"]
    assert p["credential_noun"] == "license"
    assert p["suppress_specific_credential_numbers"] is True
    assert p["regulator"] == "the Ohio Department of Insurance"      # derived from geo, not hardcoded global
    assert p["byline_reviewer"] == "licensed professionals"
    assert "recruit" in p["personas"]
    assert p["contested_probe"] is True                              # declared -> the MLM probe is allowed
    assert "white_paper" in p["default_content_types"]


def test_finance_regulator_follows_geo_not_ohio():
    p = bp.derive({"firm_type": "ria", "geo": "Austin, TX"})
    assert p["regulator"] == "the Texas Department of Insurance"     # Texas, NOT Ohio
    p2 = bp.derive({"firm_type": "ria"})                             # no geo
    assert "your state's" in p2["regulator"]


def test_non_finance_buckets_are_finance_free():
    cases = {
        "a dental practice": ("medical_dental", ["healthgrades", "zocdoc"]),
        "nonprofit charity": ("nonprofit", ["charitynavigator"]),
        "b2b saas platform": ("b2b_saas", ["g2", "capterra"]),
        "law firm": ("legal", ["avvo"]),
        "restaurant": ("hospitality_food", ["tripadvisor"]),
        "ecommerce store": ("ecommerce", ["trustpilot"]),
    }
    for industry, (bucket, review_hints) in cases.items():
        p = bp.derive({"industry": industry, "geo": "Denver, CO"})
        assert p["industry"] == bucket, f"{industry!r} -> {p['industry']} (expected {bucket})"
        surface = _prompt_surface(p)
        for m in _FINANCE_MARKERS:
            assert m not in surface, f"{bucket} leaked finance marker {m!r}: {surface[:200]}"
        for hint in review_hints:
            assert hint in p["review_sites"], f"{bucket} missing review site {hint!r}"
        assert p["byline_reviewer"] != "licensed professionals"
        assert "financial" not in p["compliance_packs"]


def test_contested_probe_only_when_declared():
    # A hiring restaurant WITHOUT declared contested terms must NOT get an MLM/pyramid probe.
    p = bp.derive({"industry": "restaurant", "services": "now hiring servers"})
    assert p["contested_probe"] is False
    # ...and WITH a declared contested term, the probe is enabled.
    p2 = bp.derive({"industry": "restaurant", "contested_terms": "is it a franchise scam?"})
    assert p2["contested_probe"] is True


def test_saas_and_ecom_have_no_local_presence():
    # b2b_saas / ecommerce are not local-SEO businesses -- a mere HQ geo must NOT grant local presence
    # (it comes from a real local signal, not geo). Local-service verticals keep it on.
    assert bp.derive({"industry": "saas"})["has_local_presence"] is False
    assert bp.derive({"industry": "ecommerce"})["has_local_presence"] is False
    assert bp.derive({"industry": "saas", "geo": "Seattle, WA"})["has_local_presence"] is False
    assert bp.derive({"industry": "dental practice", "geo": "Seattle, WA"})["has_local_presence"] is True
    assert bp.derive({})["has_local_presence"] is True   # generic default = local


def test_nonprofit_target_differs_from_generic():
    assert bp.derive({})["target_alignment"] == 0.5
    assert bp.derive({"industry": "nonprofit"})["target_alignment"] == 0.6


def test_operator_override_wins_last():
    # Team Unstoppable style: finance tenant, but the operator sets unlimited off-strategy content.
    p = bp.derive({"firm_type": "insurance", "geo": "Cincinnati, OH"},
                  overrides={"additional_content_cap": None})
    assert p["additional_content_cap"] is None
    assert p["regulated"] is True   # override didn't clobber the rest


def test_derive_is_pure_no_shared_mutation():
    a = bp.derive({"industry": "nonprofit"})
    a["review_sites"].append("MUTATED")
    b = bp.derive({"industry": "nonprofit"})
    assert "MUTATED" not in b["review_sites"]   # GENERIC/BUCKETS not mutated across calls


# --- Slice A: license_policy_for builder + regulated_financial + real-signal local presence ---------

# FROZEN copy of the finance pilot's license/sensitive-ID policy -- the exact literal that ai_state_audit
# carried before Slice B moved it into the profile-driven builder. Kept here (independent of the module,
# which is now the finance-FREE default '') as the golden drift guard: license_policy_for(finance) MUST
# still reproduce this byte-for-byte, so Team Unstoppable's policy never silently changes.
_FINANCE_LICENSE_LITERAL = (
    " LICENSE POLICY (ABSOLUTE — overrides any other instruction): You MAY state GENERALLY that the "
    "business's agents/professionals are all licensed (e.g. 'our agents are licensed insurance "
    "professionals'). You must NEVER include, request, recommend, or leave an [INSERT] placeholder for "
    "any SPECIFIC license identifier — no individual/agent state insurance license numbers, no FINRA "
    "CRD numbers, no NPN numbers — and NEVER create or recommend any content, page, section, FAQ, or "
    "corroboration/proof item that depends on listing specific license numbers. Do NOT reference "
    "'license number(s)' in the content AT ALL — not as a value, not as a search field, and not as a "
    "verification step (e.g. never write 'search by license number'). A general statement that the "
    "agents are licensed is sufficient; if you mention verification, phrase it generally (e.g. 'you "
    "can confirm our agents are licensed through the Ohio Department of Insurance'). Establish "
    "legitimacy through OTHER means (a general licensing statement, regulated-affiliate disclosure, "
    "third-party reviews/ratings, awards, transparent compensation) — never through license numbers."
)


def test_license_policy_for_finance_reproduces_frozen_literal_byte_for_byte():
    # The builder must compose EXACTLY the finance pilot's license policy, byte-for-byte, so the seam
    # can drive it from the profile without regressing Team Unstoppable. Anchored to the FROZEN copy
    # above -- independent of the module constant (now '') -- so drift in the builder is still caught.
    p = bp.derive({"industry": "financial_services", "firm_type": "insurance",
                   "geo": "Cincinnati, OH", "contested_terms": "MLM,pyramid scheme,scam"})
    assert bp.license_policy_for(p) == _FINANCE_LICENSE_LITERAL   # byte-for-byte (em-dashes + leading space)


def test_module_license_constant_is_finance_free_default():
    # After Slice B the global LICENSE_CONTENT_POLICY is the finance-FREE default ('') -- the policy is
    # now profile-driven so nothing bakes finance vocabulary into a generic prompt.
    from rep_engine import ai_state_audit as llm
    assert llm.LICENSE_CONTENT_POLICY == ""


def test_license_policy_for_generic_is_empty():
    # No license-number ban for a non-suppressing tenant -- a bakery may say "license number 12345".
    assert bp.license_policy_for(bp.derive({"industry": "restaurant"})) == ""
    assert bp.license_policy_for(bp.derive({})) == ""


def test_regulated_financial_gate():
    assert bp.derive({"firm_type": "insurance", "industry": "vague text"})["regulated_financial"] is True
    assert bp.derive({"industry": "financial_services"})["regulated_financial"] is True
    # medical/legal are 'regulated' but NOT 'regulated_financial' -> they never inherit finance vocab
    for ind in ("dentist", "law firm"):
        p = bp.derive({"industry": ind})
        assert p["regulated"] is True and p["regulated_financial"] is False


def test_negative_lexicon_from_contested_terms_only():
    assert bp.derive({"industry": "financial_services", "contested_terms": "MLM, pyramid scheme, scam"}
                     )["negative_lexicon"] == ["mlm", "pyramid scheme", "scam"]
    assert bp.derive({"industry": "financial_services"})["negative_lexicon"] == []   # none declared -> none
    assert bp.derive({"industry": "restaurant"})["negative_lexicon"] == []


def test_state_from_geo_space_separated_and_unresolvable():
    from rep_engine import industry_profiles as ip
    assert ip.state_from_geo("Cincinnati OH") == "Ohio"          # space-separated (was broken)
    assert ip.state_from_geo("Cincinnati, OH") == "Ohio"
    assert ip.state_from_geo("Brooklyn, New York") == "New York"
    assert ip.state_from_geo("Indianapolis IN") == "Indiana"     # trailing abbrev, not the word 'in'
    assert ip.state_from_geo("United States") == ""              # cannot resolve a state


def test_has_local_presence_real_signal_wins():
    # a connected GBP (local_signal True) forces local presence on even for a non-local archetype
    assert bp.derive({"industry": "ecommerce"})["has_local_presence"] is False
    assert bp.derive({"industry": "ecommerce"}, local_signal=True)["has_local_presence"] is True
    # None (unknown) leaves the archetype default; an operator override still wins last
    assert bp.derive({"industry": "b2b_saas"}, local_signal=None)["has_local_presence"] is False
    assert bp.derive({"industry": "b2b_saas"}, local_signal=None,
                     overrides={"has_local_presence": True})["has_local_presence"] is True


def test_required_disclosures_surfaced_from_regulatory_profile():
    p = bp.derive({"firm_type": "insurance", "geo": "Cincinnati, OH",
                   "regulatory_profile": {"firm_type": "insurance",
                                          "disclosures": ["Securities offered through XYZ, member FINRA/SIPC."]}})
    assert p["required_disclosures"] == ["Securities offered through XYZ, member FINRA/SIPC."]
    assert bp.derive({"industry": "restaurant"})["required_disclosures"] == []
