"""
llms.txt generator (Recommendation #2d)
=======================================
Emit an `llms.txt` for the client's site -- the emerging convention (akin to robots.txt/sitemap) that
tells AI crawlers what a site is and points them at its most citable pages. Generated from the
business profile + the latest crawl, so it is accurate and current. Almost no competitor ships this,
and it is a direct, cheap AEO/GEO lever (clearer entity + a curated content map for the engines).

Run:  python -m rep_engine.llms_txt generate --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("llms_txt")


def _pages(business_id: int) -> list[dict]:
    with db() as conn:
        s = conn.execute("SELECT summary FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                         (business_id,)).fetchone()
    if not s or not s["summary"]:
        return []
    summ = s["summary"] if isinstance(s["summary"], dict) else json.loads(s["summary"])
    out = []
    for p in summ.get("pages", []) or []:
        url = p.get("url")
        if not url or "thin_content" in (p.get("issues") or []):
            continue
        out.append({"url": url, "title": p.get("title") or url,
                    "desc": (p.get("meta_description") or p.get("summary") or "").strip()})
    return out[:30]


def generate(business_id: int, quiet: bool = True) -> dict:
    """Build the llms.txt markdown for a business. Returns {content, page_count} (dormant-safe:
    works off the profile alone if there's no crawl yet)."""
    with db() as conn:
        b = conn.execute("SELECT name, domain, services, goal, geo FROM businesses WHERE id=%s",
                         (business_id,)).fetchone()
    if not b:
        return {"content": "", "page_count": 0}
    name = b["name"] or "This business"
    services = (b.get("services") or "").strip()
    geo = (b.get("geo") or "").strip()
    summary = (b.get("goal") or "").strip()
    desc = f"{name}" + (f" provides {services}" if services else "") + (f" in {geo}" if geo else "") + "."
    lines = [f"# {name}", "", f"> {desc}", ""]
    if summary:
        lines += ["## About", "", summary, ""]
    if services or geo:
        lines += ["## Services" + (f" ({geo})" if geo else ""), ""]
        for s in [x.strip() for x in services.split(",") if x.strip()]:
            lines.append(f"- {s}")
        lines.append("")
    pages = _pages(business_id)
    if pages:
        lines += ["## Key pages", ""]
        for p in pages:
            d = f": {p['desc']}" if p["desc"] else ""
            lines.append(f"- [{p['title']}]({p['url']}){d}")
        lines.append("")
    lines += ["## Contact", "", f"- Website: {b.get('domain') or ''}".rstrip(), ""]
    content = "\n".join(lines)
    out = {"content": content, "page_count": len(pages),
           "note": "Place this at https://<your-domain>/llms.txt so AI crawlers can read it."}
    if not quiet:
        print(content)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="llms.txt generator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "generate":
        generate(args.business_id, quiet=False)


if __name__ == "__main__":
    main()
