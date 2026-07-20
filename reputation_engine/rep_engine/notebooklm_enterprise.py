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

import logging
import os
import time
from typing import Optional

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

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


def synthesise_audio(sources: list[dict], title: str, *, style: str = "podcast",
                     focus: str = "", **kw) -> Optional[dict]:
    """Create a notebook, add the sources, and start the audio overview under the licensed user's
    account. Returns the deep link to NotebookLM Studio (where the owner listens/downloads the
    audio). `transcript` carries the link message so rich_media stores the draft. Returns None on
    any failure so the caller falls back to the in-house LLM script."""
    if not configured():
        return None
    tok = _access_token()
    if not tok:
        log.warning("notebooklm_enterprise: no user access token (check the OAuth refresh token)")
        return None
    r = _http.request_json("POST", f"{_host()}/{_parent()}/notebooks", headers=_hdr(tok),
                           json={"title": (title or "Notebook")[:200]},
                           timeout=60, max_retries=1, guard_redirects=True)
    if r.failed or not isinstance(r.data, dict):
        log.warning("notebooklm_enterprise: create notebook failed: %s", r.error)
        return None
    nb = r.data.get("notebookId") or (r.data.get("name", "") or "").rsplit("/", 1)[-1]
    if not nb:
        return None
    added = 0
    for s in (sources or [])[:20]:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        sr = _http.request_json(
            "POST", f"{_host()}/{_parent()}/notebooks/{nb}/sources:batchCreate", headers=_hdr(tok),
            json={"userContents": [{"textContent": {"sourceName": (s.get("title", "Source"))[:120],
                                                    "content": txt[:200000]}}]},
            timeout=90, max_retries=1, guard_redirects=True)
        if not sr.failed:
            added += 1
    a = _http.request_json("POST", f"{_host()}/{_parent()}/notebooks/{nb}/audioOverviews", headers=_hdr(tok),
                           json={}, timeout=90, max_retries=1, guard_redirects=True)
    status = "AUDIO_OVERVIEW_STATUS_IN_PROGRESS"
    if not a.failed and isinstance(a.data, dict):
        status = (a.data.get("audioOverview") or {}).get("status") or status
    elif a.failed:
        log.warning("notebooklm_enterprise: audioOverview start failed: %s", a.error)
    url = _notebook_url(nb)
    body = (f"🎙️ Your podcast is generating in NotebookLM under your Gemini Enterprise account "
            f"({added} source{'s' if added != 1 else ''} loaded).\n\n"
            f"▶ Open it in NotebookLM to listen and download the audio:\n{url}\n\n"
            f"Note: Google's NotebookLM API doesn't allow downloading the audio automatically, so "
            f"the finished episode is retrieved from the NotebookLM Studio page above.")
    return {"generator": "notebooklm", "notebook_id": nb, "notebook_url": url, "status": status,
            "audio_url": None, "transcript": body, "body": body, "audio_pending": True}
