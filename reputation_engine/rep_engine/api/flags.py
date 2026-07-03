"""Platform-wide feature flags (app_settings key/value store).

A deliberately tiny module with NO heavy imports, so both auth.py (public_user payload) and
billing.py (enforcement gate) can read flags without a circular import. Flags are stored in the
`app_settings` table as text and interpreted as booleans here.

The flag that matters today: `billing_enabled` — the master switch that keeps the whole billing
system wired but dormant until the super-admin turns it on.
"""

from __future__ import annotations

from typing import Optional

_TRUE = {"1", "true", "yes", "on"}

BILLING_ENABLED = "billing_enabled"


def get_flag(conn, key: str, default: bool = False) -> bool:
    row = conn.execute("SELECT value FROM app_settings WHERE key=%s", (key,)).fetchone()
    if not row or row["value"] is None:
        return default
    return str(row["value"]).strip().lower() in _TRUE


def set_flag(conn, key: str, value: bool, actor: Optional[str] = None) -> None:
    """Upsert a boolean flag. Caller commits."""
    conn.execute(
        "INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (%s,%s,now(),%s) "
        "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now(), updated_by=EXCLUDED.updated_by",
        (key, "true" if value else "false", actor),
    )


def billing_enabled(conn) -> bool:
    """True only when the super-admin has flipped the master switch on. Default OFF."""
    return get_flag(conn, BILLING_ENABLED, default=False)
