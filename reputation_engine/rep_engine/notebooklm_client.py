"""
Google NotebookLM API client for the Reputation Crowding-Out Engine.

NotebookLM ingests multiple source documents (audit answers, competitor research,
gap model summaries, report sections) and synthesises them into content types that
a single-prompt LLM call cannot match:
  - Audio Overview  : two-host podcast-style discussion (NotebookLM's signature feature)
  - Study Guide     : structured learning document across all sources
  - FAQ             : question-answer pairs synthesised from every source
  - Briefing Doc    : executive summary drawn from the full source set
  - Table of Contents / Timeline : structural navigation docs

These types complement -- not replace -- the in-house LLM content path (Module 6
and agent_content.py): Module 6 excels at writing single-topic owned-content assets
(article, bio, FAQ for a specific URL); NotebookLM excels at synthesising ACROSS
many heterogeneous sources with grounded citations.

API reference:
  https://ai.google.dev/gemini-api/docs/semantic-retrieval
  https://ai.google.dev/api/semantic-retrieval/corpora

Auth: Google AI Studio API key (same key as GEMINI_API_KEY; no separate key needed).
    Set NOTEBOOKLM_API_KEY in .env to use a dedicated key; falls back to GEMINI_API_KEY.

Design invariants (mirrors the rest of the engine):
  - Fail-closed: any API error returns None / [] rather than raising; callers
    handle missing results as "content unavailable".
  - Budget-gated: the caller (rich_media_generator) checks over_budget() before
    any call into this module.
  - Untrusted content fencing: source text derived from third-party / contested
    sources MUST be fenced by the caller before being stored as a corpus document.
  - Ephemeral corpora: each generation run creates a corpus, uses it, then deletes
    it -- we do not maintain persistent notebooks for long-running cost reasons.
  - SSRF guard: URL sources are validated by netguard before being passed to the API.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

try:
    from . import http as _http
    from . import netguard as _netguard
except ImportError:  # pragma: no cover -- loose-script fallback
    import http as _http  # type: ignore
    import netguard as _netguard  # type: ignore

log = logging.getLogger("notebooklm_client")

# Google Generative Language API base (Semantic Retrieval / NotebookLM backend).
# Override with NOTEBOOKLM_BASE_URL env for staging / VPC endpoints.
_BASE = os.getenv(
    "NOTEBOOKLM_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
)

# Maximum characters per corpus document chunk (API limit is ~10 000 chars).
_CHUNK_MAX = 9_000

# Supported note generation types the API accepts.
NOTE_TYPES = {
    "study_guide": "STUDY_GUIDE",
    "faq": "FAQ",
    "briefing_doc": "BRIEFING_DOC",
    "table_of_contents": "TABLE_OF_CONTENTS",
    "timeline": "TIMELINE",
}

# Audio Overview styles.
AUDIO_STYLES = {"podcast", "briefing"}


# ---------------------------------------------------------------------------
# Internal HTTP helpers (thin wrappers over the engine's resilient http.py)
# ---------------------------------------------------------------------------

def _api_key() -> str:
    """Resolve API key: NOTEBOOKLM_API_KEY first, then GEMINI_API_KEY."""
    for var in ("NOTEBOOKLM_API_KEY", "GEMINI_API_KEY"):
        k = os.getenv(var, "")
        if k and "YOUR_" not in k:
            return k
    return ""


def _headers(key: str) -> dict:
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _post(path: str, body: dict, key: str) -> Optional[dict]:
    url = f"{_BASE}/{path}"
    res = _http.request_json("POST", url, headers=_headers(key), json=body)
    if res.failed:
        log.warning("NotebookLM POST %s failed: %s", path, res.error)
        return None
    return res.data or {}


def _delete(path: str, key: str) -> bool:
    url = f"{_BASE}/{path}"
    res = _http.request_json("DELETE", url, headers=_headers(key))
    if res.failed and res.status != 404:
        log.warning("NotebookLM DELETE %s failed: %s", path, res.error)
        return False
    return True


# ---------------------------------------------------------------------------
# Corpus (notebook) lifecycle
# ---------------------------------------------------------------------------

def create_corpus(display_name: str, key: str) -> Optional[str]:
    """Create a new corpus (notebook). Returns the corpus resource name or None.

    Resource name format: ``corpora/corpus-{uuid}``
    """
    body = {"corpus": {"displayName": display_name[:128]}}
    res = _post("corpora", body, key)
    if not res:
        return None
    name = res.get("name")
    if name:
        log.info("NotebookLM: created corpus %r", name)
    return name or None


def delete_corpus(corpus_name: str, key: str) -> bool:
    """Delete a corpus and all its documents. Safe to call even if it doesn't exist."""
    if not corpus_name:
        return False
    ok = _delete(corpus_name, key)
    if ok:
        log.info("NotebookLM: deleted corpus %r", corpus_name)
    return ok


