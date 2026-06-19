"""Citation analytics integration tests -- require REP_TEST_DSN."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from conftest import requires_db


def _biz(conn, name="Acme Co", domain="acme.com", contested="MLM"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo) "
        "VALUES (%s,%s,'win',%s,'Cincinnati OH') RETURNING id", (name, domain, contested)
    ).fetchone()
    conn.commit()
    return r["id"]


def _run(conn, bid, when=None):
    when = when or datetime.now()
    return conn.execute("INSERT INTO audit_runs (business_id, finished_at) VALUES (%s,%s) RETURNING id",
                        (bid, when)).fetchone()["id"]


def _ans(conn, rid, bid, sources, persona="", location=""):
    conn.execute(
        "INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,cited_sources,persona,location,failed) "
        "VALUES (%s,%s,'e','p','t',%s,%s,%s,false)",
        (rid, bid, json.dumps(sources), persona, location),
    )
    conn.commit()


@requires_db
def test_share_of_voice_classifies_domains(fresh_schema):
    conn = fresh_schema
    from rep_engine import citation_analytics as ca
    bid = _biz(conn, domain="acme.com", contested="MLM")
    rid = _run(conn, bid)
    # owned (acme.com), neutral (wikipedia), contested (ripoffreport)
    _ans(conn, rid, bid, ["https://acme.com/about", "https://en.wikipedia.org/x",
                          "https://ripoffreport.com/acme"])
    out = ca.analyze(bid, quiet=True)
    sov = out["share_of_voice"]
    assert "owned" in sov and "neutral" in sov and "contested" in sov
    assert out["total_citations"] == 3
    # owned domain present in top list
    assert any(d["classification"] == "owned" for d in out["top_domains"])


@requires_db
def test_momentum_flags_contested_falling_owned_rising(fresh_schema):
    conn = fresh_schema
    from rep_engine import citation_analytics as ca
    bid = _biz(conn, domain="acme.com")
    # prev run: contested-heavy
    r1 = _run(conn, bid, datetime.now() - timedelta(days=30))
    _ans(conn, r1, bid, ["https://ripoffreport.com/x", "https://ripoffreport.com/y", "https://acme.com/a"])
    # current run: owned-heavy
    r2 = _run(conn, bid, datetime.now())
    _ans(conn, r2, bid, ["https://acme.com/a", "https://acme.com/b", "https://acme.com/c"])
    out = ca.momentum(bid, quiet=True)
    # acme.com should be a rising owned gainer; ripoffreport a contested loser
    assert "acme.com" in out["summary"]["owned_or_neutral_gainers"]
    assert any("ripoff" in d for d in out["summary"]["contested_losers"])


@requires_db
def test_persona_location_lenses(fresh_schema):
    conn = fresh_schema
    from rep_engine import citation_analytics as ca
    bid = _biz(conn, domain="acme.com")
    rid = _run(conn, bid)
    # generic lens sees contested; cincinnati-local lens sees owned
    _ans(conn, rid, bid, ["https://ripoffreport.com/x"], persona="", location="")
    _ans(conn, rid, bid, ["https://acme.com/a"], persona="local_customer", location="Cincinnati OH")
    out = ca.personas(bid, quiet=True)
    lenses = {(l["persona"], l["location"]): l for l in out["lenses"]}
    assert ("(generic)", "(generic)") in lenses
    assert ("local_customer", "Cincinnati OH") in lenses
    # the local lens should show owned share, the generic lens contested share
    local = lenses[("local_customer", "Cincinnati OH")]["share_of_voice"]
    generic = lenses[("(generic)", "(generic)")]["share_of_voice"]
    assert local.get("owned", 0) > 0
    assert generic.get("contested", 0) > 0


@requires_db
def test_momentum_needs_two_runs(fresh_schema):
    conn = fresh_schema
    from rep_engine import citation_analytics as ca
    bid = _biz(conn)
    rid = _run(conn, bid)
    _ans(conn, rid, bid, ["https://acme.com/a"])
    assert ca.momentum(bid, quiet=True) == {}


@requires_db
def test_domain_extraction_handles_dict_and_str(fresh_schema):
    conn = fresh_schema
    from rep_engine import citation_analytics as ca
    bid = _biz(conn, domain="acme.com")
    rid = _run(conn, bid)
    # mix of str URL and dict source shapes
    _ans(conn, rid, bid, ["https://acme.com/a", {"url": "https://example.org/b"},
                          {"domain": "news.com"}])
    out = ca.analyze(bid, quiet=True)
    domains = [d["domain"] for d in out["top_domains"]]
    assert "acme.com" in domains
    assert "example.org" in domains
    assert "news.com" in domains


def test_source_type_buckets():
    from rep_engine.citation_analytics import _source_type
    biz = {"domain": "acme.com"}
    cases = {
        "acme.com": "own", "blog.acme.com": "own",
        "yelp.com": "review", "bbb.org": "review",
        "facebook.com": "social", "linkedin.com": "social",
        "reddit.com": "forum", "quora.com": "forum",
        "forbes.com": "news",
        "ripoffreport.com": "complaint",         # complaint wins over any 'review' overlap
        "en.wikipedia.org": "reference",
        "yellowpages.com": "directory",
        "some-random-blog.net": "other",
    }
    for domain, expected in cases.items():
        assert _source_type(domain, biz) == expected, f"{domain} -> {_source_type(domain, biz)}"
    assert _source_type("", biz) == "other"
