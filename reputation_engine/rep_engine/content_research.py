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
    # --- NON-TEXT MIX: cited counts/cadence for video/podcast/social/backlinks + refresh + displacement
    #     (2026 web-research pass; see the count-helper functions below that size each surface from these) ---
    {"claim": "YouTube's AI-citation presence is rising, not saturated: citations in Google AI Overviews rose >300% from early Aug 2025, and by Sept 2025 YouTube was cited in as much as ~60% of tracked AI Overviews — treat video as a growing AEO channel worth entering now, not a mature one.",
     "metric": "aio_youtube_citation_growth", "value": "+300% since Aug 2025; cited in up to ~60% of AIOs by Sept 2025", "applies_to": "content_type:video",
     "source": "BrightEdge (via MediaPost)", "url": "https://www.mediapost.com/publications/article/400334/youtube-citations-in-google-ai-overviews-surge.html", "as_of": "2025", "tier": "industry"},
    {"claim": "YouTube wins AI citations disproportionately for specific query intents — tutorials/how-to, product demos, reviews, and pricing/deal queries. Produce video for the HIGH-VIDEO-INTENT clusters inside a pillar, not for every subtopic.",
     "metric": "video_intent_targeting", "value": "how-to / demo / review / pricing queries", "applies_to": "content_type:video",
     "source": "BrightEdge AI Catalyst (via Search Engine Land)", "url": "https://searchengineland.com/youtube-ai-search-citations-data-462830", "as_of": "2025", "tier": "industry"},
    {"claim": "Embedding video roughly doubles on-page dwell time (~6 min with video vs ~2.5 min text-only across 500k sessions; ~+40% on Wistia's own blog) — a video strengthens the engagement/ranking signal of the text page it sits on, so pair pillar video with the pillar page.",
     "metric": "video_dwell_time_lift", "value": "~2x dwell (6 min vs 2.5 min); ~+40% on-blog", "applies_to": "content_type:video",
     "source": "Wistia (500k page sessions)", "url": "https://wistia.com/learn/marketing/video-time-on-page", "as_of": "2024", "tier": "industry"},
    {"claim": "Video occupies SERP real estate on the majority of searches (~57% desktop / ~61% mobile carry a video result) and ~80% of those come from YouTube — a YouTube video is a second page-1 surface to help crowd out a negative narrative on high-video-intent terms.",
     "metric": "serp_video_prevalence", "value": "video on ~57-61% of searches; ~80% sourced from YouTube", "applies_to": "content_type:video",
     "source": "BrightEdge (via Wistia Video SEO)", "url": "https://wistia.com/learn/marketing/video-seo", "as_of": "2024", "tier": "industry"},
    {"claim": "Publishing cadence drives YouTube growth: across 10.2M channels, 12+ uploads/month showed ~4.1x higher median monthly view growth (2.18% vs 0.53%) and weekly posting ~2.5x vs sub-monthly. Floor = ~1 video/week (4/mo); fastest growth at 12+/month.",
     "metric": "youtube_upload_cadence", "value": ">=1/week floor; 12+/mo = ~4.1x view growth", "applies_to": "content_type:video",
     "source": "vidIQ (10,210,278 channels, Apr 2025-Mar 2026)", "url": "https://vidiq.com/blog/post/How-Often-Post-on-Youtube/", "as_of": "2026", "tier": "industry"},
    {"claim": "Quality and consistency outweigh raw upload count — YouTube states upload quantity is not a crucial optimization factor. Do NOT trade video quality for a higher per-cluster count; a few strong complete videos beat many thin ones.",
     "metric": "cadence_quality_tradeoff", "value": "consistency + AVD > raw frequency", "applies_to": "content_type:video",
     "source": "AIR Media-Tech / YouTube Creator guidance", "url": "https://air.io/en/youtube-hacks/the-death-of-daily-uploads-what-cadence-actually-triggers-algorithm-love-in-2025", "as_of": "2025", "tier": "editorial"},
    {"claim": "Keep AEO/GEO videos short and complete: sub-2-minute videos hold ~70%+ average completion vs ~35% for 10-min+ videos. Script each to answer one query fully and tightly rather than padding length.",
     "metric": "video_length_completion", "value": "<2 min ~70%+ completion vs ~35% for >10 min", "applies_to": "content_type:video",
     "source": "Wistia (via Green Frog Labs Video SEO stats)", "url": "https://greenfroglabs.com/blog/video-seo-statistics", "as_of": "2026", "tier": "editorial"},
    {"claim": "Do NOT size video off the '53x more likely to hit page one' figure — Forrester (2009) itself said in 2012 the data was 'almost certainly no longer accurate.' Treat it as historical color only.",
     "metric": "forrester_53x_stale", "value": "53x (2009) — disavowed by source in 2012, do not rely on", "applies_to": "content_type:video",
     "source": "Forrester Research (retracted as outdated)", "url": "https://www.forrester.com/blogs/09-01-08-the_easiest_way_to_a_first_page_ranking_on_google/", "as_of": "2012", "tier": "editorial"},
    {"claim": "Audio is a corroboration/authority play, not a direct-citation volume play: LLMs and crawlers cannot parse raw audio, so a podcast is invisible to AI unless every episode ships a published transcript + its own indexable page. Always pair audio with structured text — the transcript earns the citation.",
     "metric": "audio_requires_transcript", "value": "transcript + indexable page per episode (audio alone = invisible to AI)", "applies_to": "content_type:podcast",
     "source": "NeuronWriter — Turning Audio into Authority (AI Search Era)", "url": "https://neuronwriter.com/podcast-workflow-neuronwriter-2026/", "as_of": "2026", "tier": "editorial"},
    {"claim": "For thought-leadership authority, aim for ~1-2 guest appearances per MONTH sustained, with strategic show selection beating raw volume — one well-aligned show/month with promotion outperforms dozens of disconnected appearances. Consistency around the same topics builds the repeated co-occurrence AI rewards.",
     "metric": "podcast_cadence", "value": "1-2 guest appearances/month (consistency > volume)", "applies_to": "content_type:podcast",
     "source": "Content Allies / Podsicle Media — B2B Podcast Guesting Strategy", "url": "https://www.podsiclemedia.com/blog/podcast-strategy-for-thought-leadership-complete-b2b-guide", "as_of": "2026", "tier": "editorial"},
    {"claim": "Quarterly appearances on niche shows are the minimum effective cadence (vendor data: ~3x faster domain-authority improvement + ~39% more organic links/yr vs one-offs; single-vendor, directional). Use quarterly per active topic as the FLOOR and 1-2/mo as the target.",
     "metric": "podcast_cadence_floor", "value": "quarterly minimum (~3x faster DA vs one-offs)", "applies_to": "content_type:podcast",
     "source": "PodcastHawk — Podcast Guesting Backlinks & Authority Guide", "url": "https://podcasthawk.com/unlock-massive-seo-growth-in-2025-your-ultimate-guide-to-podcast-guesting-backlinks-authority/", "as_of": "2025", "tier": "editorial"},
    {"claim": "To make an episode AI-citable, publish it text-first: full transcript with speaker attribution and question-shaped headings, a 300-800 word show-notes summary, its own indexable page with PodcastEpisode/PodcastSeries schema, and a YouTube mirror. Raw unedited transcripts underperform — structure with definitions and Q&A.",
     "metric": "podcast_publishing_spec", "value": "transcript + 300-800w show notes + PodcastEpisode schema + YouTube mirror", "applies_to": "goal:aeo",
     "source": "Springcast — Podcast SEO 2026 (Google & AI)", "url": "https://www.springcast.io/en/blog/podcast-seo/", "as_of": "2026", "tier": "editorial"},
    {"claim": "A guest expert on a third-party show is external corroboration of expertise (E-E-A-T), but the citation credit accrues to the named, credentialed author + freshness date on the published transcript page, not the audio — byline the transcript to a real author to convert the appearance into a trust signal.",
     "metric": "podcast_eeat_corroboration", "value": "third-party appearance = external E-E-A-T (credit the bylined transcript)", "applies_to": "goal:seo",
     "source": "Rephonic — Should Brands Target Podcasts to Improve AI Visibility?", "url": "https://rephonic.com/blog/podcast-mentions-ai-visibility/", "as_of": "2025", "tier": "editorial"},
    {"claim": "Post to LinkedIn 2-5 times per week (6-10 for aggressive reach) — engagement keeps rising with frequency and LinkedIn does not penalize frequent posting; moving from 1/wk to 2-5/wk added ~1,180+ impressions per post.",
     "metric": "posts_per_week_linkedin", "value": "2-5 posts/week (up to 6-10 aggressive)", "applies_to": "content_type:social_post",
     "source": "Buffer — How Often to Post on Social Media in 2026 (2M+ posts)", "url": "https://buffer.com/resources/social-media-frequency-guide/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Post to X/Twitter 3-4 times per day (~21-28/week) — the short-shelf-life feed rewards volume; concentrate atomized one-liners, stats, and quote hooks here.",
     "metric": "posts_per_day_x", "value": "3-4 posts/day (~21-28/week)", "applies_to": "content_type:social_post",
     "source": "Buffer frequency guide (EverywhereMarketer study, 30 top X accounts)", "url": "https://buffer.com/resources/social-media-frequency-guide/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Post to Instagram 3-5 times per week for the reach/growth sweet spot (measured: 3-5/wk ~+12% reach; 6-9/wk ~+18%; 10+/wk ~+24%).",
     "metric": "posts_per_week_instagram", "value": "3-5 posts/week", "applies_to": "content_type:social_post",
     "source": "Buffer — Instagram posting frequency analysis (2M posts)", "url": "https://buffer.com/resources/how-often-to-post-on-instagram/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Post to Facebook 1-2 times per day (~7-14/week); above ~2/day returns diminish for most pages.",
     "metric": "posts_per_day_facebook", "value": "1-2 posts/day (~7-14/week)", "applies_to": "content_type:social_post",
     "source": "HubSpot study of 13,500+ Facebook users (via Buffer)", "url": "https://buffer.com/resources/social-media-frequency-guide/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Post to TikTok 2-5 times/week as the base tier for short-form video atoms (2-5/wk up to +17% views/post; 6-10/wk ~+29%; 11+/wk ~+34%).",
     "metric": "posts_per_week_tiktok", "value": "2-5 posts/week", "applies_to": "content_type:social_post",
     "source": "Buffer TikTok frequency data (via frequency guide)", "url": "https://buffer.com/resources/social-media-frequency-guide/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Reddit's LLM-citation dominance is platform-specific and growing: Perplexity drew ~24% of all citations from Reddit and ~31% from social overall (Jan 2026); Reddit was ~44% of Google AI Overviews' social citations; citation share grew 73%+ YoY. Prioritize authentic, question-answering participation over broadcast posting — cadence is relevance-gated, not volume-scalable.",
     "metric": "reddit_citation_share_by_platform", "value": "Perplexity ~24%; Google AIO social ~44%; +73% YoY", "applies_to": "goal:geo",
     "source": "Tinuiti Q1 2026 AI Citations Trends; tryProfound AI Platform Citation Patterns", "url": "https://www.tryprofound.com/blog/ai-platform-citation-patterns", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Atomize each long-form pillar (1,500-2,000 words) into ~15 social atoms — roughly 5 LinkedIn + 5-6 X + 2-3 Instagram + 1 email; practical upper bound 15-20 distinct posts per 2,000-word piece.",
     "metric": "social_atoms_per_pillar", "value": "15 atoms/pillar (range 15-20)", "applies_to": "content_type:social_post",
     "source": "DigitalApplied — Content Repurposing: One Piece, Ten Formats", "url": "https://www.digitalapplied.com/blog/content-repurposing-one-piece-ten-formats-guide", "as_of": "2026-01", "tier": "editorial"},
    {"claim": "Consistency beats raw volume — regular posting correlated with ~5x more engagement across 100,000+ Buffer users. For crowding out a negative narrative, sustained weekly cadence matters more than a single high-volume burst.",
     "metric": "consistency_engagement_multiplier", "value": "~5x engagement from regular posting", "applies_to": "global",
     "source": "Buffer — analysis of 100,000+ users (via frequency guide)", "url": "https://buffer.com/resources/social-media-frequency-guide/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Number of unique REFERRING DOMAINS is the single strongest-correlated factor with first-page Google rankings — prioritize acquiring NEW referring domains (link diversity) over raw backlink count.",
     "metric": "referring_domains_ranking_correlation", "value": "r=0.38 (strongest factor studied)", "applies_to": "goal:seo",
     "source": "Backlinko + Ahrefs — 11.8M Google Search Results", "url": "https://backlinko.com/search-engine-ranking", "as_of": "2020-04", "tier": "industry"},
    {"claim": "The #1 organic result has ~3.8x more backlinks than positions #2-10, and a page with zero referring domains earns essentially zero organic traffic — a minimum viable referring-domain base is required before ranking is possible.",
     "metric": "top_position_backlink_multiple", "value": "3.8x more backlinks at #1; ~0 traffic at 0 referring domains", "applies_to": "goal:seo",
     "source": "Backlinko + Ahrefs — 11.8M search results study", "url": "https://backlinko.com/search-engine-ranking", "as_of": "2020-04", "tier": "industry"},
    {"claim": "For AI-visibility (GEO/AEO), off-site BRAND MENTIONS beat backlinks by ~3x: branded web mentions correlate 0.664 with AI-Overview visibility vs 0.218 for backlinks; branded anchor text 0.527; YouTube mentions 0.737 (strongest single signal). Weight the earned-media plan toward mentions/digital PR, not just followed links.",
     "metric": "brand_mention_vs_backlink_ai_correlation", "value": "web mentions 0.664 vs backlinks 0.218; YouTube 0.737; anchor 0.527", "applies_to": "goal:geo",
     "source": "Ahrefs — ~75,000-brand AI Visibility study (Brand Radar)", "url": "https://ahrefs.com/academy/how-to-use-brand-radar/overview", "as_of": "2025-12", "tier": "industry"},
    {"claim": "Brands in the top quartile for web mentions receive up to 10x more AI-Overview citations than the next quartile — mention VOLUME (breadth of third-party corroboration) is the lever for getting cited, and to crowd out a negative narrative you must out-mention it across many sources.",
     "metric": "top_quartile_mention_ai_citation_multiple", "value": "up to 10x more AI-overview citations (top vs next quartile)", "applies_to": "goal:geo",
     "source": "Ahrefs Google AI Overview mentions study", "url": "https://ahrefs.com/academy/how-to-use-brand-radar/overview", "as_of": "2025", "tier": "industry"},
    {"claim": "In the local pack, link and citation signals are secondary but real: links ~8% and citations ~6% of local-pack ranking weight — size local digital-PR/citation effort modestly (GBP, on-page, and reviews matter more).",
     "metric": "local_pack_link_citation_weight", "value": "links 8%, citations 6% of local-pack weight", "applies_to": "goal:seo",
     "source": "BrightLocal / Whitespark Local Search Ranking Factors 2026", "url": "https://www.brightlocal.com/learn/google-local-algorithm-and-ranking-factors/", "as_of": "2025-11", "tier": "industry"},
    {"claim": "Citation CONSISTENCY (accurate NAP across major directories) matters more than raw citation count — consistent-NAP businesses are ~40% more likely to appear in the local pack. Build a consistent core citation set, not a high number.",
     "metric": "nap_consistency_local_pack_lift", "value": "+40% local-pack likelihood with consistent NAP", "applies_to": "goal:seo",
     "source": "BrightLocal local ranking factors guidance", "url": "https://www.brightlocal.com/learn/google-local-algorithm-and-ranking-factors/", "as_of": "2025", "tier": "industry"},
    {"claim": "Safe referring-domain acquisition velocity is baseline-relative, not a flat number: new sites ~5-10 quality links/mo (keep under ~5 NEW referring domains/mo); established domains can sustain ~2-2.5x their median monthly RD baseline (newer sites 1.5-2x). Ramp gradually — step-changes read engineered.",
     "metric": "safe_referring_domain_velocity", "value": "new: 5-10 links/mo (<5 new RDs); established: 2-2.5x baseline RD/mo", "applies_to": "goal:seo",
     "source": "Link-velocity industry syntheses (Sharprocket, Outreach Desk, W3era)", "url": "https://outreachdesk.com/link-velocity/", "as_of": "2026", "tier": "editorial"},
    {"claim": "Digital-PR output guideline: new sites realistically place ~1-3 earned placements/guest posts per month; established sites ~6-8/month — a usable per-month target for the earned-mention/link production line.",
     "metric": "guest_post_digital_pr_cadence", "value": "new sites 1-3/mo; established sites 6-8/mo", "applies_to": "goal:seo",
     "source": "Link-velocity industry syntheses", "url": "https://outreachdesk.com/link-velocity/", "as_of": "2026", "tier": "editorial"},
    {"claim": "Blog traffic gains flatten after ~11 posts/month — companies at 11-16/mo already capture most of the traffic lift, so for a small/single business target a steady climb toward ~8-16/month rather than chasing the 16+ ceiling from day one.",
     "metric": "diminishing_returns_threshold", "value": "~11 posts/mo before per-post returns flatten", "applies_to": "global",
     "source": "HubSpot blogging frequency benchmarks (via ConsultEvo)", "url": "https://consultevo.com/hubspot-blogging-frequency-guide/", "as_of": "2023", "tier": "industry"},
    {"claim": "Updating existing content beats net-new for maintaining a footprint: HubSpot found 76% of monthly blog views and 92% of blog leads came from older posts, and systematically refreshing old posts drove ~+106% organic traffic — budget a meaningful share of monthly output to refresh, not only new.",
     "metric": "refresh_vs_new_traffic_share", "value": "76% views / 92% leads from existing posts; +106% traffic from refresh", "applies_to": "goal:seo",
     "source": "HubSpot historical-optimization research (via Bluehost)", "url": "https://www.bluehost.com/blog/fresh-content-seo/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Refresh cadence should be tiered by volatility: evergreen pages every 6-12 months, competitive/high-value topics every 3-6 months, and fast-moving industries plus any page with stats/benchmarks/comparisons every 1-3 months. A substantial update changes ~20-30% of the text.",
     "metric": "refresh_interval_by_content_type", "value": "3-6 mo competitive; 6-12 mo evergreen; 1-3 mo time-sensitive; ~20-30% text changed", "applies_to": "goal:seo",
     "source": "Bluehost Fresh Content for SEO (citing Google substantial-update guidance)", "url": "https://www.bluehost.com/blog/fresh-content-seo/", "as_of": "2026-01", "tier": "industry"},
    {"claim": "Page-one content for popular keywords is updated within ~2 years on average (~730 days across 17,805 keywords); high-difficulty (KD 90+) refresh every ~320 days and 'best software' terms every ~143 days — the harder/more competitive the target, the shorter the refresh interval must be.",
     "metric": "seo_page1_update_interval", "value": "~730 days avg; ~320 days KD 90+; ~143 days 'best software'", "applies_to": "goal:seo",
     "source": "Siege Media content-refresh data study (17,805 keywords)", "url": "https://www.siegemedia.com/strategy/content-refresh", "as_of": "2025-04", "tier": "industry"},
    {"claim": "AI search rewards recency aggressively: across 7,683 dated pages / 47,097 citations, 75% of LLM-cited pages were updated in the last year and 88% within two; 'always-on' consistently-cited pages have a median update age of ~5.6 months. Refresh core pages roughly every 3-6 months to stay AI-citable.",
     "metric": "ai_citation_median_update_age", "value": "75% cited pages updated <1yr; always-on median ~5.6 mo", "applies_to": "goal:geo",
     "source": "Seer Interactive — Content Recency's Impact on AI Visibility (2026)", "url": "https://www.seerinteractive.com/insights/study-content-recencys-impact-on-ai-visibility-in-2026", "as_of": "2026-07", "tier": "industry"},
    {"claim": "ChatGPT shows the strongest recency bias: 76.4% of its most-cited pages were updated within 30 days; content updated within 30 days earns ~3.2x more AI citations, and citation rates drop 40-60% after ~90 days without a meaningful update.",
     "metric": "ai_freshness_citation_lift", "value": "30-day-fresh ~3.2x citations; -40-60% after 90 days", "applies_to": "goal:geo",
     "source": "Quattr content-freshness analysis (2026 AI-citation studies)", "url": "https://www.quattr.com/blog/content-freshness", "as_of": "2026-01", "tier": "industry"},
    {"claim": "~50% of AI citations come from content <13 weeks (~90 days) old — treat ~quarterly as the maximum refresh clock for any page you want LLM-cited, and monthly-to-bimonthly for the 'always-on' cited set. This is the freshness floor for crowding out a negative narrative in AI answers.",
     "metric": "ai_citation_half_life", "value": "~50% of AI citations from content <13 weeks old", "applies_to": "goal:geo",
     "source": "Rank & Convert — The 13-Week Rule", "url": "https://rank-and-convert.ghost.io/the-13-week-rule-how-content-freshness-drives-ai-search-citations/", "as_of": "2026-01", "tier": "editorial"},
    {"claim": "Burst-then-drip is the supported publishing pattern for launch/crowd-out: an initial concentrated burst establishes topical coverage and dating signals, then a steady drip sustains freshness. The pattern is supported but no precise optimal burst size is evidenced — size the burst from the gap/cluster count and hold the drip at the diminishing-returns band.",
     "metric": "burst_then_drip_support", "value": "pattern-supported; no evidenced optimal burst size", "applies_to": "global",
     "source": "ClearVoice — how many blog posts for launch", "url": "https://www.clearvoice.com/resources/how-many-posts-does-my-blog-need/", "as_of": "2023", "tier": "editorial"},
    {"claim": "To bury ONE negative page-1 result, produce ~8-12 original, indexed positive pages within the first 90 days — the concrete asset volume a reputation program should generate to start displacing a negative.",
     "metric": "displacement_asset_volume", "value": "8-12 positive indexed pages / 90 days (per negative)", "applies_to": "goal:reputation",
     "source": "NetReputation — How to Bury Negative Search Results (2026)", "url": "https://www.netreputation.com/how-to-bury-negative-search-results/", "as_of": "2026", "tier": "industry"},
    {"claim": "Displacement needs sustained cadence, not a one-time burst: at minimum one owned-site update per month, weekly posting on at least one social/publishing platform, and roughly quarterly PR — consistency over months, not weeks, is what suppresses.",
     "metric": "displacement_cadence", "value": ">=1 owned update/mo + weekly social + ~quarterly PR", "applies_to": "goal:reputation",
     "source": "NetReputation — How to Bury Negative Search Results", "url": "https://www.netreputation.com/how-to-bury-negative-search-results/", "as_of": "2026", "tier": "industry"},
    {"claim": "Time-to-suppress: visible ranking movement typically begins at months 3-9, stretching to 9-18 months when the negative sits on a high-authority source — size the program to run for that whole window, not a single sprint.",
     "metric": "time_to_suppress", "value": "3-9 mo to move; 9-18 mo for high-authority negatives", "applies_to": "goal:reputation",
     "source": "NetReputation — How to Bury Negative Search Results", "url": "https://www.netreputation.com/how-to-bury-negative-search-results/", "as_of": "2026", "tier": "industry"},
    {"claim": "Independent ORM benchmark corroborates the timeline: measurable progress within 60-90 days, with full suppression of a negative off page one typically taking 4-8 months depending on how competitive the landscape is.",
     "metric": "time_to_suppress_corroboration", "value": "measurable 60-90 days; full off-page-1 4-8 months", "applies_to": "goal:reputation",
     "source": "Reputation X — Suppress Negative Search Results", "url": "https://www.reputationx.com/services/repair/suppress", "as_of": "2025", "tier": "editorial"},
    {"claim": "Page 1 has 10 organic slots; the displacement target is to control/influence enough of them (~8-10) with pages you own or influence so the negative is pushed to page 2 — the total program must be able to occupy ~8-10 page-1 positions.",
     "metric": "page1_slots_to_control", "value": "10 organic slots; control/influence ~8-10 to bury one negative", "applies_to": "goal:reputation",
     "source": "Reputation Rhino — How to Push Down Negative Google Search Results", "url": "https://www.reputationrhino.com/how-to-push-down-negative-google-search-results-a-practical-plan-that-works/", "as_of": "2025", "tier": "editorial"},
    {"claim": "Minimum viable displacement floor: strongly linking as few as ~3 controlled assets can push them into positions #3-#5 and bury one negative onto page 2 — a floor that moves one result, not a whole narrative, so treat it as the minimum, not the target.",
     "metric": "min_assets_to_bury_one", "value": "~3 strongly-linked assets can occupy #3-#5", "applies_to": "goal:reputation",
     "source": "Reputation Rhino / NetReputation ORM guidance", "url": "https://www.reputationrhino.com/how-to-push-down-negative-google-search-results-a-practical-plan-that-works/", "as_of": "2025", "tier": "editorial"},
    {"claim": "'Off page 1' is the displacement finish line because page 2+ earns a combined organic CTR under 1% (~0.63-0.78%) and only ~0.63% of searchers reach page two — pushing a negative to page 2 removes ~70%+ of its clicks.",
     "metric": "page2_ctr", "value": "<1% to page 2 (0.63-0.78%); ~70%+ click loss off p1", "applies_to": "goal:reputation",
     "source": "Backlinko — 4M Google Search Results (2025); First Page Sage", "url": "https://backlinko.com/google-ctr-stats", "as_of": "2025", "tier": "industry"},
    {"claim": "Organic CTR is front-loaded (pos1 ~40%, pos2 ~19%, pos3 ~10%, tapering to ~1.6% at pos10) so displacement value is non-linear — shoving a negative from a top-3 slot toward pos 8-10 destroys most of its traffic even before it leaves page 1.",
     "metric": "ctr_by_position", "value": "pos1 ~40% / pos3 ~10% / pos10 ~1.6%", "applies_to": "goal:reputation",
     "source": "First Page Sage — Google CTR by Ranking Position", "url": "https://firstpagesage.com/reports/google-click-through-rates-ctrs-by-ranking-position/", "as_of": "2025", "tier": "industry"},
    {"claim": "For the AI/answer channel, displacement works by CONSENSUS not rank: an LLM synthesizes a brand answer from ~30-40 sources and triangulates agreement across independent ones — seed enough positive/corroborating placements that the majority of retrievable sources agree, not just one owned page.",
     "metric": "ai_sources_synthesized", "value": "~30-40 sources triangulated per brand answer", "applies_to": "goal:geo",
     "source": "ScaleVisible — The Consensus Model", "url": "https://scalevisible.com/aiseo-strategy/building-ai-consensus/", "as_of": "2026", "tier": "editorial"},
    {"claim": "AI displacement requires BREADTH across trusted source types — brands present simultaneously on owned site + Wikipedia + Reddit + review platforms + YouTube are cited far more (and framed more positively) than single-channel brands. Spread corroborating positives across ~4-5 source types, don't stack them on the site alone.",
     "metric": "ai_corroboration_breadth", "value": "corroborate across ~4-5 trusted source types", "applies_to": "goal:geo",
     "source": "ScaleVisible / Semrush most-cited-domains guidance", "url": "https://scalevisible.com/aiseo-strategy/building-ai-consensus/", "as_of": "2026", "tier": "editorial"},
    {"claim": "AI share-of-voice is the measurable displacement metric: SOV = % of category AI answers mentioning the brand; track SOV + sentiment weekly on high-value commercial prompts, because presence with negative framing does NOT count as displacement — the goal is positive-framed SOV, not raw mentions.",
     "metric": "ai_share_of_voice", "value": "SOV = % of category AI answers mentioning brand; track weekly", "applies_to": "goal:geo",
     "source": "Cognizo — How to Measure AI Share of Voice (2026)", "url": "https://www.cognizo.ai/blog/how-to-measure-ai-share-voice-methods-tools-benchmarks", "as_of": "2026", "tier": "industry"},
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


