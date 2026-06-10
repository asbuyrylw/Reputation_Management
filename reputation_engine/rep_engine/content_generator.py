"""
Reputation Crowding-Out Engine -- Module 6: AI Content Generator
================================================================
Closes the loop from gap -> finished DRAFT artifact. For each content-type work
order in the plan, it generates the actual asset (FAQ, schema JSON-LD, article,
bio, GBP post, review-request copy), scores it against a quality rubric, auto-
revises if it falls short, runs a compliance screen, and stores it as a
`pending_review` draft. NOTHING is auto-published.

Design principles (from the roadmap):
  - AI generates, HUMAN approves, system tracks. Auto-drafting removes ~80% of the
    labor while keeping the human gate -- essential for regulated (financial) clients.
  - Win-Gate-style self-evaluation: generate -> score against rubric -> auto-revise
    if below threshold -> re-score (bounded passes).
  - Compliance gate as a first-class step: disclosures present, no performance
    promises, broker-dealer relationship disclosed where relevant.
  - pgvector-ready: a hook to skip generation when equivalent content already
    exists (no-op until pgvector is wired).

Run:
    python -m rep_engine.content_generator generate --business-id 1            # all auto content WOs
    python -m rep_engine.content_generator generate --business-id 1 --wo 12    # one work order
    python -m rep_engine.content_generator list --business-id 1                # show drafts + status
    python -m rep_engine.content_generator approve --draft 5 --reviewer "Logan"
    python -m rep_engine.content_generator reject  --draft 5 --reviewer "Logan" --notes "off-brand"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from pydantic import ValidationError

try:
    from . import ai_state_audit as llm   # reuse the orchestrator LLM plumbing
    from .llm_schemas import ComplianceResult, EvalResult
except ImportError:  # pragma: no cover
    import ai_state_audit as llm  # type: ignore
    from llm_schemas import ComplianceResult, EvalResult  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("content_generator")

DB_DSN = os.getenv("REP_DB_DSN", "postgresql://USER:PASSWORD@localhost:5432/reputation")  # PH 1

QUALITY_THRESHOLD = float(os.getenv("CONTENT_QUALITY_THRESHOLD", "0.75"))   # PH 2
MAX_REVISIONS = int(os.getenv("CONTENT_MAX_REVISIONS", "2"))                # PH 3

# Capabilities that this module knows how to generate (others stay manual).
GENERATABLE = {
    "content_writing": "article",
    "schema_markup": "schema",
    "review_generation": "review_request",
}
# asset_type inferred from work-order title keywords as a fallback
TITLE_HINTS = [
    ("faq", "faq"), ("schema", "schema"), ("bio", "bio"),
    ("article", "article"), ("post", "gbp_post"), ("review", "review_request"),
]


def db() -> psycopg.Connection:
    return psycopg.connect(DB_DSN, row_factory=dict_row)


def _ensure_table() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_drafts (
                id BIGSERIAL PRIMARY KEY, business_id BIGINT, work_order_id BIGINT,
                asset_type TEXT, title TEXT, body TEXT, target_query TEXT,
                quality_score NUMERIC(4,2), quality_notes JSONB DEFAULT '{}'::jsonb,
                revision_count INT DEFAULT 0, compliance_pass BOOLEAN,
                compliance_flags JSONB DEFAULT '[]'::jsonb,
                status TEXT DEFAULT 'pending_review', reviewer TEXT, reviewed_at TIMESTAMPTZ,
                published_asset_id BIGINT, created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now())
        """)
        conn.commit()


# ----------------------------------------------------------------------------
# pgvector hook (no-op until wired) -- would prevent regenerating existing content
# ----------------------------------------------------------------------------
def _already_covered(business_id: int, topic: str) -> bool:
    """Placeholder for the pgvector semantic-dedup check. Returns False (always
    generate) until pgvector memory is wired in. PH 4."""
    return False


# ----------------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------------
GEN_SYSTEM = (
    "You are an expert content writer for a reputation program that works by "
    "publishing ACCURATE, helpful, well-structured content so it is what AI "
    "assistants surface about a business. Never fabricate facts, credentials, "
    "reviews, or statistics. If you don't have a fact, write around it or use a "
    "clearly-labeled placeholder like [INSERT: founding year]. Write in a warm, "
    "trustworthy, plain tone. Output ONLY the asset content -- no preamble."
)


