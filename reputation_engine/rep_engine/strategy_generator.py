"""
Reputation Crowding-Out Engine -- Module 2: Strategy + Work-Order Generator
===========================================================================
Consumes the structured GAP MODEL from Module 1 (ai_state_audit.py) and produces:
  1. A phased, dated strategic plan (front-loaded fast wins -> build -> amplify -> steady-state).
  2. Concrete WORK ORDERS, each classified as AUTO (system does it) or HUMAN
     (work order for a person/VA), with a recommended TOOL drawn from a registry.
  3. Metrics + monitoring cadence tied back to Module 1's diff().

Tool philosophy
---------------
The TOOL_REGISTRY is an AVAILABLE toolbox, not a mandate. Each capability lists
candidate tools (AppSumo lifetime deals, open-source, and APIs). The generator
picks the best fit by preference order (auto/API > open-source > AppSumo-manual),
and only assigns an AppSumo tool when it genuinely fits the task. If nothing fits,
the work order says so and falls back to the system's own generation or a plain
human instruction. Tools can be enabled/disabled per deployment.

Run:
    python strategy_generator.py plan --business-id 1 --start 2026-06-09
    python strategy_generator.py tools          # list the registry
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("strategy_generator")

DB_DSN = os.getenv("REP_DB_DSN", "postgresql://USER:PASSWORD@localhost:5432/reputation")  # PH 1


# ----------------------------------------------------------------------------
# TOOL REGISTRY  --  available toolbox, picked only when beneficial
# ----------------------------------------------------------------------------
class Exec(str, Enum):
    AUTO = "auto"          # system executes via API/code, no human needed
    SEMI = "semi"          # API exists but needs human review/trigger
    MANUAL = "manual"      # no usable API; human operates the tool from a work order


@dataclass
class Tool:
    key: str
    name: str
    capability: str            # canonical capability id (see CAPABILITIES)
    execution: Exec
    notes: str = ""
    enabled: bool = True        # flip off per deployment if you don't own/want it


# Canonical capabilities the engine can request for a work order.
CAPABILITIES = [
    "site_audit", "keyword_research", "topic_research", "content_writing",
    "content_optimization", "fact_checking", "video_creation", "video_repurpose",
    "social_publishing", "press_outreach", "media_list_building", "link_building",
    "review_generation", "ai_visibility_tracking", "form_capture", "visitor_tracking",
    "schema_markup", "course_microsite",
]

# Registry. preference within a capability = order listed (best/most-automatable first).
# AppSumo lifetime-deal tools are included as MANUAL options where they fit.
TOOL_REGISTRY: list[Tool] = [
    # --- site audit / technical SEO ---
    Tool("lighthouse", "Lighthouse CI", "site_audit", Exec.AUTO, "OSS; programmatic Core Web Vitals + SEO checks. Preferred."),
    Tool("screaming_frog", "Screaming Frog CLI", "site_audit", Exec.AUTO, "Crawl + on-page export via CLI. Preferred for structure."),
    Tool("screpy", "Screpy", "site_audit", Exec.MANUAL, "AppSumo; dashboarded audit. Use for client-facing visuals."),
    Tool("siteguru", "SiteGuru", "site_audit", Exec.MANUAL, "AppSumo; readable audit + to-do list."),
    Tool("brandalyzer", "Brandalyzer", "site_audit", Exec.MANUAL, "AppSumo; brand/site analysis."),
    Tool("clickrank", "ClickRank", "site_audit", Exec.MANUAL, "AppSumo; SEO automation/audit."),
    Tool("vispr_seo", "Vispr SEO Network", "link_building", Exec.MANUAL, "AppSumo; network/SEO."),
    # --- keyword / topic research ---
    Tool("topic_mojo", "Topic Mojo", "topic_research", Exec.MANUAL, "AppSumo; question/topic discovery -- great for matching AI prompt gaps."),
    Tool("writerzen", "WriterZen", "keyword_research", Exec.MANUAL, "AppSumo; keyword + content cluster."),
    Tool("getgeni", "GetGenie", "keyword_research", Exec.SEMI, "AppSumo; some API; SEO + content."),
    Tool("squirrly", "Squirrly SEO", "content_optimization", Exec.MANUAL, "AppSumo; live on-page optimization (WordPress)."),
    # --- content writing / optimization / fact-check ---
    Tool("llm_native", "Engine-native LLM", "content_writing", Exec.AUTO, "System writes drafts directly. Default for owned content."),
    Tool("texta", "Texta.ai", "content_writing", Exec.SEMI, "AppSumo; long-form gen."),
    Tool("shopia", "Shopia.ai", "content_writing", Exec.SEMI, "AppSumo; content + scheduling."),
    Tool("blogify", "Blogify", "content_writing", Exec.MANUAL, "AppSumo; blog gen/repurpose."),
    Tool("katteb", "Katteb", "fact_checking", Exec.MANUAL, "AppSumo; fact-checked content -- useful for trust-sensitive claims."),
    Tool("konvey", "Konvey", "content_optimization", Exec.MANUAL, "AppSumo; conversion copy."),
    # --- video creation / repurpose ---
    Tool("steve_ai", "Steve.ai", "video_creation", Exec.MANUAL, "AppSumo; script->video explainers."),
    Tool("pipio", "Pipio", "video_creation", Exec.MANUAL, "AppSumo; AI presenter video."),
    Tool("vadoo", "Vadoo.tv/.ai", "video_creation", Exec.MANUAL, "AppSumo; short video gen + hosting."),
    Tool("flexclip", "FlexClip", "video_creation", Exec.MANUAL, "AppSumo; quick branded video."),
    Tool("onetake", "OneTake AI", "video_repurpose", Exec.MANUAL, "AppSumo; long->clips."),
    Tool("hippo", "Hippo Video", "video_repurpose", Exec.MANUAL, "AppSumo; video + hosting."),
    Tool("videopeel", "VideoPeel", "review_generation", Exec.MANUAL, "AppSumo; collect video testimonials."),
    Tool("motionvid", "MotionVid AI", "video_creation", Exec.MANUAL, "AppSumo; video gen."),
    # --- social publishing ---
    Tool("creasquare", "CreaSquare", "social_publishing", Exec.SEMI, "AppSumo; multi-channel social gen + schedule."),
    Tool("genius_ai", "Genius.ai", "social_publishing", Exec.SEMI, "AppSumo; social content/ads."),
    # --- press / outreach / media lists ---
    Tool("press_ranger", "Press Ranger", "media_list_building", Exec.SEMI, "AppSumo; ~journalist/outlet DB. Primary for local media lists."),
    Tool("bizreply", "BizReply", "social_publishing", Exec.MANUAL, "AppSumo; monitor + reply to relevant mentions (engagement)."),
    Tool("cxassist", "CXAssist", "press_outreach", Exec.SEMI, "AppSumo; email assistant/auto-reply."),
    # --- link building ---
    Tool("linksy", "Linksy AI Link Builder", "link_building", Exec.MANUAL, "AppSumo; outreach link building."),
    Tool("linkly", "Linkly", "link_building", Exec.SEMI, "AppSumo; trackable links/redirects (analytics, not acquisition)."),
    # --- AI visibility tracking (complements Module 1) ---
    Tool("measuremate", "MeasureMate", "ai_visibility_tracking", Exec.MANUAL, "AppSumo; metrics dashboard."),
    Tool("module1", "Engine Module 1 audit", "ai_visibility_tracking", Exec.AUTO, "Our own harness. Primary tracker."),
    # --- capture / tracking / courses ---
    Tool("deftform", "DeftForm", "form_capture", Exec.SEMI, "AppSumo; forms -> webhook to GHL."),
    Tool("visitortracking", "VisitorTracking.com", "visitor_tracking", Exec.SEMI, "AppSumo; site visitor ID/analytics."),
    Tool("learniverse", "Learniverse", "course_microsite", Exec.MANUAL, "AppSumo; courses (financial-literacy content asset)."),
    Tool("acadle", "Acadle", "course_microsite", Exec.MANUAL, "AppSumo; academy/community (authority asset)."),
    Tool("notebooklm", "NotebookLM", "topic_research", Exec.MANUAL, "Free; synthesize source docs into briefs/audio."),
    Tool("getgeni2", "Vadoo AI captions", "video_repurpose", Exec.MANUAL, "AppSumo; captions/clips."),
]


def registry_for(capability: str) -> list[Tool]:
    pref = {Exec.AUTO: 0, Exec.SEMI: 1, Exec.MANUAL: 2}
    tools = [t for t in TOOL_REGISTRY if t.capability == capability and t.enabled]
    return sorted(tools, key=lambda t: pref[t.execution])


def best_tool(capability: str) -> Optional[Tool]:
    tools = registry_for(capability)
    return tools[0] if tools else None


# ----------------------------------------------------------------------------
# Mapping gap-model sections -> capabilities + phase
# ----------------------------------------------------------------------------
@dataclass
class WorkOrder:
    wo_id: str
    title: str
    capability: str
    execution: str
    recommended_tool: Optional[str]
    alternatives: list[str]
    instruction: str
    phase: str
    week: int
    depends_on: list[str] = field(default_factory=list)


PHASES = [
    ("Phase 0 - Baseline & Fast Wins", 0, 2),     # weeks 0-2
    ("Phase 1 - Owned Hub & Schema", 2, 6),       # weeks 2-6
    ("Phase 2 - Corroboration & Amplify", 4, 12), # weeks 4-12
    ("Phase 3 - Steady State & Monitor", 12, 24), # weeks 12+
]


def _phase_for_week(week: int) -> str:
    for name, lo, hi in PHASES:
        if lo <= week < hi:
            return name
    return PHASES[-1][0]


def build_work_orders(gap: dict) -> list[WorkOrder]:
    wos: list[WorkOrder] = []
    n = 0

    def add(title, capability, instruction, week, deps=None):
        nonlocal n
        n += 1
        tool = best_tool(capability)
        alts = [t.name for t in registry_for(capability)[1:4]]
        wos.append(WorkOrder(
            wo_id=f"WO-{n:03d}", title=title, capability=capability,
            execution=(tool.execution.value if tool else "manual"),
            recommended_tool=(tool.name if tool else None),
            alternatives=alts,
            instruction=instruction, phase=_phase_for_week(week), week=week,
            depends_on=deps or [],
        ))

    # --- Phase 0: fast wins (reviews, tracking baseline, one explainer) ---
    add("Establish AI-visibility baseline", "ai_visibility_tracking",
        "Run Module 1 audit + gap model; store as the baseline report the client receives.", 0)
    add("Launch review-generation sequence", "review_generation",
        "Build a GHL automation texting/emailing happy clients a direct Google review link "
        "post-positive-interaction. Seed reviews mentioning service + locale.", 0)
    add("Claim/optimize Google Business Profile", "social_publishing",
        "Verify GBP; complete categories, services, photos, NAP consistency; enable reviews.", 1)

    # --- Phase 1: owned content for each missing topic + schema ---
    for i, item in enumerate(gap.get("missing_owned_content", []) or []):
        topic = item.get("topic", f"topic {i+1}")
        atype = item.get("asset_type", "article")
        why = item.get("why", "")
        cap = "video_creation" if "video" in atype.lower() else "content_writing"
        add(f"Create owned asset: {topic}", cap,
            f"Produce a {atype} on '{topic}'. Rationale: {why}. Draft via engine-native LLM; "
            f"fact-check trust-sensitive claims; publish on the business domain.", 3)
    for sg in gap.get("schema_gaps", []) or []:
        add(f"Add schema: {sg}", "schema_markup",
            f"Generate and deploy JSON-LD ({sg}) on the relevant pages so answer engines "
            f"can cleanly extract facts.", 4)

    # --- Phase 2: corroboration (press, media list, partner, link) ---
    if gap.get("thin_corroboration"):
        add("Build local media list", "media_list_building",
            "Assemble a Cincinnati-area finance/local-business journalist + outlet list "
            "with angles (veteran-owned, financial literacy, community workshops).", 5)
        for i, claim in enumerate(gap.get("thin_corroboration", [])):
            c = claim.get("claim", f"claim {i+1}")
            where = claim.get("where_to_get_it", "")
            add(f"Corroborate: {c}", "press_outreach",
                f"Secure third-party coverage/mention supporting '{c}'. Source: {where}. "
                f"Draft pitch; route via outreach tool; human approves before send.", 6)
    add("Book local/finance podcast appearances", "press_outreach",
        "Identify 3-5 relevant local/finance podcasts; pitch the principal as guest; "
        "each episode yields an indexed third-party positive page.", 7)

    # --- Per-surface actions straight from the gap model (ethical, accurate only) ---
    surfaces = gap.get("surface_actions", {}) or {}
    surface_week = {"google_business": 1, "linkedin": 5, "facebook": 5, "x": 6, "reddit": 8}
    for surface, actions in surfaces.items():
        for act in (actions or []):
            wk = surface_week.get(surface, 6)
            cap = "social_publishing"
            note = ""
            if surface == "reddit":
                note = (" NOTE: Reddit must be genuine, human, value-add participation only "
                        "-- never automated reputation posting (ban risk + policy violation).")
            add(f"{surface.replace('_',' ').title()} action", cap,
                f"{act}{note}", wk)

    # --- Phase 3: steady-state monitoring ---
    add("Recurring AI-visibility monitor", "ai_visibility_tracking",
        "Schedule monthly Module 1 audit + diff; generate the monthly progress report.", 12)
    return wos


# ----------------------------------------------------------------------------
# Plan assembly (dates, metrics)
# ----------------------------------------------------------------------------
METRICS = [
    "Avg goal_alignment across answer engines (target: rising; from Module 1 diff)",
    "Contested-term mention rate (target: falling as accurate content crowds out)",
    "Owned-content surfacing rate (target: rising)",
    "# of owned hub pages published with schema",
    "# of third-party corroborating placements (press, podcast, partner)",
    "Google Business review count + average rating + recency",
    "Local branded-query presence in Perplexity / ChatGPT-search",
]


def assemble_plan(business: dict, gap: dict, start: date) -> dict:
    wos = build_work_orders(gap)
    for w in wos:
        w_start = start + timedelta(weeks=w.week)
        w.__dict__["target_date"] = w_start.isoformat()
    phases = {}
    for name, lo, hi in PHASES:
        phases[name] = {
            "weeks": f"{lo}-{hi if hi < 24 else '24+'}",
            "work_orders": [w.wo_id for w in wos if w.phase == name],
        }
    auto = [w for w in wos if w.execution == "auto"]
    human = [w for w in wos if w.execution in ("manual", "semi")]
    return {
        "business": {k: business.get(k) for k in ("name", "domain", "goal", "geo")},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start.isoformat(),
        "summary": gap.get("summary", ""),
        "expected_timeline": {
            "first_visible_movement": "weeks 8-16 (retrieval-grounded engines first)",
            "durable_results": "months 4-6 on local/branded queries",
            "note": "Crowding-out, not suppression: results come from out-producing and "
                    "out-corroborating accurate content, not removing third-party views.",
        },
        "phases": phases,
        "metrics": METRICS,
        "monitoring_cadence": "Monthly Module 1 audit + diff -> client progress report.",
        "counts": {"total": len(wos), "auto": len(auto), "human": len(human)},
        "work_orders": [w.__dict__ for w in wos],
    }


# ----------------------------------------------------------------------------
# DB + CLI
# ----------------------------------------------------------------------------
def db() -> psycopg.Connection:
    return psycopg.connect(DB_DSN, row_factory=dict_row)


def _latest_gap(business_id: int) -> tuple[dict, dict]:
    with db() as conn:
        b = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        g = conn.execute(
            "SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
    if not b:
        raise SystemExit(f"No business id {business_id}")
    if not g:
        raise SystemExit("No gap model yet -- run Module 1 gap-model first.")
    return dict(b), (g["model"] if isinstance(g["model"], dict) else json.loads(g["model"]))


def plan_cmd(business_id: int, start: Optional[str]) -> None:
    business, gap = _latest_gap(business_id)
    start_date = date.fromisoformat(start) if start else date.today()
    plan = assemble_plan(business, gap, start_date)
    # persist
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS strategy_plans ("
            "id BIGSERIAL PRIMARY KEY, business_id BIGINT, plan JSONB, created_at TIMESTAMPTZ DEFAULT now())"
        )
        conn.execute("INSERT INTO strategy_plans (business_id, plan) VALUES (%s,%s)",
                     (business_id, json.dumps(plan)))
        conn.commit()
    print(json.dumps(plan, indent=2))
    log.info("Plan: %d work orders (%d auto / %d human)",
             plan["counts"]["total"], plan["counts"]["auto"], plan["counts"]["human"])


def tools_cmd() -> None:
    by_cap: dict[str, list[Tool]] = {}
    for c in CAPABILITIES:
        by_cap[c] = registry_for(c)
    for cap, tools in by_cap.items():
        print(f"\n{cap}:")
        for t in tools:
            star = " *" if t == tools[0] else "  "
            print(f" {star} [{t.execution.value:6}] {t.name} -- {t.notes}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Strategy + work-order generator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("plan")
    pp.add_argument("--business-id", type=int, required=True)
    pp.add_argument("--start", help="ISO date the plan begins (default today)")
    sub.add_parser("tools")
    args = ap.parse_args()
    if args.cmd == "plan":
        plan_cmd(args.business_id, args.start)
    elif args.cmd == "tools":
        tools_cmd()


if __name__ == "__main__":
    main()
