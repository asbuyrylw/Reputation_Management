"""Stripe billing: plan->price mapping + webhook idempotency (Phase 2c)

plan_catalog.stripe_price_id maps each plan to a Stripe Price (seeded from STRIPE_PRICE_<CODE>
env vars). stripe_events records processed webhook event ids so a redelivered event is handled
exactly once. (subscriptions already carries stripe_customer_id / stripe_subscription_id from
alembic 0013.)

Revision ID: 0014_stripe
Revises: 0013_billing
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "0014_stripe"
down_revision = "0013_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE plan_catalog ADD COLUMN IF NOT EXISTS stripe_price_id TEXT")
    op.execute(
        """CREATE TABLE IF NOT EXISTS stripe_events (
            event_id     TEXT PRIMARY KEY,
            type         TEXT,
            processed_at TIMESTAMPTZ DEFAULT now()
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_events CASCADE")
    op.execute("ALTER TABLE plan_catalog DROP COLUMN IF EXISTS stripe_price_id")
