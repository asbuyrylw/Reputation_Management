"""
Brand guardrails + source-material corpus
=========================================
Two things that make generated content actually the CLIENT's, not generic web filler:

  1. brand guardrails  — hard branding/voice rules injected into EVERY generation prompt. For
     Team Unstoppable: always brand as "Team Unstoppable", never present as Primerica (Primerica is
     only the firm they're licensed through). Stored per-business, editable.
  2. source corpus     — documents the owner uploads (brand docs, scripts, product one-pagers,
     testimonials, FAQs). Concatenated + budget-trimmed and fed to Claude AND NotebookLM as grounding
     so every asset is built on the client's REAL facts.

`grounding_block()` returns the combined guardrail + corpus, ready to prepend to any generator's
prompt.

FAIL-LOUD (reputation-safety invariant): a BROKEN read must never look identical to "no facts."
For a reputation product, silently generating ungrounded content because a corpus read errored is
the exact harm the product sells against. So the reads here catch ONLY the legitimately-dormant
"table/column not created yet" case (pre-migration) and return empty for it; every OTHER failure is
logged at ERROR and re-raised, so a grounding job fails loudly (and is retried) instead of quietly
shipping ungrounded content that masquerades as "the client uploaded no facts."
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("source_material")

# Postgres SQLSTATEs for the ONLY errors that legitimately mean "not set up yet" (dormant-safe):
# undefined_table / undefined_column. Everything else is a real read failure that must fail loud.
_DORMANT_SQLSTATES = ("42P01", "42703")


def _is_dormant_schema(exc: Exception) -> bool:
    """True only for 'relation/column does not exist yet' (pre-migration) — the sole case allowed to
    return empty silently. Any other DB error is a genuine failure and must NOT masquerade as an
    empty corpus. Reads the SQLSTATE (psycopg3 `.sqlstate` / psycopg2 `.pgcode`), driver-agnostic."""
    code = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    return code in _DORMANT_SQLSTATES


def _approx_tokens(text: str) -> int:
    return max(1, int(len(text or "") / 4))


def guardrails(business_id: int) -> str:
    """The business's hard branding/voice rules (empty string if none set). Raises loudly on a real
    read error rather than returning '' (which would silently drop the client's brand rules)."""
    try:
        with db() as conn:
            r = conn.execute("SELECT brand_guardrails FROM businesses WHERE id=%s", (business_id,)).fetchone()
        return (r["brand_guardrails"] or "").strip() if r else ""
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            return ""  # column not migrated yet -- legitimately no guardrails
        log.error("source_material.guardrails read FAILED for business %s (NOT empty — a broken read): %s",
                  business_id, e, exc_info=True)
        raise


def set_guardrails(business_id: int, text: str) -> bool:
    with db() as conn:
        n = conn.execute("UPDATE businesses SET brand_guardrails=%s WHERE id=%s",
                         (text or None, business_id)).rowcount
        conn.commit()
    return bool(n)


# ---------------------------------------------------------------------------
# source documents
# ---------------------------------------------------------------------------
def add_document(business_id: int, content: str, *, title: Optional[str] = None,
                 source_type: str = "upload", source_url: Optional[str] = None,
                 created_by: Optional[int] = None) -> Optional[int]:
    content = (content or "").strip()
    if not content:
        return None
    try:
        with db() as conn:
            r = conn.execute(
                "INSERT INTO source_documents (business_id, title, source_type, source_url, content, "
                "tokens, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (business_id, (title or "Untitled")[:200], source_type, source_url, content,
                 _approx_tokens(content), created_by)).fetchone()
            conn.commit()
        return r["id"]
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            log.warning("source_material.add_document: table not migrated yet")
            return None
        log.error("source_material.add_document FAILED for business %s: %s", business_id, e, exc_info=True)
        raise


