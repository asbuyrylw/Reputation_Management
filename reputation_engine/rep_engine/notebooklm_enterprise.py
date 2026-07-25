"""
NotebookLM Enterprise — assisted podcast flow via the LICENSED USER (OAuth)
==========================================================================
Proven live against Google's NotebookLM Enterprise API (Discovery Engine). The audio-generation
license is a per-USER seat, so this authenticates as the licensed user via an offline OAuth refresh
token (NOT a service account — a service account can't hold the seat). Flow, all confirmed working:

    POST   {loc}-discoveryengine.googleapis.com/v1alpha/projects/{num}/locations/{loc}/notebooks
    POST   .../notebooks/{id}/sources:batchCreate      (userContents[].textContent)
    POST   .../notebooks/{id}/audioOverviews           (empty body -> starts generation)

Google exposes NO method to DOWNLOAD the finished audio (verified against the discovery doc across
v1alpha/v1beta/v1 — the AudioOverview resource has only create+delete and no audio-data field), so
this "assisted" flow generates the podcast under the owner's account and returns a DEEP LINK to
NotebookLM Studio where they listen/download it. When Google adds a download method, only
_finish_audio() changes.

Config (dormant until set; configured() then True):
    NOTEBOOKLM_ENABLED=1
    NOTEBOOKLM_OAUTH_CLIENT_ID / NOTEBOOKLM_OAUTH_CLIENT_SECRET / NOTEBOOKLM_OAUTH_REFRESH_TOKEN
        (an offline user credential for the licensed account — e.g. from
         `gcloud auth application-default login --scopes=...cloud-platform` -> the ADC json)
    NOTEBOOKLM_PROJECT_NUMBER   (the project holding the Gemini Enterprise/NotebookLM subscription)
    NOTEBOOKLM_LOCATION=global
    NOTEBOOKLM_UI_URL           (optional deep-link template, {id}/{project}/{location} placeholders)

Fail-closed: any misconfig/error returns None so rich_media_generator falls back to the LLM script.
"""
from __future__ import annotations

import hashlib
import json as _json
import logging
import os
import time
from typing import Optional

try:
    from . import http as _http
    from .db import db
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("notebooklm_enterprise")
_token_cache: dict = {"tok": None, "exp": 0}


