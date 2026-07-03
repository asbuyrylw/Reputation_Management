"""super-admin flag + platform feature flags + per-org billing exemption

- users.is_super_admin: the single platform owner who can flip the billing master switch
  (only logan@nexgenixai.com is seeded TRUE in code). Regular admins cannot.
- organizations.billing_exempt: an org that is never metered/charged even when billing is on
  (the pilot, Team Unstoppable, is exempted here so it can never be billed by accident).
- app_settings: a tiny key/value store for platform-wide flags. `billing_enabled` defaults to
  'false' so the whole billing system is wired but dormant until the super-admin turns it on.

Revision ID: 0039_super_admin_billing_flags
Revises: 0038_wo_planned_promote
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

revision = "0039_super_admin_billing_flags"
down_revision = "0038_wo_planned_promote"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS billing_exempt BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(
        "CREATE TABLE IF NOT EXISTS app_settings ("
        " key TEXT PRIMARY KEY,"
        " value TEXT NOT NULL,"
        " updated_at TIMESTAMPTZ DEFAULT now(),"
        " updated_by TEXT)"
    )
    # Billing wired but OFF until the super-admin flips it.
    op.execute("INSERT INTO app_settings (key, value) VALUES ('billing_enabled', 'false') "
               "ON CONFLICT (key) DO NOTHING")
    # The pilot is permanently billing-exempt, so it is never charged even after billing is on.
    op.execute(
        "UPDATE organizations SET billing_exempt=TRUE "
        "WHERE id IN (SELECT org_id FROM businesses WHERE lower(name)='team unstoppable' AND org_id IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_settings")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS billing_exempt")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_super_admin")
