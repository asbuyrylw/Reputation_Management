"""User-managed prompts / topics CRUD. The enabled prompts merge into the audit battery
(ai_state_audit.build_prompt_battery) so the whole pipeline measures what the owner cares
about. AI suggestions are produced by the 'suggest_prompts' BACKGROUND JOB (LLM spend out
of the request path), saved DISABLED for review -- not generated inline here."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, require_business_editor

router = APIRouter(prefix="/businesses/{business_id}", tags=["prompts"])


class PromptCreate(BaseModel):
    prompt: str
    topic: Optional[str] = ""
    tags: Optional[str] = ""


class PromptUpdate(BaseModel):
    enabled: Optional[bool] = None
    topic: Optional[str] = None
    tags: Optional[str] = None


@router.get("/prompts")
def list_prompts(business_id: int = Depends(authorize_business)):
    from ... import prompts as _p
    return _p.list_prompts(business_id)


@router.post("/prompts", status_code=201)
def add_prompt(payload: PromptCreate, business_id: int = Depends(require_business_editor)):
    from ... import prompts as _p
    try:
        pid = _p.add_prompt(business_id, payload.prompt, topic=payload.topic or "",
                            tags=payload.tags or "", source="user")
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if pid is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"prompt limit reached (max {_p.MAX_PROMPTS})")
    return {"id": pid}


@router.patch("/prompts/{prompt_id}")
def update_prompt(prompt_id: int, payload: PromptUpdate,
                  business_id: int = Depends(require_business_editor)):
    from ... import prompts as _p
    try:
        ok = _p.update_prompt(business_id, prompt_id, enabled=payload.enabled,
                              topic=payload.topic, tags=payload.tags)
    except ValueError as e:          # enabling past the tracked-prompt cap
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt not found (or nothing to update)")
    return {"updated": prompt_id}


@router.delete("/prompts/{prompt_id}")
def delete_prompt(prompt_id: int, business_id: int = Depends(require_business_editor)):
    from ... import prompts as _p
    if not _p.delete_prompt(business_id, prompt_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt not found")
    return {"deleted": prompt_id}
