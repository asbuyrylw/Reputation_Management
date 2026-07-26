"""
Content-effectiveness research KB — WHY the strategy makes the content decisions it makes
=========================================================================================
The strategist used to decide HOW MUCH / WHAT TYPE / WHAT STRUCTURE / WHAT WORD COUNT from hand-tuned
constants and prompt prose with no citable basis. This module is the evidence base it now reads, so
every one of those decisions traces to a real, dated source (Google Search Central, the Princeton GEO
paper, and reputable SEO studies). Mirrors authoritative_sources.py's shape:

  * RESEARCH   -- list of {claim, metric, value, applies_to, source, url, as_of, tier}
  * WORD_COUNTS-- research-informed word-count target per content_type (piece_brief reads this)
  * research_for(intent, content_type, goal) -> the relevant claims
  * research_block(...)                        -> an injectable prompt string (apply + cite)
  * word_count_for(content_type)               -> (target_words, source) for piece_brief

Compiled 2026-07 via a cited web-research pass. Lower-confidence values are tier 'editorial' and noted.
Word counts are LENGTH GUIDANCE, not quotas -- length correlates with rank, it does not cause it
(Backlinko/Google Mueller), and this engine deliberately fights padding/AI-slop, so targets are set to
the research-supported band, not the maximum.
"""
from __future__ import annotations

from typing import Optional

