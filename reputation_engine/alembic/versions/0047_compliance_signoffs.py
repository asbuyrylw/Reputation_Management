"""compliance_signoffs — immutable principal sign-off record at content approval

Broker-dealer/RIA marketing rules (FINRA 2210 / SEC) require principal review + recordkeeping of
every advertisement. The human gate blocked publish on failure but recorded no attestable sign-off.
This append-only ledger records, at approve time: who approved, the compliance verdict + flags,
that placeholders were resolved, a body hash (tamper-evidence), and any override reason. Never
updated or deleted in code.

Revision ID: 0047_compliance_signoffs
Revises: 0046_asset_placements
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0047_compliance_signoffs"
down_revision = "0046_asset_placements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS compliance_signoffs (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
        draft_id BIGINT,
        asset_id BIGINT,
        approver TEXT,
        compliance_pass BOOLEAN,
        compliance_flags JSONB DEFAULT '[]'::jsonb,
        placeholders JSONB DEFAULT '[]'::jsonb,
        body_hash TEXT,
        override_reason TEXT,
        signed_at TIMESTAMPTZ DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_compliance_signoffs_biz ON compliance_signoffs(business_id, signed_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS compliance_signoffs")
