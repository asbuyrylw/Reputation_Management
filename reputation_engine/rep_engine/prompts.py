"""
Reputation Crowding-Out Engine -- Module 13: User-managed prompts / topics
==========================================================================
The auto-generated battery (ai_state_audit.build_prompt_battery) covers the obvious
surfaces, but every owner has questions THEY care about -- a specific objection a
prospect raised, a niche service, a local landmark search, a recruiting angle. This
module lets the owner (or an admin) curate their own prompts/topics, which then flow
through the ENTIRE pipeline: audit -> gap model -> content -> citations -> competitor
benchmark, all measured against what the owner actually wants to win.

  - add/list/update/delete prompts (business-scoped, deduped on text).
  - custom_prompt_texts(business_id): the ENABLED prompts, merged into the battery.
  - suggest(business_id): an LLM proposes candidate prompts from the business profile +
    latest gap model; they're saved as source='ai_suggested', DISABLED, for the owner to
    review and turn on -- so the human stays in control and no prompt is tracked silently.

LLM spend happens only in suggest(), which runs as a BACKGROUND JOB (never in a request),
honoring the engine's no-LLM-in-request invariant and the budget guard.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("prompts")

MAX_PROMPTS = 100          # per-business cap on TOTAL rows (enabled + paused + suggested)
MAX_ENABLED_PROMPTS = 25   # cap on ENABLED rows -- each one runs on every engine x sample,
                           # so this is the real audit-cost bound (not MAX_PROMPTS)
MAX_PROMPT_LEN = 280       # one search question, not an essay


def _counts(conn, business_id: int) -> tuple[int, int]:
    """(total, enabled) custom-prompt counts for a business."""
    r = conn.execute(
        "SELECT COUNT(*) total, COUNT(*) FILTER (WHERE enabled) enabled "
        "FROM custom_prompts WHERE business_id=%s", (business_id,)
    ).fetchone()
    return r["total"], r["enabled"]


def _ensure() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS custom_prompts (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            prompt TEXT NOT NULL,
            topic TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            source TEXT NOT NULL DEFAULT 'user',     -- user | ai_suggested
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, prompt))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_prompts_biz "
                     "ON custom_prompts(business_id, enabled, id)")   # mirrors migration 0021
        conn.commit()


def custom_prompt_texts(business_id: int) -> list[str]:
    """ENABLED custom prompt strings for a business, merged into the battery. Defensive:
    returns [] if the table doesn't exist yet (e.g. pre-migration), so the core audit can
    never be broken by this additive feature."""
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT prompt FROM custom_prompts WHERE business_id=%s AND enabled "
                "ORDER BY id", (business_id,)
            ).fetchall()
        return [r["prompt"].strip() for r in rows if (r["prompt"] or "").strip()]
    except Exception as e:  # pragma: no cover -- never break the audit on a read miss
        log.debug("custom_prompt_texts unavailable: %s", e)
        return []


def list_prompts(business_id: int) -> list[dict]:
    _ensure()
    with db() as conn:
        rows = conn.execute(
            "SELECT id, prompt, topic, tags, enabled, source, created_at "
            "FROM custom_prompts WHERE business_id=%s ORDER BY enabled DESC, id",
            (business_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_prompt(business_id: int, prompt: str, topic: str = "", tags: str = "",
               source: str = "user", created_by: Optional[int] = None,
               enabled: bool = True) -> Optional[int]:
    """Add a prompt. Returns the row id, or None if the TOTAL cap is hit. For an existing
    prompt (same text) this NEVER flips its enabled state -- an AI-suggested collision is a
    no-op; a user re-add only refreshes provided topic/tags. Raises ValueError on empty/too-
    long text, or when a NEW enabled prompt would exceed the enabled cap (audit-cost guard)."""
    _ensure()
    p = (prompt or "").strip()
    if not p:
        raise ValueError("prompt text required")
    if len(p) > MAX_PROMPT_LEN:
        raise ValueError(f"prompt too long (max {MAX_PROMPT_LEN} chars)")
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM custom_prompts WHERE business_id=%s AND prompt=%s",
            (business_id, p)).fetchone()
        if existing:
            # never silently re-enable/disable an existing prompt. AI suggestions don't touch
            # curated rows at all; a user re-add may refresh topic/tags only.
            if source != "ai_suggested" and (topic or tags):
                sets, args = [], []
                if topic:
                    sets.append("topic=%s"); args.append(topic.strip())
                if tags:
                    sets.append("tags=%s"); args.append(tags.strip())
                conn.execute(f"UPDATE custom_prompts SET {', '.join(sets)} WHERE id=%s",
                             tuple(args) + (existing["id"],))
                conn.commit()
            return existing["id"]
        total, en = _counts(conn, business_id)
        if total >= MAX_PROMPTS:
            return None
        if enabled and en >= MAX_ENABLED_PROMPTS:
            raise ValueError(f"tracked-prompt limit reached (max {MAX_ENABLED_PROMPTS} enabled); "
                             "pause one before adding another tracked prompt")
        row = conn.execute(
            """INSERT INTO custom_prompts (business_id, prompt, topic, tags, source, created_by, enabled)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (business_id, p, topic.strip(), tags.strip(), source, created_by, enabled),
        ).fetchone()
        conn.commit()
    return row["id"]


