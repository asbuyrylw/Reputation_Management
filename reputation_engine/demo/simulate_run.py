"""
SIMULATION HARNESS -- integration smoke test with FAKE engine responses.
========================================================================
!!! THIS DOES NOT PRODUCE REAL DATA ABOUT ANY BUSINESS. !!!

It plugs synthetic, clearly-labeled answers into the REAL pipeline so you can watch
every stage run (audit -> scoring -> gap model -> citation share-of-voice ->
timeline -> acceleration -> report) and inspect the report artifact. The engine
answers and their scores are invented fixtures, not anything an AI actually said.
To get REAL results, set real API keys and run preflight + orchestrator instead.

Run:
    REP_DB_DSN=postgresql://... python demo/simulate_run.py
"""

from __future__ import annotations

import os
import sys

# the business name is prefixed so it is impossible to mistake for a real client
SIM_NAME = "[SIMULATED] Demo Financial Team"
SIM_DOMAIN = "demo-financial.example"

# A small fixture of plausible-but-FAKE engine answers, keyed by a substring of the
# prompt. These are illustrative only -- invented to exercise the scoring/gap logic.
FAKE_ANSWERS = {
    "legitimate": (
        "The team appears to be a legitimate financial-services group with licensed "
        "agents; some online discussion debates the multi-level structure.",
        ["https://demo-financial.example/about", "https://en.wikipedia.org/wiki/Financial_adviser",
         "https://www.bbb.org/"],
    ),
    "reviews": (
        "Reviews are mixed: several clients praise the service, while a few forum "
        "posts raise concerns about recruiting practices.",
        ["https://www.trustpilot.com/", "https://ripoffreport.com/"],
    ),
    "should i use": (
        "It can be a fit if you want hands-on planning; compare fees against a "
        "fee-only fiduciary before deciding.",
        ["https://demo-financial.example/services", "https://www.investopedia.com/"],
    ),
    "_default": (
        "The organization offers life insurance and investment products through "
        "independent representatives.",
        ["https://demo-financial.example/", "https://www.naic.org/"],
    ),
}

# Fixed scores per prompt substring so the run is deterministic (NOT model output).
FAKE_SCORES = {
    "legitimate": {"sentiment": "mixed", "goal_alignment": 0.35, "mentions_contested": True,
                   "surfaces_owned": True, "key_sources": ["demo-financial.example", "bbb.org"],
                   "missing": ["state licensing detail", "years in business"]},
    "reviews": {"sentiment": "mixed", "goal_alignment": 0.10, "mentions_contested": True,
                "surfaces_owned": False, "key_sources": ["trustpilot.com", "ripoffreport.com"],
                "missing": ["volume of positive verified reviews"]},
    "should i use": {"sentiment": "neutral", "goal_alignment": 0.45, "mentions_contested": False,
                     "surfaces_owned": True, "key_sources": ["demo-financial.example"],
                     "missing": ["fee transparency page"]},
    "_default": {"sentiment": "neutral", "goal_alignment": 0.50, "mentions_contested": False,
                 "surfaces_owned": True, "key_sources": ["demo-financial.example"], "missing": []},
}

# Second-run scores: a modest, believable improvement so the timeline/trend and
# citation momentum sections have movement to show (still entirely fixture data).
FAKE_SCORES_RUN2 = {
    "legitimate": {**FAKE_SCORES["legitimate"], "goal_alignment": 0.45, "mentions_contested": False,
                   "key_sources": ["demo-financial.example", "bbb.org"]},
    "reviews": {**FAKE_SCORES["reviews"], "goal_alignment": 0.28,
                "key_sources": ["demo-financial.example", "trustpilot.com"]},
    "should i use": {**FAKE_SCORES["should i use"], "goal_alignment": 0.50},
    "_default": {**FAKE_SCORES["_default"], "goal_alignment": 0.54},
}
# Second-run answers shift citations toward owned/neutral (the crowding-out story).
FAKE_ANSWERS_RUN2 = {
    "legitimate": ("The team is a licensed financial-services group; its official site "
                   "and BBB profile are the primary sources cited.",
                   ["https://demo-financial.example/about", "https://demo-financial.example/credentials",
                    "https://www.bbb.org/"]),
    "reviews": ("Reviews are increasingly positive, with verified client testimonials "
                "on the company site featured alongside third-party ratings.",
                ["https://demo-financial.example/reviews", "https://www.trustpilot.com/"]),
    "should i use": ("A reasonable fit for hands-on planning; the firm now publishes a "
                     "clear fee-transparency page.",
                     ["https://demo-financial.example/services", "https://demo-financial.example/fees"]),
    "_default": ("The organization offers life insurance and investment products through "
                 "licensed representatives.",
                 ["https://demo-financial.example/", "https://www.naic.org/"]),
}


