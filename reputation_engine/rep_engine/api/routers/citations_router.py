"""Computer-use citation/directory-listing builder API (LATER: CI-5).

Every run is triggered by an explicit editor click -- never a scheduled job -- and always pauses
for an explicit confirm before any submit-like action. See rep_engine.citation_builder for the
full safety posture.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import authorize_business, get_current_user, require_business_editor

try:
    from ... import citation_builder as _cb
except ImportError:  # pragma: no cover
    import citation_builder as _cb  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["citations"])


@router.get("/citation-directories")
def directories(business_id: int = Depends(authorize_business)):
    return {"configured": _cb.configured(),
            "directories": [{"key": k, **v, "has_credentials": _cb.has_directory_credentials(business_id, k)}
                            for k, v in _cb.directories().items()]}


class DirectoryCredentials(BaseModel):
    username: str
    password: str


@router.put("/citation-directories/{directory_key}/credentials")
def set_credentials(directory_key: str, body: DirectoryCredentials,
                    business_id: int = Depends(require_business_editor)):
    res = _cb.set_directory_credentials(business_id, directory_key, body.username, body.password)
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("error", "could not save credentials"))
    return res


class RunCreate(BaseModel):
    directory_key: str
    work_order_id: Optional[int] = None


@router.post("/citation-runs")
def create_run(body: RunCreate, business_id: int = Depends(require_business_editor),
              user: dict = Depends(get_current_user)):
    res = _cb.start_run(business_id, body.directory_key, work_order_id=body.work_order_id,
                        created_by=user.get("id"))
    if res.get("skipped"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, res["reason"])
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("error", "run failed"))
    return res


@router.get("/citation-runs")
def runs(business_id: int = Depends(authorize_business)):
    return {"runs": _cb.list_runs(business_id)}


@router.get("/citation-runs/{run_id}")
def run_detail(run_id: int, business_id: int = Depends(authorize_business)):
    run = _cb.get_run(run_id, business_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@router.post("/citation-runs/{run_id}/confirm")
def confirm_run(run_id: int, business_id: int = Depends(require_business_editor)):
    res = _cb.confirm_and_continue(run_id, business_id)
    if not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("error", "could not continue run"))
    return res


@router.post("/citation-runs/{run_id}/cancel")
def cancel_run(run_id: int, business_id: int = Depends(require_business_editor)):
    res = _cb.cancel_run(run_id, business_id)
    if not res.get("ok"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, res.get("error", "run not found"))
    return res


@router.get("/citation-runs/{run_id}/screenshot/{step}")
def run_screenshot(run_id: int, step: int, business_id: int = Depends(authorize_business)):
    import os
    fp = _cb.screenshot_path(run_id, business_id, step)
    if not fp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "screenshot not found")
    base = os.path.realpath(_cb._OUTPUT_DIR)
    path = os.path.realpath(fp if os.path.isabs(fp) else os.path.join(os.getcwd(), fp))
    if not (path == base or path.startswith(base + os.sep)) or not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    return FileResponse(path, media_type="image/png")
