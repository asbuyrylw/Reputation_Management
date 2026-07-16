"""
YouTube OAuth provider + Data API v3 upload client (video publishing)
=====================================================================
Publishes a rendered explainer MP4 (+ SRT captions + rich description) to the owner's YouTube channel.
YouTube is the single most-cited domain in Google AI Overviews — read through its CAPTIONS/transcript
— so this is the last, highest-leverage step of the video citability loop.

Shares the Google OAuth client (GOOGLE_OAUTH_CLIENT_ID/SECRET) with the other Google providers but is
a SEPARATE module so the `youtube.upload` scope never entangles with GBP/GSC scopes. OAuth mirrors
google_search_console.py. The upload uses the resumable protocol (needs the response Location header +
a raw byte PUT), which http.request_json doesn't surface, so it uses `requests` directly against the
fixed googleapis.com host (no SSRF surface — the host is not user-controlled).

Dormant-safe: `configured()` is False without the Google OAuth client; every call returns a structured
{ok:False,...} rather than raising.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

try:
    from ... import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

log = logging.getLogger("connections.youtube")

AUTH_HOST = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
UPLOAD_VIDEOS = "https://www.googleapis.com/upload/youtube/v3/videos"
UPLOAD_CAPTIONS = "https://www.googleapis.com/upload/youtube/v3/captions"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
# youtube.upload = insert videos/captions; youtube.readonly = channel liveness probe.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def authorize_url(state: str, redirect_uri: str) -> str:
    q = {
        "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_HOST}?{urlencode(q)}"


def _expires_at(expires_in) -> Optional[datetime]:
    try:
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def exchange_code(code: str, redirect_uri: str) -> dict:
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={"code": code, "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
              "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "error": res.error or "token exchange failed"}
    d = res.data
    return {"ok": True, "access_token": d.get("access_token"),
            "refresh_token": d.get("refresh_token"),
            "expires_at": _expires_at(d.get("expires_in")),
            "scopes": (d.get("scope") or "").split() or SCOPES}


def refresh(creds: dict) -> dict:
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    rt = creds.get("refresh_token")
    if not rt:
        return {"ok": False, "error": "no refresh token stored"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={"refresh_token": rt, "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
              "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
              "grant_type": "refresh_token"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20, max_retries=2, guard_redirects=True)
    if res.ok and isinstance(res.data, dict):
        return {"ok": True, "access_token": res.data.get("access_token"),
                "refresh_token": res.data.get("refresh_token"),
                "expires_at": _expires_at(res.data.get("expires_in"))}
    transient = res.status is None or (res.status or 0) >= 500
    return {"ok": False, "transient": transient, "error": res.error or "refresh failed"}


def revoke(token: Optional[str]) -> None:
    if not token:
        return
    try:
        _http.request_json("POST", REVOKE_URL, data={"token": token},
                           headers={"Content-Type": "application/x-www-form-urlencoded"},
                           timeout=10, max_retries=1, guard_redirects=True, parse_json=False)
    except Exception:  # noqa: BLE001
        pass


def my_channel(access_token: str) -> dict:
    """Liveness probe + channel identity for the connection card. {ok, title, channel_id}."""
    res = _http.request_json("GET", f"{CHANNELS_URL}?part=snippet&mine=true",
                             headers={"Authorization": f"Bearer {access_token}"},
                             timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "status": res.status, "error": res.error}
    items = res.data.get("items") or []
    if not items:
        return {"ok": False, "error": "no YouTube channel on this Google account"}
    snip = items[0].get("snippet") or {}
    return {"ok": True, "channel_id": items[0].get("id"), "title": snip.get("title")}


# ---------------------------------------------------------------------------
# Upload (Data API v3, resumable) -- the actual publish
# ---------------------------------------------------------------------------
def upload_video(access_token: str, video_bytes: bytes, *, title: str, description: str = "",
                 tags: Optional[list] = None, privacy: str = "unlisted",
                 category_id: str = "22") -> dict:
    """Resumable upload of an MP4 to the owner's channel. privacy: 'unlisted' (default, safe — human
    flips to public), 'private', or 'public'. Returns {ok, video_id, url} or {ok:False, status, error,
    auth_failed}. category 22 = People & Blogs. Never raises."""
    if not video_bytes:
        return {"ok": False, "error": "no video bytes to upload"}
    import requests
    meta = {"snippet": {"title": (title or "Video")[:100], "description": (description or "")[:5000],
                        "tags": [str(t)[:30] for t in (tags or [])][:15], "categoryId": category_id},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    try:
        init = requests.post(
            f"{UPLOAD_VIDEOS}?uploadType=resumable&part=snippet,status",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(video_bytes))},
            data=json.dumps(meta), timeout=30, allow_redirects=False)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"upload init failed: {e}"}
    if init.status_code in (401, 403):
        return {"ok": False, "status": init.status_code, "error": init.text[:300], "auth_failed": True}
    if init.status_code not in (200, 201):
        return {"ok": False, "status": init.status_code, "error": init.text[:300]}
    session_url = init.headers.get("Location")
    if not session_url:
        return {"ok": False, "error": "YouTube did not return an upload session URL"}
    try:
        up = requests.put(session_url, headers={"Content-Type": "video/mp4"},
                          data=video_bytes, timeout=600)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"upload PUT failed: {e}"}
    if up.status_code not in (200, 201):
        return {"ok": False, "status": up.status_code, "error": up.text[:300]}
    try:
        vid = up.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "upload succeeded but response was unparseable"}
    video_id = vid.get("id")
    if not video_id:
        return {"ok": False, "error": f"no video id in response: {str(vid)[:200]}"}
    return {"ok": True, "video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}


def insert_captions(access_token: str, video_id: str, srt_text: str, *, language: str = "en",
                    name: str = "English") -> dict:
    """Upload an SRT caption track (multipart/related). Best-effort — if it fails, YouTube still
    auto-captions the clear avatar narration. Returns {ok} or {ok:False, status, error}."""
    if not (video_id and srt_text.strip()):
        return {"ok": False, "error": "missing video_id or captions"}
    import requests
    meta = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
    boundary = "===============rep_caption_boundary=="
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta)}\r\n"
        f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n"
        f"{srt_text}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    try:
        r = requests.post(
            f"{UPLOAD_CAPTIONS}?part=snippet&uploadType=multipart",
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": f"multipart/related; boundary={boundary}"},
            data=body, timeout=60)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"caption upload failed: {e}"}
    if r.status_code not in (200, 201):
        return {"ok": False, "status": r.status_code, "error": r.text[:300]}
    return {"ok": True}
