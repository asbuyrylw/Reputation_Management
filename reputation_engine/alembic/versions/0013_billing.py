"""plan_catalog + subscriptions: packaging + per-org plan/quota enforcement (Phase 2b)

plan_catalog holds the subscription tiers (limits + price); one subscription per org links
it to a plan with a status (trialing|active|past_due|canceled) and period. Quota enforcement
(audits/month, businesses) and entitlement gates read these. Stripe ids are nullable here and
populated in Phase 2c. Plans are seeded idempotently from the COGS model at app startup
(billing.seed_plans), so this migration only creates the tables.

Revision ID: 0013_billing
Revises: 0012_organizations
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "0013_billing"
down_revision = "0012_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS plan_catalog (
            code                    TEXT PRIMARY KEY,            -- starter|growth|pro|agency
            name                    TEXT NOT NULL,
            price_usd_month         INTEGER NOT NULL,
            max_businesses          INTEGER,                     -- NULL = unlimited
            max_audits_per_month    INTEGER,                     -- NULL = unlimited
            max_engines             INTEGER,
            max_samples_per_prompt  INTEGER,
            seats                   INTEGER,
            trial_days              INTEGER NOT NULL DEFAULT 14,
            is_active               BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order              INTEGER NOT NULL DEFAULT 0,
            created_at              TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id                     BIGSERIAL PRIMARY KEY,
            org_id                 BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            plan_code              TEXT REFERENCES plan_catalog(code),
            status                 TEXT NOT NULL DEFAULT 'trialing',  -- trialing|active|past_due|canceled
            current_period_start   TIMESTAMPTZ,
            current_period_end     TIMESTAMPTZ,
            trial_end              TIMESTAMPTZ,
            stripe_customer_id     TEXT,                              -- populated in Phase 2c
            stripe_subscription_id TEXT,
            created_at             TIMESTAMPTZ DEFAULT now(),
            updated_at             TIMESTAMPTZ DEFAULT now(),
            UNIQUE (org_id)                                           -- one subscription per org
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS plan_catalog CASCADE")
