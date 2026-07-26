"""
Authoritative citation sources + real statistics (finance vertical + a UNIVERSAL business pack)
================================================================================================
Finance/insurance/investing sources dominate the registry (the pilot vertical), but a UNIVERSAL pack
(Google Business Profile, FTC, BLS) is always included via _relevant_tags so a NON-finance tenant still
grounds its content in real authorities. Add more industry packs by tagging new SOURCES entries.

AI answer engines (ChatGPT, Perplexity, Gemini, Google AI Overviews) decide WHOM to cite largely by
source authority: .gov/regulator, official industry data, and peer-reviewed research rank highest.
The single biggest GEO/citability lever for a page is INLINE links to authoritative primary sources +
real, attributable statistics. This module curates those sources (verified 2026-07) and a set of
real, datable statistics, and produces a grounding block the content generator injects so drafts cite
REAL authorities and quote REAL numbers instead of vague claims -- never fabricated ones.

Compliance guardrail baked into the grounding text: these back EDUCATIONAL claims only; never use them
to imply guarantees, specific returns, or that an individual agent's license is confirmed (the reader
must check the ODI/BrokerCheck lookup themselves).
"""
from __future__ import annotations

import re
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

# Each source: name, url, provides (what it authoritatively supplies), cite_when, tier, tags.
# tier: primary (govt/regulator/data producer) > industry > academic > editorial(own-survey only).
SOURCES: list[dict] = [
    # --- government / regulatory ---
    {"name": "SEC EDGAR", "url": "https://www.sec.gov/edgar/search/", "tier": "primary",
     "provides": "public-company filings (10-K/10-Q/8-K)", "cite_when": "a claim about a public company (e.g. Primerica, NYSE: PRI)",
     "tags": ["company", "investing"]},
    {"name": "SEC Investor.gov", "url": "https://www.investor.gov", "tier": "primary",
     "provides": "plain-language investor education + compound-interest calculators", "cite_when": "basic investing definitions / avoiding investment fraud",
     "tags": ["investing", "education"]},
    {"name": "FINRA BrokerCheck", "url": "https://brokercheck.finra.org", "tier": "primary",
     "provides": "securities-license / CRD verification", "cite_when": "verifying a securities professional's license (general -- reader checks it)",
     "tags": ["licensing", "investing"]},
    {"name": "Ohio Department of Insurance", "url": "https://insurance.ohio.gov", "tier": "primary",
     "provides": "Ohio insurance regulation + agent/agency license lookup + consumer protection", "cite_when": "confirming agents are (generally) Ohio-licensed; consumer-protection claims",
     "tags": ["licensing", "insurance", "local", "ohio"]},
    {"name": "NAIC", "url": "https://content.naic.org", "tier": "primary",
     "provides": "insurance-regulator body; free Life Insurance Policy Locator", "cite_when": "cross-state insurance facts / finding a lost policy",
     "tags": ["insurance", "consumer_trust"]},
    {"name": "CFPB", "url": "https://www.consumerfinance.gov", "tier": "primary",
     "provides": "consumer-finance protections + plain-language money guides", "cite_when": "consumer debt/credit rights, budgeting basics",
     "tags": ["debt", "education"]},
    {"name": "IRS", "url": "https://www.irs.gov", "tier": "primary",
     "provides": "federal tax rules; retirement-account limits; life-insurance tax treatment", "cite_when": "401(k)/IRA limits; 'life-insurance death benefits are generally income-tax-free'",
     "tags": ["tax", "retirement", "insurance"]},
    {"name": "Social Security Administration", "url": "https://www.ssa.gov", "tier": "primary",
     "provides": "Social Security benefits + actuarial life tables", "cite_when": "retirement-income planning; life-expectancy",
     "tags": ["retirement"]},
    {"name": "FDIC", "url": "https://www.fdic.gov", "tier": "primary",
     "provides": "deposit insurance ($250k)", "cite_when": "'deposits are FDIC-insured up to $250,000'",
     "tags": ["investing"]},
    {"name": "U.S. Treasury (yield data)", "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/", "tier": "primary",
     "provides": "official Treasury par-yield curve (risk-free benchmark)", "cite_when": "benchmark/'safe' rate comparisons",
     "tags": ["investing", "macro_data"]},
    # --- insurance industry data ---
    {"name": "LIMRA", "url": "https://www.limra.com", "tier": "industry",
     "provides": "life-insurance ownership + coverage-gap research (Insurance Barometer)", "cite_when": "life-insurance ownership %, coverage gap, cost misperception",
     "tags": ["insurance", "life_insurance"]},
    {"name": "Insurance Information Institute (Triple-I)", "url": "https://www.iii.org", "tier": "industry",
     "provides": "consumer-facing insurance facts + statistics", "cite_when": "quick, citable industry stats",
     "tags": ["insurance", "life_insurance"]},
    {"name": "ACLI (American Council of Life Insurers)", "url": "https://www.acli.com", "tier": "industry",
     "provides": "Life Insurers Fact Book: coverage in force, benefits paid", "cite_when": "industry-scale figures (total coverage, benefits paid)",
     "tags": ["insurance", "life_insurance"]},
    # --- macro / investing data ---
    {"name": "FRED (St. Louis Fed)", "url": "https://fred.stlouisfed.org", "tier": "primary",
     "provides": "800k+ official economic series (saving rate, CPI, debt)", "cite_when": "personal saving rate, inflation, household-debt series",
     "tags": ["macro_data", "debt", "investing"]},
    {"name": "Bureau of Labor Statistics", "url": "https://www.bls.gov", "tier": "primary",
     "provides": "CPI (inflation), wage growth, consumer expenditure", "cite_when": "inflation/cost-of-living, wage growth",
     "tags": ["macro_data"]},
    {"name": "U.S. Census Bureau", "url": "https://www.census.gov", "tier": "primary",
     "provides": "median household income, demographics (national + local)", "cite_when": "median income; Cincinnati/Ohio demographics",
     "tags": ["macro_data", "local"]},
    {"name": "Federal Reserve (Survey of Consumer Finances)", "url": "https://www.federalreserve.gov/econres/scfindex.htm", "tier": "primary",
     "provides": "gold-standard household balance sheet: net worth, debt, ownership", "cite_when": "median net worth / household debt / retirement-account ownership",
     "tags": ["debt", "retirement", "macro_data"]},
    {"name": "Federal Reserve (Report on Economic Well-Being / SHED)", "url": "https://www.federalreserve.gov/consumerscommunities/shed.htm", "tier": "primary",
     "provides": "financial-fragility survey (emergency-expense coverage)", "cite_when": "the $400/$1,000 emergency-savings fragility claims",
     "tags": ["debt", "emergency_savings"]},
    # --- academic / research ---
    {"name": "GFLEC (financial-literacy research)", "url": "https://gflec.org", "tier": "academic",
     "provides": "Lusardi-Mitchell 'Big Three' financial-literacy benchmark", "cite_when": "financial-literacy gap claims",
     "tags": ["education", "financial_literacy"]},
    {"name": "FINRA Investor Education Foundation (NFCS)", "url": "https://www.finrafoundation.org/national-financial-capability-study", "tier": "academic",
     "provides": "National Financial Capability Study (25k+ adults, by state)", "cite_when": "financial-capability / literacy statistics (incl. Ohio)",
     "tags": ["education", "financial_literacy"]},
    {"name": "NBER", "url": "https://www.nber.org", "tier": "academic",
     "provides": "working papers; official recession dating; household-finance economics", "cite_when": "rigorous economics of saving/retirement/insurance demand",
     "tags": ["investing", "retirement"]},
    {"name": "Google Scholar", "url": "https://scholar.google.com", "tier": "academic",
     "provides": "discovery layer for peer-reviewed studies", "cite_when": "locating the primary study behind a claim",
     "tags": ["education", "financial_literacy", "investing"]},
    # --- consumer / nonprofit ---
    {"name": "Pew Research Center", "url": "https://www.pewresearch.org", "tier": "industry",
     "provides": "nonpartisan survey research on savings/retirement/financial stress", "cite_when": "attitudinal/confidence claims",
     "tags": ["education", "retirement"]},
    {"name": "NEFE (National Endowment for Financial Education)", "url": "https://www.nefe.org", "tier": "industry",
     "provides": "independent financial-education research + polls", "cite_when": "value/impact of financial education",
     "tags": ["education", "financial_literacy"]},
    {"name": "Better Business Bureau", "url": "https://www.bbb.org", "tier": "industry",
     "provides": "business trust profiles + complaint records", "cite_when": "establishing business trust; scam avoidance",
     "tags": ["consumer_trust"]},
    {"name": "Primerica Financial Security Monitor", "url": "https://www.primerica.com/public/financial-security-monitor.html", "tier": "industry",
     "provides": "quarterly survey of middle-income ($30k-$130k) households", "cite_when": "on-brand middle-income debt/savings/retirement-confidence trends (Primerica-affiliated)",
     "tags": ["debt", "financial_literacy", "primerica"]},
    # --- UNIVERSAL: authoritative for ANY local/service business (not vertical-specific), so a
    #     non-finance tenant still gets grounded citations for local presence, consumer trust + market data.
    {"name": "Google Business Profile Help", "url": "https://support.google.com/business", "tier": "primary",
     "provides": "official guidance on local presence, reviews, and Google Search/Maps eligibility", "cite_when": "local-SEO / reviews / how customers find the business",
     "tags": ["general", "local", "consumer_trust"]},
    {"name": "FTC Consumer Advice", "url": "https://consumer.ftc.gov", "tier": "primary",
     "provides": "federal consumer-protection + honest-advertising guidance", "cite_when": "trust, avoiding scams, truthful claims for any business",
     "tags": ["general", "consumer_trust"]},
    {"name": "U.S. Bureau of Labor Statistics", "url": "https://www.bls.gov", "tier": "primary",
     "provides": "official occupation, wage, industry + local-area economic data", "cite_when": "industry/occupation/local market facts for any vertical",
     "tags": ["general", "macro_data", "local"]},
]

