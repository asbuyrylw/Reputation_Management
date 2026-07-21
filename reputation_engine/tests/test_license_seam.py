"""License-policy seam (6.1 Slice B) -- the license/sensitive-ID policy is profile-driven, not baked
into every tenant's prompt. Pure (no DB): builds profiles via business_profile.derive and checks the
module system-prompt aliases are finance-FREE while the per-tenant builder splices the finance policy
back in. Slice A already golden-locked that license_policy_for(finance) reproduces the exact literal;
here we assert the SEAM keeps finance's policy and drops it for a generic tenant.
"""
from __future__ import annotations

from rep_engine import business_profile as bp

# Clauses that appear IFF the finance license policy is present.
_FINANCE_LICENSE_CLAUSES = ["FINRA CRD", "no NPN numbers", "the Ohio Department of Insurance",
                            "licensed insurance professionals"]


def _finance_license() -> str:
    return bp.license_policy_for(bp.derive(
        {"industry": "financial_services", "firm_type": "insurance", "geo": "Cincinnati, OH"}))


def test_finance_license_composes_full_policy():
    lic = _finance_license()
    for clause in _FINANCE_LICENSE_CLAUSES:
        assert clause in lic, f"finance license missing {clause!r}"
    assert bp.license_policy_for(bp.derive({"industry": "restaurant"})) == ""   # generic: none


def test_gap_system_module_alias_is_finance_free():
    from rep_engine import ai_state_audit as llm
    for name in ("GAP_SYSTEM", "GAP_CRITIC_SYSTEM"):
        s = getattr(llm, name)
        for clause in _FINANCE_LICENSE_CLAUSES:
            assert clause not in s, f"{name} module alias leaked finance clause {clause!r}"
    # the module alias equals the builder with no license (the GENERIC default)
    assert llm.GAP_SYSTEM == llm._gap_system()
    assert llm.GAP_CRITIC_SYSTEM == llm._gap_critic_system()


def test_gap_builder_splices_finance_license_but_keeps_agnostic_tail():
    from rep_engine import ai_state_audit as llm
    lic = _finance_license()
    gs = llm._gap_system(lic)
    for clause in _FINANCE_LICENSE_CLAUSES:
        assert clause in gs                       # finance keeps its policy
    assert llm._gap_system("") == llm.GAP_SYSTEM   # empty license -> the finance-free alias
    # NO_NEGATIVE + UNTRUSTED stay agnostic + always present in both variants
    assert "negative disambiguation" in gs.lower() or "not to be confused" in gs.lower()
    assert llm.UNTRUSTED_INSTRUCTION in gs and llm.UNTRUSTED_INSTRUCTION in llm.GAP_SYSTEM
