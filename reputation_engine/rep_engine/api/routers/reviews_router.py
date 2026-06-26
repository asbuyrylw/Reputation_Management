"""Review-reply approval API (Integrations Phase 3).

The human-gated reply queue for Google reviews. Drafts are produced by the ingest job; here a
human approves (auto-posts via GBP when connected, else stays approved for manual posting),
rejects, or edits (which re-screens and resets compliance_pass). Auto-reply is OFF in Phase 3.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_current_user, require_business_editor

try:
    from ... import gbp_reviews as _gbp
except ImportError:  # pragma: no cover
    import gbp_reviews as _gbp  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["reviews"])


class ReplyEdit(BaseModel):
    draft: str


def _actor(user: dict) -> str:
    return user.get("full_name") or user["email"]


@router.get("/review-replies")
def review_replies(status: Optional[str] = None,
                   business_id: int = Depends(authorize_business)):
    return _gbp.list_review_replies(business_id, status_filter=status)


@router.post("/review-replies/{reply_id}/approve")
def approve_reply(reply_id: int, business_id: int = Depends(require_business_editor),
                  user: dict = Depends(get_current_user)):
    try:
        ok = _gbp.approve_reply(reply_id, _actor(user), business_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reply not found or not pending")
    try:
        from .. import jobs as _jobs
        _jobs.enqueue(business_id, "post_review_replies", requested_by=user["id"])
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "reply_id": reply_id, "status": "approved"}


@router.post("/review-replies/{reply_id}/reject")
def reject_reply(reply_id: int, business_id: int = Depends(require_business_editor),
                 user: dict = Depends(get_current_user)):
    if not _gbp.reject_reply(reply_id, _actor(user), business_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reply not found")
    return {"ok": True, "reply_id": reply_id, "status": "rejected"}


@router.patch("/review-replies/{reply_id}")
def edit_reply(reply_id: int, body: ReplyEdit,
               business_id: int = Depends(require_business_editor),
               user: dict = Depends(get_current_user)):
    if not body.draft.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "draft cannot be empty")
    if not _gbp.edit_reply(reply_id, body.draft, _actor(user), business_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reply not found or not editable")
    return {"ok": True, "reply_id": reply_id, "status": "pending_review"}
