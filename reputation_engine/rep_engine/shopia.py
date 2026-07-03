"""
Shopia / Axelerate API client — a SECONDARY, on-demand quality-check layer (NOT a primary generator)
====================================================================================================
Our own pipeline stays the primary content engine (grounded + compliance-screened + reputation-tuned).
Shopia is used only as a *second opinion* / quality check when asked: AI-and-plagiarism detection,
content audit, internal-link optimization, topic clustering, SEO report, content repurposing, image,
etc. Its own article generation is deliberately NOT used as our writer (it reads generic + AI-flagged).

How the API works (reverse-engineered against the live API; it's a Bubble.io app):
  * Base:  https://app.shopia.ai/api/1.1
  * Auth:  the account API key goes in the request BODY -- `api_key` for most endpoints, `token`
           for the workflow runner. (NOT a Bearer header for the public workflow endpoints.)
  * The credit-list features are USER-BUILT AUTOMATIONS: build each one in Shopia's no-code builder,
    then trigger it here by its workflow ref via `run_workflow_api_v2` (async -> returns a job id you
    poll with `get_api_job`). There are also a few direct "writer" endpoints (generate_text_auth, ...).

Config (dormant-safe -- every call is a no-op {skipped} without these):
  * SHOPIA_API_KEY            -- the account API key (required to do anything).
  * SHOPIA_WF_<KIND>          -- the workflow ref for a given check kind, e.g.
       SHOPIA_WF_AI_DETECTION, SHOPIA_WF_CONTENT_AUDIT, SHOPIA_WF_INTERNAL_LINKS,
       SHOPIA_WF_TOPIC_CLUSTER, SHOPIA_WF_SEO_REPORT, SHOPIA_WF_REPURPOSE, SHOPIA_WF_IMAGE.
    A check with no ref configured is skipped (so we never call a check the owner hasn't built).

Host-pinned to app.shopia.ai via the SSRF-guarded http client. Keyless/dormant-safe throughout.
"""
from __future__ import annotations

import json
import logging
import os
import time

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

log = logging.getLogger("shopia")

_BASE = "https://app.shopia.ai/api/1.1"
_POLL_EVERY = 3          # seconds between get_api_job polls
_DEFAULT_DEADLINE = 120  # seconds max wall-clock for one automation run


def _key() -> str:
    return (os.getenv("SHOPIA_API_KEY") or "").strip()


def configured() -> bool:
    return bool(_key())


def workflow_ref(kind: str) -> str:
    """The configured workflow ref for a check kind (SHOPIA_WF_<KIND>), or '' if none."""
    return (os.getenv(f"SHOPIA_WF_{kind.upper().strip()}") or "").strip()


def _wf(endpoint: str, params: dict, *, auth_param: str = "api_key", timeout: int = 60):
    """POST to a Shopia workflow endpoint with the key in the body. Returns the parsed dict/list, or
    None on failure / not-configured. Never raises."""
    if not configured():
        return None
    body = {auth_param: _key(), **params}
    res = _http.request_json(
        "POST", f"{_BASE}/wf/{endpoint}",
        headers={"Content-Type": "application/json"},
        json=body, timeout=timeout, max_retries=2, guard_redirects=True,
    )
    if res.failed or not isinstance(res.data, (dict, list)):
        if res.failed:
            log.warning("shopia %s failed: %s", endpoint, res.error)
        return None
    # Bubble wraps successful workflow output under {"status":"success","response":{...}}
    if isinstance(res.data, dict) and "response" in res.data:
        return res.data["response"]
    return res.data


def status() -> dict:
    """Lightweight config status for the UI: is the key set, and which checks have a workflow ref."""
    kinds = ["ai_detection", "content_audit", "internal_links", "topic_cluster",
             "seo_report", "repurpose", "image"]
    return {"configured": configured(),
            "checks": {k: bool(workflow_ref(k)) for k in kinds}}


def run_automation(ref: str, inputs: dict, *, deadline: int = _DEFAULT_DEADLINE) -> dict:
    """Trigger a Shopia automation by workflow ref and return its outputs. Uses the async runner
    (run_workflow_api_v2 -> job id -> poll get_api_job). Best-effort + dormant-safe: returns
    {"skipped"|"error"|"ok", ...} and never raises. NOTE: the exact `inputs` field names + the
    output shape depend on how the automation was built in Shopia; finalize on first live test."""
    if not configured():
        return {"skipped": True, "reason": "no SHOPIA_API_KEY"}
    if not (ref or "").strip():
        return {"skipped": True, "reason": "no workflow ref configured"}
    kick = _wf("run_workflow_api_v2",
               {"token": _key(), "workflow": ref, "inputs": json.dumps(inputs), "get_job_id": "yes"},
               auth_param="token")
    if not isinstance(kick, dict):
        return {"error": "could not start the automation"}
    # Some configs return the outputs immediately; async ones return a job id to poll.
    if kick.get("outputs") is not None and not kick.get("job_id") and not kick.get("api_job"):
        return {"ok": True, "outputs": kick.get("outputs")}
    job_id = kick.get("job_id") or kick.get("api_job") or kick.get("id")
    if not job_id:
        return {"ok": True, "raw": kick}  # nothing to poll; hand back whatever came
    waited = 0
    while waited < deadline:
        time.sleep(_POLL_EVERY)
        waited += _POLL_EVERY
        job = _wf("get_api_job", {"api_job": job_id})
        if not isinstance(job, dict):
            continue
        st = str(job.get("status") or job.get("state") or "").lower()
        if st in ("done", "success", "completed", "complete", "finished"):
            return {"ok": True, "outputs": job.get("outputs") or job.get("result") or job.get("output")}
        if st in ("error", "failed", "cancelled"):
            return {"error": job.get("error") or "automation failed", "raw": job}
    return {"error": "timed out waiting for the automation", "job_id": job_id}


def check(kind: str, *, text: str = "", url: str = "", extra: dict | None = None,
          deadline: int = _DEFAULT_DEADLINE) -> dict:
    """Run a configured secondary check (kind -> SHOPIA_WF_<KIND>). Dormant-safe: {skipped} when the
    key or the kind's workflow ref isn't set. `inputs` defaults to {"input": text|url}; pass `extra`
    to add/override fields to match how the automation was built."""
    ref = workflow_ref(kind)
    if not configured() or not ref:
        return {"skipped": True, "reason": f"shopia not configured for '{kind}'"}
    inputs = {"input": text or url}
    if extra:
        inputs.update(extra)
    return run_automation(ref, inputs, deadline=deadline)


def verify() -> bool:
    """Cheap connectivity + auth check (no automation run, no run-credits): a metadata endpoint that
    accepts a body api_key. True if the key is accepted."""
    if not configured():
        return False
    res = _http.request_json(
        "POST", f"{_BASE}/wf/search_get_admin_templates",
        headers={"Content-Type": "application/json"},
        json={"api_key": _key(), "return_limit": 1}, timeout=20, max_retries=1, guard_redirects=True,
    )
    return not res.failed