# Real, verified, DATABLE statistics. `stat` is quoted as-is; `source` names the authority; `as_of` is
# the reference period. Always attributed + dated; approximate; educational only.
STATS: list[dict] = [
    {"stat": "About 51% of U.S. adults report owning life insurance (2024), down from 63% in 2011.",
     "source": "LIMRA Insurance Barometer 2024", "url": "https://www.limra.com", "as_of": "2024", "tags": ["life_insurance", "insurance"]},
    {"stat": "About 42% of adults (roughly 102 million people) say they need life insurance or need more of it.",
     "source": "LIMRA", "url": "https://www.limra.com", "as_of": "2024", "tags": ["life_insurance", "insurance"]},
    {"stat": "Roughly 72% of Americans overestimate the cost of term life insurance, and younger adults overestimate it by about 3x.",
     "source": "LIMRA", "url": "https://www.limra.com", "as_of": "2024", "tags": ["life_insurance", "insurance"]},
    {"stat": "Independent agents accounted for about 54% of the individual life insurance market (up from 46% in 2015).",
     "source": "Insurance Information Institute", "url": "https://www.iii.org", "as_of": "2024", "tags": ["life_insurance", "insurance"]},
    {"stat": "Only about 63% of U.S. adults could cover a $400 emergency expense with cash or its equivalent (down from 68% in 2021).",
     "source": "Federal Reserve Report on Economic Well-Being (SHED)", "url": "https://www.federalreserve.gov/consumerscommunities/shed.htm", "as_of": "2024", "tags": ["emergency_savings", "debt"]},
    {"stat": "About 24% of Americans have no emergency savings at all, and only around 47% could cover a $1,000 emergency from savings.",
     "source": "Bankrate Emergency Savings Report", "url": "https://www.bankrate.com/banking/savings/emergency-savings-report/", "as_of": "2024", "tags": ["emergency_savings", "debt"]},
    {"stat": "Median U.S. household net worth was about $192,900 (inflation-adjusted), up 37% from 2019.",
     "source": "Federal Reserve Survey of Consumer Finances", "url": "https://www.federalreserve.gov/econres/scfindex.htm", "as_of": "2022", "tags": ["debt", "retirement"]},
    {"stat": "Real median U.S. household income was about $80,610.",
     "source": "U.S. Census Bureau", "url": "https://www.census.gov", "as_of": "2023", "tags": ["macro_data", "local"]},
    {"stat": "On the standard 'Big Three' financial-literacy questions (interest, inflation, risk), only about a third of U.S. adults answer all three correctly.",
     "source": "GFLEC / FINRA Investor Education Foundation", "url": "https://gflec.org", "as_of": "2023", "tags": ["financial_literacy", "education"]},
    {"stat": "Life-insurance death benefits paid to beneficiaries are generally income-tax-free.",
     "source": "IRS", "url": "https://www.irs.gov", "as_of": "current", "tags": ["insurance", "tax", "life_insurance"]},
    {"stat": "The share of middle-income households able to pay their credit-card balance in full fell from 44% (2020) to about 29% (2025).",
     "source": "Primerica Financial Security Monitor", "url": "https://www.primerica.com/public/financial-security-monitor.html", "as_of": "2025", "tags": ["debt", "primerica", "financial_literacy"]},
    {"stat": "Social Security is designed to replace only about 40% of pre-retirement income for a typical worker.",
     "source": "Social Security Administration", "url": "https://www.ssa.gov", "as_of": "current", "tags": ["retirement"]},
]