def _match(prompt: str, table: dict):
    p = prompt.lower()
    for key, val in table.items():
        if key != "_default" and key in p:
            return val
    return table["_default"]


def main() -> None:
    if not os.getenv("REP_DB_DSN"):
        print("Set REP_DB_DSN first (a throwaway/test database).")
        sys.exit(1)

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from rep_engine import ai_state_audit as m
    from rep_engine import citation_analytics as ca
    from rep_engine import timeline_estimator as te
    from rep_engine import acceleration_advisor as aa
    from rep_engine import feedback_loop as fb

    print("=" * 70)
    print(" SIMULATED RUN -- fake engine answers, NOT real data about any business")
    print("=" * 70)

    m.init_db()

    # one fixture engine standing in for a live AI engine
    class SimEngine:
        name = "simulated"
        model = "sim-fixture-v1"
        def answer(self, prompt: str) -> dict:
            text, sources = _match(prompt, FAKE_ANSWERS)
            return m._ok(text, sources)

    # patch the pipeline to use the fixture engine + deterministic fixture scores
    m.active_engines = lambda: [SimEngine()]
    m.score_answer = lambda b, prompt, ans: _match(prompt, FAKE_SCORES)
    m.POLITE_DELAY_S = 0  # no need to rate-limit a fixture engine

    # create the clearly-labeled simulated business
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(os.environ["REP_DB_DSN"], row_factory=dict_row)
    # clean any prior simulated business + its dependent rows (FK-safe)
    old = conn.execute("SELECT id FROM businesses WHERE name=%s", (SIM_NAME,)).fetchall()
    for r in old:
        oid = r["id"]
        for tbl, col in [("answers", "business_id"), ("citation_momentum", "business_id"),
                         ("learned_effectiveness", "business_id"), ("learned_baseline", "business_id"),
                         ("pipeline_steps", None), ("pipeline_runs", "business_id"),
                         ("gap_models", "business_id"), ("site_audits", "business_id"),
                         ("audit_runs", "business_id"), ("business_config", "business_id")]:
            try:
                if tbl == "pipeline_steps":
                    conn.execute("DELETE FROM pipeline_steps WHERE pipeline_run_id IN "
                                 "(SELECT id FROM pipeline_runs WHERE business_id=%s)", (oid,))
                else:
                    conn.execute(f"DELETE FROM {tbl} WHERE {col}=%s", (oid,))
            except Exception:  # noqa: BLE001 -- table may not exist
                conn.rollback()
        conn.execute("DELETE FROM businesses WHERE id=%s", (oid,))
    conn.commit()
    bid = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,%s,'financial services','win local trust queries','MLM','Cincinnati OH') RETURNING id",
        (SIM_NAME, SIM_DOMAIN),
    ).fetchone()["id"]
    conn.execute("INSERT INTO business_config (business_id, samples_per_prompt, monthly_budget_usd) "
                 "VALUES (%s,2,25) ON CONFLICT (business_id) DO NOTHING", (bid,))
    conn.commit()

    import json as _json
    from datetime import datetime, timedelta, timezone

    def _inject_gap(run_id, summary):
        conn.execute("CREATE TABLE IF NOT EXISTS gap_models (id BIGSERIAL PRIMARY KEY, business_id BIGINT, "
                     "run_id BIGINT, model JSONB, created_at TIMESTAMPTZ DEFAULT now())")
        conn.execute("INSERT INTO gap_models (business_id, run_id, model) VALUES (%s,%s,%s)",
                     (bid, run_id, _json.dumps(summary)))
        conn.commit()

    GAP1 = {"summary": "[SAMPLE] Owned content leads on branded queries; contested framing "
                       "concentrated in a few review/forum sources on category queries.",
            "missing_owned_content": ["fee-transparency page", "verified-reviews page",
                                      "state-licensing / credentials page"],
            "schema_gaps": ["Organization", "Review", "FAQPage"],
            "contested_sources": ["ripoffreport.com"], "priority_topics": ["legitimacy", "reviews", "fees"]}
    GAP2 = {"summary": "[SAMPLE] Owned + neutral sources now dominate; contested share down "
                       "after publishing credentials, fee, and verified-review pages.",
            "missing_owned_content": ["client success stories"],
            "schema_gaps": ["FAQPage"], "contested_sources": [],
            "priority_topics": ["reviews depth", "local content"]}

    # ---- RUN 1 (backdated ~5 weeks so the trend has a time axis) ----
    print(f"\n[1] AUDIT run 1 (fixture answers) for business id={bid}")
    m.score_answer = lambda b, prompt, ans: _match(prompt, FAKE_SCORES)
    rid1 = m.audit(bid)
    back = datetime.now(timezone.utc) - timedelta(days=35)
    conn.execute("UPDATE audit_runs SET started_at=%s, finished_at=%s WHERE id=%s",
                 (back, back, rid1))
    conn.commit()
    _inject_gap(rid1, GAP1)
    ca.analyze(bid, quiet=True)
    n1 = conn.execute("SELECT COUNT(*) n FROM answers WHERE run_id=%s", (rid1,)).fetchone()["n"]
    conn.commit()  # release any read locks before run 2 opens its own connection
    print(f"    run 1 recorded {n1} answers (backdated 35 days)")

    # ---- RUN 2 (today, improved fixtures -> visible progress) ----
    print("[2] AUDIT run 2 (improved fixture answers, today)", flush=True)
    _ans2 = dict(FAKE_ANSWERS_RUN2)
    _sc2 = dict(FAKE_SCORES_RUN2)

    class SimEngine2:
        name = "simulated"; model = "sim-fixture-v1"
        def answer(self, prompt: str) -> dict:
            text, sources = _match(prompt, _ans2)
            return m._ok(text, sources)

    m.active_engines = lambda: [SimEngine2()]
    m.score_answer = lambda b, prompt, ans: _match(prompt, _sc2)
    sys.stdout.flush()
    rid2 = m.audit(bid)
    sys.stdout.flush()
    _inject_gap(rid2, GAP2)
    print(f"    run 2 recorded answers (today), run id={rid2}", flush=True)

    # ---- analytics across both runs ----
    print("\n[3] CITATION SHARE OF VOICE + MOMENTUM")
    sov = ca.analyze(bid, quiet=True)
    print(f"    total citations: {sov.get('total_citations')}  share: {sov.get('share_of_voice')}")
    mom = ca.momentum(bid, quiet=True)
    if mom.get("summary"):
        print(f"    gainers: {mom['summary'].get('owned_or_neutral_gainers')}  "
              f"contested losers: {mom['summary'].get('contested_losers')}")

    print("\n[4] LEARN + TIMELINE ESTIMATE (two runs -> trajectory available)")
    fb.learn(bid, quiet=True)
    est = te.estimate(bid, quiet=True)
    exp = est.get("expected", {})
    print(f"    expected window: {exp.get('label', exp.get('months', 'n/a'))}  "
          f"confidence: {est.get('confidence', 'n/a')}")

    print("\n[5] ACCELERATION OPTIONS")
    adv = aa.advise(bid, quiet=True)
    for lv in adv.get("levers_ranked_by_impact", [])[:3]:
        print(f"    - {lv['unit']}: up to {lv['weeks_saved_range']['high']} wks saved ({lv.get('weight_basis')})")

    print("\n[6] COMPETITOR BENCHMARK (fixture)")
    from rep_engine import competitor as cpmod
    cpmod.register_competitor(bid, "Rival Wealth Partners", "rival-wealth.example")
    cpmod.register_competitor(bid, "Cardinal Advisors", "cardinal-adv.example")
    # fixture engine where the subject appears most, rivals less -> subject ranks #1
    class BenchEngine:
        name = "simulated"; model = "sim-fixture-v1"
        def answer(self, prompt: str) -> dict:
            p = prompt.lower()
            if "legitimate" in p:
                return m._ok(f"{SIM_NAME} is a licensed local team; some compare it to "
                             "Rival Wealth Partners.",
                             [f"https://{SIM_DOMAIN}/about", "https://rival-wealth.example"])
            if "review" in p:
                return m._ok(f"{SIM_NAME} has strong verified reviews.", [f"https://{SIM_DOMAIN}/reviews"])
            return m._ok(f"{SIM_NAME} offers financial planning; Cardinal Advisors is another option.",
                         [f"https://{SIM_DOMAIN}/", "https://cardinal-adv.example"])
    m.active_engines = lambda: [BenchEngine()]
    conn.commit()  # release locks before benchmark opens its own connection
    cpmod.benchmark(bid, quiet=True)
    cmp = cpmod.compare(bid, quiet=True)
    print(f"    subject rank: #{cmp.get('subject_rank')} of {cmp.get('field_size')} "
          f"across {cmp.get('prompts_compared')} prompts")
    for s in cmp.get("standings", []):
        print(f"      {s['name']}: {round(s['appearance_rate']*100)}%"
              f"{'  <- you' if s['is_subject'] else ''}")

    print("\n[7] REPORT (watermarked SAMPLE)")
    os.environ["REP_REPORT_WATERMARK"] = "SAMPLE \u2014 SIMULATED DATA, NOT A REAL AUDIT"
    from rep_engine import report_generator as rg
    path = rg.generate(bid)
    print(f"    report: {path}")

    print("\nDONE. SIMULATED two-run demo. Every number is fixture data, watermarked")
    print("SAMPLE throughout. Wire real keys + run preflight for real results.")


if __name__ == "__main__":
    main()
