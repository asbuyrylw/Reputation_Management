"""
Reputation Crowding-Out Engine -- Google Analytics (GA4) ingest + reads (Wave 1)
===============================================================================
The behavioral outcome layer (sessions/users/pageviews/conversions/engagement) that complements
GSC's acquisition data. Mirrors gsc_data.py: keyless/no-connection = safe no-op. Three grains:
ga_daily (backbone), ga_top_pages (landing-page attribution, is_our_content), ga_channels (mix).

Run:  python -m rep_engine.ga_data ingest --business-id 2
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
    from .gsc_data import _norm_url  # reuse the URL normalizer
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from connections import vault as _vault  # type: ignore
    from gsc_data import _norm_url  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("ga_data")

WINDOW_DAYS = 28
LAG_DAYS = 2
BACKFILL_DAYS = 400


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _provider():
    try:
        from .connections.providers import google_analytics as g
    except ImportError:  # pragma: no cover
        from connections.providers import google_analytics as g  # type: ignore
    return g


def _connection(business_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM platform_connections WHERE business_id=%s AND kind='google_analytics' "
            "AND status='active' ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    if not row:
        return None
    creds = _vault.credentials(row["id"], business_id)
    if not creds:
        return None
    prop = (creds.get("meta") or {}).get("ga_property") or creds.get("account_ref")
    if not prop:
        return None
    creds["property"] = prop
    return creds


def _our_paths(business_id: int) -> dict:
    """Map page PATH -> asset_id for our published content (GA reports pagePath, not full URL)."""
    out: dict[str, Optional[int]] = {}
    with db() as conn:
        for r in conn.execute("SELECT id, published_url FROM assets WHERE business_id=%s AND "
                              "published_url IS NOT NULL", (business_id,)).fetchall():
            p = (urlparse(r["published_url"]).path or "").rstrip("/") or "/"
            out[p] = r["id"]
    return out


def _i(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ga_date(s: str) -> Optional[str]:
    # GA4 "date" dimension is YYYYMMDD
    if s and len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s or None


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------
def ingest(business_id: int, connection_id: Optional[int] = None) -> dict:
    creds = _connection(business_id)
    if not creds:
        return {"skipped": True, "reason": "no active Google Analytics connection/property"}
    g = _provider()
    token, prop, cid = creds["access_token"], creds["property"], creds["id"]
    today = _today()
    end = today - timedelta(days=1)

    with db() as conn:
        mx = conn.execute("SELECT MAX(date) m FROM ga_daily WHERE business_id=%s AND property=%s",
                          (business_id, prop)).fetchone()["m"]
    start = (today - timedelta(days=BACKFILL_DAYS)) if mx is None else (mx - timedelta(days=LAG_DAYS))
    days = _ingest_daily(g, token, prop, business_id, cid, start.isoformat(), end.isoformat())

    win_start = (end - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    win_end = end.isoformat()
    pages = _ingest_pages(g, token, prop, business_id, cid, win_start, win_end, _our_paths(business_id))
    chans = _ingest_channels(g, token, prop, business_id, cid, win_start, win_end)

    out = {"property": prop, "days_ingested": days, "backfilled": mx is None,
           "top_pages": pages, "channels": chans}
    log.info("ga ingest biz %d: %s", business_id, {k: out[k] for k in ("property", "days_ingested", "backfilled")})
    return out


def _ingest_daily(g, token, prop, business_id, cid, start, end) -> int:
    res = g.run_report(token, prop, dimensions=["date"],
                       metrics=["sessions", "totalUsers", "screenPageViews", "conversions",
                                "engagementRate", "averageSessionDuration"],
                       start_date=start, end_date=end)
    if not res.get("ok"):
        return 0
    n = 0
    for r in res.get("rows") or []:
        try:
            d = _parse_ga_date((r["dims"] or [None])[0])
            m = r["metrics"] or []
            with db() as conn:
                conn.execute(
                    "INSERT INTO ga_daily (business_id, connection_id, property, date, sessions, users, "
                    "pageviews, conversions, engagement_rate, avg_session_sec) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (business_id, property, date) DO UPDATE SET sessions=EXCLUDED.sessions, "
                    "users=EXCLUDED.users, pageviews=EXCLUDED.pageviews, conversions=EXCLUDED.conversions, "
                    "engagement_rate=EXCLUDED.engagement_rate, avg_session_sec=EXCLUDED.avg_session_sec, "
                    "captured_at=now()",
                    (business_id, cid, prop, d, _i(m[0] if len(m) > 0 else 0),
                     _i(m[1] if len(m) > 1 else 0), _i(m[2] if len(m) > 2 else 0),
                     _f(m[3] if len(m) > 3 else 0), _f(m[4] if len(m) > 4 else None),
                     _f(m[5] if len(m) > 5 else None)))
                conn.commit()
            n += 1
        except Exception as e:  # noqa: BLE001
            log.debug("ga daily row skipped: %s", e)
    return n


def _ingest_pages(g, token, prop, business_id, cid, start, end, our_paths) -> int:
    res = g.run_report(token, prop, dimensions=["pagePath"], metrics=["sessions", "conversions"],
                       start_date=start, end_date=end, limit=250)
    if not res.get("ok"):
        return 0
    n = 0
    for r in res.get("rows") or []:
        try:
            page = (r["dims"] or [None])[0] or ""
            path = (urlparse(page).path or page or "").rstrip("/") or "/"
            aid = our_paths.get(path)
            m = r["metrics"] or []
            with db() as conn:
                conn.execute(
                    "INSERT INTO ga_top_pages (business_id, connection_id, property, period_start, "
                    "period_end, page, sessions, conversions, is_our_content, asset_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (business_id, property, period_start, period_end, page) DO UPDATE SET "
                    "sessions=EXCLUDED.sessions, conversions=EXCLUDED.conversions, "
                    "is_our_content=EXCLUDED.is_our_content, asset_id=EXCLUDED.asset_id, captured_at=now()",
                    (business_id, cid, prop, start, end, page, _i(m[0] if m else 0),
                     _f(m[1] if len(m) > 1 else 0), aid is not None, aid))
                conn.commit()
            n += 1
        except Exception as e:  # noqa: BLE001
            log.debug("ga page row skipped: %s", e)
    return n


def _ingest_channels(g, token, prop, business_id, cid, start, end) -> int:
    res = g.run_report(token, prop, dimensions=["sessionDefaultChannelGroup"],
                       metrics=["sessions", "conversions"], start_date=start, end_date=end, limit=50)
    if not res.get("ok"):
        return 0
    n = 0
    for r in res.get("rows") or []:
        try:
            ch = (r["dims"] or [None])[0] or "(other)"
            m = r["metrics"] or []
            with db() as conn:
                conn.execute(
                    "INSERT INTO ga_channels (business_id, connection_id, property, period_start, "
                    "period_end, channel, sessions, conversions) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (business_id, property, period_start, period_end, channel) DO UPDATE SET "
                    "sessions=EXCLUDED.sessions, conversions=EXCLUDED.conversions, captured_at=now()",
                    (business_id, cid, prop, start, end, ch, _i(m[0] if m else 0),
                     _f(m[1] if len(m) > 1 else 0)))
                conn.commit()
            n += 1
        except Exception as e:  # noqa: BLE001
            log.debug("ga channel row skipped: %s", e)
    return n


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def _has_connection(business_id: int) -> bool:
    with db() as conn:
        r = conn.execute("SELECT 1 FROM platform_connections WHERE business_id=%s AND "
                         "kind='google_analytics' AND status='active' LIMIT 1", (business_id,)).fetchone()
    return bool(r)


def latest(business_id: int) -> dict:
    with db() as conn:
        mx = conn.execute("SELECT MAX(date) m FROM ga_daily WHERE business_id=%s", (business_id,)).fetchone()["m"]
        if not mx:
            return {"has_data": False, "collecting": _has_connection(business_id)}
        cur = conn.execute(
            "SELECT COALESCE(SUM(sessions),0) s, COALESCE(SUM(users),0) u, COALESCE(SUM(pageviews),0) p, "
            "COALESCE(SUM(conversions),0) c, AVG(engagement_rate) e FROM ga_daily "
            "WHERE business_id=%s AND date > %s", (business_id, mx - timedelta(days=WINDOW_DAYS))).fetchone()
        prev = conn.execute(
            "SELECT COALESCE(SUM(sessions),0) s, COALESCE(SUM(conversions),0) c FROM ga_daily "
            "WHERE business_id=%s AND date > %s AND date <= %s",
            (business_id, mx - timedelta(days=2 * WINDOW_DAYS), mx - timedelta(days=WINDOW_DAYS))).fetchone()
    return {"has_data": True, "collecting": False, "as_of": mx.isoformat(),
            "sessions": int(cur["s"]), "users": int(cur["u"]), "pageviews": int(cur["p"]),
            "conversions": float(cur["c"]), "engagement_rate": float(cur["e"]) if cur["e"] is not None else None,
            "sessions_delta": int(cur["s"]) - int(prev["s"]),
            "conversions_delta": float(cur["c"]) - float(prev["c"])}


def trend(business_id: int, days: Optional[int] = None) -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT date, sessions, users, pageviews, conversions FROM ga_daily "
                            "WHERE business_id=%s ORDER BY date", (business_id,)).fetchall()
    out = [{"date": r["date"].isoformat(), "sessions": r["sessions"], "users": r["users"],
            "pageviews": r["pageviews"], "conversions": float(r["conversions"] or 0)} for r in rows]
    return out[-days:] if days else out


def top_pages(business_id: int, limit: int = 25, ours_only: bool = False) -> list[dict]:
    with db() as conn:
        win = conn.execute("SELECT MAX(period_end) m FROM ga_top_pages WHERE business_id=%s", (business_id,)).fetchone()["m"]
        if not win:
            return []
        sql = ("SELECT page, sessions, conversions, is_our_content, asset_id FROM ga_top_pages "
               "WHERE business_id=%s AND period_end=%s")
        params = [business_id, win]
        if ours_only:
            sql += " AND is_our_content"
        sql += " ORDER BY sessions DESC LIMIT %s"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [{"page": r["page"], "sessions": r["sessions"], "conversions": float(r["conversions"] or 0),
             "is_our_content": r["is_our_content"], "asset_id": r["asset_id"]} for r in rows]


def channels(business_id: int) -> list[dict]:
    with db() as conn:
        win = conn.execute("SELECT MAX(period_end) m FROM ga_channels WHERE business_id=%s", (business_id,)).fetchone()["m"]
        if not win:
            return []
        rows = conn.execute("SELECT channel, sessions, conversions FROM ga_channels "
                           "WHERE business_id=%s AND period_end=%s ORDER BY sessions DESC",
                           (business_id, win)).fetchall()
    return [{"channel": r["channel"], "sessions": r["sessions"], "conversions": float(r["conversions"] or 0)} for r in rows]


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="Google Analytics (GA4) ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("ingest", "show"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    out = ingest(args.business_id) if args.cmd == "ingest" else latest(args.business_id)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
