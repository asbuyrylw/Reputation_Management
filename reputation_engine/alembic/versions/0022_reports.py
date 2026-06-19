"""reports: track generated monthly report files so the console can list + download them

report_generator writes a .docx to REP_OUTPUT_DIR; this table records each one (path +
filename + when) so the API can serve it back to the owner -- the deliverable a managed-
service client actually renews for.

Revision ID: 0022_reports
Revises: 0021_custom_prompts
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "0022_reports"
down_revision = "0021_custom_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'monthly',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_reports_biz ON reports(business_id, id DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reports")
