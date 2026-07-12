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
prompt. Everything is dormant-safe: no guardrail / no docs -> empty string, generation unaffected.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("source_material")


def _approx_tokens(text: str) -> int:
    return max(1, int(len(text or "") / 4))


def guardrails(business_id: int) -> str:
    """The business's hard branding/voice rules (empty string if none set)."""
    try:
        with db() as conn:
            r = conn.execute("SELECT brand_guardrails FROM businesses WHERE id=%s", (business_id,)).fetchone()
        return (r["brand_guardrails"] or "").strip() if r else ""
    except Exception:  # noqa: BLE001 -- column may not exist yet
        return ""


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
    except Exception as e:  # noqa: BLE001 -- table may not exist yet
        log.warning("source_material.add_document failed: %s", e)
        return None


def list_documents(business_id: int) -> list[dict]:
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, title, source_type, source_url, tokens, active, created_at "
                "FROM source_documents WHERE business_id=%s ORDER BY id DESC", (business_id,)).fetchall()
        return [{"id": r["id"], "title": r["title"], "source_type": r["source_type"],
                 "source_url": r["source_url"], "tokens": r["tokens"], "active": r["active"],
                 "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]
    except Exception:  # noqa: BLE001
        return []


def delete_document(business_id: int, doc_id: int) -> bool:
    try:
        with db() as conn:
            n = conn.execute("DELETE FROM source_documents WHERE id=%s AND business_id=%s",
                             (doc_id, business_id)).rowcount
            conn.commit()
        return bool(n)
    except Exception:  # noqa: BLE001
        return False


def set_active(business_id: int, doc_id: int, active: bool) -> bool:
    try:
        with db() as conn:
            n = conn.execute("UPDATE source_documents SET active=%s WHERE id=%s AND business_id=%s",
                             (active, doc_id, business_id)).rowcount
            conn.commit()
        return bool(n)
    except Exception:  # noqa: BLE001
        return False


def corpus(business_id: int, max_tokens: int = 6000) -> str:
    """Concatenate the active source docs, newest first, trimmed to a token budget."""
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT title, content, tokens FROM source_documents WHERE business_id=%s AND active "
                "ORDER BY id DESC", (business_id,)).fetchall()
    except Exception:  # noqa: BLE001
        return ""
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
    Empty string when nothing is configured (generation is unaffected)."""
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
