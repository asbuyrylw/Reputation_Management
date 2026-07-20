"""Chrome "Reply Assist" extension API.

Two authorization paths, deliberately kept separate:
  - /businesses/{business_id}/extension-tokens (mint/list/revoke) -- normal cookie/session auth,
    same as every other console route.
  - /ext/v1/queue -- a bearer-token-only, read-only route the browser extension calls from its
    background service worker (no session cookie available there; a different origin can't send
    our httpOnly cookie anyway). Scoped to exactly one business by the token itself.

Never exposes write/approve/publish actions here -- the human still clicks "post" on the
platform's own page; this only serves the already-drafted reply text for them to review/insert.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..deps import get_current_user, require_business_editor

try:
    from ... import ext_tokens as _et
    from ... import response_policy as _rp
except ImportError:  # pragma: no cover
    import ext_tokens as _et  # type: ignore
    import response_policy as _rp  # type: ignore

router = APIRouter(tags=["extension"])

# The extension only needs third-party reply drafts (Yelp/Reddit/Facebook) -- the surface GBP
# review replies and auto-postable owned channels don't need a human-paste workflow for.
_EXT_KINDS = {"mention_reply", "review_reply"}


class TokenCreate(BaseModel):
    label: Optional[str] = None


@router.post("/businesses/{business_id}/extension-tokens")
def create_extension_token(business_id: int, body: TokenCreate,
                           business=Depends(require_business_editor),
                           user: dict = Depends(get_current_user)):
    tok = _et.create_token(business_id, user.get("id"), body.label)
    return {"ok": True, "id": tok["id"], "token": tok["token"], "created_at": tok["created_at"]}


@router.get("/businesses/{business_id}/extension-tokens")
def list_extension_tokens(business_id: int, business=Depends(require_business_editor)):
    return {"tokens": _et.list_tokens(business_id)}


@router.delete("/businesses/{business_id}/extension-tokens/{token_id}")
def revoke_extension_token(business_id: int, token_id: int, business=Depends(require_business_editor)):
    if not _et.revoke_token(token_id, business_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "token not found")
    return {"ok": True}


def _ext_business_id(authorization: Optional[str] = Header(None)) -> int:
    raw = (authorization or "").removeprefix("Bearer ").strip()
    business_id = _et.resolve_business(raw) if raw else None
    if business_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked extension token")
    return business_id


@router.get("/ext/v1/queue")
def extension_queue(business_id: int = Depends(_ext_business_id)):
    """Read-only pending-reply feed for the browser extension. Each item carries the platform
    ('source'), the review/comment URL (so the content script can match it to the page the
    operator is looking at), and the already-drafted 'draft' text -- never auto-posted."""
    items = [i for i in _rp.list_queue(business_id) if i.get("kind") in _EXT_KINDS and i.get("draft")]
    return {"items": items}