# ---------------------------------------------------------------------------
# Document / chunk ingestion
# ---------------------------------------------------------------------------

def add_text_document(corpus_name: str, title: str, text: str, key: str) -> Optional[str]:
    """Add a plain-text document to a corpus as one or more chunks.

    Returns the document resource name, or None on failure.
    Large texts are split at paragraph boundaries to respect the per-chunk limit.
    """
    if not corpus_name or not text or not text.strip():
        return None
    chunks = _split_chunks(text)
    body = {
        "document": {
            "displayName": title[:128],
            "customMetadata": [
                {"key": "source", "stringValue": "reputation_engine"},
            ],
        },
        "chunks": [{"data": {"stringValue": seg}} for seg in chunks],
    }
    path = f"{corpus_name}/documents"
    res = _post(path, body, key)
    if not res:
        return None
    doc_name = res.get("name")
    log.debug("NotebookLM: added doc %r (%d chunks) to %r", doc_name, len(chunks), corpus_name)
    return doc_name or None


def add_url_document(corpus_name: str, url: str, title: str, key: str) -> Optional[str]:
    """Add a public web URL as a source document.

    The URL is validated by netguard before being sent to the API. Returns the
    document resource name, or None on failure or blocked URL.
    """
    if not corpus_name or not url:
        return None
    try:
        _netguard.assert_url_allowed(url)
    except Exception as e:
        log.warning("NotebookLM: URL %r blocked by netguard: %s", url, e)
        return None
    body = {
        "document": {
            "displayName": title[:128],
            "customMetadata": [
                {"key": "source_url", "stringValue": url[:512]},
                {"key": "source", "stringValue": "reputation_engine"},
            ],
        }
    }
    res = _post(f"{corpus_name}/documents", body, key)
    if not res:
        return None
    return res.get("name") or None


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

def generate_audio_overview(
    corpus_name: str, key: str, style: str = "podcast"
) -> Optional[dict]:
    """Generate an Audio Overview from a corpus.

    This is NotebookLM's signature feature: a natural two-host AI-narrated
    podcast synthesising all corpus sources into an engaging discussion.

    Args:
        corpus_name: Resource name of the corpus to synthesise.
        key: Google API key.
        style: ``'podcast'`` (two hosts, conversational) or ``'briefing'``
               (single narrator, more formal).

    Returns:
        Dict with keys ``audio_url``, ``transcript``, ``duration_seconds``,
        ``style``, ``corpus_name`` -- or None if generation failed.
    """
    if not corpus_name or not key:
        return None
    style = style if style in AUDIO_STYLES else "podcast"
    body = {
        "generationType": "AUDIO_OVERVIEW",
        "audioConfig": {"style": style.upper()},
    }
    # Audio generation can take 10-60 s; the http helper's 60 s default is fine.
    res = _post(f"{corpus_name}:generateDiscussion", body, key)
    if not res:
        return None
    return _parse_audio(res, corpus_name, style)


def generate_note(
    corpus_name: str, note_type: str, key: str
) -> Optional[str]:
    """Generate a structured note from a corpus.

    Args:
        corpus_name: Resource name of the corpus to synthesise.
        note_type: One of ``NOTE_TYPES`` keys (``'study_guide'``, ``'faq'``,
                   ``'briefing_doc'``, ``'table_of_contents'``, ``'timeline'``).
        key: Google API key.

    Returns:
        The note content as a markdown string, or None on failure.
    """
    if not corpus_name or not key:
        return None
    api_type = NOTE_TYPES.get(note_type)
    if not api_type:
        log.warning("NotebookLM: unknown note_type %r; valid: %s", note_type,
                    list(NOTE_TYPES))
        return None
    body = {"generationType": api_type}
    res = _post(f"{corpus_name}:generateNote", body, key)
    if not res:
        return None
    # The API may return the content under different keys across versions.
    content = (res.get("content") or res.get("text")
               or res.get("note") or res.get("output"))
    if not content:
        log.warning("NotebookLM: generateNote returned no content for type %r", note_type)
    return content or None