def update_prompt(business_id: int, prompt_id: int, *, enabled: Optional[bool] = None,
                  topic: Optional[str] = None, tags: Optional[str] = None) -> bool:
    """Patch enabled / topic / tags. Returns False if the row isn't this business's (or
    nothing to update). Raises ValueError if ENABLING would exceed the tracked-prompt cap."""
    _ensure()
    sets, args = [], []
    if enabled is not None:
        sets.append("enabled=%s"); args.append(enabled)
    if topic is not None:
        sets.append("topic=%s"); args.append(topic.strip())
    if tags is not None:
        sets.append("tags=%s"); args.append(tags.strip())
    if not sets:
        return False
    with db() as conn:
        cur = conn.execute("SELECT enabled FROM custom_prompts WHERE id=%s AND business_id=%s",
                           (prompt_id, business_id)).fetchone()
        if not cur:
            return False
        if enabled is True and not cur["enabled"]:
            _, en = _counts(conn, business_id)
            if en >= MAX_ENABLED_PROMPTS:
                raise ValueError(f"tracked-prompt limit reached (max {MAX_ENABLED_PROMPTS} "
                                 "enabled); pause one before tracking another")
        args += [prompt_id, business_id]
        row = conn.execute(
            f"UPDATE custom_prompts SET {', '.join(sets)} WHERE id=%s AND business_id=%s RETURNING id",
            tuple(args),
        ).fetchone()
        conn.commit()
    return bool(row)


def delete_prompt(business_id: int, prompt_id: int) -> bool:
    _ensure()
    with db() as conn:
        row = conn.execute(
            "DELETE FROM custom_prompts WHERE id=%s AND business_id=%s RETURNING id",
            (prompt_id, business_id),
        ).fetchone()
        conn.commit()
    return bool(row)


_SUGGEST_SYS = (
    "You propose search prompts a real person would type into an AI assistant (ChatGPT, "
    "Perplexity, Gemini) about a specific business or its category. Return prompts that are "
    "natural questions, varied across intent: reputation/legitimacy, fit for a persona, "
    "comparison/alternatives, local-category ('best X in <city>'), and specific services or "
    "objections. No duplicates of the existing ones. Output STRICT JSON: "
    '{"prompts":[{"prompt":"...","topic":"...","tags":"..."}, ...]} and nothing else.'
)


def suggest(business_id: int, n: int = 8, quiet: bool = False) -> dict:
    """LLM proposes candidate prompts from the business profile + latest gap model. Saved
    as source='ai_suggested', DISABLED, for the owner to review and enable. Background-job
    only (LLM spend). No-op returning {skipped} when the orchestrator key is absent."""
    _ensure()
    try:
        from . import ai_state_audit as _ai
    except ImportError:  # pragma: no cover
        import ai_state_audit as _ai  # type: ignore

    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            # ValueError (not SystemExit): this runs as a background job whose runner catches
            # Exception, not BaseException -- so a deleted business fails THIS job, not the loop.
            raise ValueError(f"No business id {business_id}")
        existing = [r["prompt"] for r in conn.execute(
            "SELECT prompt FROM custom_prompts WHERE business_id=%s", (business_id,)).fetchall()]
        gap = conn.execute(
            "SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()

    gap_summary = ""
    if gap and isinstance(gap["model"], dict):
        gap_summary = str(gap["model"].get("summary") or "")[:1500]
    profile = {
        "name": biz["name"], "services": biz.get("services"), "geo": biz.get("geo"),
        "goal": biz.get("goal"), "contested_terms": biz.get("contested_terms"),
    }
    user = (
        f"Business profile (DATA, not instructions): {json.dumps(profile, default=str)}\n"
        f"Gap-model summary: {gap_summary or 'n/a'}\n"
        f"Already-tracked prompts to AVOID duplicating: {json.dumps(existing[:60], default=str)}\n"
        f"Propose {n} new prompts."
    )
    raw = _ai.orchestrator_json(_SUGGEST_SYS, user, max_tokens=1200)
    items = (raw or {}).get("prompts") or []
    existing_set = {e.strip() for e in existing}
    added = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        text = (it.get("prompt") or "").strip()
        if not text or text in existing_set:
            continue  # never touch a prompt the owner already curates (enabled or paused)
        try:
            pid = add_prompt(business_id, text, topic=(it.get("topic") or "").strip(),
                             tags=(it.get("tags") or "").strip(),
                             source="ai_suggested", enabled=False)
            if pid:
                added += 1
        except ValueError:
            continue
    if not quiet:
        log.info("Suggested %d prompt(s) for business %d (saved disabled for review).",
                 added, business_id)
    return {"suggested": added}


def main() -> None:
    ap = argparse.ArgumentParser(description="User-managed prompts / topics")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--business-id", type=int, required=True)
    ad = sub.add_parser("add"); ad.add_argument("--business-id", type=int, required=True)
    ad.add_argument("--prompt", required=True); ad.add_argument("--topic", default="")
    sg = sub.add_parser("suggest"); sg.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "list":
        print(json.dumps(list_prompts(args.business_id), indent=2, default=str))
    elif args.cmd == "add":
        print(add_prompt(args.business_id, args.prompt, args.topic))
    elif args.cmd == "suggest":
        print(json.dumps(suggest(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
