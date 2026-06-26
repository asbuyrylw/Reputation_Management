"""Connections vault API (Integrations Phase 1).

Business-scoped CRUD over `platform_connections` + the UNPREFIXED OAuth callback. The callback
intentionally does NOT depend on `authorize_business`: its tenancy comes solely from the
single-use, HMAC-signed `oauth_states` row. Secrets are never returned (redacted DTOs only) and
never accepted into a GET; the connect POSTs are bearer-authed from the SPA so they pass CSRF.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, get_current_user, require_business_editor

try:
    from ... import scheduler as _scheduler
    from ...connections import vault as _vault, oauth as _oauth, status as _cstatus
    from ...connections.providers import wordpress as _wp
    from ... import notifications as _notify
except ImportError:  # pragma: no cover
    import scheduler as _scheduler  # type: ignore
    from connections import vault as _vault, oauth as _oauth, status as _cstatus  # type: ignore
    from connections.providers import wordpress as _wp  # type: ignore
    import notifications as _notify  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["connections"])
callback_router = APIRouter(tags=["connections"])

# kinds connectable via a direct (non-OAuth) credential POST.
_DIRECT_KINDS = {"wordpress_org", "ayrshare_profile"}
_OAUTH_KINDS = {"google_business_profile", "google_search_console", "google_analytics"}

# Per-platform OAuth-callback config (label, GBP-allowlist state, connect notification). Keeps the
# callback generic so a new Google read-only product (GSC) doesn't inherit GBP-specific fields.
_CALLBACK_META = {
    "google_business_profile": {
        "label": "Google Business Profile", "gbp_access": "pending",
        "notify_title": "Connected Google Business Profile",
        "notify_body": ("Your Google Business Profile is connected. Review replies need Google's "
                        "approval before they can post; we'll start importing reviews now."),
    },
    "google_search_console": {
        "label": "Google Search Console", "gbp_access": None,
        "notify_title": "Connected Google Search Console",
        "notify_body": ("Search Console is connected. Pick which property to import, then we'll "
                        "start pulling your real clicks, impressions and ranking positions."),
    },
    "google_analytics": {
        "label": "Google Analytics", "gbp_access": None,
        "notify_title": "Connected Google Analytics",
        "notify_body": ("Google Analytics is connected. Pick which property to import, then we'll "
                        "start pulling your sessions, conversions and behavior data."),
    },
}
_MAX_PENDING_STATES = 12  # per-business flood cap on state minting


class ConnectRequest(BaseModel):
    kind: str
    # WordPress app-password
    site_url: Optional[str] = None
    wp_user: Optional[str] = None
    app_password: Optional[str] = None
    # Ayrshare profile-key (Phase 5)
    profile_key: Optional[str] = None
    display_name: Optional[str] = None
    label: Optional[str] = None


def _schedule_connection_jobs(business_id: int, kind: str) -> None:
    """Recurring upkeep for a freshly-connected account (no-op-safe if already scheduled)."""
    try:
        _scheduler.upsert_schedule(business_id, "refresh_connection_token", 12)
        if kind == "google_business_profile":
            _scheduler.upsert_schedule(business_id, "ingest_gbp_reviews", 24)
            _scheduler.upsert_schedule(business_id, "gbp_reconcile", 24)
    except Exception:  # noqa: BLE001 -- scheduling is best-effort, never block a connect
        pass


@router.get("/connections")
def list_connections(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    try:
        from ...crypto import configured as _vault_ready
    except ImportError:  # pragma: no cover
        from crypto import configured as _vault_ready  # type: ignore
    return {"vault_ready": bool(_vault_ready()),
            "connections": _vault.list_connections(business_id)}


@router.post("/connections/{kind}/authorize")
def authorize(kind: str, business_id: int = Depends(require_business_editor),
              user: dict = Depends(get_current_user)):
    if kind not in _OAUTH_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{kind} does not use OAuth")
    # flood control: prune expired states, then cap pending mints per business.
    try:
        _oauth.prune_expired()
        from ...db import db
    except ImportError:  # pragma: no cover
        from db import db  # type: ignore
    with db() as c:
        pending = c.execute("SELECT COUNT(*) n FROM oauth_states WHERE business_id=%s",
                            (business_id,)).fetchone()["n"]
    if pending >= _MAX_PENDING_STATES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many pending connection attempts")
    try:
        out = _oauth.build_state(business_id, kind, created_by=user["id"])
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return out


@router.post("/connections")
def connect_direct(body: ConnectRequest, business_id: int = Depends(require_business_editor),
                   user: dict = Depends(get_current_user)):
    if body.kind not in _DIRECT_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported direct-connect kind: {body.kind}")
    try:
        from ...crypto import configured as _vault_ready
    except ImportError:  # pragma: no cover
        from crypto import configured as _vault_ready  # type: ignore
    if not _vault_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Connections are not configured on this server (TOKEN_ENC_KEY unset).")

    if body.kind == "wordpress_org":
        if not (body.site_url and body.wp_user and body.app_password):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "site_url, wp_user and app_password are required")
        v = _wp.verify_app_password(body.site_url, body.wp_user, body.app_password)
        if not v.get("ok"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, v.get("error") or "verification failed")
        conn_id = _vault.upsert_connection(
            business_id, "wordpress_org", token_type="app_password",
            access_token=body.app_password, account_ref=v["account_ref"],
            meta=v["meta"], label=body.label or v["meta"].get("site_url"),
            connected_by=user["id"], status="active")
    elif body.kind == "ayrshare_profile":
        if not body.profile_key:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "profile_key is required")
        conn_id = _vault.upsert_connection(
            business_id, "ayrshare_profile", token_type="ayrshare_profile",
            access_token=body.profile_key, account_ref=(body.display_name or "ayrshare"),
            profile_ref=body.display_name, meta={"display_name": body.display_name},
            label=body.label or body.display_name, connected_by=user["id"], status="active")
    else:  # pragma: no cover -- guarded above
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported kind")

    _schedule_connection_jobs(business_id, body.kind)
    return {"ok": True, "connection_id": conn_id}


@router.post("/connections/{conn_id}/test")
def test_connection(conn_id: int, business_id: int = Depends(require_business_editor)):
    return _cstatus.test_connection(conn_id, business_id)


@router.delete("/connections/{conn_id}")
def disconnect(conn_id: int, business_id: int = Depends(require_business_editor)):
    out = _vault.disconnect(conn_id, business_id)
    if not out.get("ok"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    return out


@callback_router.get("/connections/{kind}/callback")
def oauth_callback(kind: str, code: Optional[str] = None, state: Optional[str] = None,
                   error: Optional[str] = None):
    """OAuth redirect target. Unauthenticated: tenancy comes from the single-use oauth_states row."""
    if error:
        return RedirectResponse(_oauth.callback_landing(kind, ok=False, reason=error), status_code=302)
    if not (code and state):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing code/state")
    try:
        st = _oauth.verify_state(state)
    except ValueError as e:
        # Absent / expired / tampered state is a security failure -> 403 (not a redirect).
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    business_id, platform = st["business_id"], st["platform"]
    if platform != kind:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "platform mismatch")
    try:
        tok = _oauth.exchange(platform, code, st["redirect_uri"])
    except Exception as e:  # noqa: BLE001
        return RedirectResponse(_oauth.callback_landing(kind, ok=False, reason="exchange_failed"),
                                status_code=302)
    if not tok.get("ok"):
        return RedirectResponse(_oauth.callback_landing(kind, ok=False, reason="exchange_failed"),
                                status_code=302)
    meta = _CALLBACK_META.get(platform, {"label": platform, "gbp_access": None,
                                          "notify_title": f"Connected {platform}", "notify_body": ""})
    _vault.upsert_connection(
        business_id, platform, token_type="google_oauth",
        access_token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        expires_at=tok.get("expires_at"), scopes=tok.get("scopes"),
        gbp_access=meta["gbp_access"], status="active",
        label=meta["label"], connected_by=st.get("created_by"))
    # GBP schedules its ingest at callback; GSC schedules ingest at PROPERTY-SELECT (we don't yet
    # know which property), so only the token-refresh upkeep is scheduled here for GSC.
    _schedule_connection_jobs(business_id, platform)
    try:
        _notify.notify(business_id, "connection_connected", meta["notify_title"], meta["notify_body"],
                       severity="info", dedup_key=f"conn-ok:{platform}:{business_id}")
    except Exception:  # noqa: BLE001
        pass
    return RedirectResponse(_oauth.callback_landing(kind, ok=True), status_code=302)


# ---------------------------------------------------------------------------
# Google Search Console: property selection (GSC ingest is scheduled here, not at callback)
# ---------------------------------------------------------------------------
class GscPropertyRequest(BaseModel):
    property: str


@router.get("/connections/{conn_id}/gsc/sites")
def gsc_sites(conn_id: int, business_id: int = Depends(require_business_editor)):
    """List the verified GSC properties this connection can access (for the property picker)."""
    creds = _vault.credentials(conn_id, business_id)
    if not creds or creds.get("kind") != "google_search_console":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GSC connection not found")
    try:
        from ...connections.providers import google_search_console as _gsc
    except ImportError:  # pragma: no cover
        from connections.providers import google_search_console as _gsc  # type: ignore
    return {"sites": _gsc.list_sites(creds.get("access_token") or "")}


@router.put("/connections/{conn_id}/gsc/property")
def set_gsc_property(conn_id: int, body: GscPropertyRequest,
                     business_id: int = Depends(require_business_editor),
                     user: dict = Depends(get_current_user)):
    """Store the chosen property on the connection + schedule the daily GSC ingest, then kick a
    first ingest so data starts flowing immediately."""
    creds = _vault.credentials(conn_id, business_id)
    if not creds or creds.get("kind") != "google_search_console":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GSC connection not found")
    # Update the EXISTING callback-created connection in place (account_ref is part of the dedup
    # key, so a re-upsert would orphan a duplicate row).
    _vault.set_account_and_meta(conn_id, business_id, account_ref=body.property,
                                meta_updates={"gsc_property": body.property})
    try:
        _scheduler.upsert_schedule(business_id, "ingest_gsc", 24)
        from .. import jobs as _jobs
        _jobs.enqueue(business_id, "ingest_gsc", requested_by=user["id"])
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "property": body.property}


@router.get("/connections/{conn_id}/ga/properties")
def ga_properties(conn_id: int, business_id: int = Depends(require_business_editor)):
    """List the GA4 properties this connection can access (for the property picker)."""
    creds = _vault.credentials(conn_id, business_id)
    if not creds or creds.get("kind") != "google_analytics":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GA connection not found")
    try:
        from ...connections.providers import google_analytics as _ga
    except ImportError:  # pragma: no cover
        from connections.providers import google_analytics as _ga  # type: ignore
    return {"properties": _ga.list_properties(creds.get("access_token") or "")}


@router.put("/connections/{conn_id}/ga/property")
def set_ga_property(conn_id: int, body: GscPropertyRequest,
                    business_id: int = Depends(require_business_editor),
                    user: dict = Depends(get_current_user)):
    """Store the chosen GA4 property + schedule daily GA ingest + kick a first ingest."""
    creds = _vault.credentials(conn_id, business_id)
    if not creds or creds.get("kind") != "google_analytics":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GA connection not found")
    _vault.set_account_and_meta(conn_id, business_id, account_ref=body.property,
                                meta_updates={"ga_property": body.property})
    try:
        _scheduler.upsert_schedule(business_id, "ingest_ga", 24)
        from .. import jobs as _jobs
        _jobs.enqueue(business_id, "ingest_ga", requested_by=user["id"])
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "property": body.property}
