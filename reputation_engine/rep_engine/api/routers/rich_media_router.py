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

try:
    from ... import content_generator as _cg
except ImportError:  # pragma: no cover
    import content_generator as _cg  # type: ignore

# Text-like rich-media that is really an editable DRAFT (belongs in the Drafts flow), vs. produced
# media (rendered video/podcast audio) that belongs in Media. The FE uses `is_editable_draft` to route
# a piece to the right section and show the editor.
_EDITABLE_ASSET_TYPES = {"deep_article", "research_brief", "slide_deck", "infographic",
                         "explainer_video", "video_script", "blog_series", "newsletter", "report"}


def _annotate(d: dict) -> dict:
    """Attach fix_reasons ('what needs fixed') + is_editable_draft so the console can surface exactly
    why a piece is held and let the owner edit/fix it in the Drafts flow."""
    if not isinstance(d, dict):
        return d
    d["fix_reasons"] = _cg.fix_reasons(d)
    d["is_editable_draft"] = (d.get("asset_type") in _EDITABLE_ASSET_TYPES)
    return d


@router.get("/rich-media-drafts")
def list_rich_media(asset_type: Optional[str] = None, status_filter: Optional[str] = None,
                    limit: int = 100, business_id: int = Depends(authorize_business)):
    """The rich-media feed: podcast / slide_deck / infographic / explainer_video / research_brief /
    deep_article / … drafts, newest first. Each row carries `fix_reasons` (what needs fixed) and
    `is_editable_draft` (text-like drafts belong in the Drafts flow; rendered media belongs in Media)."""
    return {"configured": _rmg.configured(),
            "drafts": [_annotate(r) for r in
                       _rmg.api_list(business_id, asset_type=asset_type, status=status_filter, limit=limit)]}


@router.get("/rich-media-drafts/{draft_id}")
def get_rich_media(draft_id: int, business_id: int = Depends(authorize_business)):
    """Full draft incl. body (markdown) + transcript + audio_url + fix_reasons, for the editor/viewer."""
    d = _rmg.api_get(business_id, draft_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    return _annotate(d)


class RichMediaEdit(BaseModel):
    body: Optional[str] = None
    transcript: Optional[str] = None


@router.patch("/rich-media-drafts/{draft_id}")
def edit_rich_media(draft_id: int, payload: RichMediaEdit,
                    business_id: int = Depends(require_business_editor),
                    user: dict = Depends(get_current_user)):
    """Edit a rich-media draft's body/transcript and RE-GRADE it (geo_score + truncation + compliance
    + status), so an owner can fix a held/needs_fix brief or script and move it toward production —
    the same edit→fix→approve flow content drafts have. 404 if not found."""
    if payload.body is None and payload.transcript is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "provide body and/or transcript")
    d = _rmg.update_draft(business_id, draft_id, body=payload.body, transcript=payload.transcript,
                          reviewer=(user or {}).get("email"))
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    return _annotate(d)


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


@router.delete("/rich-media-drafts/{draft_id}")
def delete_rich_media(draft_id: int, business_id: int = Depends(require_business_editor),
                      user: dict = Depends(get_current_user)):
    """Permanently delete a rich-media draft (owner action). Cascades to a linked rendered video so
    the delete doesn't orphan the MP4. 404 if the draft doesn't exist / isn't this business's."""
    if not _rmg.delete_draft(business_id, draft_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    return {"id": draft_id, "deleted": True}


class RenderVideoRequest(BaseModel):
    provider: Optional[str] = None   # 'heygen' (default, verbatim) | 'veo' (generative clip/B-roll)
    # 'Send back with changes': an owner can edit the script and pick a different presenter/voice/
    # orientation/background, then re-render. All optional -> a bare call re-renders as-is.
    script: Optional[str] = None      # edited narration script; saved to the draft before rendering
    avatar_id: Optional[str] = None   # HeyGen avatar (presenter); None -> the configured default
    voice_id: Optional[str] = None    # HeyGen voice; None -> the configured default
    aspect: Optional[str] = None      # '16:9' (landscape) | '9:16' (portrait / reels)
    background: Optional[str] = None  # a hex color ('#0b1020') or an image URL


@router.post("/rich-media-drafts/{draft_id}/render-video", status_code=202)
def render_rich_media_video(draft_id: int, background: BackgroundTasks,
                            body: RenderVideoRequest = RenderVideoRequest(),
                            business_id: int = Depends(require_business_editor),
                            user: dict = Depends(get_current_user)):
    """Render a REAL MP4 for an explainer_video / video_script draft. Renderer = body.provider
    ('heygen' default — the avatar speaks the vetted script VERBATIM, brand-safe; or 'veo' — Google's
    generative video, best for a short cinematic clip/B-roll, narration is generated not verbatim).
    'Send back with changes': an edited `script` is saved to the draft (re-graded) first, and
    avatar_id/voice_id/aspect/background override the presenter/voice/orientation/background for this
    render. Explicit action (cost per render). Enqueued off the request path. 409 if the draft isn't a
    video script; the job returns {skipped} until the chosen renderer's keys are configured."""
    d = _rmg.api_get(business_id, draft_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rich-media draft not found")
    if d.get("asset_type") not in ("explainer_video", "video_script"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"draft is a {d.get('asset_type')}, not a video script")
    if not _jobs.rate_ok(business_id, "render_video"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You're rendering videos too often — give it a little while.")
    # Save an edited script to the draft BEFORE rendering, so the rendered video matches the reviewed
    # text (and the draft is re-graded/compliance-checked by update_draft). Best-effort: a save failure
    # shouldn't block the render of the existing body.
    if body.script and body.script.strip():
        try:
            _rmg.update_draft(business_id, draft_id, body=body.script,
                              reviewer=(user or {}).get("email") or (user or {}).get("full_name"))
        except Exception:  # noqa: BLE001
            pass
    job_id, active = _jobs.enqueue(business_id, "render_video",
                                   args={"draft_id": draft_id, "provider": body.provider,
                                         "avatar_id": body.avatar_id, "voice_id": body.voice_id,
                                         "aspect": body.aspect, "background": body.background},
                                   requested_by=(user or {}).get("id"))
    if job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"a video render is already running (#{active})")
    if api_settings().job_worker == "inline":
        background.add_task(_jobs.run_job, job_id)
    return JSONResponse(status_code=202, content={"job_id": job_id, "job_type": "render_video",
                                                  "status": "queued", "draft_id": draft_id})
