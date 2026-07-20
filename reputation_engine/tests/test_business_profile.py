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
    """Everything that flows into a prompt/compliance/persona/source decision, MINUS tenant-declared
    passthrough fields (contested_terms/firm_type echo the owner's own input, not a leak)."""
    p = dict(profile)
    for k in ("contested_terms", "firm_type", "industry"):
        p.pop(k, None)
    return json.dumps(p, default=str).lower()


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