def _asset_type_for(wo: dict) -> Optional[str]:
    cap = (wo.get("capability") or "").lower()
    if cap in GENERATABLE:
        # refine via title
        title = (wo.get("title") or "").lower()
        for kw, t in TITLE_HINTS:
            if kw in title:
                return t
        return GENERATABLE[cap]
    # fallback: infer from title only
    title = (wo.get("title") or "").lower()
    for kw, t in TITLE_HINTS:
        if kw in title:
            return t
    return None


def _gen_prompt(biz: dict, wo: dict, asset_type: str) -> str:
    name = biz.get("name", "the business")
    geo = biz.get("geo", "")
    svc = biz.get("services", "")
    instr = wo.get("instruction", "")
    title = wo.get("title", "")
    specs = {
        "faq": "Write an FAQ page (6-10 Q&A pairs) in markdown that directly answers "
               "the real questions people ask about this business.",
        "schema": "Output ONLY valid JSON-LD schema markup (no prose) appropriate to the "
                  "page -- choose from Organization, LocalBusiness, FAQPage, Person, Review.",
        "article": "Write a 500-800 word helpful article in markdown with a clear H1 and "
                   "subheadings, answering the target question accurately.",
        "bio": "Write a professional bio page in markdown (200-350 words) establishing "
               "authority and trust. Use placeholders for any facts you don't have.",
        "gbp_post": "Write a short Google Business Profile post (80-150 words), friendly and local.",
        "review_request": "Write a short, warm review-request message (SMS + email versions) "
                          "asking a happy client to leave a Google review, with a placeholder for the link.",
    }
    spec = specs.get(asset_type, "Write the requested asset in markdown.")
    return (
        f"Business: {name}\nLocation: {geo}\nServices: {svc}\n"
        f"Work order: {title}\nInstruction: {instr}\n"
        f"Target AI query to satisfy: {wo.get('target_query','(general trust/visibility)')}\n\n"
        f"Task: {spec}"
    )


def _generate_one(biz: dict, wo: dict, asset_type: str) -> str:
    # creative long-form generation -> mid tier (Sonnet/gpt-4o), not full Opus.
    return llm.orchestrator_text(GEN_SYSTEM, _gen_prompt(biz, wo, asset_type),
                                 max_tokens=2200, tier="mid")


# ----------------------------------------------------------------------------
# Self-evaluation (Win-Gate-style) + auto-revision
# ----------------------------------------------------------------------------
EVAL_SYSTEM = (
    "You are a strict content QA reviewer. Score the draft against this rubric and "
    "return STRICT JSON only: {\"score\": 0.0-1.0, \"accuracy\": bool (no fabricated "
    "facts/reviews/stats), \"answers_query\": bool, \"structure\": bool (clear headings/"
    "format for the asset type), \"tone\": bool (warm, trustworthy, not salesy), "
    "\"issues\": [strings], \"fixes\": [concise actionable fixes]}. Be hard on "
    "fabrication: any invented specific fact, statistic, credential, or review caps "
    "score at 0.4."
)


def _evaluate(asset_type: str, target_query: str, body: str) -> dict:
    user = json.dumps({"asset_type": asset_type, "target_query": target_query, "draft": body})
    # rubric scoring is classification/QA -> cheap tier (Haiku/gpt-4o-mini).
    res = llm.orchestrator_json(EVAL_SYSTEM, user, tier="cheap")
    if not res:
        return {}
    try:
        # Garbled/out-of-range eval JSON is 'could not evaluate', NOT a real score of 0.
        return EvalResult.model_validate(res).model_dump()
    except ValidationError as e:
        log.warning("_evaluate: eval JSON failed validation (treating as unscored): %s",
                    str(e).splitlines()[0] if str(e) else e)
        return {}


REVISE_SYSTEM = (
    "You are revising a content draft to fix the listed issues while keeping what "
    "works. Do not introduce fabricated facts -- use [INSERT: ...] placeholders "
    "instead. Output ONLY the revised asset content, no preamble."
)


def _revise(body: str, fixes: list) -> str:
    user = "Issues/fixes to address:\n- " + "\n- ".join(fixes or []) + f"\n\nCurrent draft:\n{body}"
    # creative rewrite -> mid tier (Sonnet/gpt-4o).
    return llm.orchestrator_text(REVISE_SYSTEM, user, max_tokens=2200, tier="mid")


