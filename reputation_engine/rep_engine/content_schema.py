"""
Structured data (JSON-LD) for generated content (Phase 5B).
===========================================================
Google's structured-data guides say to mark up content with schema.org JSON-LD so search + answer
engines can extract entities and relationships. The engine previously emitted NONE (schema was a
manual dev task), so every published piece shipped as bare prose. This builds the JSON-LD
DETERMINISTICALLY from the finished asset — Article/BlogPosting, FAQPage (when the body has a Q&A
block), VideoObject (video pieces, with transcript), LocalBusiness (local pages), and an
ImageObject list — plus a helper to inject a single `<script type="application/ld+json">` block on
publish.

SD-policy compliant: the markup only reflects content that is actually on the page (title, author,
date, the real Q&A text, the real transcript) — nothing fabricated, no numbers we don't have.
Pure + dependency-light (no LLM, no network); safe to call at approve()/publish time.
"""
from __future__ import annotations

import json
import re
from typing import Optional

try:
    from . import content_quality as _cq
except ImportError:  # pragma: no cover
    import content_quality as _cq  # type: ignore

# Asset types that are a VIDEO deliverable (get VideoObject, not Article).
_VIDEO_TYPES = frozenset({"explainer_video", "video_script", "video", "explainer"})
_LOCAL_TYPES = frozenset({"local_page"})


def _https(domain: str) -> str:
    d = (domain or "").strip()
    if not d:
        return ""
    return d if d.startswith("http") else "https://" + d.lstrip("/")


def _org(biz: dict) -> dict:
    o: dict = {"@type": "Organization", "name": (biz.get("name") or "").strip() or "The business"}
    url = _https(biz.get("domain") or "")
    if url:
        o["url"] = url
    return o


# A heading (markdown ## / ###) that reads like a QUESTION, followed by its answer paragraph.
_HEADING = re.compile(r"^\s{0,3}#{2,4}\s+(.+?)\s*$", re.M)
_WH = re.compile(r"^\s*(what|why|how|when|where|who|which|is|are|do|does|can|should)\b", re.I)


def _strip_md(t: str) -> str:
    t = re.sub(r"[*_`#>]+", "", t or "")
    return re.sub(r"\s+", " ", t).strip()


def faq_pairs(body: str, limit: int = 12) -> list[tuple[str, str]]:
    """Extract Q&A pairs for FAQPage: a question-style heading + the text until the next heading.
    Best-effort and conservative — returns [] when the body has no clear Q&A structure."""
    if not body:
        return []
    heads = list(_HEADING.finditer(body))
    pairs: list[tuple[str, str]] = []
    for i, m in enumerate(heads):
        q = _strip_md(m.group(1))
        if not (q.endswith("?") or _WH.match(q)):
            continue
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        ans = _strip_md(body[start:end])
        if len(q) >= 8 and len(ans) >= 20:
            pairs.append((q, ans[:900]))
        if len(pairs) >= limit:
            break
    return pairs


def build_jsonld(asset_type: str, title: str, body: str, biz: dict, *,
                 byline: Optional[str] = None, published_at: Optional[str] = None,
                 url: Optional[str] = None, geo: str = "",
                 images: Optional[list[dict]] = None) -> list[dict]:
    """Build the JSON-LD object list for a finished content asset. Deterministic; only reflects real
    content. `images` (optional) = [{url, alt}] once real images are attached (Phase 5C)."""
    at = (asset_type or "").lower()
    title = (title or "").strip()
    body = body or ""
    objs: list[dict] = []
    publisher = _org(biz)
    image_urls = [im.get("url") for im in (images or []) if im.get("url")]

    if at in _VIDEO_TYPES:
        # VideoObject + transcript — the highest-value AI/Google video signal (content_quality builds it).
        transcript = _cq._spoken_only(body) if hasattr(_cq, "_spoken_only") else body
        dur = _cq._runtime_secs(body) if hasattr(_cq, "_runtime_secs") else 0
        objs.append(_cq.video_object_schema(
            title=title, description=(body[:280]), transcript=transcript, duration_secs=dur,
            business_name=biz.get("name") or "", geo=geo, upload_date=(published_at or "")[:10],
            thumbnail_url=(image_urls[0] if image_urls else "")))
    else:
        # Article / BlogPosting — every text piece.
        art: dict = {
            "@context": "https://schema.org",
            "@type": "BlogPosting" if at in ("blog", "blog_post") else "Article",
            "headline": title[:110] or "Article",
            "publisher": publisher,
        }
        if byline:
            art["author"] = {"@type": "Person", "name": byline}
        elif publisher.get("name"):
            art["author"] = {"@type": "Organization", "name": publisher["name"]}
        if published_at:
            art["datePublished"] = published_at[:10]
            art["dateModified"] = published_at[:10]
        if url:
            art["mainEntityOfPage"] = {"@type": "WebPage", "@id": url}
        if image_urls:
            art["image"] = image_urls
        objs.append(art)

    # FAQPage — only when the body actually carries a Q&A block (SD policy: reflect visible content).
    pairs = faq_pairs(body)
    if pairs:
        objs.append({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs],
        })

    # LocalBusiness — for local landing pages, from the business's own identity (no fabricated NAP).
    if at in _LOCAL_TYPES and (biz.get("name")):
        lb: dict = {"@context": "https://schema.org", "@type": "LocalBusiness",
                    "name": biz.get("name")}
        if _https(biz.get("domain") or ""):
            lb["url"] = _https(biz["domain"])
        area = geo or biz.get("geo") or ""
        if area:
            lb["areaServed"] = area
        objs.append(lb)

    return objs


def to_script(objs: list[dict]) -> str:
    """Render the JSON-LD object list as a single `<script type="application/ld+json">` block
    (a @graph when there is more than one object). '' when there is nothing to emit."""
    if not objs:
        return ""
    if len(objs) == 1:
        graph = objs[0]
    else:
        graph = {"@context": "https://schema.org",
                 "@graph": [{k: v for k, v in o.items() if k != "@context"} for o in objs]}
    return ('<script type="application/ld+json">'
            + json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
            + "</script>")