# =====================================================================================================
# NON-TEXT MIX count helpers -- how MUCH of each non-text surface to produce, sized from the cited
# entries above (2026 web-research pass), so video / podcast / social / backlinks / cadence / refresh /
# displacement are evidence-sized like blog length is, NOT hand-tuned constants. Every helper returns
# (min, max, source) and is CONSERVATIVE: where evidence supports "include it" but not a precise count,
# the source string says so (directional / editorial-tier). Callers clamp to their own budget.
# =====================================================================================================
def video_count_for(cluster_count: int, *, high_intent_ratio: float = 0.5, severity: float = 0.5) -> tuple[int, int, str]:
    """(min, max, source) videos for a pillar program. Video is produced for the HIGH-VIDEO-INTENT
    clusters (how-to/demo/review/pricing -- BrightEdge) + 1 flagship pillar video, NOT every subtopic;
    YouTube citations concentrate in ~40-60% of subtopics. Monthly output stays >=1/week (vidIQ cadence)."""
    n = max(0, int(cluster_count or 0))
    lo = 1 + round(0.40 * n)
    hi = 1 + round(0.60 * n)
    if severity >= 0.66:      # crowding out a strong negative -> lean to the top of the band
        lo = hi
    return (max(1, lo), max(1, hi),
            "BrightEdge video-intent targeting (40-60% of subtopics) + vidIQ cadence (>=1/week); "
            "directional (extrapolated from intent data, not an effect size)")


