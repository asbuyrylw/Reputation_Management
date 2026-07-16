"""Rich-media API (podcast / slide deck / infographic / explainer / long-form).

rich_media_generator.py writes to rich_media_drafts but had no HTTP surface, so the generated media
was unreachable from the console. This router exposes it: list (gallery), detail (viewer), and the
human approve/reject gate -- mirroring visuals_router. Rich media is text (body) + optional podcast
audio_url, so there is no binary to serve; the body/transcript/audio_url ride in the JSON.
Dormant-safe: empty list until something is generated; `configured` reports whether the NotebookLM
audio path is available (text always works via the in-house LLM fallback).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import authorize_business, get_current_user, require_business_editor
from ..settings import api_settings
from .. import jobs as _jobs

try:
    from ... import rich_media_generator as _rmg
except ImportError:  # pragma: no cover
    import rich_media_generator as _rmg  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["rich-media"])


@router.get("/rich-media-drafts")
def list_rich_media(asset_type: Optional[str] = None, status_filter: Optional[str] = None,
                    limit: int = 100, business_id: int = Depends(authorize_business)):
    """The rich-media gallery feed: podcast / slide_deck / infographic / explainer_video /
    research_brief / deep_article / blog_series / newsletter drafts, newest first. Lightweight rows
    (flags for which viewer to use) + `configured` so the UI can show a 'connect for audio' hint."""
    return {"configured": _rmg.configured(),
            "drafts": _rmg.api_list(business_id, asset_type=asset_type, status=status_filter, limit=limit)}


@router.get("/rich-media-drafts/{draft_id}")
def get_rich_media(draft_id: int, business_id: int = Depends(authorize_business)):
    """Full draft incl. body (markdown) + transcript + audio_url, for the viewer modal."""
    d = _rmg.api_get(business_id, draft_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    return d


class StatusUpdate(BaseModel):
    reason: Optional[str] = None


@router.post("/rich-media-drafts/{draft_id}/approve")
def approve_rich_media(draft_id: int, business_id: int = Depends(require_business_editor),
                       user: dict = Depends(get_current_user)):
    if not _rmg.set_status(business_id, draft_id, "approved", reviewer=(user or {}).get("email")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    return {"id": draft_id, "status": "approved"}


@router.post("/rich-media-drafts/{draft_id}/reject")
def reject_rich_media(draft_id: int, body: StatusUpdate = StatusUpdate(),
                      business_id: int = Depends(require_business_editor),
                      user: dict = Depends(get_current_user)):
    if not _rmg.set_status(business_id, draft_id, "rejected", reviewer=(user or {}).get("email")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    return {"id": draft_id, "status": "rejected"}


class RenderVideoRequest(BaseModel):
    provider: Optional[str] = None   # 'heygen' (default, verbatim) | 'veo' (generative clip/B-roll)


@router.post("/rich-media-drafts/{draft_id}/render-video", status_code=202)
def render_rich_media_video(draft_id: int, background: BackgroundTasks,
                            body: RenderVideoRequest = RenderVideoRequest(),
                            business_id: int = Depends(require_business_editor),
                            user: dict = Depends(get_current_user)):
    """Render a REAL MP4 for an explainer_video / video_script draft. Renderer = body.provider
    ('heygen' default — the avatar speaks the vetted script VERBATIM, brand-safe; or 'veo' — Google's
    generative video, best for a short cinematic clip/B-roll, narration is generated not verbatim).
    Explicit action (cost per render). Enqueued off the request path. 409 if the draft isn't a video
    script; the job returns {skipped} until the chosen renderer's keys are configured."""
    d = _rmg.api_get(business_id, draft_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    if d.get("asset_type") not in ("explainer_video", "video_script"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"draft is a {d.get('asset_type')}, not a video script")
    if not _jobs.rate_ok(business_id, "render_video"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You're rendering videos too often — give it a little while.")
    job_id, active = _jobs.enqueue(business_id, "render_video",
                                   args={"draft_id": draft_id, "provider": body.provider},
                                   requested_by=(user or {}).get("id"))
    if job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"a video render is already running (#{active})")
    if api_settings().job_worker == "inline":
        background.add_task(_jobs.run_job, job_id)
    return JSONResponse(status_code=202, content={"job_id": job_id, "job_type": "render_video",
                                                  "status": "queued", "draft_id": draft_id})