# Map service/industry keywords -> the tags whose sources+stats are relevant.
_KEYWORD_TAGS: list[tuple[str, list[str]]] = [
    (r"life\s*insurance|term life|insurance", ["insurance", "life_insurance", "consumer_trust", "licensing"]),
    (r"invest|securities|wealth|retirement|401|ira|annuit", ["investing", "retirement", "macro_data", "company"]),
    (r"debt|budget|credit", ["debt", "emergency_savings"]),
    (r"financial (education|literacy|training)|educat", ["education", "financial_literacy"]),
    (r"tax", ["tax"]),
    (r"primerica", ["primerica", "company"]),
]


def _relevant_tags(services: str, industry: str = "", geo: str = "") -> set:
    text = f"{services} {industry}".lower()
    tags: set = set()
    for pat, tg in _KEYWORD_TAGS:
        if re.search(pat, text):
            tags.update(tg)
    if geo:
        tags.update({"local"})
    if re.search(r"\bohio|cincinnati|dayton", (geo or "").lower() + " " + text):
        tags.update({"ohio", "local", "licensing"})
    # a financial/insurance business always benefits from the trust + macro anchors
    if tags:
        tags.update({"consumer_trust", "macro_data"})
    # UNIVERSAL pack: every tenant (finance OR not) gets the industry-agnostic authorities (Google
    # Business Profile, FTC, BLS) so non-finance businesses are never left without grounded citations.
    tags.update({"general"})
    return tags


