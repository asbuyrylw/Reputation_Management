"""source_ingest.ingest_from_pages -- website -> grounding corpus (Phase G.1 / UX-2).

Needs REP_TEST_DSN (writes source_documents). Locks: artifacts + thin pages excluded, dedup by URL,
substantive pages ingested as source_type='site_crawl', and RE-ingest is idempotent (replaces, no
duplicates) so re-syncing keeps the corpus current instead of piling up.
"""
from __future__ import annotations

from conftest import requires_db


def _biz(conn, domain="acme.com"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, geo) VALUES ('Acme',%s,'win','Denver CO') "
        "RETURNING id", (domain,)).fetchone()
    conn.commit()
    return r["id"]


def _page(url, *, status=200, words=300, text="lorem ipsum " * 60, title="Page"):
    from rep_engine import site_crawl as sc
    return sc.PageAudit(url=url, status=status, word_count=words, main_text=text, title=title)


def _crawl_docs(conn, bid):
    return conn.execute(
        "SELECT title, source_type, source_url FROM source_documents "
        "WHERE business_id=%s AND source_type='site_crawl' ORDER BY id", (bid,)).fetchall()


@requires_db
def test_ingest_filters_and_dedupes(fresh_schema):
    conn = fresh_schema
    from rep_engine import source_ingest as si
    bid = _biz(conn)
    pages = [
        _page("https://acme.com/about", words=400, title="About"),
        _page("https://acme.com/pricing", words=250, title="Pricing"),
        _page("https://acme.com/about#team", words=400, title="About dup"),          # dup URL (fragment)
        _page("https://acme.com/thin", words=10, text="hi", title="Thin"),            # too thin
        _page("https://acme.com/wp-json/x", words=500, title="WP artifact"),          # crawl artifact
        _page("https://acme.com/down", status=500, title="Down"),                     # non-200
    ]
    out = si.ingest_from_pages(bid, pages)
    assert out["ingested"] == 2                       # about + pricing only
    assert out["source_type"] == "site_crawl"
    titles = {r["title"] for r in _crawl_docs(conn, bid)}
    assert titles == {"About", "Pricing"}


@requires_db
def test_reingest_is_idempotent(fresh_schema):
    conn = fresh_schema
    from rep_engine import source_ingest as si
    bid = _biz(conn)
    first = [_page("https://acme.com/a", title="A"), _page("https://acme.com/b", title="B")]
    si.ingest_from_pages(bid, first)
    # re-sync with a changed site (b gone, c added) -> corpus REFLECTS the new crawl, no dupes
    second = [_page("https://acme.com/a", title="A"), _page("https://acme.com/c", title="C")]
    out = si.ingest_from_pages(bid, second)
    assert out["ingested"] == 2 and out["replaced"] == 2
    titles = {r["title"] for r in _crawl_docs(conn, bid)}
    assert titles == {"A", "C"}                        # replaced, not accumulated


@requires_db
def test_upload_docs_are_not_touched_by_sync(fresh_schema):
    conn = fresh_schema
    from rep_engine import source_ingest as si
    from rep_engine import source_material as sm
    bid = _biz(conn)
    sm.add_document(bid, "hand-written brand facts", title="Brand", source_type="upload")
    si.ingest_from_pages(bid, [_page("https://acme.com/a", title="A")])
    # the manual upload survives a website sync (only site_crawl docs are refreshed)
    kinds = conn.execute(
        "SELECT source_type, COUNT(*) c FROM source_documents WHERE business_id=%s GROUP BY source_type",
        (bid,)).fetchall()
    by = {r["source_type"]: r["c"] for r in kinds}
    assert by.get("upload") == 1 and by.get("site_crawl") == 1
