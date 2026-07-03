"""
Reputation Crowding-Out Engine -- Module 11: Competitor Benchmarking
====================================================================
Answers the question buyers actually ask: "in AI answers about my category, how
often does the engine surface ME versus my competitors?" This is the competitive
share-of-voice view -- the one capability gap versus packaged trackers.

How it works (reuses the existing audit machinery):
  1. register_competitor(business_id, name, domain) -- track a rival for a subject.
  2. benchmark(business_id) -- run the SUBJECT's prompt battery once, and for each
     answer record whether it mentions the subject and/or each competitor. This
     measures PRESENCE in the same category queries, which is the fair comparison.
  3. compare(business_id) -- report each party's "appearance rate" (share of prompts
     they show up in) and who wins head-to-head, plus per-prompt detail.

Honesty notes:
  - Presence is measured by name/domain mention in the answer text + cited sources.
    It is a transparent heuristic, not a semantic judgment; flagged as such.
  - This is measurement for crowding-out (out-appear competitors with accurate
    content), never disparagement of them.
  - Like the rest of the engine, failed engine calls are excluded, not counted as
    absences -- so a competitor isn't credited/penalized by a failed probe.

Run:
    python -m rep_engine.competitor add --business-id 1 --name "Rival LLC" --domain rival.com
    python -m rep_engine.competitor benchmark --business-id 1
    python -m rep_engine.competitor compare --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import re


try:
    from .db import db
    from .textutils import strip_www as _strip_www
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from textutils import strip_www as _strip_www  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("competitor")





def _ensure() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS competitors (
            id BIGSERIAL PRIMARY KEY, business_id BIGINT, name TEXT, domain TEXT,
            created_at TIMESTAMPTZ DEFAULT now(), UNIQUE (business_id, name))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS competitor_answers (
            id BIGSERIAL PRIMARY KEY, competitor_id BIGINT REFERENCES competitors(id),
            business_id BIGINT, run_id BIGINT, engine TEXT, prompt TEXT, answer_text TEXT,
            cited_sources JSONB DEFAULT '[]'::jsonb, mentions_subject BOOLEAN,
            mentions_competitor BOOLEAN, sample_idx INT DEFAULT 0, failed BOOLEAN DEFAULT FALSE,
            persona TEXT DEFAULT '', location TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT now())""")
        conn.commit()


def register_competitor(business_id: int, name: str, domain: str = "") -> int:
    _ensure()
    with db() as conn:
        row = conn.execute(
            """INSERT INTO competitors (business_id, name, domain) VALUES (%s,%s,%s)
               ON CONFLICT (business_id, name) DO UPDATE SET domain=EXCLUDED.domain
               RETURNING id""",
            (business_id, name, domain),
        ).fetchone()
        conn.commit()
    log.info("Registered competitor '%s' for business %d", name, business_id)
    return row["id"]


def _mentions(text: str, sources, name: str, domain: str) -> bool:
    """Transparent heuristic: does the answer mention this party by name or cite its
    domain? Word-boundary match on name; substring match on domain in cited sources."""
    if not text and not sources:
        return False
    hay = (text or "").lower()
    if name:
        # match the distinctive part of the name (first token >=4 chars or whole name)
        toks = [t for t in re.split(r"\W+", name.lower()) if len(t) >= 4]
        needle = name.lower()
        if re.search(r"\b" + re.escape(needle) + r"\b", hay):
            return True
        for t in toks:
            if re.search(r"\b" + re.escape(t) + r"\b", hay):
                return True
    if domain:
        dom = _strip_www(domain.lower())
        if dom and dom in hay:
            return True
        items = sources if isinstance(sources, list) else (json.loads(sources) if sources else [])
        for s in items:
            sd = s.get("url", "") if isinstance(s, dict) else str(s)
            if dom and dom in sd.lower():
                return True
    return False


