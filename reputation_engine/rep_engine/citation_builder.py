"""
Reputation Crowding-Out Engine -- computer-use citation/directory-listing builder
==================================================================================
`local_seo_gaps` can recommend a missing directory citation (Apple Maps, Bing Places, Nextdoor
Business, ...) but nothing acts on it today -- it's pure toil for the owner. This module drives a
headless browser through a directory's own claim/update flow, screenshot-by-screenshot, under
Google's Gemini Computer Use API, so the owner reviews the result instead of doing the clicking.

SAFETY POSTURE (non-negotiable, mirrors the compliance gates elsewhere in this codebase):
  - The run is ALWAYS triggered by an explicit human action -- never a background/scheduled job.
  - The loop stops and waits for an explicit human confirm before any submit-like action (claim,
    publish, save, pay, confirm) -- see `_is_submit_like`. It never commits anything to a public
    directory on its own.
  - The directory account password is NEVER sent to the model. Login is done deterministically
    with Playwright's own field-matching (`_login`); only the model's SCREENSHOTS + navigation
    actions go to Gemini, never the credential text.
  - Dormant by default: `configured()` is False without both a computer-use key and the Playwright
    Chromium binary, and every entry point returns {skipped} rather than raising.

KNOWN LIMITATION (MVP): the live Playwright browser/page for an in-progress run is held in an
in-process dict (`_LIVE_RUNS`), not serialized -- `confirm_and_continue` must hit the same server
process that started the run. Fine for a single-instance API/worker deploy (this one); would need
a redesign (e.g. a dedicated long-lived runner process) to scale beyond that.

PROTOCOL NOTE: live-verified against the real API on 2026-07-06 (model gemini-2.5-computer-use-
preview-10-2025) against harmless public test fixtures -- example.com (click-through), the
Selenium project's own web-form.html (type + submit, confirm-gate), and the-internet.herokuapp.com
/login (the deterministic `_login` path) -- no real directory/login was touched. Findings that
changed the code:
  - The model's first turn is a bootstrapping `open_web_browser` call regardless of screen content
    (not universal -- seen most but not all runs); handled as a no-op in `_execute_action`.
  - Real actions only follow once the conversation includes a proper `functionResponse` turn
    acknowledging the PRIOR action -- a stateless "screenshot + task text" retry with no
    conversation history makes the model repeat `open_web_browser` forever. `_loop` carries a
    real, growing `contents` array (function-call / function-response turns), not just the latest
    screenshot.
  - Coordinate actions (`click_at`, `type_text_at`) carry NO semantic label of their own -- the
    model's stated intent ("click the Submit button") arrives as a separate `text` part in the
    SAME response. `_call_model` captures it into `action["reasoning"]`; without this,
    `_is_submit_like` had nothing to match against and the confirm-gate silently never fired.
    VERIFIED LIVE: a real Submit click on the Selenium test form was correctly held for
    confirmation (reasoning said "click the Submit button"), and only actually fired -- the
    browser genuinely navigated to the form's success page -- after the explicit confirm call.
  - The action-name set isn't fully documented (preview API): `type_text_at` and `wait_N_seconds`-
    style names showed up in live responses alongside the documented `click_at`/`navigate`/etc.
    `_execute_action` handles both; any FUTURE undocumented name still degrades to a safe no-op.
  - Not yet clean: the model doesn't always signal `done` cleanly after a confirmed action (a
    follow-up call can come back unparseable), ending the run as `failed` even though the action
    itself succeeded. Fails closed (no further clicks), just an imprecise final status -- a
    reasonable improvement, not a safety issue.
This is still a preview API and may drift; re-verify against the live docs if it starts erroring.

Config (all optional; unset -> dormant):
    COMPUTER_USE_PROVIDER=gemini
    COMPUTER_USE_MODEL=gemini-2.5-computer-use-preview-10-2025
    COMPUTER_USE_API_KEY=      # falls back to GEMINI_API_KEY
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
from typing import Optional

try:
    from .db import db
    from . import http as _http
    from . import crypto as _crypto
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import http as _http  # type: ignore
    import crypto as _crypto  # type: ignore

from psycopg.types.json import Json

log = logging.getLogger("citation_builder")

_OUTPUT_DIR = os.getenv("REP_OUTPUT_DIR", "output")
_GEMINI_BASE = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
_MAX_STEPS = 20

# Directories with a real listing-management flow but no API -- the entire reason this exists.
_DIRECTORIES = {
    "apple_maps": {"label": "Apple Maps Connect", "url": "https://mapsconnect.apple.com/"},
    "bing_places": {"label": "Bing Places for Business", "url": "https://www.bingplaces.com/"},
    "nextdoor_business": {"label": "Nextdoor Business", "url": "https://business.nextdoor.com/"},
}

_SUBMIT_WORDS = re.compile(
    r"\b(submit|confirm|claim|publish|save changes|pay|checkout|place order|finish|complete|send)\b",
    re.I,
)

# In-process only (see module docstring's KNOWN LIMITATION).
_LIVE_RUNS: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _cu_key() -> str:
    explicit = os.getenv("COMPUTER_USE_API_KEY", "").strip()
    return explicit or os.getenv("GEMINI_API_KEY", "").strip()


def _cu_model() -> str:
    return (os.getenv("COMPUTER_USE_MODEL") or "gemini-2.5-computer-use-preview-10-2025").strip()


def _chromium_installed() -> bool:
    """True only if a Playwright Chromium browser binary is actually on disk. The pip package being
    importable is NOT enough -- `playwright install chromium` must have downloaded the browser, or a
    run fails at launch. Filesystem check only (no driver spawn -> safe in an async request)."""
    import glob
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    roots = [base] if base else [
        os.path.expanduser("~/.cache/ms-playwright"),                 # Linux (Railway)
        os.path.expanduser("~/Library/Caches/ms-playwright"),         # macOS
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"),  # Windows
    ]
    return any(r and glob.glob(os.path.join(r, "chromium-*")) for r in roots)


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:  # noqa: BLE001 -- package not installed
        return False
    # The docstring/promise is "gated on the Chromium binary" -- honor it, so configured() doesn't
    # report LIVE when only the pip package is present and a run would fail at browser launch.
    return _chromium_installed()


def configured() -> bool:
    return bool(_cu_key()) and _playwright_available()


def directories() -> dict:
    return dict(_DIRECTORIES)


# ---------------------------------------------------------------------------
# Directory credentials (Fernet-encrypted, same at-rest posture as the connections vault)
# ---------------------------------------------------------------------------
def set_directory_credentials(business_id: int, directory_key: str, username: str, password: str) -> dict:
    if directory_key not in _DIRECTORIES:
        return {"ok": False, "error": f"unknown directory '{directory_key}'"}
    enc = _crypto.encrypt(password)
    with db() as conn:
        conn.execute(
            "INSERT INTO directory_credentials (business_id, directory_key, username, password_enc) "
            "VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (business_id, directory_key) DO UPDATE SET "
            "username=EXCLUDED.username, password_enc=EXCLUDED.password_enc, updated_at=now()",
            (business_id, directory_key, username, enc))
        conn.commit()
    return {"ok": True}


def has_directory_credentials(business_id: int, directory_key: str) -> bool:
    with db() as conn:
        r = conn.execute(
            "SELECT 1 FROM directory_credentials WHERE business_id=%s AND directory_key=%s",
            (business_id, directory_key)).fetchone()
    return bool(r)


def _get_directory_credentials(business_id: int, directory_key: str) -> Optional[dict]:
    with db() as conn:
        r = conn.execute(
            "SELECT username, password_enc FROM directory_credentials WHERE business_id=%s AND directory_key=%s",
            (business_id, directory_key)).fetchone()
    if not r:
        return None
    return {"username": r["username"], "password": _crypto.decrypt(r["password_enc"])}


# ---------------------------------------------------------------------------
# Run persistence
# ---------------------------------------------------------------------------
def _create_run(business_id: int, directory_key: str, work_order_id: Optional[int],
                created_by: Optional[int]) -> int:
    with db() as conn:
        row = conn.execute(
            "INSERT INTO citation_runs (business_id, work_order_id, directory_key, status, created_by) "
            "VALUES (%s,%s,%s,'running',%s) RETURNING id",
            (business_id, work_order_id, directory_key, created_by)).fetchone()
        conn.commit()
    return int(row["id"])


def _append_step(run_id: int, step: dict) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE citation_runs SET steps = steps || %s::jsonb, updated_at=now() WHERE id=%s",
            (Json([step]), run_id))
        conn.commit()


def _set_status(run_id: int, status: str, *, pending_action: Optional[dict] = None,
                error: Optional[str] = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE citation_runs SET status=%s, pending_action=%s, error=%s, updated_at=now() WHERE id=%s",
            (status, Json(pending_action) if pending_action else None, error, run_id))
        conn.commit()


def get_run(run_id: int, business_id: int) -> Optional[dict]:
    with db() as conn:
        r = conn.execute(
            "SELECT id, business_id, work_order_id, directory_key, status, steps, pending_action, "
            "error, created_at, updated_at FROM citation_runs WHERE id=%s AND business_id=%s",
            (run_id, business_id)).fetchone()
    return dict(r) if r else None


def list_runs(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, work_order_id, directory_key, status, error, created_at, updated_at "
            "FROM citation_runs WHERE business_id=%s ORDER BY id DESC", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def _save_step_image(business_id: int, run_id: int, step_idx: int, raw: bytes) -> str:
    d = os.path.join(_OUTPUT_DIR, "citations", str(business_id), str(run_id))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"step_{step_idx}_{secrets.token_hex(4)}.png")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def screenshot_path(run_id: int, business_id: int, step_idx: int) -> Optional[str]:
    """The stored screenshot path for one step, tenancy-scoped. None if not found/not this business."""
    run = get_run(run_id, business_id)
    if not run:
        return None
    steps = run.get("steps") or []
    for s in steps:
        if s.get("step") == step_idx:
            return s.get("screenshot")
    return None


# ---------------------------------------------------------------------------
# Deterministic login (credentials NEVER go to the model)
# ---------------------------------------------------------------------------
_USER_SELECTORS = ['input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]',
                   'input[type="text"][name*="user" i]', 'input[id*="user" i]']
_PASS_SELECTORS = ['input[type="password"]']
_SUBMIT_SELECTORS = ['button[type="submit"]', 'input[type="submit"]']


def _login(page, creds: dict) -> bool:
    """Best-effort: fill the first matching username/password fields and submit. Returns whether a
    password field was found at all (not whether login actually succeeded -- callers verify via
    the next screenshot the same way the computer-use loop verifies everything else)."""
    user_field = None
    for sel in _USER_SELECTORS:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            user_field = loc
            break
    pass_field = None
    for sel in _PASS_SELECTORS:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            pass_field = loc
            break
    if not pass_field:
        return False
    if user_field:
        user_field.fill(creds["username"])
    pass_field.fill(creds["password"])
    for sel in _SUBMIT_SELECTORS:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click()
            break
    else:
        pass_field.press("Enter")
    page.wait_for_timeout(2000)
    return True


# ---------------------------------------------------------------------------
# Gemini Computer Use loop
# ---------------------------------------------------------------------------
def _task_prompt(directory: dict, biz: dict) -> str:
    facts = {k: v for k, v in biz.items() if v}
    return (
        f"You are updating/claiming the business listing for this business on {directory['label']}. "
        f"You are already logged in. Navigate this site's own UI to reach the listing claim or edit "
        f"form, and fill in the business's name, address, phone, website, and category using ONLY "
        f"these facts (do not invent anything not listed): {json.dumps(facts, default=str)}. "
        f"Stop as soon as you reach a final submit/confirm/publish/save/pay button -- do NOT click it. "
        f"Say you are done once the form is filled and ready for a human to submit."
    )


def _is_submit_like(action: dict) -> bool:
    text = " ".join(str(action.get(k, "")) for k in ("label", "reasoning", "target_label", "text"))
    return bool(_SUBMIT_WORDS.search(text))


def _denorm(x: int, y: int, vw: int, vh: int) -> tuple[float, float]:
    """Gemini Computer Use returns coordinates on a 0-999 normalized scale."""
    return (x / 999.0) * vw, (y / 999.0) * vh


def _execute_action(page, action: dict) -> None:
    """Action-name coverage is empirically grown, not spec-complete (preview API): live testing
    against real pages surfaced `type_text_at` (click-then-type, not in the initially-documented
    action set) and `wait_5_seconds`-style names (a number embedded in the name, not a separate
    arg) alongside the documented `click_at`/`type_text`/`navigate`/etc. -- both handled below via
    substring/regex matching rather than an exact-name allowlist, so the NEXT undocumented variant
    degrades to a harmless no-op (next screenshot shows nothing changed; loop ends at _MAX_STEPS)
    instead of silently mis-firing."""
    kind = (action.get("type") or "").lower()
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]
    if kind == "open_web_browser":
        pass  # the model's mandatory bootstrap call -- a browser page is already open
    elif kind in ("click", "click_at"):
        px, py = _denorm(int(action.get("x", 0)), int(action.get("y", 0)), vw, vh)
        page.mouse.click(px, py)
    elif kind == "type_text_at":
        px, py = _denorm(int(action.get("x", 0)), int(action.get("y", 0)), vw, vh)
        page.mouse.click(px, py)
        page.keyboard.type(str(action.get("text", "")))
    elif kind == "type_text":
        page.keyboard.type(str(action.get("text", "")))
    elif kind == "key_combination":
        page.keyboard.press("+".join(action.get("keys") or []))
    elif kind == "scroll_document":
        dy = 600 if (action.get("direction") or "down") == "down" else -600
        page.mouse.wheel(0, dy)
    elif kind == "navigate":
        page.goto(action.get("url") or "", timeout=30000)
    elif kind == "go_back":
        page.go_back()
    elif kind == "go_forward":
        page.go_forward()
    elif kind == "wait" or re.match(r"^wait(_\d+_?sec(onds?)?)?$", kind):
        m = re.search(r"(\d+)", kind)
        page.wait_for_timeout((int(m.group(1)) if m else 1.5) * 1000)
    # unknown action types are no-ops -- the next screenshot will show nothing changed and the
    # loop will naturally end at _MAX_STEPS rather than crash.


def _call_model(contents: list[dict]) -> tuple[Optional[dict], Optional[dict]]:
    """One Gemini Computer Use turn over the FULL running conversation (contents). Live-verified:
    without the real function-call/function-response history the model just repeats its
    bootstrapping `open_web_browser` call forever -- see module docstring's PROTOCOL NOTE.
    Returns (parsed_action, raw_function_call) so the caller can append the exact model turn back
    onto `contents`; (None, None) if the call fails or the response can't be parsed (a hard stop,
    never a guess)."""
    key = _cu_key()
    hdr = {"Content-Type": "application/json", "x-goog-api-key": key}
    body = {"contents": contents, "tools": [{"computer_use": {"environment": "ENVIRONMENT_BROWSER"}}]}
    res = _http.request_json("POST", f"{_GEMINI_BASE}/models/{_cu_model()}:generateContent",
                             headers=hdr, json=body, timeout=60, max_retries=1, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        log.warning("computer-use call failed: %s", res.error if res.failed else "malformed response")
        return None, None
    try:
        cand = (res.data.get("candidates") or [{}])[0]
        parts_out = ((cand.get("content") or {}).get("parts") or [])
        # The model's reasoning arrives as a separate `text` part alongside the functionCall in
        # the SAME response (live-verified) -- click_at/type_text_at carry no semantic label of
        # their own (just coordinates), so without this, `_is_submit_like` would have nothing to
        # check and could never catch a click the model itself describes as "submit"/"confirm".
        reasoning = "".join(p.get("text", "") for p in parts_out if p.get("text"))
        for p in parts_out:
            fc = p.get("functionCall")
            if fc:
                name = str(fc.get("name") or "")
                args = fc.get("args") or {}
                if name.lower() in ("done", "task_complete", "finished"):
                    return {"type": "done", "note": args.get("note") or reasoning[:300]}, fc
                return {"type": name, **args, "reasoning": reasoning}, fc
        # No function call -- the model likely responded with plain text (e.g. "I'm done").
        if re.search(r"\bdone\b|\bfinished\b|\bready\b", reasoning, re.I):
            return {"type": "done", "note": reasoning[:300]}, None
        return None, None
    except Exception as e:  # noqa: BLE001 -- preview API response shape may drift
        log.warning("computer-use response parse failed: %s", e)
        return None, None


def _seed_contents(task_prompt: str) -> list[dict]:
    return [{"role": "user", "parts": [{"text": task_prompt}]}]


def _attach_screenshot(contents: list[dict], shot: bytes, *, first: bool,
                       last_action_name: Optional[str], url: str) -> None:
    """First step: the screenshot rides along on the seed text turn. Every later step: Gemini
    expects a `functionResponse` acknowledging the PRIOR action before it will move on (see
    PROTOCOL NOTE) -- the new screenshot travels alongside that acknowledgement."""
    b64 = base64.b64encode(shot).decode("ascii")
    if first:
        contents[-1]["parts"].append({"inline_data": {"mime_type": "image/png", "data": b64}})
    else:
        contents.append({"role": "user", "parts": [
            {"functionResponse": {"name": last_action_name or "", "response": {"url": url}}},
            {"inline_data": {"mime_type": "image/png", "data": b64}},
        ]})


def _fetch_business_facts(business_id: int) -> dict:
    """NAP (name/address/phone) isn't a first-class column yet -- it lives in `profile` (JSONB,
    populated at onboarding) if the operator filled it in. `start_run` refuses to run without an
    address/phone present, rather than letting the model fill a public directory with blanks."""
    with db() as conn:
        r = conn.execute(
            "SELECT name, domain, geo, industry, services, profile FROM businesses WHERE id=%s",
            (business_id,)).fetchone()
    if not r:
        return {}
    row = dict(r)
    profile = row.pop("profile", None) or {}
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except Exception:  # noqa: BLE001
            profile = {}
    facts = {**row, **(profile if isinstance(profile, dict) else {})}
    return {k: v for k, v in facts.items() if v}


def _loop(run_id: int, business_id: int) -> dict:
    """Drives the conversation forward from `live["next_step"]`, using `live["contents"]` as the
    running transcript (see PROTOCOL NOTE) -- so resuming after a confirm continues the SAME
    conversation rather than starting a fresh, memory-less one."""
    live = _LIVE_RUNS[run_id]
    page, contents = live["page"], live["contents"]
    for step_idx in range(live.get("next_step", 0), _MAX_STEPS):
        shot = page.screenshot(type="png")
        path = _save_step_image(business_id, run_id, step_idx, shot)
        _attach_screenshot(contents, shot, first=(step_idx == 0),
                          last_action_name=live.get("last_action_name"), url=page.url)
        action, fc = _call_model(contents)
        if action is None:
            _append_step(run_id, {"step": step_idx, "screenshot": path, "action": None,
                                  "note": "computer-use call failed or was unparseable"})
            _set_status(run_id, "failed", error="computer-use call failed or was unparseable")
            _close_run(run_id)
            return {"ok": False, "run_id": run_id, "status": "failed"}
        if action.get("type") == "done":
            _append_step(run_id, {"step": step_idx, "screenshot": path, "action": action})
            _set_status(run_id, "done")
            _close_run(run_id)
            return {"ok": True, "run_id": run_id, "status": "done"}
        contents.append({"role": "model", "parts": [{"functionCall": fc}]})
        live["last_action_name"] = fc.get("name") if fc else action.get("type")
        if _is_submit_like(action):
            _append_step(run_id, {"step": step_idx, "screenshot": path, "action": action,
                                  "note": "awaiting human confirmation before this submit-like action"})
            live["next_step"] = step_idx + 1
            _set_status(run_id, "awaiting_confirmation", pending_action=action)
            return {"ok": True, "run_id": run_id, "status": "awaiting_confirmation",
                    "step": step_idx, "proposed_action": action}
        _execute_action(page, action)
        _append_step(run_id, {"step": step_idx, "screenshot": path, "action": action})
    _set_status(run_id, "failed", error=f"reached the {_MAX_STEPS}-step safety cap without finishing")
    _close_run(run_id)
    return {"ok": False, "run_id": run_id, "status": "failed"}


def _close_run(run_id: int) -> None:
    live = _LIVE_RUNS.pop(run_id, None)
    if not live:
        return
    try:
        live["context"].close()
        live["browser"].close()
        live["pw"].stop()
    except Exception:  # noqa: BLE001 -- best-effort cleanup
        pass


def start_run(business_id: int, directory_key: str, *, work_order_id: Optional[int] = None,
             created_by: Optional[int] = None) -> dict:
    """Kick off a supervised citation-builder run. ALWAYS call this from an explicit human action
    (a button click), never a scheduled/background job -- see module docstring."""
    if not configured():
        return {"skipped": True,
                "reason": "citation builder not configured (need COMPUTER_USE_API_KEY/GEMINI_API_KEY "
                          "and `playwright install chromium`)"}
    if directory_key not in _DIRECTORIES:
        return {"ok": False, "error": f"unknown directory '{directory_key}'"}
    creds = _get_directory_credentials(business_id, directory_key)
    if not creds:
        return {"ok": False, "error": "no saved login for this directory -- add one first"}
    biz = _fetch_business_facts(business_id)
    if not (biz.get("address") and biz.get("phone")):
        return {"ok": False,
                "error": "business profile is missing an address/phone -- add them before "
                         "submitting to a public directory (this run refuses to fill blanks)"}
    run_id = _create_run(business_id, directory_key, work_order_id, created_by)
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.goto(_DIRECTORIES[directory_key]["url"], timeout=60000)
        _login(page, creds)  # credentials touch Playwright only, never the model
        task_prompt = _task_prompt(_DIRECTORIES[directory_key], biz)
        _LIVE_RUNS[run_id] = {"pw": pw, "browser": browser, "context": context, "page": page,
                              "contents": _seed_contents(task_prompt), "last_action_name": None,
                              "next_step": 0}
        return _loop(run_id, business_id)
    except Exception as e:  # noqa: BLE001 -- surface as a failed run, not a 500
        log.warning("citation run %s failed: %s", run_id, e)
        _set_status(run_id, "failed", error=str(e))
        _close_run(run_id)
        return {"ok": False, "run_id": run_id, "error": str(e)}


def confirm_and_continue(run_id: int, business_id: int) -> dict:
    """Execute exactly the one held submit-like action the operator just approved, then keep
    going under the same stop-before-the-next-submit rule. Requires the run's browser session to
    still be live in THIS process (see module docstring's KNOWN LIMITATION)."""
    run = get_run(run_id, business_id)
    if not run or run.get("status") != "awaiting_confirmation":
        return {"ok": False, "error": "no action awaiting confirmation for this run"}
    live = _LIVE_RUNS.get(run_id)
    if not live:
        _set_status(run_id, "failed", error="run session expired (server restarted) -- start a new run")
        return {"ok": False, "error": "run session no longer live -- start a new run"}
    action = run.get("pending_action") or {}
    _execute_action(live["page"], action)
    return _loop(run_id, business_id)


def cancel_run(run_id: int, business_id: int) -> dict:
    run = get_run(run_id, business_id)
    if not run:
        return {"ok": False, "error": "run not found"}
    _close_run(run_id)
    _set_status(run_id, "cancelled")
    return {"ok": True}
