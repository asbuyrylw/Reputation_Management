"""Visual content API (LATER: CI-4).

Generate human-gated visuals (image / quote-card / video-brief) for a work order, list them, and
approve/reject. Generation runs in a job (image gen can be slow + needs a provider key). Dormant-safe:
without an image key the job returns {skipped} and nothing breaks; quote-cards always work.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_current_user, require_business_editor

try:
    from ... import visual_content as _vc
except ImportError:  # pragma: no cover
    import visual_content as _vc  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["visuals"])

_KINDS = {"image", "quote_card", "meme", "video_brief"}


class VisualRequest(BaseModel):
    kind: str = "image"
    prompt: Optional[str] = None
    text: Optional[str] = None
    attribution: Optional[str] = None
    topic: Optional[str] = None
    work_order_id: Optional[int] = None
    draft_id: Optional[int] = None


def _actor(user: dict) -> str:
    return user.get("full_name") or user["email"]


@router.get("/visuals")
def visuals(status: Optional[str] = None, business_id: int = Depends(authorize_business)):
    return {"image_configured": _vc.image_configured(), "video_configured": _vc.video_configured(),
            "visuals": _vc.list_visuals(business_id, status)}


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
