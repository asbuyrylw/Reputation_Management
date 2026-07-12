"""
NotebookLM Enterprise API client (Google Cloud Discovery Engine)
================================================================
The REAL NotebookLM API — distinct from the dead public-Gemini scaffold in notebooklm_client.py.
It lives on the Discovery Engine host and authenticates with an OAuth2 service-account bearer token
(NOT an `AIza...` API key), which is why the plain NOTEBOOKLM_API_KEY could never work against it:

    POST https://{us|eu|global}-discoveryengine.googleapis.com/v1alpha/
         projects/{PROJECT_NUMBER}/locations/{LOCATION}/notebooks/{NOTEBOOK_ID}/audioOverviews

Config (all via env; DORMANT until a service account is provided — configured() is then True):
    NOTEBOOKLM_ENABLED=1
    NOTEBOOKLM_PROJECT_NUMBER=123456789012   (or reuse GEMINI_PROJECT_NAME's trailing segment)
    NOTEBOOKLM_LOCATION=global               (us | eu | global; default global)
    NOTEBOOKLM_SA_JSON={...}                 (inline service-account JSON)  -- OR --
    GOOGLE_APPLICATION_CREDENTIALS=/path/sa.json  /  NOTEBOOKLM_SA_FILE=/path/sa.json

Auth is minted here with pyjwt (RS256, via the already-present `cryptography` dep) exchanging a
signed JWT for an access token at oauth2.googleapis.com/token — no extra dependency needed.

STATUS: create-notebook / add-source / create-audio-overview follow the documented shapes. The
audio *retrieval/download* step is NOT documented in the public API yet, so synthesise_audio kicks
off the overview and returns its status; the download is finalized + verified once a real service
account is wired (see _retrieve_audio). Everything is fail-closed: any misconfig/error returns None
so rich_media_generator falls back to the in-house LLM script.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

log = logging.getLogger("notebooklm_enterprise")

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_token_cache: dict = {"tok": None, "exp": 0}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def enabled() -> bool:
    return (os.getenv("NOTEBOOKLM_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "on")


def _sa_info() -> Optional[dict]:
    """The service-account JSON, from an inline env var or a file path. None if absent/unparseable."""
    raw = (os.getenv("NOTEBOOKLM_SA_JSON", "") or "").strip()
    if raw:
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            log.warning("notebooklm_enterprise: NOTEBOOKLM_SA_JSON is not valid JSON")
            return None
    path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "") or os.getenv("NOTEBOOKLM_SA_FILE", "") or "").strip()
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            log.warning("notebooklm_enterprise: could not read service-account file %s", path)
    return None


def _project_number() -> str:
    p = (os.getenv("NOTEBOOKLM_PROJECT_NUMBER", "") or "").strip()
    if p:
        return p
    # GEMINI_PROJECT_NAME is like 'projects/<number-or-id>' — take the trailing segment.
    g = (os.getenv("GEMINI_PROJECT_NAME", "") or "").strip()
    return g.rsplit("/", 1)[-1] if g else ""


def _location() -> str:
    return (os.getenv("NOTEBOOKLM_LOCATION", "global") or "global").strip()


def configured() -> bool:
    """True only when a real NotebookLM Enterprise integration can actually authenticate: enabled +
    a service account + a project number. A plain AIza API key does NOT satisfy this (Enterprise
    requires OAuth2)."""
    return enabled() and bool(_sa_info()) and bool(_project_number())


# ---------------------------------------------------------------------------
# Auth — service-account JWT -> OAuth2 access token
# ---------------------------------------------------------------------------
def _access_token() -> Optional[str]:
    info = _sa_info()
    if not info or not info.get("private_key") or not info.get("client_email"):
        return None
    now = int(time.time())
    if _token_cache["tok"] and _token_cache["exp"] - 60 > now:
        return _token_cache["tok"]
    try:
        import jwt  # pyjwt; RS256 signing uses the `cryptography` package (already a dependency)
    except Exception:  # noqa: BLE001
        log.warning("notebooklm_enterprise: pyjwt unavailable — cannot mint SA token")
        return None
    token_uri = info.get("token_uri", _OAUTH_TOKEN_URL)
    claims = {"iss": info["client_email"], "scope": _SCOPE, "aud": token_uri, "iat": now, "exp": now + 3600}
    try:
        assertion = jwt.encode(claims, info["private_key"], algorithm="RS256")
    except Exception as e:  # noqa: BLE001
        log.warning("notebooklm_enterprise: JWT signing failed: %s", e)
        return None
    res = _http.request_json(
        "POST", token_uri, headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        timeout=30, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict) or not res.data.get("access_token"):
        log.warning("notebooklm_enterprise: token exchange failed: %s", res.error if res.failed else "no token")
        return None
    _token_cache["tok"] = res.data["access_token"]
    _token_cache["exp"] = now + int(res.data.get("expires_in", 3600))
    return _token_cache["tok"]


def _host() -> str:
    return (os.getenv("NOTEBOOKLM_BASE_URL", "") or "").strip() \
        or f"https://{_location()}-discoveryengine.googleapis.com/v1alpha"


def _parent() -> str:
    return f"projects/{_project_number()}/locations/{_location()}"


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# API calls (documented shapes)
# ---------------------------------------------------------------------------
def create_notebook(title: str, tok: str) -> Optional[str]:
    res = _http.request_json("POST", f"{_host()}/{_parent()}/notebooks",
                             headers=_hdr(tok), json={"title": (title or "Notebook")[:200]},
                             timeout=60, max_retries=1, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        log.warning("notebooklm_enterprise: create_notebook failed: %s", res.error)
        return None
    name = res.data.get("name") or res.data.get("notebookId") or ""
    return name.rsplit("/", 1)[-1] if name else None


def add_text_source(notebook_id: str, source_name: str, content: str, tok: str) -> bool:
    res = _http.request_json(
        "POST", f"{_host()}/{_parent()}/notebooks/{notebook_id}/sources:batchCreate", headers=_hdr(tok),
        json={"userContents": [{"textContent": {"sourceName": (source_name or "source")[:120],
                                                "content": (content or "")[:200000]}}]},
        timeout=90, max_retries=1, guard_redirects=True)
    if res.failed:
        log.warning("notebooklm_enterprise: add_text_source failed: %s", res.error)
    return not res.failed


def create_audio_overview(notebook_id: str, tok: str, *, focus: str = "", lang: str = "en") -> Optional[dict]:
    body: dict = {"languageCode": lang}
    if focus:
        body["episodeFocus"] = focus[:2000]
    res = _http.request_json("POST", f"{_host()}/{_parent()}/notebooks/{notebook_id}/audioOverviews",
                             headers=_hdr(tok), json=body, timeout=90, max_retries=1, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        log.warning("notebooklm_enterprise: create_audio_overview failed: %s", res.error)
        return None
    return res.data


def _retrieve_audio(notebook_id: str, tok: str) -> Optional[dict]:
    """Fetch the finished audio overview (audio URI + transcript). The public API docs do not yet
    document a retrieval/download endpoint, so this tries the natural GET and returns whatever comes
    back; it's finalized/verified once a real service account is available to test against. Returns
    {audio_url, transcript} or None."""
    res = _http.request_json("GET", f"{_host()}/{_parent()}/notebooks/{notebook_id}/audioOverviews",
                             headers=_hdr(tok), timeout=30, max_retries=1, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return None
    items = res.data.get("audioOverviews") or ([res.data] if res.data.get("name") else [])
    ov = items[0] if items else {}
    uri = ov.get("audioUri") or ov.get("uri") or ((ov.get("audio") or {}).get("uri"))
    return {"audio_url": uri, "transcript": ov.get("transcript")} if (uri or ov.get("transcript")) else None


# ---------------------------------------------------------------------------
# Orchestrated audio-overview (the interface rich_media_generator uses when live)
# ---------------------------------------------------------------------------
def synthesise_audio(sources: list[dict], title: str, *, style: str = "podcast",
                     focus: str = "", poll_secs: int = 120) -> Optional[dict]:
    """Full flow: create a notebook -> add the assembled sources -> create an audio overview ->
    (attempt to) retrieve it. Returns {audio_url, transcript, notebook_id, status,
    generator:'notebooklm_enterprise'} on success, or None to signal the caller to fall back to the
    in-house LLM. Fully fail-closed. NOTE: until the retrieval step is verified live, this may return
    a result WITHOUT an audio_url/transcript (just a status), in which case rich_media_generator
    treats it as 'not usable yet' and falls back to the LLM script — so nothing empty is ever stored."""
    if not configured():
        return None
    tok = _access_token()
    if not tok:
        log.warning("notebooklm_enterprise: no access token (check the service account) — falling back")
        return None
    nb = create_notebook(title, tok)
    if not nb:
        return None
    for s in (sources or [])[:20]:
        add_text_source(nb, s.get("title", "source"), s.get("text", ""), tok)
    ov = create_audio_overview(nb, tok, focus=focus or title)
    if ov is None:
        return None
    status = ov.get("status") or ov.get("audioOverviewStatus") or ""
    # Best-effort poll for completion, then retrieve. Bounded so a stuck overview can't hang the job.
    audio = None
    deadline = time.monotonic() + max(0, poll_secs)
    while time.monotonic() < deadline:
        audio = _retrieve_audio(nb, tok)
        if audio and audio.get("audio_url"):
            break
        time.sleep(15)
    return {"audio_url": (audio or {}).get("audio_url"),
            "transcript": (audio or {}).get("transcript"),
            "notebook_id": nb, "status": status, "generator": "notebooklm_enterprise"}
