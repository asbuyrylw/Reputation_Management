"""Visual content API (LATER: CI-4).

Generate human-gated visuals (image / quote-card / video-brief / video) for a work order, list them,
and approve/reject. Generation runs in a job (image/video gen can be slow + needs a provider key).
Dormant-safe: without a provider key the job returns {skipped} and nothing breaks; quote-cards
always work.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import authorize_business, get_current_user, require_business_editor

try:
    from ... import visual_content as _vc
except ImportError:  # pragma: no cover
    import visual_content as _vc  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["visuals"])

_KINDS = {"image", "quote_card", "meme", "video_brief", "video"}
_IMG_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
             ".mp4": "video/mp4", ".webm": "video/webm"}


class VisualRequest(BaseModel):
    kind: str = "image"
    prompt: Optional[str] = None
    text: Optional[str] = None
    attribution: Optional[str] = None
    topic: Optional[str] = None
    work_order_id: Optional[int] = None
    draft_id: Optional[int] = None
    aspect_ratio: Optional[str] = None


def _actor(user: dict) -> str:
    return user.get("full_name") or user["email"]


@router.get("/visuals")
def visuals(status: Optional[str] = None, draft_id: Optional[int] = None,
            business_id: int = Depends(authorize_business)):
    return {"image_configured": _vc.image_configured(), "video_configured": _vc.video_configured(),
            "visuals": _vc.list_visuals(business_id, status, draft_id)}


@router.get("/visuals/{visual_id}/file")
def visual_file(visual_id: int, business_id: int = Depends(authorize_business)):
    """Serve a generated visual's bytes (tenancy-checked, no path traversal). Prefers the local
    file (fast, e.g. single-machine dev); falls back to the DB blob when the file isn't on THIS
    service's disk (the split API/worker Railway deploy) so visuals render everywhere."""
    fp = _vc.visual_file_path(visual_id, business_id)
    if fp:
        base = os.path.realpath(_vc._OUTPUT_DIR)
        path = os.path.realpath(fp if os.path.isabs(fp) else os.path.join(os.getcwd(), fp))
        if (path == base or path.startswith(base + os.sep)) and os.path.isfile(path):
            media = _IMG_MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
            return FileResponse(path, media_type=media)
    # local file absent (or on another service's disk) -> serve the DB blob
    blob = _vc.visual_file_blob(visual_id, business_id)
    if blob:
        data, media = blob
        return Response(content=data, media_type=media)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "visual file not found")


@router.post("/visuals/generate")
def generate(body: VisualRequest, business_id: int = Depends(require_business_editor),
             user: dict = Depends(get_current_user)):
    if body.kind not in _KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown visual kind '{body.kind}'")
    args = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        from .. import jobs as _jobs
        job_id, active = _jobs.enqueue(business_id, "generate_visual", requested_by=user["id"], args=args)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"could not queue: {e}")
    return {"ok": True, "job_id": job_id or active, "queued": bool(job_id),
            "image_configured": _vc.image_configured()}


@router.post("/visuals/{visual_id}/approve")
def approve_visual(visual_id: int, business_id: int = Depends(require_business_editor),
                   user: dict = Depends(get_current_user)):
    if not _vc.set_visual_status(visual_id, "approved", _actor(user), business_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visual not found")
    return {"ok": True, "visual_id": visual_id, "status": "approved"}


@router.post("/visuals/{visual_id}/reject")
def reject_visual(visual_id: int, business_id: int = Depends(require_business_editor),
                  user: dict = Depends(get_current_user)):
    if not _vc.set_visual_status(visual_id, "rejected", _actor(user), business_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visual not found")
    return {"ok": True, "visual_id": visual_id, "status": "rejected"}
