"""Structured data (Phase 5B) — regression lock for the JSON-LD builder.

Proves content_schema builds valid schema.org JSON-LD deterministically from a finished asset:
Article/BlogPosting for text, FAQPage when the body has a Q&A block, VideoObject (with transcript)
for video, LocalBusiness for local pages — and only reflects real content (SD-policy safe).
"""
from __future__ import annotations

import json

from rep_engine import content_schema as cs

BIZ = {"name": "Acme Life", "domain": "acmelife.com", "geo": "Cincinnati, OH"}


def test_article_schema():
    objs = cs.build_jsonld("article", "Term life insurance guide", "Body text here.", BIZ,
                           byline="editorial team", published_at="2026-08-01")
    art = objs[0]
    assert art["@type"] == "Article"
    assert art["headline"].startswith("Term life")
    assert art["author"]["name"] == "editorial team"
    assert art["datePublished"] == "2026-08-01"
    assert art["publisher"]["url"] == "https://acmelife.com"
    # renders to a single ld+json script
    script = cs.to_script(objs)
    assert script.startswith('<script type="application/ld+json">') and script.endswith("</script>")
    assert json.loads(script[len('<script type="application/ld+json">'):-len("</script>")])["@type"] == "Article"


def test_blogposting_type():
    objs = cs.build_jsonld("blog", "How we help", "x", BIZ)
    assert objs[0]["@type"] == "BlogPosting"


def test_faqpage_when_qa_present():
    body = ("## What is term life insurance?\nIt is coverage for a set term of years that pays a "
            "benefit if you pass away during it.\n\n## How much does it cost?\nPremiums depend on age, "
            "health, term length and coverage amount.\n")
    objs = cs.build_jsonld("article", "Term life FAQ", body, BIZ)
    faq = next((o for o in objs if o["@type"] == "FAQPage"), None)
    assert faq is not None
    qs = [q["name"] for q in faq["mainEntity"]]
    assert "What is term life insurance?" in qs and len(faq["mainEntity"]) == 2


def test_no_faqpage_without_qa():
    objs = cs.build_jsonld("article", "A plain article", "Just prose, no question headings here at all.", BIZ)
    assert all(o["@type"] != "FAQPage" for o in objs)


def test_video_object_with_transcript():
    script_body = "[0:05] Welcome to the explainer. [0:12] Here's what term life covers. [0:30] Thanks."
    objs = cs.build_jsonld("explainer_video", "Term life explainer", script_body, BIZ,
                           published_at="2026-08-01")
    vo = objs[0]
    assert vo["@type"] == "VideoObject"
    assert vo["transcript"] and "term life" in vo["transcript"].lower()


def test_localbusiness_for_local_page():
    objs = cs.build_jsonld("local_page", "Cincinnati life insurance", "Local page body", BIZ)
    lb = next((o for o in objs if o["@type"] == "LocalBusiness"), None)
    assert lb is not None
    assert lb["name"] == "Acme Life" and lb["areaServed"] == "Cincinnati, OH"


def test_graph_when_multiple_objects():
    body = "## What is it?\nAn answer long enough to count as a real answer paragraph here."
    script = cs.to_script(cs.build_jsonld("article", "T", body, BIZ))
    parsed = json.loads(script[len('<script type="application/ld+json">'):-len("</script>")])
    assert "@graph" in parsed and len(parsed["@graph"]) == 2