def benchmark(business_id: int, quiet: bool = False) -> dict:
    """Run the subject's prompt battery once and record, per answer, whether the
    subject and each registered competitor are mentioned. Reuses the live audit
    engines; with no keys configured the engines are skipped (nothing recorded)."""
    _ensure()
    # imported lazily so this module loads without the full audit stack at import time
    from . import ai_state_audit as m

    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            # ValueError (not SystemExit): benchmark() runs as a background job and compare()
            # in a request -- a BaseException would escape the runner / request handler.
            raise ValueError(f"No business id {business_id}")
        comps = conn.execute("SELECT * FROM competitors WHERE business_id=%s", (business_id,)).fetchall()
        if not comps:
            if not quiet:
                log.info("No competitors registered for business %d; add some first.", business_id)
            return {}
        # a shared benchmark run id groups this comparison. kind='competitor' so it isn't
        # mistaken for an AI-reputation audit in the Audits list.
        run = conn.execute("INSERT INTO audit_runs (business_id, kind) VALUES (%s,'competitor') RETURNING id",
                           (business_id,)).fetchone()
        run_id = run["id"]

        battery = m.build_prompt_battery_lensed(dict(biz))
        engines = m.active_engines()
        subj_name = biz["name"]
        subj_domain = (biz.get("domain") or "")
        recorded = 0
        for prompt, persona, location in battery:
            for eng in engines:
                ans = eng.answer(prompt)
                if ans.get("skipped"):
                    continue
                failed = bool(ans.get("failed"))
                text = ans.get("text", "")
                sources = ans.get("sources", [])
                mentions_subject = (not failed) and _mentions(text, sources, subj_name, subj_domain)
                for comp in comps:
                    mc = (not failed) and _mentions(text, sources, comp["name"], comp.get("domain") or "")
                    conn.execute(
                        """INSERT INTO competitor_answers (competitor_id, business_id, run_id, engine,
                            prompt, answer_text, cited_sources, mentions_subject, mentions_competitor,
                            persona, location, failed)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (comp["id"], business_id, run_id, eng.name, prompt, text,
                         json.dumps(sources), mentions_subject, mc, persona, location, failed),
                    )
                    recorded += 1
        # Leave finished_at NULL: a competitor benchmark is not an AI reputation audit, and the
        # "latest AI audit" queries all filter `finished_at IS NOT NULL`. compare()/trend() read
        # competitor_answers (by run_id), not this flag, so they're unaffected. (kind='competitor'.)
        # Mark the run 'complete' (not the default 'in_progress') so it reaches a terminal status;
        # finished_at stays NULL so it never enters the ai_audit finished-run selectors.
        conn.execute("UPDATE audit_runs SET status='complete' WHERE id=%s", (run_id,))
        conn.commit()
    if not quiet:
        log.info("Benchmark run %d complete (%d competitor-answer rows).", run_id, recorded)
    return {"run_id": run_id, "rows": recorded}


def compare(business_id: int, quiet: bool = False) -> dict:
    """Report appearance rates: across the benchmark prompts, how often the subject
    appears vs. each competitor, and head-to-head wins. Uses the latest benchmark run."""
    _ensure()
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            # ValueError (not SystemExit): benchmark() runs as a background job and compare()
            # in a request -- a BaseException would escape the runner / request handler.
            raise ValueError(f"No business id {business_id}")
        run = conn.execute(
            "SELECT MAX(run_id) r FROM competitor_answers WHERE business_id=%s", (business_id,)
        ).fetchone()
        if not run or run["r"] is None:
            if not quiet:
                log.info("No benchmark run found; run benchmark first.")
            return {}
        rid = run["r"]
        comps = conn.execute("SELECT * FROM competitors WHERE business_id=%s", (business_id,)).fetchall()

        # distinct non-failed prompts in this run = the comparison set
        prompts = conn.execute(
            "SELECT DISTINCT prompt FROM competitor_answers WHERE run_id=%s AND NOT failed", (rid,)
        ).fetchall()
        n_prompts = len(prompts)

        # subject appearance: a prompt counts if ANY engine answer for it mentioned subject
        subj_prompts = conn.execute(
            "SELECT COUNT(DISTINCT prompt) c FROM competitor_answers "
            "WHERE run_id=%s AND mentions_subject AND NOT failed", (rid,)
        ).fetchone()["c"]

        standings = [{
            "name": biz["name"], "is_subject": True,
            "appears_in": subj_prompts,
            "appearance_rate": round(subj_prompts / n_prompts, 4) if n_prompts else 0.0,
        }]
        for comp in comps:
            cp = conn.execute(
                "SELECT COUNT(DISTINCT prompt) c FROM competitor_answers "
                "WHERE run_id=%s AND competitor_id=%s AND mentions_competitor AND NOT failed",
                (rid, comp["id"]),
            ).fetchone()["c"]
            standings.append({
                "name": comp["name"], "is_subject": False,
                "appears_in": cp,
                "appearance_rate": round(cp / n_prompts, 4) if n_prompts else 0.0,
            })
        standings.sort(key=lambda x: x["appearance_rate"], reverse=True)

        # head-to-head: the actual prompts where subject appears and competitor doesn't (subject
        # win), vice-versa, and where BOTH appear (ties). Returning the prompt text (not just a
        # count) lets the console show WHICH questions drive each bucket -- the context the owner
        # asked for ("only you / only them doesn't make sense without context").
        def _distinct_prompts(comp_id: int, where: str) -> list[str]:
            rows = conn.execute(
                "SELECT DISTINCT a.prompt FROM competitor_answers a "
                f"WHERE a.run_id=%s AND a.competitor_id=%s AND NOT a.failed AND {where} "
                "ORDER BY a.prompt",
                (rid, comp_id),
            ).fetchall()
            return [r["prompt"] for r in rows if r["prompt"]]

        head_to_head = []
        for comp in comps:
            subj_only_list = _distinct_prompts(comp["id"], "a.mentions_subject AND NOT a.mentions_competitor")
            comp_only_list = _distinct_prompts(comp["id"], "a.mentions_competitor AND NOT a.mentions_subject")
            both_list = _distinct_prompts(comp["id"], "a.mentions_subject AND a.mentions_competitor")
            head_to_head.append({
                "competitor": comp["name"],
                "subject_only_prompts": len(subj_only_list),
                "competitor_only_prompts": len(comp_only_list),
                # cap the lists so a huge battery can't bloat the payload; counts stay exact
                "prompts_subject_only": subj_only_list[:30],
                "prompts_competitor_only": comp_only_list[:30],
                "prompts_both": both_list[:30],
            })

    rank = next((i for i, s in enumerate(standings, 1) if s["is_subject"]), None)
    result = {
        "business": biz["name"], "run_id": rid, "prompts_compared": n_prompts,
        "subject_rank": rank, "field_size": len(standings),
        "standings": standings, "head_to_head": head_to_head,
        "method": ("Appearance rate = share of category prompts in which the party is "
                   "mentioned by name or cited domain (transparent heuristic, not a "
                   "semantic judgment). Failed engine calls are excluded."),
    }
    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result


def trend(business_id: int) -> dict:
    """Subject vs. competitor APPEARANCE RATE over time -- one point per benchmark run,
    so the console can chart visibility climbing (or not) against rivals. Same appearance-
    rate definition as compare() (share of a run's non-failed category prompts in which the
    party is mentioned); points are ordered by run date."""
    _ensure()
    with db() as conn:
        biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            return {"business": None, "competitors": [], "points": []}
        comps = [r["name"] for r in conn.execute(
            "SELECT name FROM competitors WHERE business_id=%s ORDER BY id", (business_id,)
        ).fetchall()]
        runs = conn.execute(
            "SELECT run_id, MIN(created_at) dt, "
            "COUNT(DISTINCT prompt) FILTER (WHERE NOT failed) nprompts, "
            "COUNT(DISTINCT prompt) FILTER (WHERE mentions_subject AND NOT failed) subj "
            "FROM competitor_answers WHERE business_id=%s GROUP BY run_id "
            # drop all-failed runs: a run with no usable prompts is 'no data', not a real 0%
            "HAVING COUNT(*) FILTER (WHERE NOT failed) > 0 "
            "ORDER BY MIN(created_at), run_id", (business_id,),
        ).fetchall()
        points = []
        for r in runs:
            np = r["nprompts"] or 0
            point = {
                "run_id": r["run_id"], "date": r["dt"],
                "subject_rate": round(r["subj"] / np, 4) if np else 0.0,
                "competitors": {},
            }
            for cname in comps:
                cp = conn.execute(
                    "SELECT COUNT(DISTINCT a.prompt) c FROM competitor_answers a "
                    "JOIN competitors c ON c.id=a.competitor_id "
                    "WHERE a.run_id=%s AND a.business_id=%s AND c.name=%s "
                    "AND a.mentions_competitor AND NOT a.failed",
                    (r["run_id"], business_id, cname),
                ).fetchone()["c"]
                point["competitors"][cname] = round(cp / np, 4) if np else 0.0
            points.append(point)
    return {"business": biz["name"], "competitors": comps, "points": points}


def main() -> None:
    ap = argparse.ArgumentParser(description="Competitor share-of-voice benchmarking")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--business-id", type=int, required=True)
    a.add_argument("--name", required=True); a.add_argument("--domain", default="")
    b = sub.add_parser("benchmark"); b.add_argument("--business-id", type=int, required=True)
    c = sub.add_parser("compare"); c.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "add":
        register_competitor(args.business_id, args.name, args.domain)
    elif args.cmd == "benchmark":
        benchmark(args.business_id)
    elif args.cmd == "compare":
        compare(args.business_id)


if __name__ == "__main__":
    main()