def sources_for(services: str = "", industry: str = "", geo: str = "", limit: int = 12) -> list[dict]:
    """Authoritative sources relevant to this business, primary/industry tiers first."""
    tags = _relevant_tags(services, industry, geo)
    picked = [s for s in SOURCES if set(s["tags"]) & tags]
    tier_rank = {"primary": 0, "industry": 1, "academic": 2, "editorial": 3}
    picked.sort(key=lambda s: tier_rank.get(s["tier"], 9))
    return picked[:limit]


def stats_for(services: str = "", industry: str = "", geo: str = "", limit: int = 8) -> list[dict]:
    """Real, datable statistics relevant to this business's topics."""
    tags = _relevant_tags(services, industry, geo)
    return [s for s in STATS if set(s["tags"]) & tags][:limit]


def grounding_block(services: str = "", industry: str = "", geo: str = "") -> str:
    """A grounding block the content generator injects so drafts cite REAL authorities inline (the #1
    GEO/citability lever) and quote REAL, dated statistics -- never invented ones. Returns '' if
    nothing relevant (dormant-safe)."""
    srcs = sources_for(services, industry, geo)
    stats = stats_for(services, industry, geo)
    if not srcs and not stats:
        return ""
    lines = ["AUTHORITATIVE SOURCES you MAY cite INLINE as markdown links to back a claim (these are the "
             ".gov / regulator / official-industry / academic sources AI answer engines trust -- inline "
             "citations to them are the single biggest lever for getting CITED by AI). Use only the ones "
             "that genuinely fit a claim on THIS page; never force-fit. Never imply an individual's "
             "license is confirmed -- point the reader to the lookup to verify:"]
    for s in srcs:
        lines.append(f"- {s['name']} ({s['url']}) — {s['provides']}. Cite for: {s['cite_when']}.")
    if stats:
        lines.append("")
        lines.append("REAL, ATTRIBUTABLE STATISTICS -- you MUST quote AT LEAST 2-3 of these in the piece "
                     "(long-form: 3-5), each woven into the relevant section with an INLINE markdown link "
                     "to its source and the year, e.g. 'About 51% of U.S. adults own life insurance "
                     "([LIMRA, 2024](https://www.limra.com)).' A concrete, sourced statistic is the single "
                     "most-cited element by AI answer engines. Quote the number AS-IS; keep the 'as of' "
                     "year; choose the ones that genuinely fit this page's topic; NEVER invent or alter a "
                     "statistic, and NEVER state one without its source:")
        for st in stats:
            lines.append(f"- \"{st['stat']}\" — {st['source']} ({st['as_of']}), {st['url']}")
    return "\n".join(lines)


def grounding_for_business(business_id: int) -> str:
    """Convenience: pull the business's services/industry/geo and build the grounding block."""
    try:
        with db() as conn:
            b = conn.execute("SELECT services, industry, geo FROM businesses WHERE id=%s",
                             (business_id,)).fetchone()
        if not b:
            return ""
        return grounding_block(b.get("services") or "", b.get("industry") or "", b.get("geo") or "")
    except Exception:  # noqa: BLE001 -- grounding is best-effort, never blocks generation
        return ""