def podcast_appearance_target(severity: float = 0.5, *, months: int = 12) -> tuple[int, int, str]:
    """(min, max, source) guest podcast appearances over `months`. Audio is a corroboration/authority
    LAYER sized on cadence, not per-cluster: quarterly-per-topic floor -> 1-2/month target, leaning to
    2/mo when crowding out an active negative. Editorial-tier consensus (Podsicle/PodcastHawk/Springcast)."""
    m = max(1, int(months or 1))
    lo = max(4, m // 3)                                   # quarterly floor
    hi = min(m * 2, round(m * (1 + max(0.0, min(1.0, severity)))))   # up to 2/mo
    return (lo, max(lo, hi),
            "Podcast guesting cadence: quarterly floor -> 1-2/mo (Podsicle/PodcastHawk/Springcast); "
            "editorial consensus, not an effect size. Pair each with a published transcript to be AI-citable.")


_SOCIAL_WEEKLY = {   # evidence-backed posts/WEEK bands (Buffer 2026 / HubSpot); reddit is relevance-gated
    "linkedin": (2, 5), "linkedin_aggressive": (6, 10),
    "x": (21, 28), "twitter": (21, 28),
    "instagram": (3, 5), "facebook": (7, 14), "tiktok": (2, 5),
    "reddit": (1, 3),   # substantive, genuinely-relevant contributions only -- NOT volume-scalable
}


def social_count_for(platform: str, *, aggressive: bool = False) -> tuple[int, int, str]:
    """(min, max, source) POSTS PER WEEK for a platform, from Buffer 2026 / HubSpot cadence studies.
    Reddit is quality-GATED (1-3 substantive contributions/wk), never volume-scaled."""
    p = (platform or "").lower().replace(" ", "")
    key = "linkedin_aggressive" if (p == "linkedin" and aggressive) else p
    band = _SOCIAL_WEEKLY.get(key) or _SOCIAL_WEEKLY.get(p) or (2, 5)
    note = ("Buffer 2026 / HubSpot per-platform cadence (posts/week)"
            if p != "reddit" else
            "Reddit is relevance-gated: cap to genuinely relevant threads (LLMs cite Reddit heavily "
            "but ban automated posting) -- quality, not volume")
    return (band[0], band[1], note)


def social_atoms_per_piece(word_count: int = 2000) -> tuple[int, int, str]:
    """(min, max, source) social atoms a long-form pillar yields (repurpose once, distribute many):
    ~15-20 per 2,000 words (~5 LinkedIn + 5-6 X + 2-3 IG + 1 email), scaled linearly, clamped [8, 20]."""
    wc = max(1, int(word_count or 2000))
    n = max(8, min(20, round(15 * wc / 2000)))
    return (max(8, n - 3), n,
            "Repurposing yield ~15-20 atoms/pillar (editorial repurposing guides); scales with length")


def backlink_target_for(authority: str = "established", *, severity: float = 0.5,
                        baseline_rd_per_mo: Optional[float] = None) -> tuple[int, int, str]:
    """(min, max, source) NEW referring domains/month -- baseline-RELATIVE acquisition velocity (safe,
    never a step-change that trips spam signals). Given a baseline, target ~1.5-2.5x it; else authority
    defaults. More referring domains correlate with higher rank (Backlinko/Ahrefs)."""
    if baseline_rd_per_mo and baseline_rd_per_mo > 0:
        return (round(1.5 * baseline_rd_per_mo), round(2.5 * baseline_rd_per_mo),
                "1.5-2.5x your current referring-domain velocity (safe, no step-change); baseline-relative")
    band = (2, 4) if (authority or "").lower() in ("new", "low") else (4, 8)
    if severity >= 0.66:
        band = (band[1], band[1] + 2)
    return (band[0], band[1],
            "New referring domains/mo via guest posts + digital PR (editorial link-velocity synthesis); "
            "keep low-authority sites under ~5/mo to stay safe")


def publishing_cadence_for(severity: float = 0.5, *, has_base_corpus: bool = True) -> tuple[int, int, str]:
    """(min, max, source) published pieces/MONTH overall. Band 8-16; push toward/above 16 when crowding
    out a negative (HubSpot: 16+/mo ~ 3.5x traffic; per-post ROI flattens ~11/mo). Once a base corpus
    exists, split ~60% net-new / ~40% refresh (existing posts drive most traffic; refresh ~+106%)."""
    lo, hi = 8, 16
    if severity >= 0.66:
        lo = 12
    split = (" -- split ~60% net-new / ~40% refresh of existing pieces" if has_base_corpus else
             " -- mostly net-new until a base corpus exists")
    return (lo, hi,
            "HubSpot blog frequency: 16+/mo ~ 3.5x traffic (per-post ROI flattens ~11/mo)" + split)


def refresh_interval_for(content_tier: str = "competitive", *, goal: str = "seo") -> tuple[int, int, str]:
    """(min, max, source) MONTHS between substantial updates -- a refresh clock. Evergreen 6-12,
    competitive 3-6, time-sensitive 1-3; tightened for GEO/AEO (AI cites fresh content far more, so keep
    anything you want LLM-cited on a <=quarterly clock)."""
    tier = (content_tier or "competitive").lower()
    base = {"evergreen": (6, 12), "competitive": (3, 6), "time_sensitive": (1, 3)}.get(tier, (3, 6))
    if (goal or "").lower() in ("geo", "aeo"):
        base = (min(base[0], 3), min(base[1], 6)) if tier != "time_sensitive" else (1, 2)
        return (base[0], base[1],
                "AI cites recently-updated content far more (Perplexity ~82% <30d vs ~37% older): keep "
                "cited pages on a <=quarterly refresh clock")
    return (base[0], base[1], "Refresh clock by content tier (SEO page-1 pages updated ~every 3-6 mo)")


def displacement_pages_for(num_negatives: int = 1, *, high_authority: bool = False,
                           days: int = 90) -> tuple[int, int, str]:
    """(min, max, source) positive/neutral indexed assets to publish (first ~90 days) to bury a negative
    page-1 result and control ~8-10 of the 10 slots. ~8-12 assets PER negative; ~1.5-2x for a
    high-authority negative. ORM-vendor guidance (directional, not peer-reviewed)."""
    n = max(1, int(num_negatives or 1))
    lo, hi = 8 * n, 12 * n
    if high_authority:
        lo, hi = round(lo * 1.5), round(hi * 2)
    return (max(3, lo), hi,
            "~8-12 original positive/earned assets per page-1 negative in the first 90 days to control "
            "8-10 of 10 slots (ORM-vendor guidance; directional). High-authority negatives take 9-18 mo.")


def review_velocity_target(num_negatives: int = 0, *, competitive: bool = False,
                           deficit: int = 0) -> tuple[int, int, str]:
    """(min, max, source) NEW Google reviews/MONTH to earn -- review count/recency/velocity is a top
    local-pack ranking signal AND the sentiment AI reads. Baseline steady velocity ~3-6/mo; push higher
    for a competitive local market, a review DEFICIT vs the local competitors, and to counter page-1
    negatives (positive-review flow dilutes a negative narrative). Steady + genuine only -- never a
    burst (Google filters review spikes)."""
    lo, hi = 3, 6
    if competitive:
        lo, hi = 5, 10
    # More negatives / a bigger deficit -> a higher sustained velocity to out-weigh them.
    bump = min(8, max(0, int(num_negatives or 0)) * 2 + (2 if int(deficit or 0) >= 10 else 0))
    lo, hi = lo + bump, hi + bump
    return (lo, hi,
            "Review velocity/recency is a top local-pack signal (Whitespread/BrightLocal local-SEO "
            "surveys); earn steadily & genuinely -- Google filters review bursts. Raise the rate for a "
            "competitive market, a review deficit, or to out-weigh a negative narrative.")