def query_corpus(corpus_name: str, query: str, key: str, top_k: int = 5) -> list:
    """Retrieve the most relevant passages for a query. Useful for targeted Q&A.

    Returns a list of passage dicts (``content``, ``score``, ``source`` keys).
    """
    if not corpus_name or not query or not key:
        return []
    body = {"query": query, "resultsCount": min(max(1, top_k), 20)}
    res = _post(f"{corpus_name}:query", body, key)
    if not res:
        return []
    raw = res.get("relevantChunks") or res.get("passages") or []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        chunk = item.get("chunk") or item
        text = (chunk.get("data", {}).get("stringValue")
                or chunk.get("content") or chunk.get("text") or "")
        out.append({
            "content": text[:2000],
            "score": item.get("chunkRelevanceScore") or item.get("score"),
            "source": chunk.get("name") or "",
        })
    return out


# ---------------------------------------------------------------------------
# Convenience: full round-trip helpers
# ---------------------------------------------------------------------------

def synthesise_audio(
    sources: list[dict],
    notebook_title: str,
    key: str,
    style: str = "podcast",
) -> Optional[dict]:
    """Create a corpus, add sources, generate Audio Overview, delete corpus.

    ``sources`` is a list of ``{"title": str, "text": str}`` dicts. URL sources
    are supported via ``{"title": str, "url": str}`` dicts.

    Returns the audio result dict (see ``generate_audio_overview``) or None.
    This is the primary entry point for the rich_media_generator.
    """
    corpus = create_corpus(notebook_title, key)
    if not corpus:
        return None
    try:
        for s in sources:
            if s.get("url"):
                add_url_document(corpus, s["url"], s.get("title", "source"), key)
            elif s.get("text"):
                add_text_document(corpus, s.get("title", "source"), s["text"], key)
        result = generate_audio_overview(corpus, key, style=style)
        if result:
            result["notebook_title"] = notebook_title
        return result
    finally:
        delete_corpus(corpus, key)


def synthesise_note(
    sources: list[dict],
    notebook_title: str,
    note_type: str,
    key: str,
) -> Optional[str]:
    """Create a corpus, add sources, generate a note, delete corpus.

    Returns the note text (markdown) or None.
    """
    corpus = create_corpus(notebook_title, key)
    if not corpus:
        return None
    try:
        for s in sources:
            if s.get("url"):
                add_url_document(corpus, s["url"], s.get("title", "source"), key)
            elif s.get("text"):
                add_text_document(corpus, s.get("title", "source"), s["text"], key)
        return generate_note(corpus, note_type, key)
    finally:
        delete_corpus(corpus, key)


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _split_chunks(text: str, max_chars: int = _CHUNK_MAX) -> list:
    """Split text at paragraph boundaries into chunks of at most max_chars."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # Prefer splitting at a paragraph break to keep context coherent.
            para = text.rfind("\n\n", start, end)
            if para > start:
                end = para
        seg = text[start:end].strip()
        if seg:
            chunks.append(seg)
        start = end
    return chunks


def _parse_audio(res: dict, corpus_name: str, style: str) -> Optional[dict]:
    """Normalise the audio generation response into a stable dict."""
    # The API may evolve its response shape; handle known variants gracefully.
    audio_url = (
        res.get("audioUri") or res.get("audio_uri")
        or res.get("outputUri") or res.get("output_uri")
        or res.get("uri") or ""
    )
    transcript = res.get("transcript") or res.get("transcription") or ""
    duration = None
    try:
        duration = int(
            res.get("durationSeconds") or res.get("duration_seconds") or 0
        ) or None
    except (TypeError, ValueError):
        pass
    if not audio_url and not transcript:
        log.warning("NotebookLM: audio response had neither audioUri nor transcript")
        return None
    return {
        "audio_url": audio_url,
        "transcript": transcript,
        "duration_seconds": duration,
        "style": style,
        "corpus_name": corpus_name,
    }