# tier: primary (Google's own docs) > academic (peer-reviewed / arXiv) > industry (vendor studies) >
# editorial (single-vendor blog numbers / lower-confidence). applies_to: intent:* | content_type:* |
# goal:aeo|seo|geo|topical_authority | global.
RESEARCH: list[dict] = [
    # --- topical authority / clusters ---
    {"claim": "A topic cluster = one pillar page + many cluster pages, each answering a distinct subtopic; "
              "start with ~8-12 high-quality clusters around distinct search intents (HubSpot's model scales "
              "to ~100 subtopics; 20-30 supporting articles anchor a strong pillar).",
     "metric": "cluster_count", "value": "8-12 to start (20-30 for a strong pillar)",
     "applies_to": "goal:topical_authority", "source": "HubSpot — Topic Clusters",
     "url": "https://blog.hubspot.com/marketing/topic-clusters-seo", "as_of": "2024", "tier": "industry"},
    {"claim": "More internal links between related cluster pages correlated with higher rankings and more "
              "impressions in HubSpot's controlled interlinking experiment — cross-link the pillar and spokes.",
     "metric": "interlink_effect", "value": "more internal links -> higher rank + impressions",
     "applies_to": "goal:topical_authority", "source": "HubSpot Research",
     "url": "https://blog.hubspot.com/marketing/topic-clusters-seo", "as_of": "2024", "tier": "industry"},
    {"claim": "Google publishes no 'topical authority' score; it rewards content that covers a topic "
              "substantially/comprehensively and adds original information or analysis (helpful-content self-"
              "assessment).",
     "metric": "comprehensiveness_signal", "value": "comprehensive + original coverage",
     "applies_to": "goal:seo", "source": "Google Search Central — Creating Helpful Content",
     "url": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
     "as_of": "2025", "tier": "primary"},
    # --- word count by intent / type ---
    {"claim": "The average Google top-10 result is ~1,447 words (11.8M results analyzed) — informational "
              "pages that rank tend to be reasonably in-depth.",
     "metric": "word_count", "value": "~1447 (top-10 avg)", "applies_to": "intent:informational",
     "source": "Backlinko — 11.8M Search Results", "url": "https://backlinko.com/search-engine-ranking",
     "as_of": "2020", "tier": "industry"},
    {"claim": "Length CORRELATES with rank but does not CAUSE it — Backlinko found no relationship WITHIN "
              "page 1, and Google (Mueller) confirms word count is not a ranking factor. Write to fully "
              "answer the query, never pad to hit a number.",
     "metric": "word_count_causation", "value": "correlation only, NOT causal", "applies_to": "global",
     "source": "Backlinko / Google (Mueller)", "url": "https://backlinko.com/search-engine-ranking",
     "as_of": "2020", "tier": "industry"},
    {"claim": "HubSpot's analysis of ~6,000 of its posts found blogs of ~2,100-2,400 words earned the most "
              "organic traffic; pillar pages run longer (~4,000).",
     "metric": "ideal_blog_length", "value": "blog ~2100-2400; pillar ~4000",
     "applies_to": "content_type:blog", "source": "HubSpot (via Search Engine Journal)",
     "url": "https://www.searchenginejournal.com/ideal-blog-post-length-for-seo/255633/",
     "as_of": "2021", "tier": "editorial"},
    # --- GEO / AEO tactics (academic — Princeton GEO) ---
    {"claim": "GEO tactics (adding quotations, statistics, and authoritative citations) boost a source's "
              "visibility in generative-engine answers by up to ~40% (GEO-bench, ~10k queries).",
     "metric": "geo_overall", "value": "+up to 40%", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO (arXiv 2311.09735, KDD 2024)",
     "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "Adding relevant direct QUOTATIONS was the single most effective GEO tactic (~+41% relative "
              "visibility) — include at least one crisp, attributable quote per section.",
     "metric": "geo_lift_quotations", "value": "+41%", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "Adding STATISTICS improved generative-engine visibility by ~+33% — put at least one real, "
              "cited, attributable statistic in each section (never invent numbers).",
     "metric": "geo_lift_statistics", "value": "+33%", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "FLUENCY optimization (clear, well-written prose) improved visibility by ~+29% — plain, "
              "scannable, grammatical writing beats dense jargon for AI citation.",
     "metric": "geo_lift_fluency", "value": "+29%", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "Adding authoritative CITE-SOURCES improved visibility by ~+28% — link claims to primary/.gov/"
              "regulator/peer-reviewed sources inline.",
     "metric": "geo_lift_cite_sources", "value": "+28%", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "KEYWORD STUFFING did NOT help and measured negative (~-8%) for generative-engine visibility — "
              "traditional keyword density backfires for GEO.",
     "metric": "geo_lift_keyword_stuffing", "value": "~-8% (negative)", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "GEO's 'Equalizer Effect': lower-ranked sources benefit MOST (a position-5 source gained up to "
              "+115% visibility from GEO tactics) — GEO lets a page that isn't #1 still get cited in AI answers.",
     "metric": "geo_equalizer", "value": "+115% for position-5 sources", "applies_to": "goal:geo",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "For AI/answer-engine trust, make it self-evident WHO created the content, carry a byline "
              "linking to author background, and provide original information (Who/How/Why).",
     "metric": "answer_first_eeat", "value": "byline + original info + Who/How/Why", "applies_to": "goal:aeo",
     "source": "Google Search Central — Helpful Content",
     "url": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
     "as_of": "2025", "tier": "primary"},
    # --- which content types move which channel ---
    {"claim": "YouTube is the single most-cited domain in Google AI Overviews (~29.5% citation share) and #1 "
              "in AI Mode (~16.6%), cited ~200x more than any other video platform — 'video for AI visibility' "
              "means YouTube.",
     "metric": "aio_youtube_share", "value": "29.5% (AIO); ~200x vs other video", "applies_to": "content_type:video",
     "source": "BrightEdge (via Search Engine Land)",
     "url": "https://searchengineland.com/youtube-ai-search-citations-data-462830", "as_of": "2025", "tier": "industry"},
    {"claim": "99.58% of featured snippets come from pages already ranking in the top 10, and ~12% of queries "
              "return one — an FAQ/direct-answer block only wins the snippet after the page ranks.",
     "metric": "featured_snippet_top10", "value": "99.58% from top-10; ~12% of queries",
     "applies_to": "content_type:faq", "source": "Ahrefs — 2M Featured Snippets",
     "url": "https://ahrefs.com/blog/featured-snippets-study/", "as_of": "2020", "tier": "industry"},
    {"claim": "Paragraph/definition snippets are typically 40-60 words — open each answer with a self-contained "
              "40-60 word direct answer under a heading that matches the question.",
     "metric": "answer_length", "value": "40-60 words", "applies_to": "content_type:faq",
     "source": "Semrush — Featured Snippet studies",
     "url": "https://www.semrush.com/blog/how-to-earn-google-featured-snippets-mobile-study/",
     "as_of": "2020", "tier": "industry"},
    {"claim": "Original data/statistics content is a repeatable way to earn AI citations and links (statistics "
              "were a top GEO tactic, +33%).",
     "metric": "original_data_citations", "value": "+33% (statistics)", "applies_to": "content_type:article",
     "source": "Aggarwal et al., GEO", "url": "https://arxiv.org/abs/2311.09735", "as_of": "2024", "tier": "academic"},
    {"claim": "Reddit is the most-referenced domain across LLM answers (~40% of references), then Wikipedia "
              "(~26%) and YouTube (~24%) — third-party corroboration + community presence matter for GEO.",
     "metric": "llm_reference_share", "value": "Reddit 40% / Wikipedia 26% / YouTube 24%",
     "applies_to": "goal:geo", "source": "Semrush — Most-Cited Domains in AI",
     "url": "https://www.semrush.com/blog/most-cited-domains-ai/", "as_of": "2025", "tier": "industry"},
    # --- cadence / freshness ---
    {"claim": "Companies publishing 16+ posts/month got ~3.5x more traffic (and ~4.5x more leads) than those "
              "publishing 0-4/month — a front-loaded burst then a steady drip beats sporadic publishing.",
     "metric": "cadence_traffic", "value": "16+/mo -> ~3.5x traffic", "applies_to": "global",
     "source": "HubSpot — Blog Frequency",
     "url": "https://marketinginsidergroup.com/content-marketing/how-often-should-you-blog-blog-post-frequency-research/",
     "as_of": "2021", "tier": "industry"},
    {"claim": "Perplexity cites content updated within 30 days at ~82%, dropping to ~37% for older content — "
              "keep cornerstone pieces fresh (a refresh clock) to stay citable.",
     "metric": "freshness", "value": "82% (<30d) vs 37% (older)", "applies_to": "goal:geo",
     "source": "Whitehat SEO", "url": "https://whitehat-seo.co.uk/blog/ai-engines-comparison-citations",
     "as_of": "2025", "tier": "editorial"},
    {"claim": "AI-Overview keywords skew long-tail and specific (~60% have <=100 searches/mo; ~60% in KD 21-60) "
              "— answer the specific question, don't just target head terms.",
     "metric": "aio_query_profile", "value": "~60% <=100 searches; KD 21-60", "applies_to": "intent:informational",
     "source": "Semrush — AI Overviews Study", "url": "https://www.semrush.com/blog/semrush-ai-overviews-study/",
     "as_of": "2025", "tier": "industry"},
    # --- E-E-A-T / author authority ---
    {"claim": "Google's Quality Rater Guidelines score pages on E-E-A-T (Experience, Expertise, "
              "Authoritativeness, Trust) — Trust is the most important; expertise without trust scores low.",
     "metric": "eeat_trust_primacy", "value": "Trust = most important of E-E-A-T", "applies_to": "goal:seo",
     "source": "Google Search Quality Rater Guidelines (Sept 2025)",
     "url": "https://guidelines.raterhub.com/searchqualityevaluatorguidelines.pdf", "as_of": "2025", "tier": "primary"},
    {"claim": "YMYL topics (health, finance, safety; +civics/elections as of 2025) are held to the highest "
              "E-E-A-T bar — financial content must be accurate, well-sourced, and clearly authored.",
     "metric": "ymyl_scope", "value": "finance is YMYL -> highest E-E-A-T bar", "applies_to": "intent:informational",
     "source": "Google Search Quality Rater Guidelines (2025)",
     "url": "https://guidelines.raterhub.com/searchqualityevaluatorguidelines.pdf", "as_of": "2025", "tier": "primary"},
    {"claim": "Google ties named authorship to E-E-A-T: make it self-evident who authored the content and "
              "carry a byline linking to author background where one is expected.",
     "metric": "byline_signal", "value": "named author + byline", "applies_to": "goal:seo",
     "source": "Google Search Central — Helpful Content (Who/How/Why)",
     "url": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
     "as_of": "2025", "tier": "primary"},
]

# Research-informed word-count target per platform content_type: (target_words, source). Set to the
# research-supported band (not the maximum) because length correlates but does not cause rank and this
# engine fights padding. piece_brief reads this (falling back to its own constant when a type is absent).
WORD_COUNTS: dict[str, tuple[int, str]] = {
    "article":       (1450, "Backlinko: top-10 avg ~1,447 words"),
    "blog":          (1500, "HubSpot: blogs ~2,100-2,400 earn most traffic (moderated to avoid padding)"),
    "white_paper":   (2000, "in-depth authority format (E-E-A-T comprehensiveness)"),
    "faq":           (700,  "Ahrefs/Semrush: 40-60 word answers x several Q&As"),
    "local_page":    (800,  "local landing: NAP + service + proof, concise"),
    "deep_article":  (2500, "HubSpot: pillar pages ~4,000 words (moderated)"),
    "landing_page":  (900,  "commercial landing: concise, CTA-forward"),
}

_GOAL_TERMS = {"aeo", "seo", "geo", "topical_authority"}

# Research-backed piece-count target for a topical-authority PROGRAM (pillar + N supporting clusters),
# so EVERY builder sizes a program from the evidence -- not from "however many seed keywords happen to
# exist" (the under-production the audit flagged). Sourced from the cluster_count claim above:
# 8-12 clusters to start (5 = activation minimum, ~15 = authority threshold), 20-30 for a strong pillar.
CLUSTER_COUNT_MIN, CLUSTER_COUNT_MAX = 8, 12
CLUSTER_COUNT_STRONG = 24
AUTHORITY_THRESHOLD = 15


def cluster_count_for(goal: str = "topical_authority", *, strong: bool = False) -> tuple[int, int, str]:
    """Research-backed (min, max, source) number of SUPPORTING pieces a pillar program needs. Builders
    (local program, generate_cluster, the strategist floor) size from this so a program is big enough to
    build authority and crowd out the negative narrative, instead of stopping at a small literal."""
    if strong:
        return CLUSTER_COUNT_MAX, CLUSTER_COUNT_STRONG, "HubSpot topic clusters: 20-30 for a strong pillar"
    return (CLUSTER_COUNT_MIN, CLUSTER_COUNT_MAX,
            "HubSpot topic clusters: 8-12 to start (5=activation minimum, ~15=authority threshold)")


def _relevant(applies_to: str, *, intent: str = "", content_type: str = "", goal: str = "",
              broad: bool = False) -> bool:
    """True when a claim's applies_to matches the requested intent/content_type/goal (or is global).
    `broad=True` (PLAN-level use, e.g. the strategist) includes EVERY claim so the plan can justify the
    whole mix -- word-count-by-intent, which types move which channel, GEO tactics -- not just globals."""
    a = (applies_to or "").lower()
    if a == "global":
        return True
    if a.startswith("intent:"):
        return broad or (bool(intent) and a.split(":", 1)[1] == intent.lower())
    if a.startswith("content_type:"):
        return broad or (bool(content_type) and a.split(":", 1)[1] == content_type.lower())
    if a.startswith("goal:"):
        # No goal requested -> include all goal-tagged claims (broad plan-level context). A goal
        # requested -> scope to THAT goal only. (The old `or g in _GOAL_TERMS` made this a no-op:
        # every goal claim leaked into every goal-scoped query, so goal filtering never happened.)
        g = a.split(":", 1)[1]
        return broad or (not goal) or g == goal.lower()
    return False


def research_for(intent: str = "", content_type: str = "", goal: str = "", limit: int = 14,
                 *, broad: bool = False) -> list[dict]:
    """The research claims relevant to a piece/plan, primary + academic tiers first. `broad=True` returns
    the full cross-category set for PLAN-level use (the strategist)."""
    picked = [r for r in RESEARCH if _relevant(r.get("applies_to", ""),
                                               intent=intent, content_type=content_type, goal=goal,
                                               broad=broad)]
    tier_rank = {"primary": 0, "academic": 1, "industry": 2, "editorial": 3}
    picked.sort(key=lambda r: tier_rank.get(r.get("tier"), 9))
    return picked[:limit]


def research_block(intent: str = "", content_type: str = "", goal: str = "", limit: int = 12,
                   *, broad: bool = False) -> str:
    """An injectable prompt block of cited, applicable content-effectiveness guidance. The model should
    APPLY these and MAY cite them. Returns '' when nothing applies (dormant-safe). `broad=True` for
    plan-level breadth (the strategist justifying the whole content mix)."""
    picked = research_for(intent=intent, content_type=content_type, goal=goal, limit=limit, broad=broad)
    if not picked:
        return ""
    lines = ["CONTENT-EFFECTIVENESS RESEARCH (apply these; each is a real, dated finding you may cite):"]
    for r in picked:
        # Flag lower-confidence (single-vendor blog / editorial) claims so the model weights them below
        # Google's own docs + peer-reviewed findings rather than treating every line as equally settled.
        conf = " — lower-confidence (single-vendor)" if r.get("tier") == "editorial" else ""
        lines.append(f"- {r['claim']} [{r['source']}, {r.get('as_of', '')}{conf}]")
    return "\n".join(lines)


def word_count_for(content_type: str) -> tuple[Optional[int], str]:
    """Research-backed word-count target + its source for a content_type, or (None, '') if not covered
    (caller keeps its own default). piece_brief uses this so per-piece length carries a citation."""
    ct = (content_type or "").lower()
    if ct in WORD_COUNTS:
        w, src = WORD_COUNTS[ct]
        return w, src
    return None, ""
