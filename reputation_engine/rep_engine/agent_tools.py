"""
LangGraph tool seam over the verified rep_engine (Phase 0 of the agentic layer).

CRITICAL INVARIANT -- every token an agent/graph spends MUST flow through this
module. It gates on cost.over_budget() BEFORE the call and records spend via
cost.record() AFTER, so the engine's guarantees survive inside a graph:
  * budget fails CLOSED (a lost cost write => over_budget True),
  * the cheap/mid/full cost tiering is preserved,
  * the Opus-4.8 prefill mitigation + provider handling in orchestrator_* is kept,
  * scraped third-party text is fenced as untrusted DATA before any prompt.

Graphs call THESE wrappers, never a raw ChatAnthropic/ChatOpenAI client -- binding
a graph straight to a provider client would silently bypass every guarantee above.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

try:
    from . import ai_state_audit as _audit
    from . import cost as _cost
    from . import http as _http
    from . import netguard as _netguard
    from . import semantic_depth as _sd
    from . import serper as _sc
except ImportError:  # pragma: no cover -- allows running as a loose script
    import ai_state_audit as _audit  # type: ignore
    import cost as _cost  # type: ignore
    import http as _http  # type: ignore
    import netguard as _netguard  # type: ignore
    import semantic_depth as _sd  # type: ignore
    import serper as _sc  # type: ignore

log = logging.getLogger("agent_tools")

# Re-export so graph nodes fence with the exact same delimiter/instruction the
# audit + content paths use.
UNTRUSTED_INSTRUCTION = _audit.UNTRUSTED_INSTRUCTION
# Re-export so content/brief generators (production_brief, rich_media, agent_content) can append the
# owner's "no specific license numbers in content" policy to their prompts from one source of truth.
LICENSE_CONTENT_POLICY = _audit.LICENSE_CONTENT_POLICY


class BudgetExceededError(RuntimeError):
    """Raised when an agent step would spend past the business's monthly budget."""


def _orchestrator_model(tier: str) -> str:
    anthropic_model, openai_model = _audit._model_for(tier)
    return anthropic_model if _audit.ORCHESTRATOR == "anthropic" else openai_model


def _record(business_id: int, tier: str, operation: str, in_text: str, out_text: str) -> None:
    # orchestrator_text/json do NOT record cost themselves (the caller does), so the
    # seam records here -- approximate tokens since the orchestrator returns no usage.
    _cost.record(business_id, None, _audit.ORCHESTRATOR, operation,
                 _orchestrator_model(tier),
                 _cost.approx_tokens(in_text), _cost.approx_tokens(out_text or ""))


def over_budget(business_id: int) -> bool:
    """Fail-closed budget check, exposed so graph EDGES can stop BEFORE spending."""
    return _cost.over_budget(business_id)


def llm_text(system: str, user: str, *, business_id: int, tier: str = "full",
             max_tokens: int = 2000, operation: str = "agent") -> str:
    """Budget-gated free-text LLM call routed through the verified orchestrator."""
    if _cost.over_budget(business_id):
        raise BudgetExceededError(f"business {business_id} is over its monthly budget")
    out = _audit.orchestrator_text(system, user, max_tokens=max_tokens, tier=tier)
    if out:  # only bill a call that actually returned output -- no phantom cost on a failed call
        _record(business_id, tier, operation, system + user, out)
    return out


def llm_json(system: str, user: str, *, business_id: int, tier: str = "full",
             operation: str = "agent", max_tokens: Optional[int] = None,
             timeout: Optional[int] = None) -> dict:
    """Budget-gated JSON LLM call routed through the verified orchestrator. max_tokens lets a caller
    whose JSON object is larger than orchestrator_json's 2000-token default raise the cap so the
    output isn't truncated mid-JSON -> unparseable -> {} (e.g. a multi-item production-brief object
    ran ~3.7k tokens and silently returned nothing at the default); timeout accommodates the longer
    generation."""
    if _cost.over_budget(business_id):
        raise BudgetExceededError(f"business {business_id} is over its monthly budget")
    kw: dict = {}
    if max_tokens is not None:
        kw["max_tokens"] = max_tokens
    if timeout is not None:
        kw["timeout"] = timeout
    out = _audit.orchestrator_json(system, user, tier=tier, **kw)
    if out:  # only bill a call that actually returned output -- no phantom cost on a failed call
        _record(business_id, tier, operation, system + user, json.dumps(out, default=str))
    return out


def fence(text: str) -> str:
    """Wrap attacker-controlled (scraped) text as untrusted DATA before a prompt."""
    return _audit._fence_untrusted(text)


