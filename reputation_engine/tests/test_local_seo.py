"""Local SEO rank tracker tests -- unit (SERP parsing heuristics) + integration (needs
REP_TEST_DSN). The live Serper call is mocked, so these run fully offline."""

from __future__ import annotations

from conftest import requires_db


# ----------------------------- unit -----------------------------
def test_host_strips_scheme_and_www():
    from rep_engine import local_seo as ls
    assert ls._host("https://www.teamunstoppable.com/about") == "teamunstoppable.com"
    assert ls._host("edwardjones.com") == "edwardjones.com"
    assert ls._host("") == ""


def test_match_party_by_domain_suffix():
    from rep_engine import local_seo as ls
    assert ls._match_party("Anything", "edwardjones.com",
                            title="Some title", link="https://www.edwardjones.com/us/fa") is True
    assert ls._match_party("Anything", "edwardjones.com",
                            title="Some title", link="https://other.com/x") is False


def test_match_party_by_name_tokens():
    from rep_engine import local_seo as ls
    # two distinctive tokens both present -> match
    assert ls._match_party("Northwestern Mutual", "",
                           title="Northwestern Mutual - Cincinnati", link="https://x.example") is True
    # single distinctive token must appear
    assert ls._match_party("Vanguard", "", title="Vanguard advisors", link="https://x.example") is True
    assert ls._match_party("Northwestern Mutual", "",
                           title="A different firm entirely", link="https://x.example") is False


def test_match_party_rejects_generic_category_word():
    from rep_engine import local_seo as ls
    stop = ls._category_stop({"services": "financial services"})
    # a domain-less competitor named for the category must NOT match every category-local title
    assert ls._match_party("Ace Financial", "", title="Best Financial Services in Cincinnati",
                           link="", stop=stop) is False
    # a distinctive domain-less name still matches
    assert ls._match_party("Buckeye Wealth Partners", "",
                           title="Buckeye Wealth Partners - Cincinnati", link="", stop=stop) is True


def test_match_party_requires_all_name_tokens():
    from rep_engine import local_seo as ls
    # must NOT match a title that contains only SOME of the distinctive tokens
    assert ls._match_party("New York Life", "", title="York County Public Library", link="") is False
    assert ls._match_party("New York Life", "", title="New York Life - Cincinnati branch", link="") is True


def test_match_party_no_shared_host_false_match():
    from rep_engine import local_seo as ls
    # a party on shared hosting must NOT be credited for the bare provider's own result
    assert ls._match_party("Joe", "joesfinance.wordpress.com",
                           title="WordPress.com", link="https://wordpress.com/") is False
    # a real subdomain of the party's domain still matches
    assert ls._match_party("Joe", "acme.com", title="x", link="https://blog.acme.com/post") is True


def test_as_rank_handles_bad_position():
    from rep_engine import local_seo as ls
    assert ls._as_rank(7, 99) == 7
    assert ls._as_rank("not-a-number", 4) == 4   # malformed -> falls back to index
    assert ls._as_rank(0, 3) == 3                 # 0 -> index
    assert ls._as_rank(None, 5) == 5


def test_rank_in_organic_uses_position_field_then_index():
    from rep_engine import local_seo as ls
    organic = [
        {"position": 1, "title": "Rival LLC", "link": "https://rival.com/a"},
        {"position": 5, "title": "Subject Co", "link": "https://subject.com/about"},
    ]
    rank, url, title = ls._rank_in_organic(organic, "Subject Co", "subject.com")
    assert rank == 5 and "subject.com" in url
    rank2, _, _ = ls._rank_in_organic(organic, "Nowhere Inc", "nowhere.com")
    assert rank2 is None


def test_rank_in_places():
    from rep_engine import local_seo as ls
    places = [{"position": 2, "title": "Subject Co", "website": "https://subject.com"}]
    assert ls._rank_in_places(places, "Subject Co", "subject.com") == 2
    assert ls._rank_in_places(places, "Other Co", "other.com") is None


def test_track_skips_without_serper_key(monkeypatch):
    from rep_engine import local_seo as ls
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    out = ls.track(1, quiet=True)
    assert out.get("skipped") is True


# ----------------------------- integration -----------------------------
def _subject(conn, name="Subject Co", domain="subject.com"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo, services) "
        "VALUES (%s,%s,'win','MLM','Cincinnati, OH','financial services') RETURNING id",
        (name, domain),
    ).fetchone()
    conn.commit()
    return r["id"]


@requires_db
def test_track_records_and_latest_rolls_up(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import local_seo as ls
    from rep_engine import competitor as cp
    bid = _subject(conn)
    cp.register_competitor(bid, "Rival LLC", "rival.com")

    # SERPER must look configured for track() to proceed; the live call is mocked.
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    def fake_serper(query, location, num=20):
        assert location == "Cincinnati, OH"   # geo-targeted, as designed
        return {
            "organic": [
                {"position": 1, "title": "Rival LLC - Cincinnati", "link": "https://rival.com/x"},
                {"position": 3, "title": "Subject Co", "link": "https://subject.com/about"},
            ],
            "places": [
                {"position": 1, "title": "Rival LLC", "website": "https://rival.com"},
            ],
        }
    monkeypatch.setattr(ls, "_serper_local", fake_serper)

    out = ls.track(bid, quiet=True)
    assert out["rows"] > 0 and out["queries"] == 4   # 4 category-local prompts

    payload = ls.latest(bid)
    s = payload["summary"]
    # subject ranks #3 (page one) in every local query, never in the map pack
    assert s["queries"] == 4
    assert s["page_one_rate"] == 1.0
    assert s["local_pack_rate"] == 0.0
    assert s["avg_organic_rank"] == 3.0
    assert s["ranked_queries"] == 4
    # a query carries the subject + the competitor (Rival #1 + map pack #1)
    q0 = payload["queries"][0]
    assert q0["subject"]["organic_rank"] == 3 and q0["subject"]["on_page_one"] is True
    rival = next(c for c in q0["competitors"] if c["name"] == "Rival LLC")
    assert rival["organic_rank"] == 1 and rival["local_pack_rank"] == 1


@requires_db
def test_latest_empty_without_runs(fresh_schema):
    conn = fresh_schema
    from rep_engine import local_seo as ls
    bid = _subject(conn)
    payload = ls.latest(bid)
    assert payload["run_id"] is None and payload["queries"] == [] and payload["summary"] is None
