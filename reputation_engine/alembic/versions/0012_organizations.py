"""organizations: the account/billing tenancy root above users + businesses (Phase 2a)

An organization is the account a customer pays under. It owns one OR many businesses
(direct customers have one; agencies/multi-location brands have several) and is the entity
billing, plans, quotas, and entitlements attach to. Users belong to an org with an org-level
role (owner|admin|member); the existing per-business `business_access` grants still provide
fine-grained access within an org. Platform staff (users.role='admin') remain above orgs and
see everything.

Backfill is conservative: existing data is moved into a single 'Default Organization' with
every user as 'member', so current business_access-based access is preserved exactly.

Revision ID: 0012_organizations
Revises: 0011_answers_grounded
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "0012_organizations"
down_revision = "0011_answers_grounded"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS organizations (
            id          BIGSERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',   -- active | suspended | cancelled
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS org_id BIGINT REFERENCES organizations(id)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id BIGINT REFERENCES organizations(id)")
    # org-level role: owner/admin manage the org (billing, members, all org businesses);
    # member is limited to their explicit business_access grants.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS org_role TEXT NOT NULL DEFAULT 'member'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_businesses_org ON businesses(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id)")

    # Backfill existing data into one default org (only if there is data to move).
    op.execute(
        """INSERT INTO organizations (name)
           SELECT 'Default Organization'
           WHERE (EXISTS (SELECT 1 FROM businesses) OR EXISTS (SELECT 1 FROM users))
             AND NOT EXISTS (SELECT 1 FROM organizations)"""
    )
    op.execute(
        "UPDATE businesses SET org_id = (SELECT id FROM organizations ORDER BY id LIMIT 1) "
        "WHERE org_id IS NULL AND EXISTS (SELECT 1 FROM organizations)"
    )
    op.execute(
        "UPDATE users SET org_id = (SELECT id FROM organizations ORDER BY id LIMIT 1) "
        "WHERE org_id IS NULL AND EXISTS (SELECT 1 FROM organizations)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_org")
    op.execute("DROP INDEX IF EXISTS idx_businesses_org")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS org_role")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS org_id")
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS org_id")
    op.execute("DROP TABLE IF EXISTS organizations CASCADE")