def enabled() -> bool:
    return (os.getenv("NOTEBOOKLM_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "on")


def _oauth() -> tuple[str, str, str]:
    return ((os.getenv("NOTEBOOKLM_OAUTH_CLIENT_ID", "") or "").strip(),
            (os.getenv("NOTEBOOKLM_OAUTH_CLIENT_SECRET", "") or "").strip(),
            (os.getenv("NOTEBOOKLM_OAUTH_REFRESH_TOKEN", "") or "").strip())


def _project() -> str:
    return (os.getenv("NOTEBOOKLM_PROJECT_NUMBER", "") or "").strip()


def _location() -> str:
    return (os.getenv("NOTEBOOKLM_LOCATION", "global") or "global").strip()


def configured() -> bool:
    """True only when a licensed-user OAuth credential + subscription project are set."""
    cid, csec, rt = _oauth()
    return enabled() and bool(cid and csec and rt) and bool(_project())


def _access_token() -> Optional[str]:
    cid, csec, rt = _oauth()
    if not (cid and csec and rt):
        return None
    now = int(time.time())
    if _token_cache["tok"] and _token_cache["exp"] - 60 > now:
        return _token_cache["tok"]
    res = _http.request_json(
        "POST", "https://oauth2.googleapis.com/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "client_id": cid, "client_secret": csec, "refresh_token": rt},
        timeout=30, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict) or not res.data.get("access_token"):
        log.warning("notebooklm_enterprise: token refresh failed: %s", res.error if res.failed else "no token")
        return None
    _token_cache["tok"] = res.data["access_token"]
    _token_cache["exp"] = now + int(res.data.get("expires_in", 3600))
    return _token_cache["tok"]


def _host() -> str:
    return (os.getenv("NOTEBOOKLM_BASE_URL", "") or "").strip() \
        or f"https://{_location()}-discoveryengine.googleapis.com/v1alpha"


def _parent() -> str:
    return f"projects/{_project()}/locations/{_location()}"


def _hdr(tok: str) -> dict:
    # X-Goog-User-Project is required for user credentials so the quota/billing project resolves.
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
            "X-Goog-User-Project": _project()}


def _notebook_url(nb: str) -> str:
    tmpl = (os.getenv("NOTEBOOKLM_UI_URL", "") or "").strip()
    if tmpl:
        return tmpl.replace("{id}", nb).replace("{project}", _project()).replace("{location}", _location())
    return f"https://notebooklm.cloud.google.com/notebook/{nb}"


# --------------------------------------------------------------------------------------------------
# Persistent per-business notebook registry (fixes "a new notebook every podcast")
# --------------------------------------------------------------------------------------------------
# One NotebookLM notebook is reused per (business, audio style) instead of created-and-abandoned each
# call. We track which SOURCE content-hashes are already in the notebook so a reused notebook doesn't
# accumulate duplicate sources (the Enterprise sources API is append-only). Kill-switch: set
# NOTEBOOKLM_PERSIST=0 to force the old create-new-each-time behavior without a deploy.

def _persist_enabled() -> bool:
    return (os.getenv("NOTEBOOKLM_PERSIST", "1") or "1").strip().lower() in ("1", "true", "yes", "on")


def _ensure_notebook_table() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notebooklm_notebooks (
                business_id   BIGINT NOT NULL,
                style         TEXT   NOT NULL,
                notebook_id   TEXT   NOT NULL,
                notebook_url  TEXT,
                source_hashes JSONB DEFAULT '[]'::jsonb,
                created_at    TIMESTAMPTZ DEFAULT now(),
                updated_at    TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (business_id, style)
            )""")
        conn.commit()


def _load_notebook(business_id: int, style: str) -> tuple[Optional[str], Optional[str], set]:
    _ensure_notebook_table()
    with db() as conn:
        r = conn.execute("SELECT notebook_id, notebook_url, source_hashes FROM notebooklm_notebooks "
                         "WHERE business_id=%s AND style=%s", (business_id, style)).fetchone()
    if not r:
        return None, None, set()
    hashes = r.get("source_hashes") if isinstance(r.get("source_hashes"), list) else []
    return r.get("notebook_id"), r.get("notebook_url"), set(hashes)


def _save_notebook(business_id: int, style: str, nb: str, url: Optional[str], hashes: set) -> None:
    _ensure_notebook_table()
    with db() as conn:
        conn.execute("""
            INSERT INTO notebooklm_notebooks (business_id, style, notebook_id, notebook_url, source_hashes, updated_at)
            VALUES (%s,%s,%s,%s,%s, now())
            ON CONFLICT (business_id, style) DO UPDATE SET
              notebook_id=EXCLUDED.notebook_id, notebook_url=EXCLUDED.notebook_url,
              source_hashes=EXCLUDED.source_hashes, updated_at=now()""",
            (business_id, style, nb, url, _json.dumps(sorted(hashes))))
        conn.commit()


def _src_hash(s: dict) -> str:
    raw = ((s.get("title") or "") + "\x00" + (s.get("text") or "")).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:20]


def _create_notebook(tok: str, title: str) -> tuple[Optional[str], Optional[str]]:
    r = _http.request_json("POST", f"{_host()}/{_parent()}/notebooks", headers=_hdr(tok),
                           json={"title": (title or "Notebook")[:200]},
                           timeout=60, max_retries=1, guard_redirects=True)
    if r.failed or not isinstance(r.data, dict):
        log.warning("notebooklm_enterprise: create notebook failed: %s", r.error)
        return None, None
    nb = r.data.get("notebookId") or (r.data.get("name", "") or "").rsplit("/", 1)[-1]
    return (nb or None), (_notebook_url(nb) if nb else None)


def _notebook_exists(tok: str, nb: str) -> bool:
    """Best-effort existence check before REUSE. Only a definitive 404 recreates; an ambiguous/transient
    error trusts the stored id (so a network hiccup never churns a fresh notebook)."""
    r = _http.request_json("GET", f"{_host()}/{_parent()}/notebooks/{nb}", headers=_hdr(tok),
                           timeout=30, max_retries=1, guard_redirects=True)
    return r.status != 404


def _add_sources(tok: str, nb: str, sources: list[dict], seen: set) -> tuple[int, list, bool]:
    """Append only sources whose content-hash isn't already in the notebook (no dup accumulation on
    reuse). Returns (added_count, newly_added_hashes, notebook_gone). notebook_gone=True on a 404 ->
    the caller recreates."""
    added, new_hashes = 0, []
    for s in (sources or [])[:20]:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        h = _src_hash(s)
        if h in seen:
            continue
        sr = _http.request_json(
            "POST", f"{_host()}/{_parent()}/notebooks/{nb}/sources:batchCreate", headers=_hdr(tok),
            json={"userContents": [{"textContent": {"sourceName": (s.get("title", "Source"))[:120],
                                                    "content": txt[:200000]}}]},
            timeout=90, max_retries=1, guard_redirects=True)
        if sr.status == 404:
            return added, new_hashes, True
        if not sr.failed:
            added += 1
            new_hashes.append(h)
    return added, new_hashes, False


def _start_audio(tok: str, nb: str) -> str:
    a = _http.request_json("POST", f"{_host()}/{_parent()}/notebooks/{nb}/audioOverviews", headers=_hdr(tok),
                           json={}, timeout=90, max_retries=1, guard_redirects=True)
    status = "AUDIO_OVERVIEW_STATUS_IN_PROGRESS"
    if not a.failed and isinstance(a.data, dict):
        _ao = a.data.get("audioOverview")   # may come back as a non-dict (enum string / list) -> guard
        status = (_ao.get("status") if isinstance(_ao, dict) else None) or status
    elif a.failed:
        log.warning("notebooklm_enterprise: audioOverview start failed: %s", a.error)
    return status


def sync_sources(business_id: int, sources: list[dict], *, style: str = "podcast") -> dict:
    """Refresh the persistent Team notebook's ground-truth sources WITHOUT generating audio. Find-or-
    create the notebook, add any NEW sources (content-hash skip), and persist the registry. Lets a
    scheduled/gap job keep the notebook current so the next podcast reflects the latest reports, gap
    model, strategy, and generated content. Dormant-safe: {skipped} when NotebookLM isn't configured."""
    if not (configured() and _persist_enabled()):
        return {"skipped": True, "reason": "notebooklm not configured / persistence disabled"}
    tok = _access_token()
    if not tok:
        return {"skipped": True, "reason": "no user access token"}
    try:
        nb, url, seen = _load_notebook(business_id, style)
        if nb and not _notebook_exists(tok, nb):
            nb, url, seen = None, None, set()
        if not nb:
            nb, url = _create_notebook(tok, f"Team notebook (business {business_id})")
            if not nb:
                return {"ok": False, "error": "could not create notebook"}
            seen = set()
        added, new_hashes, gone = _add_sources(tok, nb, sources, seen)
        if gone:
            nb, url = _create_notebook(tok, f"Team notebook (business {business_id})")
            if not nb:
                return {"ok": False, "error": "could not recreate notebook"}
            seen = set()
            added, new_hashes, _ = _add_sources(tok, nb, sources, seen)
        _save_notebook(business_id, style, nb, url or _notebook_url(nb), seen | set(new_hashes))
        return {"ok": True, "notebook_id": nb, "notebook_url": url or _notebook_url(nb),
                "added": added, "total_sources": len(seen | set(new_hashes))}
    except Exception as e:  # noqa: BLE001 -- source sync must never break the caller
        log.warning("notebooklm_enterprise: sync_sources failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}


def synthesise_audio(sources: list[dict], title: str, *, style: str = "podcast",
                     focus: str = "", business_id: Optional[int] = None, **kw) -> Optional[dict]:
    """REUSE one persistent NotebookLM notebook per (business, style), add any new sources, and start a
    fresh audio overview under the licensed user's account. Returns the deep link to NotebookLM Studio
    (where the owner listens/downloads the audio) + the reused notebook_id. `transcript` carries the
    link message so rich_media stores the draft. Returns None on any failure so the caller falls back to
    the in-house LLM script. Persistence is per-business (kill-switch NOTEBOOKLM_PERSIST=0)."""
    if not configured():
        return None
    tok = _access_token()
    if not tok:
        log.warning("notebooklm_enterprise: no user access token (check the OAuth refresh token)")
        return None
    # Fail-closed: the module + docstring promise None on ANY error so the caller falls back to the
    # in-house LLM script. Wrap the whole notebook-op body (a non-dict API response, a DB blip, etc.)
    # so nothing raises into rich_media_generator._generate_audio, which would silently DROP the podcast.
    try:
        persist = business_id is not None and _persist_enabled()
        nb: Optional[str] = None
        url: Optional[str] = None
        seen: set = set()
        if persist:
            try:
                nb, url, seen = _load_notebook(business_id, style)
            except Exception as e:  # noqa: BLE001 -- registry failure -> fall back to a fresh notebook
                log.warning("notebooklm_enterprise: notebook registry load failed (%s) -- using a fresh notebook", e)
                nb, url, seen = None, None, set()
            if nb and not _notebook_exists(tok, nb):
                log.info("notebooklm_enterprise: stored notebook %s is gone (deleted in Studio?) -- recreating", nb)
                nb, url, seen = None, None, set()
        if not nb:
            nb, url = _create_notebook(tok, title)
            if not nb:
                return None
            seen = set()
        added, new_hashes, gone = _add_sources(tok, nb, sources, seen)
        if gone:
            # the notebook vanished between the existence check and the source add -> recreate + add all
            nb, url = _create_notebook(tok, title)
            if not nb:
                return None
            seen = set()
            added, new_hashes, _ = _add_sources(tok, nb, sources, seen)
        if persist:
            try:
                _save_notebook(business_id, style, nb, url or _notebook_url(nb), seen | set(new_hashes))
            except Exception as e:  # noqa: BLE001
                log.warning("notebooklm_enterprise: notebook registry save failed: %s", e)
        status = _start_audio(tok, nb)
        url = url or _notebook_url(nb)
        total = len(seen | set(new_hashes))
        body = (f"🎙️ Your podcast is generating in NotebookLM under your Gemini Enterprise account "
                f"({total} source{'s' if total != 1 else ''} in the Team notebook).\n\n"
                f"▶ Open it in NotebookLM to listen and download the audio:\n{url}\n\n"
                f"Note: Google's NotebookLM API doesn't allow downloading the audio automatically, so "
                f"the finished episode is retrieved from the NotebookLM Studio page above.")
        return {"generator": "notebooklm", "notebook_id": nb, "notebook_url": url, "status": status,
                "audio_url": None, "transcript": body, "body": body, "audio_pending": True}
    except Exception as e:  # noqa: BLE001 -- fail-closed: any error -> None so the caller uses the LLM script
        log.warning("notebooklm_enterprise: synthesise_audio failed (%s) -- falling back to the LLM script", e)
        return None
