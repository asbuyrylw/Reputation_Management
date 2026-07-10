"""visual_assets.file_bytes: store generated visual bytes in Postgres

On a split API/worker deploy (Railway) the worker generates the file on its own disk and the API
serves it from a DIFFERENT disk with no shared volume, so images/videos 404'd and fell back to a
path. Storing the bytes in the shared DB (served by the API when the local file isn't present) makes
generated visuals render everywhere. Blobs are small (quote cards/images a few hundred KB, an
8-second Veo clip a few MB) and only human-gated visuals produce them, so the DB cost is modest.

Revision ID: 0076_visual_blob
Revises: 0075_tasks_from_gaps_no_gate
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op

revision = "0076_visual_blob"
down_revision = "0075_tasks_from_gaps_no_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE visual_assets ADD COLUMN IF NOT EXISTS file_bytes BYTEA")
    op.execute("ALTER TABLE visual_assets ADD COLUMN IF NOT EXISTS mime TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE visual_assets DROP COLUMN IF EXISTS file_bytes")
    op.execute("ALTER TABLE visual_assets DROP COLUMN IF EXISTS mime")