def list_documents(business_id: int) -> list[dict]:
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, title, source_type, source_url, tokens, active, created_at "
                "FROM source_documents WHERE business_id=%s ORDER BY id DESC", (business_id,)).fetchall()
        return [{"id": r["id"], "title": r["title"], "source_type": r["source_type"],
                 "source_url": r["source_url"], "tokens": r["tokens"], "active": r["active"],
                 "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            return []  # table not migrated yet -- legitimately no documents
        log.error("source_material.list_documents read FAILED for business %s (NOT empty): %s",
                  business_id, e, exc_info=True)
        raise


def delete_document(business_id: int, doc_id: int) -> bool:
    try:
        with db() as conn:
            n = conn.execute("DELETE FROM source_documents WHERE id=%s AND business_id=%s",
                             (doc_id, business_id)).rowcount
            conn.commit()
        return bool(n)
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            return False
        log.error("source_material.delete_document FAILED (doc %s / business %s): %s",
                  doc_id, business_id, e, exc_info=True)
        raise


def set_active(business_id: int, doc_id: int, active: bool) -> bool:
    try:
        with db() as conn:
            n = conn.execute("UPDATE source_documents SET active=%s WHERE id=%s AND business_id=%s",
                             (active, doc_id, business_id)).rowcount
            conn.commit()
        return bool(n)
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            return False
        log.error("source_material.set_active FAILED (doc %s / business %s): %s",
                  doc_id, business_id, e, exc_info=True)
        raise


def corpus(business_id: int, max_tokens: int = 6000) -> str:
    """Concatenate the active source docs, newest first, trimmed to a token budget. Raises loudly on
    a real read error — a broken corpus read must NOT return '' and let ungrounded content ship."""
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT title, content, tokens FROM source_documents WHERE business_id=%s AND active "
                "ORDER BY id DESC", (business_id,)).fetchall()
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            return ""  # table not migrated yet -- legitimately no corpus
        log.error("source_material.corpus read FAILED for business %s (NOT empty — a broken read that "
                  "must not masquerade as 'no facts'): %s", business_id, e, exc_info=True)
        raise
    parts, used = [], 0
    for r in rows:
        t = int(r["tokens"] or _approx_tokens(r["content"]))
        if used + t > max_tokens:
            # take a partial slice of this doc to fill the remaining budget
            remaining_chars = max(0, (max_tokens - used)) * 4
            if remaining_chars > 400:
                parts.append(f"## {r['title']}\n{(r['content'] or '')[:remaining_chars]}")
            break
        parts.append(f"## {r['title']}\n{r['content']}")
        used += t
    return "\n\n".join(parts).strip()


def grounding_block(business_id: int, max_tokens: int = 4500) -> str:
    """The combined brand-guardrails + source-corpus block to prepend to any generator's prompt.
    Empty string when nothing is configured (generation is unaffected). Propagates a real read
    failure (from guardrails/corpus) so a broken grounding read fails the job rather than shipping
    ungrounded content."""
    g = guardrails(business_id)
    c = corpus(business_id, max_tokens=max_tokens)
    if not g and not c:
        return ""
    out = []
    if g:
        out.append("BRAND RULES — these are ABSOLUTE and override anything else:\n" + g)
    if c:
        out.append("SOURCE MATERIAL — ground the content in these client-provided facts (do not "
                   "invent facts that contradict them):\n" + c)
    return "\n\n".join(out).strip()


import re as _re

# Imperative sentences in explicitly trusted rule documents that are RULES to obey, not facts to
# reference: "always mention X", "never say Y", "must include Z", "include this disclaimer", "avoid W".
_RULE_RE = _re.compile(
    r"\b((?:always|never|do not|don't|must not|must|avoid|ensure|be sure to|make sure|"
    r"only use|use only|include|do include|don't include|require[sd]?|no |not )\b.{4,200}?)"
    r"(?:[.!\n]|$)", _re.I)

_TRUSTED_RULE_SOURCE_TYPES = frozenset({
    "brand_rules", "brand_rule", "guardrails", "guardrail",
    "trusted_rules", "trusted_rule", "instruction_rules", "rule",
})


def _rules_from_text(text: str, limit: int = 20) -> str:
    rules, seen = [], set()
    for m in _RULE_RE.finditer(text or ""):
        r = " ".join(m.group(1).split()).strip().rstrip(",;:")
        k = r.lower()
        if len(r) >= 8 and k not in seen:
            seen.add(k)
            rules.append(r)
        if len(rules) >= limit:
            break
    return "\n".join("- " + r for r in rules) if rules else ""


def _trusted_rule_corpus(business_id: int, max_tokens: int = 4000) -> str:
    """Only source_documents explicitly stamped as trusted rules may become generation rules.
    Crawled pages and normal uploads remain grounding facts, never executable instructions."""
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT title, content, tokens, source_type FROM source_documents "
                "WHERE business_id=%s AND active AND source_type = ANY(%s) ORDER BY id DESC",
                (business_id, list(_TRUSTED_RULE_SOURCE_TYPES)),
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        if _is_dormant_schema(e):
            return ""
        log.error("source_material.instruction_rules read FAILED for business %s (NOT empty): %s",
                  business_id, e, exc_info=True)
        raise
    parts, used = [], 0
    for r in rows:
        t = int(r["tokens"] or _approx_tokens(r["content"]))
        if used + t > max_tokens:
            remaining_chars = max(0, (max_tokens - used)) * 4
            if remaining_chars > 200:
                parts.append(f"## {r['title']}\n{(r['content'] or '')[:remaining_chars]}")
            break
        parts.append(f"## {r['title']}\n{r['content']}")
        used += t
    return "\n\n".join(parts).strip()


def instruction_rules(business_id: int, limit: int = 20) -> str:
    """Lift MUST-FOLLOW imperatives only from explicitly trusted rule documents.
    Website crawls and ordinary uploads are untrusted facts for grounding; treating them as absolute
    instructions lets client-site text or prompt-injection content steer generation."""
    c = _trusted_rule_corpus(business_id, max_tokens=4000)
    if not c:
        return ""
    return _rules_from_text(c, limit=limit)


def visual_grounding(business_id: int, max_tokens: int = 400) -> str:
    """A COMPACT grounding block for IMAGE/VIDEO prompts (Gemini/Imagen/Veo), which need SHORT
    prompts — image models like Imagen have a hard prompt cap (~480 tokens), so the whole block must
    fit a tight budget shared with the user prompt + compliance policy. Brand rules come FIRST (they
    are short + non-negotiable, e.g. 'always Team Unstoppable, never Primerica'); the source snippet
    fills whatever budget remains. Empty string when nothing is configured. Callers pass a small
    max_tokens for Imagen (e.g. 180) and a larger one for video prompts."""
    budget_chars = max(80, int(max_tokens) * 4)
    g = (guardrails(business_id) or "").strip()
    out, used = [], 0
    if g:
        gg = g[:budget_chars]                      # brand rules take priority within the budget
        out.append("BRAND RULES (absolute): " + gg)
        used += len(gg)
    remaining = budget_chars - used
    if remaining > 200:
        c = corpus(business_id, max_tokens=max(1, remaining // 4))
        if c:
            snippet = " ".join(c.split())[:remaining]
            out.append("Stay consistent with these brand facts: " + snippet)
    return "\n".join(out).strip()


def has_material(business_id: int) -> bool:
    return bool(guardrails(business_id)) or bool(list_documents(business_id))
