"""
Zernio social provider -- profile + per-platform OAuth account linking (Integrations)
=====================================================================================
Zernio (zernio.com) is the social-publishing layer (replacing Ayrshare). Model:
  1. create a PROFILE per business (a container for that client's connected accounts),
  2. the owner authorizes each social account via a Zernio-hosted OAuth redirect
     (GET /connect/{platform}?profileId=...) -> the owner approves on the platform,
  3. we read the connected accounts back with GET /accounts?profileId=... (each carries an
     accountId we post with),
  4. publish via POST /posts with platforms:[{platform, accountId}].

Auth is an ACCOUNT-LEVEL key (env ZERNIA_API_KEY, `sk_...`), not per-connection -- the per-client
thing is the profile_id + its connected accountIds (non-secret), stored on the connection's meta.
All I/O is SSRF-guarded + host-pinned to zernio.com.
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote

try:
    from ... import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore


def base() -> str:
    return (os.getenv("ZERNIA_BASE_URL") or os.getenv("ZERNIO_BASE_URL") or "https://zernio.com/api/v1").rstrip("/")


def _key() -> str:
    # The env var the operator set is ZERNIA_API_KEY; accept ZERNIO_API_KEY too (brand spelling).
    return (os.getenv("ZERNIA_API_KEY") or os.getenv("ZERNIO_API_KEY") or "").strip()


def configured() -> bool:
    return bool(_key())


def _headers(json: bool = True) -> dict:
    h = {"Authorization": f"Bearer {_key()}"}
    if json:
        h["Content-Type"] = "application/json"
    return h


def create_profile(name: str, description: str = "") -> dict:
    """POST /profiles -> {ok, profile_id, raw}. The container for a client's social accounts.

    IDEMPOTENT: Zernio rejects a duplicate name with 409 'profile_name_conflict' and returns the
    existing profile's id. That happens whenever a profile was created on Zernio but our stored
    connection was lost/revoked -- so ADOPT the existing profile instead of failing, otherwise
    'Set up social' is permanently stuck (create keeps 409-ing, connect says 'set up first')."""
    if not configured():
        return {"ok": False, "error": "ZERNIA_API_KEY not set"}
    res = _http.request_json("POST", f"{base()}/profiles", headers=_headers(),
                             json={"name": name, "description": description},
                             timeout=20, max_retries=2, guard_redirects=True)
    if getattr(res, "status", None) == 409 and (res.text or ""):
        try:
            import json as _json
            body = _json.loads(res.text)
            existing = (((body.get("details") or {}).get("existingProfileId"))
                        or body.get("existingProfileId"))
            if existing:
                return {"ok": True, "profile_id": str(existing), "name": name, "adopted": True}
        except Exception:  # noqa: BLE001 -- fall through to the generic error below
            pass
        # 409 without a parseable existingProfileId -> reuse the one we can find by name.
        found = _find_profile_by_name(name)
        if found:
            return {"ok": True, "profile_id": found, "name": name, "adopted": True}
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "error": res.error or "create profile failed"}
    prof = res.data.get("profile") or res.data
    pid = prof.get("_id") or prof.get("id") or res.data.get("profileId")
    return {"ok": bool(pid), "profile_id": pid, "name": prof.get("name") or name}


def _find_profile_by_name(name: str) -> Optional[str]:
    """List Zernio profiles and return the id of the one matching `name` (case-insensitive), or None.
    Fallback for a 409 conflict whose body didn't carry existingProfileId."""
    if not configured():
        return None
    res = _http.request_json("GET", f"{base()}/profiles", headers=_headers(json=False),
                             timeout=15, max_retries=1, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return None
    profs = res.data.get("profiles") or res.data.get("data") or []
    want = (name or "").strip().lower()
    for p in profs if isinstance(profs, list) else []:
        if str(p.get("name", "")).strip().lower() == want:
            return str(p.get("_id") or p.get("id") or "")
    return None


def connect_url(platform: str, profile_id: str) -> dict:
    """GET /connect/{platform}?profileId= -> {ok, authUrl}. The owner is sent here to authorize the
    account on the platform; Zernio handles the OAuth callback, then we sync via list_accounts."""
    if not configured():
        return {"ok": False, "error": "ZERNIA_API_KEY not set"}
    res = _http.request_json("GET", f"{base()}/connect/{quote(platform)}",
                             headers=_headers(json=False), params={"profileId": profile_id},
                             timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "error": res.error or "connect url failed"}
    url = res.data.get("authUrl") or (res.data.get("authUrl") if isinstance(res.data.get("authUrl"), str) else None) \
        or res.data.get("url")
    if isinstance(res.data.get("authUrl"), dict):
        url = res.data["authUrl"].get("url") or url
    return {"ok": bool(url), "authUrl": url}


def list_accounts(profile_id: str) -> list[dict]:
    """GET /accounts?profileId= -> the profile's connected accounts (platform + accountId + handle)."""
    if not configured():
        return []
    res = _http.request_json("GET", f"{base()}/accounts", headers=_headers(json=False),
                             params={"profileId": profile_id}, timeout=20, max_retries=2,
                             guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return []
    out = []
    for a in res.data.get("accounts") or []:
        # tenant-isolation belt-and-suspenders: keep only accounts belonging to this profile
        pid = a.get("profileId")
        pid_id = pid.get("_id") if isinstance(pid, dict) else pid
        if pid_id and str(pid_id) != str(profile_id):
            continue
        out.append({"account_id": a.get("_id") or a.get("id"), "platform": a.get("platform"),
                    "username": a.get("username"), "display_name": a.get("displayName"),
                    "profile_url": a.get("profileUrl"), "is_active": a.get("isActive", True)})
    return [a for a in out if a["account_id"] and a["platform"]]


def verify() -> bool:
    """Cheap liveness probe for status._probe_zernia: list profiles with the key."""
    if not configured():
        return False
    res = _http.request_json("GET", f"{base()}/profiles", headers=_headers(json=False),
                             timeout=15, max_retries=1, guard_redirects=True)
    return res.ok
