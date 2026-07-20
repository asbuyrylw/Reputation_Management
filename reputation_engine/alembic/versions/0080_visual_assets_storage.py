"""visual_assets: durable object-storage pointers (Phase G.3)

Generated images/videos are written to the container's ephemeral disk today
(visual_content._OUTPUT_DIR = "output/") and stored as `file_path` + `file_bytes` BYTEA. Every
Railway redeploy wipes the disk, so `file_path` rows 404. Central object storage fixes that; this
migration adds the durable pointers producers will populate:

- storage_key  : the object key in the configured bucket (Railway Bucket / R2 / S3 / MinIO).
- public_url   : a PERMANENT anonymous URL -- set ONLY when a public base URL is configured
                 (R2 public domain / CloudFront). Left NULL for private Railway Buckets, whose
                 delivery is a presigned GET or the authenticated backend-proxy route.

Additive + nullable: legacy rows keep working; producers backfill going forward.

Revision ID: 0080_visual_assets_storage
Revises: 0079_brand_and_source_material
Create Date: 2026-07-20
"""
from __future__ import annotations

from alembic import op

revision = "0080_visual_assets_storage"
down_revision = "0079_brand_and_source_material"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE visual_assets ADD COLUMN IF NOT EXISTS storage_key TEXT")
    op.execute("ALTER TABLE visual_assets ADD COLUMN IF NOT EXISTS public_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE visual_assets DROP COLUMN IF EXISTS public_url")
    op.execute("ALTER TABLE visual_assets DROP COLUMN IF EXISTS storage_key")
