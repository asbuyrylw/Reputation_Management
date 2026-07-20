"""reports: durable object-storage pointers (Phase G.3)

Monthly reports are written to the container's ephemeral disk (report_generator.OUTPUT_DIR) and the
reports row stores only the file PATH -- with NO DB-blob fallback (unlike visual_assets). So every
Railway redeploy wipes the .docx/.pdf and the download route 410s ("Report file is no longer
available") for a report a client was shown last month. Add durable object-storage pointers the
generator populates + the download route serves from when the local file is gone:

- storage_key      : the .docx object key in the configured bucket.
- pdf_storage_key   : the optional LibreOffice-converted .pdf object key.

Additive + nullable: legacy rows keep working (served from disk while it exists).

Revision ID: 0081_reports_storage_key
Revises: 0080_visual_assets_storage
Create Date: 2026-07-20
"""
from __future__ import annotations

from alembic import op

revision = "0081_reports_storage_key"
down_revision = "0080_visual_assets_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS storage_key TEXT")
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS pdf_storage_key TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS pdf_storage_key")
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS storage_key")
