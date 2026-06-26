"""Platform-owner settings — the super-admin-only master switches.

Today this is just the billing master switch (`billing_enabled`): the whole billing system is
built and wired but stays dormant until the single super-admin (logan@nexgenixai.com) flips it
on here. Gated by `require_super_admin`, so regular admins cannot toggle it.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import flags
from ..deps import get_conn, get_current_user, require_super_admin

router = APIRouter(prefix="/platform", tags=["platform"])


def _actor(user: dict) -> str:
    return user.get("full_name") or user["email"]


@router.get("/settings")
def get_platform_settings(_: dict = Depends(require_super_admin), conn=Depends(get_conn)):
    """Current platform switches (super-admin only)."""
    return {"billing_enabled": flags.billing_enabled(conn)}


@router.get("/quota-usage")
def quota_usage(_: dict = Depends(require_super_admin)):
    """Shared platform-app quota usage across all tenants (Wave 5, item 22; super-admin)."""
    try:
        from ... import quota as _quota
    except ImportError:  # pragma: no cover
        import quota as _quota  # type: ignore
    return _quota.usage_report()


class PlatformSettingsUpdate(BaseModel):
    billing_enabled: Optional[bool] = None


@router.patch("/settings")
def update_platform_settings(
    body: PlatformSettingsUpdate,
    user: dict = Depends(require_super_admin),
    conn=Depends(get_conn),
):
    """Flip a platform switch (super-admin only). Today: the billing master switch."""
    if body.billing_enabled is not None:
        flags.set_flag(conn, flags.BILLING_ENABLED, body.billing_enabled, actor=_actor(user))
        conn.commit()
    return {"billing_enabled": flags.billing_enabled(conn)}