# ----------------------------------------------------------------------------
# Compliance gate (first-class)
# ----------------------------------------------------------------------------
COMPLIANCE_SYSTEM = (
    "You are a financial-services marketing compliance screener. Review the content "
    "and return STRICT JSON only: {\"pass\": bool, \"flags\": [strings]}. Flag any of: "
    "guaranteed/implied investment returns or performance promises; claims that imply "
    "the brand is an independent registered firm when it may be a representative of a "
    "broker-dealer; missing required disclosure of the broker-dealer relationship where "
    "the content markets financial products; unverifiable superlatives ('best', "
    "'#1') stated as fact; testimonials presented without context. If the content is "
    "non-financial or purely informational, pass it unless it makes false claims."
)


def _compliance(body: str) -> dict:
    # compliance screen is classification -> cheap tier (Haiku/gpt-4o-mini).
    res = llm.orchestrator_json(COMPLIANCE_SYSTEM, json.dumps({"content": body}), tier="cheap")
    # default-safe: if the screener couldn't run (no keys), mark unknown -> needs human
    if not res:
        return {"pass": None, "flags": ["compliance screener unavailable (no LLM) -- human must review"]}
    try:
        validated = ComplianceResult.model_validate(res)
    except ValidationError as e:
        # A garbled compliance response is 'unknown', NOT an auto-pass and NOT an auto-fail.
        log.warning("_compliance: screen JSON failed validation (routing to human): %s",
                    str(e).splitlines()[0] if str(e) else e)
        return {"pass": None,
                "flags": ["compliance screen returned malformed output -- human must review"]}
    # by_alias=True restores the literal 'pass' key the DB column + callers expect.
    return validated.model_dump(by_alias=True)