def fetch_text(url: str, *, timeout: int = 20, deadline: Optional[float] = 45.0) -> Optional[str]:
    """SSRF-guarded fetch of a third-party page (e.g. a contested source). Returns
    the raw text -- the caller MUST fence() it before any prompt -- or None on a
    guard block / fetch failure. Never give a graph a raw fetch tool; use this."""
    try:
        _netguard.assert_url_allowed(url)
    except _netguard.UnsafeURLError as e:
        log.warning("agent fetch blocked by SSRF guard: %s", e)
        return None
    res = _http.request_json("GET", url, parse_json=False, timeout=timeout,
                             guard_redirects=True, deadline=deadline)
    return res.text if not res.failed else None


def web_search(query: str, *, limit: int = 15) -> list:
    """Web search for discovery (industry/geo journalists, outlets, coverage). Uses
    Serper (google.serper.dev) when SERPER_API_KEY is set -- richer, structured
    results -- otherwise keyless Google News RSS. Returns [{title, url, outlet,
    snippet}]. Results are attacker-influenced -- the caller MUST fence() snippets
    before any prompt. Both backends hit a FIXED host (SSRF-safe)."""
    key = os.getenv("SERPER_API_KEY", "")
    return _serper_news(query, key, limit) if key else _rss_news(query, limit)


def _serper_news(query: str, key: str, limit: int) -> list:
    # Route through the shared TTL cache (collapses the duplicate paid Serper calls the
    # discovery/audit paths make for overlapping queries). `key` is unused now -- cached_post
    # reads SERPER_API_KEY itself and returns None when it's unset.
    data = _sc.cached_post("news", {"q": query, "num": min(limit, 20)})
    if not isinstance(data, dict):
        return []
    return [{"title": it.get("title", ""), "url": it.get("link", ""),
             "outlet": it.get("source", ""), "snippet": it.get("snippet", "")}
            for it in (data.get("news") or [])[:limit] if isinstance(it, dict)]


def _rss_news(query: str, limit: int) -> list:
    from urllib.parse import quote
    url = f"https://news.google.com/rss/search?q={quote(query)}"
    res = _http.request_json("GET", url, parse_json=False, timeout=20, max_retries=2,
                             deadline=30.0, guard_redirects=True)
    if res.failed or not res.text:
        return []
    out = []
    for it in re.findall(r"<item>(.*?)</item>", res.text, re.DOTALL)[:limit]:
        def _tag(t: str) -> str:
            m = re.search(rf"<{t}>(.*?)</{t}>", it, re.DOTALL)
            return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1)).strip() if m else ""
        out.append({"title": _tag("title"), "url": _tag("link"),
                    "outlet": _tag("source"), "snippet": _tag("description")})
    return out


_CHECKPOINTER = None


def make_checkpointer():
    """Shared checkpointer for the human-gated graphs (incident / remediation).

    With AGENT_CHECKPOINT_PG set, a DURABLE PostgresSaver (reusing REP_DB_DSN) so a
    human can resume an interrupted incident/bundle in a DIFFERENT process; otherwise
    an in-memory saver (resume only within the same process). Cached as a singleton so
    a graph's pause and its later resume share the same store. Tests pass an explicit
    checkpointer and don't touch this."""
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        if os.getenv("AGENT_CHECKPOINT_PG", "").lower() in ("1", "true", "yes"):
            _CHECKPOINTER = _pg_saver()
        else:
            from langgraph.checkpoint.memory import InMemorySaver
            _CHECKPOINTER = InMemorySaver()
    return _CHECKPOINTER


def _pg_saver():
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    try:
        from .db import dsn
    except ImportError:  # pragma: no cover
        from db import dsn  # type: ignore
    # Use the VALIDATED DSN (config.load_settings), not the raw DB_DSN env constant: a
    # placeholder/non-postgres DSN fails fast with a clear message here instead of the pool
    # silently opening against the wrong/unset target. PostgresSaver requires autocommit +
    # dict_row on its connections.
    pool = ConnectionPool(conninfo=dsn(), min_size=1, max_size=4, open=True,
                          kwargs={"autocommit": True, "row_factory": dict_row})
    saver = PostgresSaver(pool)
    saver.setup()   # idempotent: creates the langgraph checkpoint tables if absent
    return saver


def citation_readiness(text: str, *, title: str = "", target_terms: Optional[list] = None,
                       target_query: str = "") -> dict:
    """Run the AEO/GEO citation-readiness scorer on ANY page's text (e.g. a contested
    source or a competitor), so a graph can ask 'what makes this page citation-worthy
    that ours isn't'. Reuses semantic_depth.analyze_text unchanged."""
    return _sd.analyze_text(text, title=title, target_terms=target_terms or [],
                            target_query=target_query)
