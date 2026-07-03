"""
Reputation Crowding-Out Engine -- Google Search Console ingest + reads (Wave 1)
==============================================================================
Real organic-search OUTCOME data (clicks/impressions/CTR/position). Mirrors gbp_reviews.py:
keyless/no-connection = safe no-op (returns {"skipped": True}). Three grains:
  - gsc_daily: site-total daily backbone (the ROI/trend series; never anonymization-distorted).
  - gsc_query_stats / gsc_page_stats: top-N over a rolling 28-day window.
Pages are matched to OUR published content (publish_targets.external_url / assets.published_url) so
we can report "clicks earned by content WE published" as a distinct, honest, smaller number.

Data lag: GSC finalizes ~2-3 days late, so we cap "final" at today-3 and re-fetch the trailing
window each run (dataState=fresh, idempotent overwrite via ON CONFLICT). We persist daily totals
forever -> we can show multi-year ROI past GSC's own 16-month retention.

Run:
    python -m rep_engine.gsc_data ingest --business-id 2
    python -m rep_engine.gsc_data show   --business-id 2
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

try:
    from .db import db
    from .connections import vault as _vault
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from connections import vault as _vault  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("gsc_data")

WINDOW_DAYS = 28
LAG_DAYS = 3          # GSC final data lands ~2-3 days late
BACKFILL_DAYS = 480   # ~16 months (GSC retention)
ROW_LIMIT = 25000     # daily backbone (paginated)
TOPN = 250            # windowed top queries/pages


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _today() -> date:
    return datetime.now(timezone.utc).date()


def _provider():
    try:
        from .connections.providers import google_search_console as g
    except ImportError:  # pragma: no cover
        from connections.providers import google_search_console as g  # type: ignore
    return g


def _connection(business_id: int) -> Optional[dict]:
    """Newest active GSC connection with a chosen property, decrypted. None -> caller skips."""
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM platform_connections WHERE business_id=%s AND kind='google_search_console' "
            "AND status='active' ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    if not row:
        return None
    creds = _vault.credentials(row["id"], business_id)
    if not creds:
        return None
    prop = (creds.get("meta") or {}).get("gsc_property") or creds.get("account_ref")
    if not prop:
        return None
    creds["property"] = prop
    return creds


def _norm_url(u: str) -> str:
    """Normalize a URL for matching: https, lowercase host, no www, no trailing slash, no query."""
    if not u:
        return ""
    s = u.strip()
    if "//" not in s:
        s = "//" + s
    p = urlparse(s)
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "").rstrip("/")
    return f"{host}{path}"


def _our_urls(business_id: int) -> dict:
    """Map normalized URL -> asset_id for content WE published (assets + publish_targets)."""
    out: dict[str, Optional[int]] = {}
    with db() as conn:
        for r in conn.execute(
                "SELECT id, published_url FROM assets WHERE business_id=%s AND published_url IS NOT NULL",
                (business_id,)).fetchall():
            n = _norm_url(r["published_url"])
            if n:
                out[n] = r["id"]
        try:
            for r in conn.execute(
                    "SELECT asset_id, external_url FROM publish_targets WHERE business_id=%s "
                    "AND external_url IS NOT NULL", (business_id,)).fetchall():
                n = _norm_url(r["external_url"])
                if n:
                    out.setdefault(n, r["asset_id"])
        except Exception:  # noqa: BLE001 -- publish_targets may be absent on older schemas
            pass
    return out


def _row_vals(row: dict) -> tuple:
    return (int(row.get("clicks") or 0), int(row.get("impressions") or 0),
            row.get("ctr"), row.get("position"))


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------
def ingest(business_id: int, connection_id: Optional[int] = None) -> dict:
    creds = _connection(business_id)
    if not creds:
        return {"skipped": True, "reason": "no active Google Search Console connection/property"}
    g = _provider()
    token, prop, cid = creds["access_token"], creds["property"], creds["id"]
    today = _today()
    final_end = today - timedelta(days=LAG_DAYS)

    # 1. daily backbone -- backfill on first run, else incremental from max(date)-LAG
    with db() as conn:
        mx = conn.execute("SELECT MAX(date) m FROM gsc_daily WHERE business_id=%s AND property=%s",
                          (business_id, prop)).fetchone()["m"]
    backfilled = False
    if mx is None:
        start = today - timedelta(days=BACKFILL_DAYS)
        backfilled = True
        state = "final"
    else:
        start = mx - timedelta(days=LAG_DAYS)  # re-fetch trailing window (provisional -> final)
        state = "fresh"
    days = _ingest_daily(g, token, prop, business_id, cid, start.isoformat(),
                         (today - timedelta(days=1)).isoformat(), state)

    # 2. windowed top queries + pages (28d ending final_end)
    win_start = (final_end - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    win_end = final_end.isoformat()
    tq = _ingest_window(g, token, prop, business_id, cid, win_start, win_end, "query")
    our = _our_urls(business_id)
    tp = _ingest_window(g, token, prop, business_id, cid, win_start, win_end, "page", our_urls=our)

    out = {"property": prop, "days_ingested": days, "backfilled": backfilled,
           "top_queries": tq, "top_pages": tp,
           "our_pages": sum(1 for k in our)}
    log.info("gsc ingest biz %d: %s", business_id, {k: out[k] for k in ("property", "days_ingested", "backfilled")})
    return out


def _ingest_daily(g, token, prop, business_id, cid, start, end, state) -> int:
    n = 0
    start_row = 0
    while True:
        res = g.query_search_analytics(token, prop, start_date=start, end_date=end,
                                       dimensions=["date"], row_limit=ROW_LIMIT, start_row=start_row,
                                       data_state=state)
        if not res.get("ok"):
            break
        rows = res.get("rows") or []
        if not rows:
            break
        for r in rows:
            try:
                d = (r.get("keys") or [None])[0]
                clk, imp, ctr, pos = _row_vals(r)
                with db() as conn:
                    conn.execute(
                        "INSERT INTO gsc_daily (business_id, connection_id, property, date, clicks, "
                        "impressions, ctr, position, data_state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (business_id, property, date) DO UPDATE SET clicks=EXCLUDED.clicks, "
                        "impressions=EXCLUDED.impressions, ctr=EXCLUDED.ctr, position=EXCLUDED.position, "
                        "data_state=EXCLUDED.data_state, captured_at=now()",
                        (business_id, cid, prop, d, clk, imp, ctr, pos, state))
                    conn.commit()
                n += 1
            except Exception as e:  # noqa: BLE001 -- one bad row never aborts the sweep
                log.debug("gsc daily row skipped: %s", e)
        if len(rows) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT
    return n


def _ingest_window(g, token, prop, business_id, cid, start, end, dim, our_urls=None) -> int:
    res = g.query_search_analytics(token, prop, start_date=start, end_date=end,
                                   dimensions=[dim], row_limit=TOPN, start_row=0)
    if not res.get("ok"):
        return 0
    rows = res.get("rows") or []
    n = 0
    for r in rows:
        try:
            key = (r.get("keys") or [None])[0]
            clk, imp, ctr, pos = _row_vals(r)
            with db() as conn:
                if dim == "query":
                    conn.execute(
                        "INSERT INTO gsc_query_stats (business_id, connection_id, property, period_start, "
                        "period_end, query, clicks, impressions, ctr, position) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (business_id, property, period_start, period_end, query) "
                        "DO UPDATE SET clicks=EXCLUDED.clicks, impressions=EXCLUDED.impressions, "
                        "ctr=EXCLUDED.ctr, position=EXCLUDED.position, captured_at=now()",
                        (business_id, cid, prop, start, end, key, clk, imp, ctr, pos))
                else:  # page
                    norm = _norm_url(key or "")
                    aid = (our_urls or {}).get(norm)
                    conn.execute(
                        "INSERT INTO gsc_page_stats (business_id, connection_id, property, period_start, "
                        "period_end, page, clicks, impressions, ctr, position, is_our_content, asset_id) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (business_id, property, period_start, period_end, page) "
                        "DO UPDATE SET clicks=EXCLUDED.clicks, impressions=EXCLUDED.impressions, "
                        "ctr=EXCLUDED.ctr, position=EXCLUDED.position, is_our_content=EXCLUDED.is_our_content, "
                        "asset_id=EXCLUDED.asset_id, captured_at=now()",
                        (business_id, cid, prop, start, end, key, clk, imp, ctr, pos,
                         aid is not None, aid))
                conn.commit()
            n += 1
        except Exception as e:  # noqa: BLE001
            log.debug("gsc window row skipped: %s", e)
    return n


# ---------------------------------------------------------------------------
# reads (each returns gracefully before data exists)
# ---------------------------------------------------------------------------
def _has_connection(business_id: int) -> bool:
    with db() as conn:
        r = conn.execute("SELECT 1 FROM platform_connections WHERE business_id=%s AND "
                         "kind='google_search_console' AND status='active' LIMIT 1",
                         (business_id,)).fetchone()
    return bool(r)


def latest(business_id: int) -> dict:
    """Current 28-day KPIs vs the prior 28 days (+ deltas). collecting=True before data lands."""
    with db() as conn:
        mx = conn.execute("SELECT MAX(date) m FROM gsc_daily WHERE business_id=%s", (business_id,)).fetchone()["m"]
        if not mx:
            return {"has_data": False, "collecting": _has_connection(business_id)}
        cur = conn.execute(
            "SELECT COALESCE(SUM(clicks),0) clicks, COALESCE(SUM(impressions),0) impressions, "
            "AVG(position) position FROM gsc_daily WHERE business_id=%s AND date > %s",
            (business_id, mx - timedelta(days=WINDOW_DAYS))).fetchone()
        prev = conn.execute(
            "SELECT COALESCE(SUM(clicks),0) clicks, COALESCE(SUM(impressions),0) impressions, "
            "AVG(position) position FROM gsc_daily WHERE business_id=%s AND date > %s AND date <= %s",
            (business_id, mx - timedelta(days=2 * WINDOW_DAYS), mx - timedelta(days=WINDOW_DAYS))).fetchone()
    def f(x):
        return float(x) if x is not None else None
    clicks, impr = int(cur["clicks"]), int(cur["impressions"])
    pclicks, pimpr = int(prev["clicks"]), int(prev["impressions"])
    ctr = round(clicks / impr, 4) if impr else None
    return {"has_data": True, "collecting": False, "as_of": mx.isoformat(),
            "clicks": clicks, "impressions": impr, "ctr": ctr, "position": f(cur["position"]),
            "clicks_delta": clicks - pclicks, "impressions_delta": impr - pimpr,
            "clicks_prev": pclicks}


def trend(business_id: int, days: Optional[int] = None) -> list[dict]:
    sql = ("SELECT date, clicks, impressions, ctr, position FROM gsc_daily WHERE business_id=%s "
           "ORDER BY date")
    with db() as conn:
        rows = conn.execute(sql, (business_id,)).fetchall()
    out = [{"date": r["date"].isoformat(), "clicks": r["clicks"], "impressions": r["impressions"],
            "ctr": float(r["ctr"]) if r["ctr"] is not None else None,
            "position": float(r["position"]) if r["position"] is not None else None} for r in rows]
    return out[-days:] if days else out


def _latest_window(conn, business_id: int):
    return conn.execute("SELECT MAX(period_end) m FROM gsc_query_stats WHERE business_id=%s",
                        (business_id,)).fetchone()["m"]


def top_queries(business_id: int, limit: int = 25) -> list[dict]:
    with db() as conn:
        win = _latest_window(conn, business_id)
        if not win:
            return []
        rows = conn.execute(
            "SELECT query, clicks, impressions, ctr, position FROM gsc_query_stats "
            "WHERE business_id=%s AND period_end=%s ORDER BY clicks DESC, impressions DESC LIMIT %s",
            (business_id, win, limit)).fetchall()
    return [{"query": r["query"], "clicks": r["clicks"], "impressions": r["impressions"],
             "ctr": float(r["ctr"]) if r["ctr"] is not None else None,
             "position": float(r["position"]) if r["position"] is not None else None} for r in rows]


def top_pages(business_id: int, limit: int = 25, ours_only: bool = False) -> list[dict]:
    with db() as conn:
        win = conn.execute("SELECT MAX(period_end) m FROM gsc_page_stats WHERE business_id=%s",
                           (business_id,)).fetchone()["m"]
        if not win:
            return []
        sql = ("SELECT page, clicks, impressions, ctr, position, is_our_content, asset_id "
               "FROM gsc_page_stats WHERE business_id=%s AND period_end=%s")
        params = [business_id, win]
        if ours_only:
            sql += " AND is_our_content"
        sql += " ORDER BY clicks DESC, impressions DESC LIMIT %s"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [{"page": r["page"], "clicks": r["clicks"], "impressions": r["impressions"],
             "ctr": float(r["ctr"]) if r["ctr"] is not None else None,
             "position": float(r["position"]) if r["position"] is not None else None,
             "is_our_content": r["is_our_content"], "asset_id": r["asset_id"]} for r in rows]


def opportunities(business_id: int, limit: int = 15) -> list[dict]:
    """Striking-distance queries: enough impressions, ranking ~5-15, CTR below expected -> a small
    push lands page 1. Highest-leverage SEO actions."""
    with db() as conn:
        win = _latest_window(conn, business_id)
        if not win:
            return []
        rows = conn.execute(
            "SELECT query, clicks, impressions, ctr, position FROM gsc_query_stats "
            "WHERE business_id=%s AND period_end=%s AND impressions >= 30 "
            "AND position BETWEEN 5 AND 15 ORDER BY impressions DESC LIMIT %s",
            (business_id, win, limit)).fetchall()
    return [{"query": r["query"], "impressions": r["impressions"], "clicks": r["clicks"],
             "position": round(float(r["position"]), 1) if r["position"] is not None else None,
             "ctr": float(r["ctr"]) if r["ctr"] is not None else None} for r in rows]


def roi_summary(business_id: int) -> dict:
    """Before/after (earliest 28-day window vs latest) + our-content click roll-up + equivalent
    Google-Ads value where a query maps to a tracked keyword's CPC."""
    with db() as conn:
        mn = conn.execute("SELECT MIN(date) a, MAX(date) b FROM gsc_daily WHERE business_id=%s",
                          (business_id,)).fetchone()
        if not mn or not mn["a"]:
            return {"has_data": False, "collecting": _has_connection(business_id)}
        first_start, last = mn["a"], mn["b"]
        baseline = conn.execute(
            "SELECT COALESCE(SUM(clicks),0) c FROM gsc_daily WHERE business_id=%s AND date <= %s",
            (business_id, first_start + timedelta(days=WINDOW_DAYS))).fetchone()["c"]
        latest_clicks = conn.execute(
            "SELECT COALESCE(SUM(clicks),0) c FROM gsc_daily WHERE business_id=%s AND date > %s",
            (business_id, last - timedelta(days=WINDOW_DAYS))).fetchone()["c"]
        our = conn.execute(
            "SELECT COALESCE(SUM(clicks),0) c, COUNT(*) n FROM gsc_page_stats WHERE business_id=%s "
            "AND is_our_content AND period_end=(SELECT MAX(period_end) FROM gsc_page_stats WHERE business_id=%s)",
            (business_id, business_id)).fetchone()
        # equivalent value: latest-window query clicks * matched keyword CPC
        eq = conn.execute(
            "SELECT COALESCE(SUM(q.clicks * tk.cpc),0) v FROM gsc_query_stats q "
            "JOIN target_keywords tk ON lower(tk.keyword)=lower(q.query) AND tk.business_id=q.business_id "
            "WHERE q.business_id=%s AND q.period_end=(SELECT MAX(period_end) FROM gsc_query_stats WHERE business_id=%s) "
            "AND tk.cpc IS NOT NULL", (business_id, business_id)).fetchone()["v"]
    return {"has_data": True, "collecting": False,
            "baseline_clicks": int(baseline), "latest_clicks": int(latest_clicks),
            "our_content_clicks": int(our["c"]), "our_content_pages": int(our["n"]),
            "equivalent_ads_value": round(float(eq), 2) if eq else 0.0,
            "window_days": WINDOW_DAYS}


def reconcile(business_id: int) -> dict:
    """Optional prune of windowed rows older than ~24 months; gsc_daily kept forever."""
    cutoff = (_today() - timedelta(days=730)).isoformat()
    with db() as conn:
        q = conn.execute("DELETE FROM gsc_query_stats WHERE business_id=%s AND period_end < %s",
                         (business_id, cutoff)).rowcount
        p = conn.execute("DELETE FROM gsc_page_stats WHERE business_id=%s AND period_end < %s",
                         (business_id, cutoff)).rowcount
        conn.commit()
    return {"pruned_queries": int(q or 0), "pruned_pages": int(p or 0)}


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="Google Search Console ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("ingest", "show"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    out = ingest(args.business_id) if args.cmd == "ingest" else latest(args.business_id)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