# ----------------------------------------------------------------------------
# Orchestrated generation for a work order
# ----------------------------------------------------------------------------
def generate_for_wo(business_id: int, wo: dict, biz: dict) -> Optional[int]:
    asset_type = _asset_type_for(wo)
    if not asset_type:
        log.info("WO %s not a generatable content type; skipping.", wo.get("wo_code") or wo.get("wo_id"))
        return None
    topic = wo.get("title", "")
    if _already_covered(business_id, topic):
        log.info("WO '%s' already covered (pgvector); skipping.", topic)
        return None

    body = _generate_one(biz, wo, asset_type)
    if not body:
        log.warning("Generation produced no content (LLM unavailable?) for '%s'", topic)
        return None

    # self-eval + bounded auto-revision
    revisions = 0
    evaluation = _evaluate(asset_type, wo.get("target_query", ""), body)
    eval_unavailable = not evaluation  # {} => LLM unavailable OR validation failed
    score = float(evaluation.get("score", 0) or 0)
    while (not eval_unavailable and score < QUALITY_THRESHOLD
           and revisions < MAX_REVISIONS and evaluation.get("fixes")):
        body = _revise(body, evaluation.get("fixes", [])) or body
        revisions += 1
        evaluation = _evaluate(asset_type, wo.get("target_query", ""), body)
        eval_unavailable = not evaluation
        score = float(evaluation.get("score", 0) or 0)

    # compliance gate
    comp = _compliance(body)
    comp_pass = comp.get("pass")
    comp_flags = comp.get("flags", [])

    # status:
    #  - a REAL evaluation below threshold, or a REAL compliance failure -> needs_fix
    #  - could-not-evaluate (eval JSON malformed/unavailable) must NOT become a false
    #    needs_fix; it stays pending_review with a flag so a human looks at it.
    status = "pending_review"
    if eval_unavailable:
        comp_flags = list(comp_flags) + [
            "quality evaluation unavailable/malformed -- human must review"]
    elif score < QUALITY_THRESHOLD:
        status = "needs_fix"
    if comp_pass is False:
        status = "needs_fix"

    _ensure_table()
    with db() as conn:
        row = conn.execute(
            """INSERT INTO content_drafts
               (business_id, work_order_id, asset_type, title, body, target_query,
                quality_score, quality_notes, revision_count, compliance_pass,
                compliance_flags, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (business_id, wo.get("_db_id"), asset_type, topic, body,
             wo.get("target_query"), round(score, 2), json.dumps(evaluation),
             revisions, comp_pass, json.dumps(comp_flags), status),
        ).fetchone()
        conn.commit()
    log.info("Draft %d for '%s' (type=%s, score=%.2f, rev=%d, compliance=%s, status=%s)",
             row["id"], topic, asset_type, score, revisions, comp_pass, status)
    return row["id"]


def generate(business_id: int, only_wo: Optional[int] = None) -> list[int]:
    """Generate drafts for the auto content work orders of the latest plan.
    Pulls work orders from the tracking table if present, else from the plan JSON."""
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            raise SystemExit(f"No business id {business_id}")
        wos = []
        # prefer tracked work orders (they carry status + db id)
        try:
            rows = conn.execute(
                "SELECT id, wo_code, title, capability, execution, instruction "
                "FROM work_orders WHERE business_id=%s", (business_id,)
            ).fetchall()
            for r in rows:
                wos.append({"_db_id": r["id"], "wo_code": r["wo_code"], "title": r["title"],
                            "capability": r["capability"], "execution": r["execution"],
                            "instruction": r["instruction"]})
        except Exception:
            pass
        if not wos:
            plan = conn.execute(
                "SELECT plan FROM strategy_plans WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                (business_id,),
            ).fetchone()
            if plan:
                p = plan["plan"] if isinstance(plan["plan"], dict) else json.loads(plan["plan"])
                wos = p.get("work_orders", [])
    biz = dict(biz)
    created = []
    for wo in wos:
        if only_wo and wo.get("_db_id") != only_wo:
            continue
        # only attempt auto-executable content work orders
        if (wo.get("execution") or "auto") not in ("auto", "semi"):
            continue
        did = generate_for_wo(business_id, wo, biz)
        if did:
            created.append(did)
    log.info("Generated %d draft(s) for business %d", len(created), business_id)
    return created


# ----------------------------------------------------------------------------
# Review workflow
# ----------------------------------------------------------------------------
def list_drafts(business_id: int) -> None:
    _ensure_table()
    with db() as conn:
        rows = conn.execute(
            "SELECT id, asset_type, title, quality_score, compliance_pass, status, revision_count "
            "FROM content_drafts WHERE business_id=%s ORDER BY id DESC", (business_id,)
        ).fetchall()
    for r in rows:
        print(f"  [{r['id']}] {r['status']:<14} q={r['quality_score']} "
              f"compliance={r['compliance_pass']} rev={r['revision_count']} "
              f"{r['asset_type']}: {r['title']}")
    if not rows:
        print("  (no drafts yet)")


def approve(draft_id: int, reviewer: str) -> None:
    """Approve a draft and promote it into the assets table (the only path to
    'published' state). Human action only."""
    with db() as conn:
        d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (draft_id,)).fetchone()
        if not d:
            raise SystemExit(f"No draft {draft_id}")
        asset = conn.execute(
            """INSERT INTO assets (business_id, work_order_id, asset_type, title, surface, meta)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (d["business_id"], d["work_order_id"], d["asset_type"], d["title"],
             "own_site", json.dumps({"from_draft": draft_id})),
        ).fetchone()
        conn.execute(
            "UPDATE content_drafts SET status='approved', reviewer=%s, reviewed_at=now(), "
            "published_asset_id=%s, updated_at=now() WHERE id=%s",
            (reviewer, asset["id"], draft_id),
        )
        # advance the linked work order if present
        if d["work_order_id"]:
            conn.execute(
                "UPDATE work_orders SET status='done', completed_at=COALESCE(completed_at, now()), "
                "updated_at=now() WHERE id=%s AND status IN ('pending','in_progress')",
                (d["work_order_id"],),
            )
        conn.commit()
    log.info("Draft %d approved by %s -> asset %d", draft_id, reviewer, asset["id"])


def reject(draft_id: int, reviewer: str, notes: Optional[str]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE content_drafts SET status='rejected', reviewer=%s, reviewed_at=now(), "
            "quality_notes = quality_notes || %s::jsonb, updated_at=now() WHERE id=%s",
            (reviewer, json.dumps({"reject_notes": notes or ""}), draft_id),
        )
        conn.commit()
    log.info("Draft %d rejected by %s", draft_id, reviewer)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="AI content generator (drafts only; human approves)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--business-id", type=int, required=True)
    g.add_argument("--wo", type=int)
    l = sub.add_parser("list"); l.add_argument("--business-id", type=int, required=True)
    a = sub.add_parser("approve"); a.add_argument("--draft", type=int, required=True); a.add_argument("--reviewer", required=True)
    r = sub.add_parser("reject"); r.add_argument("--draft", type=int, required=True); r.add_argument("--reviewer", required=True); r.add_argument("--notes")
    args = ap.parse_args()
    if args.cmd == "generate":
        generate(args.business_id, args.wo)
    elif args.cmd == "list":
        list_drafts(args.business_id)
    elif args.cmd == "approve":
        approve(args.draft, args.reviewer)
    elif args.cmd == "reject":
        reject(args.draft, args.reviewer, args.notes)


if __name__ == "__main__":
    main()
