"""Unified approval queue API (Integrations Phase 4).

One inbox over mention replies (third_party = draft+alert only) + review replies (owned) +
scheduled publish targets (read-only). Approve/reject dispatch by item kind; third_party items
can be approved (= marked handled offline) but never auto-post. Integration settings GET here;
the auto-post-enabling PUT lands in Phase 5 (org-manager gated).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_current_user, require_business_editor

try:
    from ... import response_policy as _rp
    from ... import mention_monitor as _mm
    from ... import gbp_reviews as _gbp
except ImportError:  # pragma: no cover
    import response_policy as _rp  # type: ignore
    import mention_monitor as _mm  # type: ignore
    import gbp_reviews as _gbp  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["approvals"])

_KINDS = {"mention_reply", "review_reply"}


def _actor(user: dict) -> str:
    return user.get("full_name") or user["email"]


def _enqueue(business_id: int, job_type: str, user: dict) -> None:
    try:
        from .. import jobs as _jobs
        _jobs.enqueue(business_id, job_type, requested_by=user["id"])
    except Exception:  # noqa: BLE001
        pass


@router.get("/approval-queue")
def approval_queue(surface: Optional[str] = None, kind: Optional[str] = None,
                   business_id: int = Depends(authorize_business)):
    return {"items": _rp.list_queue(business_id, surface=surface, kind=kind)}


@router.post("/approval-queue/{kind}/{item_id}/approve")
def approve(kind: str, item_id: int, business_id: int = Depends(require_business_editor),
            user: dict = Depends(get_current_user)):
    if kind not in _KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"cannot approve kind '{kind}'")
    if kind == "mention_reply":
        if not _mm.approve(item_id, _actor(user), business_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "reply not found or not pending")
        _enqueue(business_id, "post_mention_replies", user)
    else:  # review_reply
        try:
            ok = _gbp.approve_reply(item_id, _actor(user), business_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        if not ok:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "reply not found or not pending")
        _enqueue(business_id, "post_review_replies", user)
    return {"ok": True, "kind": kind, "id": item_id, "status": "approved"}


@router.post("/approval-queue/{kind}/{item_id}/reject")
def reject(kind: str, item_id: int, business_id: int = Depends(require_business_editor),
           user: dict = Depends(get_current_user)):
    if kind not in _KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"cannot reject kind '{kind}'")
    ok = (_mm.reject(item_id, _actor(user), business_id) if kind == "mention_reply"
          else _gbp.reject_reply(item_id, _actor(user), business_id))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    return {"ok": True, "kind": kind, "id": item_id, "status": "rejected"}


@router.get("/integration-settings")
def integration_settings(business_id: int = Depends(authorize_business),
                         user: dict = Depends(get_current_user)):
    s = _rp._settings(business_id)
    from dataclasses import asdict
    try:
        from ...api.auth import is_org_manager
        can_manage = user.get("role") == "admin" or is_org_manager(user)
    except Exception:  # noqa: BLE001
        can_manage = user.get("role") == "admin"
    return {"settings": asdict(s), "can_manage_autopost": bool(can_manage),
            "autopost_globally_enabled": _autopost_global(),
            "pressranger_enabled": _pressranger_enabled()}


def _autopost_global() -> bool:
    try:
        from ...integration_flags import autopost_global_enabled
        return autopost_global_enabled()
    except Exception:  # noqa: BLE001
        return False


def _pressranger_enabled() -> bool:
    try:
        from ...integration_flags import pressranger_enabled
        return pressranger_enabled()
    except Exception:  # noqa: BLE001
        return False


# Fields whose change requires org-manager (they arm or widen automated posting).
_GATED_FIELDS = {"allow_owned_autopost", "auto_reply_reviews", "auto_reply_mentions",
                 "auto_platforms", "daily_autopost_cap", "hourly_auto_cap", "auto_reply_min_stars",
                 "auto_reply_max_len", "warmup_manual_count", "never_auto_sentiments", "blocked_channels"}
# Columns that take a JSONB value.
_JSON_FIELDS = {"auto_platforms", "never_auto_sentiments", "quiet_hours", "banned_phrases",
                "allowed_channels", "blocked_channels"}


class IntegrationSettingsUpdate(BaseModel):
    business_timezone: Optional[str] = None
    require_approval: Optional[bool] = None
    allow_owned_autopost: Optional[bool] = None
    auto_reply_reviews: Optional[bool] = None
    auto_reply_mentions: Optional[bool] = None
    auto_reply_min_stars: Optional[int] = None
    auto_reply_max_len: Optional[int] = None
    auto_platforms: Optional[list] = None
    never_auto_sentiments: Optional[list] = None
    daily_autopost_cap: Optional[int] = None
    hourly_auto_cap: Optional[int] = None
    warmup_manual_count: Optional[int] = None
    quiet_hours: Optional[dict] = None
    banned_phrases: Optional[list] = None
    allowed_channels: Optional[list] = None
    blocked_channels: Optional[list] = None
    disclosure_text: Optional[str] = None
    notify_email: Optional[bool] = None
    notify_on_auto: Optional[bool] = None


def _is_org_manager(user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    try:
        from ...api.auth import is_org_manager
        return bool(is_org_manager(user))
    except Exception:  # noqa: BLE001
        return False


@router.put("/integration-settings")
def update_integration_settings(body: IntegrationSettingsUpdate,
                                business_id: int = Depends(require_business_editor),
                                user: dict = Depends(get_current_user)):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no fields to update")
    # Arming/widening automated posting requires org-manager.
    if any(k in _GATED_FIELDS for k in fields) and not _is_org_manager(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Only an organization manager can change auto-posting settings.")
    from psycopg.types.json import Json
    try:
        from ...db import db
    except ImportError:  # pragma: no cover
        from db import db  # type: ignore
    cols = list(fields.keys())
    placeholders, values = [], []
    for c in cols:
        placeholders.append("%s")
        values.append(Json(fields[c]) if c in _JSON_FIELDS else fields[c])
    set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols)
    col_sql = ", ".join(cols)
    ph_sql = ", ".join(placeholders)
    with db() as conn:
        conn.execute(
            f"INSERT INTO integration_settings (business_id, {col_sql}, updated_by, updated_at) "
            f"VALUES (%s, {ph_sql}, %s, now()) "
            f"ON CONFLICT (business_id) DO UPDATE SET {set_clause}, updated_by=EXCLUDED.updated_by, "
            f"updated_at=now()",
            (business_id, *values, user["id"]))
        conn.commit()
    # If auto-post was just armed, surface it (transparency).
    if fields.get("allow_owned_autopost") or fields.get("auto_reply_reviews"):
        try:
            from ... import notifications as _n
            _n.notify(business_id, "autopost_armed", "Automated posting was enabled",
                      "An organization manager turned on automated posting for a connected channel.",
                      severity="info", dedup_key=f"autopost-armed:{business_id}")
        except Exception:  # noqa: BLE001
            pass
    s = _rp._settings(business_id)
    from dataclasses import asdict
    return {"ok": True, "settings": asdict(s)}
