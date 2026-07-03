"""
Schema-deploy verification (Recommendation #2d)
===============================================
The gap model recommends JSON-LD schema (FAQPage, LocalBusiness, Organization, ...). This closes the
loop: it FETCHES the live pages and confirms whether the recommended schema is actually deployed and
parseable -- so a "add schema" task can be verified done, and the plan doesn't keep recommending
schema that's already live (or claim a fix shipped when it didn't).

Run:  python -m rep_engine.schema_verify check --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import re

try:
    from . import http as _http
    from .db import db
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("schema_verify")

_DESIRED = ["Organization", "LocalBusiness", "FAQPage", "Person", "Review", "Service", "BreadcrumbList"]
_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)


def _types_in(html: str) -> set:
    found: set = set()
    for m in _LD.finditer(html or ""):
        try:
            data = json.loads(m.group(1).strip())
        except (ValueError, TypeError):
            continue
        for node in (data if isinstance(data, list) else [data]):
            if isinstance(node, dict):
                t = node.get("@type")
                for tt in (t if isinstance(t, list) else [t]):
                    if tt:
                        found.add(str(tt))
                for g in node.get("@graph", []) or []:  # @graph wrappers are common
                    if isinstance(g, dict) and g.get("@type"):
                        gt = g["@type"]
                        found.update(gt if isinstance(gt, list) else [gt])
    return found


def _key_urls(business_id: int) -> list[str]:
    with db() as conn:
        b = conn.execute("SELECT domain FROM businesses WHERE id=%s", (business_id,)).fetchone()
        s = conn.execute("SELECT summary FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                         (business_id,)).fetchone()
    urls: list[str] = []
    if s and s["summary"]:
        summ = s["summary"] if isinstance(s["summary"], dict) else json.loads(s["summary"])
        urls = [p.get("url") for p in (summ.get("pages") or []) if p.get("url")][:5]
    if not urls and b and b["domain"]:
        d = b["domain"]
        urls = [d if "//" in d else "https://" + d]
    return urls


def check(business_id: int, quiet: bool = True) -> dict:
    """Fetch up to 5 key pages, extract deployed JSON-LD @types, and report present vs missing vs the
    recommended set. Fail-safe: an unreachable page is skipped, never raises."""
    urls = _key_urls(business_id)
    present: set = set()
    checked = 0
    per_page = []
    for url in urls:
        try:
            res = _http.request_json("GET", url, parse_json=False, timeout=15, max_retries=1,
                                     guard_redirects=True)
            html = res.text if res.ok else ""
        except Exception:  # noqa: BLE001
            html = ""
        if html:
            checked += 1
            types = _types_in(html)
            present |= types
            per_page.append({"url": url, "schema_types": sorted(types)})
    missing = [t for t in _DESIRED if t not in present]
    out = {"checked_pages": checked, "deployed_schema": sorted(present),
           "recommended_missing": missing, "per_page": per_page,
           "verdict": ("no pages reachable" if checked == 0
                       else "all recommended schema present" if not missing
                       else f"{len(missing)} recommended schema type(s) not yet deployed")}
    if not quiet:
        print(json.dumps(out, indent=2, default=str))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Schema-deploy verification")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "check":
        check(args.business_id, quiet=False)


if __name__ == "__main__":
    main()
