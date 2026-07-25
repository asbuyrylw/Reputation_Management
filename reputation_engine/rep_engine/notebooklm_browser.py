"""
NotebookLM browser automation — download the just-created audio (Studio has no download API)
=============================================================================================
Google's NotebookLM Enterprise API can GENERATE an Audio Overview but exposes NO method to DOWNLOAD
the finished file (verified: the AudioOverview resource has only create+delete). The only retrieval
path is the NotebookLM Studio web UI. This module drives that UI with Playwright to fetch ONLY the
just-created audio for the business's persistent notebook, and hands the bytes to the platform's
media-ingestion path so the podcast plays in-app instead of behind an "open & download" link.

DORMANT + FAIL-CLOSED by design. `configured()` is False (returns {skipped}) unless the owner has
provisioned all of:
  NOTEBOOKLM_BROWSER_READY=1        -- set only AFTER the selectors below are validated live against
                                      the current NotebookLM DOM (this is a fast-moving Labs product;
                                      the selectors WILL need periodic re-tuning -> this is the gate)
  NOTEBOOKLM_BROWSER_STATE          -- path to (or the connections-vault key of) a storageState JSON
                                      captured from ONE human Google login on the DEDICATED, ISOLATED
                                      account that owns the Team notebook (never the owner's primary
                                      account; automating NotebookLM login violates Google ToS, so a
                                      throwaway account contains the blast radius). NEVER script login.
  NOTEBOOKLM_BROWSER_CDP (optional) -- ws:// CDP endpoint of a dedicated remote-browser host
                                      (Browserbase/browserless, stable/residential IP). Preferred over
                                      launching Chromium locally: Railway's datacenter IP is flagged by
                                      Google and Chromium would OOM the worker. If unset AND a local
                                      Playwright+Chromium is available, a local headed/persistent
                                      context is used (owner's machine only).

The FLOW (implemented with role/text locators; validate live before flipping BROWSER_READY):
  1. open a context from the captured storageState (never log in)
  2. goto https://notebooklm.google.com/notebook/{notebook_id}
  3. DETECT a login/consent wall -> abort with {skipped, login_required:true} (alert the owner; do NOT
     loop into a lockout)
  4. snapshot the set of existing Studio audio cards (ids/titles) BEFORE triggering
  5. (optional) trigger a fresh Audio Overview — usually the API already started it, so default is to
     just wait for the newest card to reach a completed/player state
  6. identify the target = the completed audio card NOT present in the before-snapshot (never "newest
     file on disk"); bind page.expect_download() to THAT card's overflow(⋮) -> Download
  7. read the download bytes, assert non-zero + audio mime
  8. return {ok, file_bytes, mime, filename, source_artifact_id}

Idempotency + safety live in the CALLER (a singleton job keyed by (business, notebook) + ingestion
keyed on source_artifact_id). This module is a pure fetch.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("notebooklm_browser")

_NOTEBOOK_URL = "https://notebooklm.google.com/notebook/{id}"
_LOGIN_HOSTS = ("accounts.google.com", "signin")


def ready() -> bool:
    """True only when the owner has validated the selectors live (see the module header)."""
    return (os.getenv("NOTEBOOKLM_BROWSER_READY", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _state_path() -> str:
    return (os.getenv("NOTEBOOKLM_BROWSER_STATE", "") or "").strip()


def _cdp() -> str:
    return (os.getenv("NOTEBOOKLM_BROWSER_CDP", "") or "").strip()


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def configured() -> bool:
    """Dormant-safe gate. Requires the live-validated flag, a captured session, and either a remote CDP
    endpoint or a local Playwright install. Any missing piece -> the fetch returns {skipped}."""
    if not ready():
        return False
    if not _state_path():
        return False
    return bool(_cdp()) or _playwright_available()


def _load_state() -> Optional[dict]:
    """Load the storageState. Prefers the connections vault (encrypted) when the value is a vault key;
    else treats it as a filesystem path to the JSON. Returns the parsed dict or None."""
    ref = _state_path()
    if not ref:
        return None
    # vault key form: "vault:<key>"
    if ref.startswith("vault:"):
        try:
            from . import connections_vault as _vault  # type: ignore
            import json as _json
            raw = _vault.get_secret(ref.split(":", 1)[1])
            return _json.loads(raw) if raw else None
        except Exception as e:  # noqa: BLE001
            log.warning("notebooklm_browser: could not load session from vault: %s", e)
            return None
    try:
        import json as _json
        with open(ref, "r", encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception as e:  # noqa: BLE001
        log.warning("notebooklm_browser: could not read storageState file %s: %s", ref, e)
        return None


def fetch_latest_audio(notebook_id: str, *, source_artifact_id: Optional[str] = None,
                       timeout_ms: int = 240_000) -> dict:
    """Fetch the just-created Audio Overview file from the persistent notebook's Studio UI.

    Returns one of:
      {ok:True, file_bytes, mime, filename, source_artifact_id}
      {skipped:True, reason}                         -- not configured / dormant
      {ok:False, error, login_required?}             -- a real failure (login wall, no completed card)

    DORMANT until configured() (see header). This is the pure fetch; the caller ingests + is idempotent
    on source_artifact_id and serializes per (business, notebook) so two fetches never race."""
    if not notebook_id:
        return {"ok": False, "error": "no notebook_id"}
    if not configured():
        return {"skipped": True,
                "reason": "notebooklm browser automation not configured (set NOTEBOOKLM_BROWSER_READY=1 "
                          "+ NOTEBOOKLM_BROWSER_STATE after validating the Studio selectors live)"}
    state = _load_state()
    if not state:
        return {"skipped": True, "reason": "no captured NotebookLM session (NOTEBOOKLM_BROWSER_STATE)"}
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as _PWTimeout  # type: ignore
    except Exception:  # noqa: BLE001
        return {"skipped": True, "reason": "playwright not installed on this host"}

    url = _NOTEBOOK_URL.format(id=notebook_id)
    try:
        with sync_playwright() as pw:
            cdp = _cdp()
            browser = pw.chromium.connect_over_cdp(cdp) if cdp else pw.chromium.launch(headless=True)
            ctx = browser.new_context(storage_state=state, accept_downloads=True)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # (3) login / consent wall -> abort loudly, don't loop into a lockout
            if any(h in (page.url or "") for h in _LOGIN_HOSTS):
                ctx.close(); browser.close()
                return {"ok": False, "login_required": True,
                        "error": "NotebookLM redirected to Google login -- the captured session expired; "
                                 "re-capture NOTEBOOKLM_BROWSER_STATE from a fresh human login."}
            # (4) snapshot existing audio cards BEFORE, (6) pick the new completed one, (6/7) download it.
            # NOTE: the selectors below are role/text-based (more stable than CSS) but MUST be validated
            # against the live NotebookLM DOM before NOTEBOOKLM_BROWSER_READY is set. They are the single
            # thing to re-tune when Google ships a Studio UI change.
            before = _audio_card_keys(page)
            target = _wait_for_new_completed_card(page, before, timeout_ms, _PWTimeout)
            if not target:
                ctx.close(); browser.close()
                return {"ok": False, "error": "no newly-completed audio card appeared within the timeout"}
            with page.expect_download(timeout=120_000) as dl_info:
                _click_card_download(page, target)
            dl = dl_info.value
            path = dl.path()
            data = open(path, "rb").read() if path else b""
            ctx.close(); browser.close()
            if not data:
                return {"ok": False, "error": "download produced no bytes"}
            fname = dl.suggested_filename or "podcast.mp3"
            mime = "audio/mpeg" if fname.lower().endswith((".mp3", ".mpeg")) else "audio/wav" \
                if fname.lower().endswith(".wav") else "application/octet-stream"
            return {"ok": True, "file_bytes": data, "mime": mime, "filename": fname,
                    "source_artifact_id": source_artifact_id or target}
    except Exception as e:  # noqa: BLE001 -- fetch must never raise into the job runner
        log.warning("notebooklm_browser: fetch failed: %s", e)
        return {"ok": False, "error": str(e)[:300]}


# --- Studio DOM helpers (role/text locators; LIVE-VALIDATE before enabling) ------------------------
def _audio_card_keys(page) -> set:
    """Best-effort set of identifiers for the audio cards currently in the Studio panel. Uses visible
    text (title + timestamp) as the key since NotebookLM cards lack stable ids in the DOM."""
    try:
        cards = page.get_by_role("listitem").all()
        keys = set()
        for c in cards:
            try:
                t = (c.inner_text(timeout=1500) or "").strip()
                if "audio" in t.lower() or "overview" in t.lower():
                    keys.add(t[:120])
            except Exception:  # noqa: BLE001
                continue
        return keys
    except Exception:  # noqa: BLE001
        return set()


def _wait_for_new_completed_card(page, before: set, timeout_ms: int, _PWTimeout):
    """Poll until a card appears that is NOT in `before` and reads as completed (has a player / download
    control). Returns its key, or None on timeout."""
    import time as _t
    deadline = timeout_ms / 1000.0
    waited = 0.0
    while waited < deadline:
        now = _audio_card_keys(page)
        fresh = [k for k in now if k not in before]
        for k in fresh:
            # a completed card exposes a play/download affordance; keep it simple + resilient
            if "min" in k.lower() or ":" in k:   # a duration stamp implies a finished render
                return k
        page.wait_for_timeout(5000)
        waited += 5.0
    # fallback: if exactly one new card exists, take it even without a duration match
    now = _audio_card_keys(page)
    fresh = [k for k in now if k not in before]
    return fresh[0] if len(fresh) == 1 else None


def _click_card_download(page, card_key: str) -> None:
    """Open the target card's overflow (⋮) menu and click Download. Text/role-based so a class change
    doesn't break it."""
    card = page.get_by_text(card_key[:60], exact=False).first
    card.scroll_into_view_if_needed(timeout=5000)
    # the overflow menu is usually a button with an aria-label like "More" within the card row
    try:
        card.get_by_role("button", name=lambda n: n and ("more" in n.lower() or "option" in n.lower())).first.click(timeout=5000)
    except Exception:  # noqa: BLE001
        card.click(timeout=5000)
    page.get_by_role("menuitem", name=lambda n: n and "download" in n.lower()).first.click(timeout=5000)
