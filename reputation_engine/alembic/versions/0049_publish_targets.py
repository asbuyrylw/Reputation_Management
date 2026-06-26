"""publish_targets + publish_attempts + assets.compliance_pass (Integrations Phase 2)

The owned-channel publisher's write model. Fan-out is NETWORK-GRAIN: one publish_targets row per
network is created up front (network NEVER NULL), so a retry of one network can never re-drive an
already-live sibling. Exactly-once is enforced by UNIQUE(asset_id,channel,connection_id,network)
plus the idempotency-key index. publish_attempts is the per-try, redacted audit trail.

assets.compliance_pass is copied from the source draft at approve() time; the runner re-checks
`compliance_pass IS TRUE` before any auto-post.

Revision ID: 0049_publish_targets
Revises: 0048_platform_connections
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0049_publish_targets"
down_revision = "0048_platform_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS compliance_pass BOOLEAN")

    op.execute("""CREATE TABLE IF NOT EXISTS publish_targets (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        work_order_id BIGINT,
        channel TEXT NOT NULL,
        network TEXT NOT NULL DEFAULT '_',
        payload_kind TEXT NOT NULL DEFAULT 'article',
        status TEXT NOT NULL DEFAULT 'queued',
        routing JSONB DEFAULT '{}'::jsonb,
        scheduled_for TIMESTAMPTZ,
        external_id TEXT,
        external_url TEXT,
        published_at TIMESTAMPTZ,
        idempotency_key TEXT NOT NULL,
        attempts INT NOT NULL DEFAULT 0,
        next_attempt_at TIMESTAMPTZ,
        last_error TEXT,
        job_id BIGINT REFERENCES api_jobs(id) ON DELETE SET NULL,
        created_by BIGINT REFERENCES users(id),
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (asset_id, channel, connection_id, network))""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_publish_targets_idem ON publish_targets (idempotency_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_publish_targets_due ON publish_targets (status) "
               "WHERE status IN ('queued','failed','scheduled')")
    op.execute("CREATE INDEX IF NOT EXISTS idx_publish_targets_business ON publish_targets (business_id)")

    op.execute("""CREATE TABLE IF NOT EXISTS publish_attempts (
        id BIGSERIAL PRIMARY KEY,
        target_id BIGINT NOT NULL REFERENCES publish_targets(id) ON DELETE CASCADE,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        job_id BIGINT REFERENCES api_jobs(id) ON DELETE SET NULL,
        attempt_no INT,
        ok BOOLEAN NOT NULL,
        http_status INT,
        external_id TEXT,
        external_url TEXT,
        request_summary JSONB DEFAULT '{}'::jsonb,
        response_summary JSONB DEFAULT '{}'::jsonb,
        error TEXT,
        retryable BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_publish_attempts_target ON publish_attempts (target_id, id DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS publish_attempts")
    op.execute("DROP TABLE IF EXISTS publish_targets")
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS compliance_pass")
